"""Tests for agente_obra — mocks the Anthropic API to avoid real calls."""

import json
import pytest
from unittest.mock import MagicMock, patch

from agents import agente_obra


SAMPLE_DATA = (
    "- Torre Cumbres: 120 deptos, avance físico 78%, avance financiero 74%, "
    "AC $108.5M, EV $113.1M, PV $107.3M, costo/m² $19,180 vs $18,400, desviación +4.2%, "
    "margen bruto 22.1%, margen neto 16.8%, flujo período -$3.2M, retenciones $8.4M, días retraso 0\n"
    "- Resi. Bosques: 48 casas, avance físico 41%, avance financiero 49%, "
    "AC $30.4M, EV $25.4M, PV $28.0M, costo/m² $28,600 vs $26,400, desviación +8.2%, "
    "margen neto 9.1%, flujo -$6.1M, retenciones $4.2M, días retraso 22\n"
)

SAMPLE_STRUCTURED_RESPONSE = {
    "proyectos": [
        {
            "nombre": "Torre Cumbres",
            "estado": "Normal",
            "kpis": {
                "avance_fisico": "78%",
                "avance_financiero": "74%",
                "desviacion_curvas": "4%",
                "cpi": 1.04,
                "spi": 1.05,
                "costo_m2_real": 19180,
                "costo_m2_presupuesto": 18400,
                "desviacion_costo": "4.2%",
                "margen_bruto": "22.1%",
                "margen_neto": "16.8%",
                "eac": 139423077,
                "vac": 5576923,
                "flujo_periodo": -3200000,
                "retenciones_pendientes": 8400000,
                "dias_retraso": 0,
            },
            "alertas": [],
        },
        {
            "nombre": "Resi. Bosques",
            "estado": "Crítico",
            "kpis": {
                "avance_fisico": "41%",
                "avance_financiero": "49%",
                "desviacion_curvas": "8%",
                "cpi": 0.84,
                "spi": 0.91,
                "costo_m2_real": 28600,
                "costo_m2_presupuesto": 26400,
                "desviacion_costo": "8.2%",
                "margen_bruto": "14.3%",
                "margen_neto": "9.1%",
                "eac": 73809524,
                "vac": -11809524,
                "flujo_periodo": -6100000,
                "retenciones_pendientes": 4200000,
                "dias_retraso": 22,
            },
            "alertas": [
                {
                    "nivel": "CRÍTICA",
                    "kpi": "margen_neto",
                    "valor_actual": "9.1%",
                    "umbral": "<12%",
                    "descripcion": "Margen neto por debajo del mínimo aceptable",
                    "accion": "Revisar contratos y ajustar presupuesto",
                }
            ],
        },
    ],
    "resumen_ejecutivo": "Resi. Bosques presenta riesgos críticos.",
    "alertas_criticas_total": 1,
    "alertas_medias_total": 1,
    "proyectos_en_riesgo": ["Resi. Bosques"],
}


# ── build_system_prompt ───────────────────────────────────────────────────────

def test_build_system_prompt_default_thresholds():
    prompt = agente_obra.build_system_prompt()
    assert "5%" in prompt           # thr_costo
    assert "12%" in prompt          # thr_margen
    assert "0.95" in prompt         # thr_cpi
    assert "0.9" in prompt          # thr_spi (Python renders 0.90 as 0.9)


def test_build_system_prompt_custom_thresholds():
    prompt = agente_obra.build_system_prompt({"thr_costo": 8, "thr_margen": 15})
    assert "8%" in prompt
    assert "15%" in prompt


def test_system_prompt_contains_evm_kpis():
    prompt = agente_obra.build_system_prompt()
    for kpi in ("CPI", "SPI", "EAC", "ETC", "VAC", "EV", "PV", "AC"):
        assert kpi in prompt, f"Missing KPI in system prompt: {kpi}"


# ── run — text mode ───────────────────────────────────────────────────────────

def _mock_message(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def test_run_text_mode_returns_string():
    with patch("agents.agente_obra.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("Análisis de obra.")
        result = agente_obra.run(SAMPLE_DATA, stream=False)
    assert isinstance(result, str)
    assert len(result) > 0


def test_run_text_mode_passes_correct_model():
    with patch("agents.agente_obra.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("ok")
        agente_obra.run(SAMPLE_DATA, stream=False)
        call_kwargs = MockClient().messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-sonnet-4-20250514"
    assert call_kwargs["max_tokens"] == 2000


def test_run_includes_context_in_prompt():
    with patch("agents.agente_obra.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("ok")
        agente_obra.run(SAMPLE_DATA, context="Mes de cierre fiscal", stream=False)
        call_kwargs = MockClient().messages.create.call_args[1]
    user_content = call_kwargs["messages"][0]["content"]
    assert "Mes de cierre fiscal" in user_content


# ── run — structured mode ─────────────────────────────────────────────────────

def test_run_structured_returns_dict():
    with patch("agents.agente_obra.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_STRUCTURED_RESPONSE)
        )
        result = agente_obra.run(SAMPLE_DATA, stream=False, structured=True)
    assert isinstance(result, dict)


def test_run_structured_has_required_keys():
    with patch("agents.agente_obra.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_STRUCTURED_RESPONSE)
        )
        result = agente_obra.run(SAMPLE_DATA, stream=False, structured=True)
    for key in ("proyectos", "resumen_ejecutivo", "alertas_criticas_total"):
        assert key in result, f"Missing key in structured output: {key}"


def test_run_structured_project_has_kpis():
    with patch("agents.agente_obra.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_STRUCTURED_RESPONSE)
        )
        result = agente_obra.run(SAMPLE_DATA, stream=False, structured=True)
    project = result["proyectos"][0]
    assert "kpis" in project
    for kpi in ("cpi", "spi", "eac", "margen_neto", "desviacion_costo"):
        assert kpi in project["kpis"], f"Missing KPI in project output: {kpi}"


def test_run_structured_raises_on_invalid_json():
    with patch("agents.agente_obra.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("not valid json {{{")
        with pytest.raises(ValueError, match="invalid JSON"):
            agente_obra.run(SAMPLE_DATA, stream=False, structured=True)


def test_run_structured_strips_markdown_fences():
    with patch("agents.agente_obra.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            "```json\n" + json.dumps(SAMPLE_STRUCTURED_RESPONSE) + "\n```"
        )
        result = agente_obra.run(SAMPLE_DATA, stream=False, structured=True)
    assert isinstance(result, dict)


def test_run_structured_max_tokens_increased():
    with patch("agents.agente_obra.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_STRUCTURED_RESPONSE)
        )
        agente_obra.run(SAMPLE_DATA, stream=False, structured=True)
        call_kwargs = MockClient().messages.create.call_args[1]
    assert call_kwargs["max_tokens"] == 3000
