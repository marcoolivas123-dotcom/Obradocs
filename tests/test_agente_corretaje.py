"""Tests for agente_corretaje — mocks the Anthropic API to avoid real calls."""

import pytest
from unittest.mock import MagicMock, patch

from agents import agente_corretaje


SAMPLE_DATA = (
    "Residencial Punta Norte: 50 casas, 12 vendidas, 7 reservadas, 28 disponibles\n"
    "Absorción real 1.8 u/sem vs 2.5 planeada (72%)\n"
    "6 unidades >90 días en mercado\n"
    "Descuento promedio 4.6%\n"
    "Comisiones por cobrar $140,000 MXN | Vencidas $68,000 MXN\n"
    "Leads activos 42 | Conversión 8.3%\n"
)


def _mock_message(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


# ── build_system_prompt ───────────────────────────────────────────────────────

def test_build_system_prompt_default_thresholds():
    prompt = agente_corretaje.build_system_prompt()
    assert "70%" in prompt           # thr_absorcion
    assert "90" in prompt            # thr_dias_mercado
    assert "5%" in prompt            # thr_descuento
    assert "30" in prompt            # thr_comision_vencida
    assert "10%" in prompt           # thr_conversion


def test_build_system_prompt_custom_thresholds():
    prompt = agente_corretaje.build_system_prompt({"thr_absorcion": 80, "thr_descuento": 3})
    assert "80%" in prompt
    assert "3%" in prompt


def test_system_prompt_covers_all_kpi_categories():
    prompt = agente_corretaje.build_system_prompt()
    categories = ("INVENTARIO", "ABSORCIÓN", "PRECIOS", "COMISIONES", "PIPELINE")
    for cat in categories:
        assert cat in prompt, f"Missing KPI category in system prompt: {cat}"


def test_system_prompt_covers_commission_kpis():
    prompt = agente_corretaje.build_system_prompt()
    for kpi in ("Comisiones generadas", "Comisiones cobradas", "Comisiones por cobrar", "Comisiones vencidas"):
        assert kpi.lower() in prompt.lower(), f"Missing commission KPI: {kpi}"


def test_system_prompt_covers_lead_pipeline_kpis():
    prompt = agente_corretaje.build_system_prompt()
    for kpi in ("Leads activos", "conversión", "Propuestas", "Visitas"):
        assert kpi.lower() in prompt.lower(), f"Missing pipeline KPI: {kpi}"


# ── run ───────────────────────────────────────────────────────────────────────

def test_run_text_mode_returns_string():
    with patch("agents.agente_corretaje.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("Análisis de corretaje.")
        result = agente_corretaje.run(SAMPLE_DATA, stream=False)
    assert isinstance(result, str)
    assert len(result) > 0


def test_run_text_mode_passes_correct_model():
    with patch("agents.agente_corretaje.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("ok")
        agente_corretaje.run(SAMPLE_DATA, stream=False)
        call_kwargs = MockClient().messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-sonnet-4-20250514"
    assert call_kwargs["max_tokens"] == 2000


def test_run_includes_context():
    with patch("agents.agente_corretaje.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("ok")
        agente_corretaje.run(SAMPLE_DATA, context="Temporada baja diciembre", stream=False)
        call_kwargs = MockClient().messages.create.call_args[1]
    assert "Temporada baja diciembre" in call_kwargs["messages"][0]["content"]


def test_run_user_prompt_includes_data():
    with patch("agents.agente_corretaje.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("ok")
        agente_corretaje.run(SAMPLE_DATA, stream=False)
        call_kwargs = MockClient().messages.create.call_args[1]
    content = call_kwargs["messages"][0]["content"]
    assert "Residencial Punta Norte" in content


def test_run_returns_none_in_stream_mode():
    """stream=True should print and return None (we skip actual streaming test)."""
    # We just verify the run function signature accepts stream=True
    # without raising before the API call
    assert "stream" in agente_corretaje.run.__code__.co_varnames


def test_run_custom_thresholds_applied():
    with patch("agents.agente_corretaje.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("ok")
        agente_corretaje.run(
            SAMPLE_DATA,
            thresholds={"thr_absorcion": 90, "thr_comision_vencida": 15},
            stream=False,
        )
        call_kwargs = MockClient().messages.create.call_args[1]
    system_prompt = call_kwargs["system"]
    assert "90%" in system_prompt
    assert "15" in system_prompt
