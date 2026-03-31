"""Tests for agente_ventas — mocks the Anthropic API to avoid real calls."""

import json
import pytest
from unittest.mock import MagicMock, patch

from agents import agente_ventas


SAMPLE_DATA = (
    "Revenue:\n"
    "- MRR: $142,000 USD | ARR: $1,704,000 | NRR: 96% | Churn mensual: 4.4%\n"
    "- Clientes activos: 87 | Perdidos: 4\n"
    "Pipeline: 14 deals activos, $312,000 USD total\n"
    "Deals estancados: Constructora López $48K (18 días), Grupo Norte $36K (21 días)\n"
    "CAC $4,800 | LTV $11,400 | Win rate 28% | Ciclo venta 47 días\n"
    "Cuota: $38,000 | Alcanzado: $29,600 (78%)\n"
)

SAMPLE_STRUCTURED_RESPONSE = {
    "revenue": {
        "mrr": 142000,
        "arr": 1704000,
        "mrr_nuevo": 18000,
        "mrr_expandido": 3200,
        "mrr_contraido": 800,
        "mrr_churned": 6200,
        "nrr": "96%",
        "churn_mensual": "4.4%",
        "churn_anualizado": "52.8%",
    },
    "pipeline": {
        "total_valor": 312000,
        "deals_activos": 14,
        "forecast_mes": 34000,
        "cuota_mensual": 38000,
        "cuota_pct": "78%",
        "pipeline_velocity": 1840,
    },
    "eficiencia": {
        "cac": 4800,
        "ltv": 11400,
        "ltv_cac_ratio": 2.375,
        "payback_cac_meses": 4,
        "win_rate": "28%",
        "ciclo_venta_dias": 47,
        "ticket_promedio": 22300,
    },
    "clientes": {"activos_total": 87, "nuevos_periodo": 3, "perdidos_periodo": 4},
    "deals_por_etapa": [
        {"etapa": "Prospecto", "cantidad": 4, "valor": 48000},
        {"etapa": "Demo/Propuesta", "cantidad": 6, "valor": 138000},
        {"etapa": "Negociación", "cantidad": 4, "valor": 126000},
    ],
    "deals_estancados": [
        {
            "nombre": "Constructora López",
            "valor": 48000,
            "etapa": "Negociación",
            "dias_sin_actividad": 18,
            "accion": "Llamar al decisor esta semana",
        },
        {
            "nombre": "Grupo Norte",
            "valor": 36000,
            "etapa": "Propuesta",
            "dias_sin_actividad": 21,
            "accion": "Enviar propuesta actualizada o cerrar el deal",
        },
    ],
    "alertas": [
        {
            "nivel": "CRÍTICA",
            "metrica": "churn_mensual",
            "valor_actual": "4.4%",
            "umbral": ">3%",
            "descripcion": "Churn supera el umbral crítico",
            "accion": "Activar programa de retención de clientes en riesgo",
        },
        {
            "nivel": "MEDIA",
            "metrica": "ltv_cac_ratio",
            "valor_actual": "2.38x",
            "umbral": "<3x",
            "descripcion": "Ratio LTV/CAC por debajo del nivel saludable",
            "accion": "Revisar estrategia de adquisición y reducir CAC",
        },
    ],
    "resumen_ejecutivo": "Churn elevado y LTV/CAC subóptimo son los principales riesgos.",
    "alertas_criticas_total": 1,
}


# ── build_system_prompt ───────────────────────────────────────────────────────

def test_build_system_prompt_default_thresholds():
    prompt = agente_ventas.build_system_prompt()
    assert "14" in prompt           # thr_deal days
    assert "3.0%" in prompt         # thr_churn
    assert "3.0×" in prompt         # thr_ltv_cac
    assert "20%" in prompt          # thr_win_rate


def test_build_system_prompt_custom_thresholds():
    prompt = agente_ventas.build_system_prompt({"thr_churn": 2.0, "thr_win_rate": 25})
    assert "2.0%" in prompt
    assert "25%" in prompt


def test_system_prompt_contains_saas_kpis():
    prompt = agente_ventas.build_system_prompt()
    for kpi in ("MRR", "ARR", "NRR", "CAC", "LTV", "churn", "win rate"):
        assert kpi.lower() in prompt.lower(), f"Missing SaaS KPI in system prompt: {kpi}"


def test_system_prompt_does_not_use_construction_margin():
    """The old thr_margen:12% construction threshold must not be in ventas."""
    prompt = agente_ventas.build_system_prompt()
    # thr_margen was removed; only SaaS-native thresholds remain
    assert "Margen neto mínimo aceptable" not in prompt


# ── run — text mode ───────────────────────────────────────────────────────────

def _mock_message(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def test_run_text_mode_returns_string():
    with patch("agents.agente_ventas.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("Análisis de ventas.")
        result = agente_ventas.run(SAMPLE_DATA, stream=False)
    assert isinstance(result, str)


def test_run_text_mode_passes_correct_model():
    with patch("agents.agente_ventas.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("ok")
        agente_ventas.run(SAMPLE_DATA, stream=False)
        call_kwargs = MockClient().messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-sonnet-4-20250514"


def test_run_includes_context():
    with patch("agents.agente_ventas.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("ok")
        agente_ventas.run(SAMPLE_DATA, context="Fin de trimestre", stream=False)
        call_kwargs = MockClient().messages.create.call_args[1]
    assert "Fin de trimestre" in call_kwargs["messages"][0]["content"]


# ── run — structured mode ─────────────────────────────────────────────────────

def test_run_structured_returns_dict():
    with patch("agents.agente_ventas.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_STRUCTURED_RESPONSE)
        )
        result = agente_ventas.run(SAMPLE_DATA, stream=False, structured=True)
    assert isinstance(result, dict)


def test_run_structured_has_required_keys():
    with patch("agents.agente_ventas.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_STRUCTURED_RESPONSE)
        )
        result = agente_ventas.run(SAMPLE_DATA, stream=False, structured=True)
    for key in ("revenue", "pipeline", "eficiencia", "deals_estancados", "alertas"):
        assert key in result, f"Missing key: {key}"


def test_run_structured_revenue_has_mrr_arr_nrr():
    with patch("agents.agente_ventas.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_STRUCTURED_RESPONSE)
        )
        result = agente_ventas.run(SAMPLE_DATA, stream=False, structured=True)
    rev = result["revenue"]
    for field in ("mrr", "arr", "nrr", "churn_mensual", "mrr_churned"):
        assert field in rev, f"Missing revenue field: {field}"


def test_run_structured_eficiencia_has_ltv_cac():
    with patch("agents.agente_ventas.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_STRUCTURED_RESPONSE)
        )
        result = agente_ventas.run(SAMPLE_DATA, stream=False, structured=True)
    ef = result["eficiencia"]
    for field in ("cac", "ltv", "ltv_cac_ratio", "win_rate", "ciclo_venta_dias"):
        assert field in ef, f"Missing eficiencia field: {field}"


def test_run_structured_raises_on_invalid_json():
    with patch("agents.agente_ventas.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("not json {{")
        with pytest.raises(ValueError, match="invalid JSON"):
            agente_ventas.run(SAMPLE_DATA, stream=False, structured=True)


def test_run_structured_strips_markdown_fences():
    with patch("agents.agente_ventas.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            "```json\n" + json.dumps(SAMPLE_STRUCTURED_RESPONSE) + "\n```"
        )
        result = agente_ventas.run(SAMPLE_DATA, stream=False, structured=True)
    assert isinstance(result, dict)
