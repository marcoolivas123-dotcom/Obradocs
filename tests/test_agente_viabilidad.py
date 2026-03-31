"""Tests for agente_viabilidad — mocks the Anthropic API to avoid real calls."""

import json
import pytest
from unittest.mock import MagicMock, patch

from agents import agente_viabilidad


SAMPLE_PROJECT = """
Nombre: Torre Insurgentes QRO
Tipo: Residencial medio
Ciudad: Querétaro, QRO
Unidades: 80 departamentos
Plazo: 24 meses
Terreno: 2,200 m²
Construida total: 9,600 m²
Vendible: 7,800 m²
Costo terreno: $18,000,000 MXN
Costo construcción: $14,500/m²
Costos indirectos: 18%
Precio venta: $42,000/m²
Precio mercado: $39,000/m²
Financiamiento: 50%
Absorción esperada: 4 u/mes
"""

SAMPLE_REPORT = {
    "viabilidad_score": 72,
    "semaforo": "Verde",
    "veredicto_titulo": "Proyecto viable con riesgo moderado",
    "veredicto_resumen": "El proyecto muestra ROI atractivo. El precio/m² supera el mercado.",
    "kpis": {
        "roi": "28%",
        "tir": "19%",
        "vpn": 12500000,
        "margen_bruto": "30%",
        "margen_neto": "21%",
        "payback": "28 meses",
        "ingresos_totales": 327600000,
        "costo_total": 258624000,
        "utilidad_neta": 68976000,
        "punto_equilibrio": "62% de ventas",
        "unidades_equilibrio": 50,
        "costo_financiero_total": 18000000,
        "max_exposicion_caja": 95000000,
        "deuda_capital_ratio": "1:1",
        "precio_promedio_m2": 42000,
        "costo_construccion_m2": 14500,
        "superficie_vendible_m2": 7800,
        "absorcion_mensual": 4,
        "tiempo_comercializacion": "20 meses",
        "terreno_pct_costo_total": "7%",
    },
    "dimensiones": {
        "financiera": {"score": 74, "analisis": "ROI sólido, TIR por encima del costo de capital."},
        "mercado": {"score": 68, "analisis": "Precio sobre mercado puede frenar absorción."},
        "tecnica": {"score": 80, "analisis": "Proyecto técnicamente sólido."},
        "legal": {"score": 85, "analisis": "Uso de suelo compatible, permisos viables."},
        "ambiental": {"score": 75, "analisis": "Sin restricciones ambientales relevantes."},
        "comercial": {"score": 65, "analisis": "Competencia activa en la zona."},
    },
    "escenarios": {
        "optimista": {
            "descripcion": "Precio +5%, absorción 5 u/mes, costo -2%",
            "roi": "35%",
            "tir": "24%",
            "ingresos": 343980000,
            "utilidad": 85356000,
            "margen_neto": "25%",
            "payback": "22 meses",
            "conclusion": "Proyecto altamente rentable.",
        },
        "base": {
            "descripcion": "Supuestos del proyecto original",
            "roi": "28%",
            "tir": "19%",
            "ingresos": 327600000,
            "utilidad": 68976000,
            "margen_neto": "21%",
            "payback": "28 meses",
            "conclusion": "Proyecto viable con gestión activa.",
        },
        "pesimista": {
            "descripcion": "Precio -8%, absorción 2.5 u/mes, costo +5%",
            "roi": "11%",
            "tir": "9%",
            "ingresos": 301392000,
            "utilidad": 24768000,
            "margen_neto": "8%",
            "payback": "38 meses",
            "conclusion": "Rentabilidad comprometida; requiere mitigación.",
        },
    },
    "riesgos": [
        {
            "categoria": "Absorción lenta",
            "nivel": "Medio",
            "probabilidad": "Media",
            "descripcion": "Precio sobre mercado puede alargar comercialización.",
            "impacto_financiero": "Reducción de TIR en 3-5 puntos",
            "mitigacion": "Ajustar precio o mejorar producto diferenciado.",
        }
    ],
    "recomendaciones": [
        "Revisar precio/m² frente a competencia antes de lanzar",
        "Contratar preventas para validar demanda",
    ],
    "conclusion_ejecutiva": "El proyecto es viable en escenario base. El riesgo principal es la absorción.",
}


def _mock_message(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


# ── run ───────────────────────────────────────────────────────────────────────

def test_run_returns_dict():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_REPORT)
        )
        result = agente_viabilidad.run(SAMPLE_PROJECT)
    assert isinstance(result, dict)


def test_run_has_top_level_keys():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_REPORT)
        )
        result = agente_viabilidad.run(SAMPLE_PROJECT)
    required = (
        "viabilidad_score", "semaforo", "veredicto_titulo", "veredicto_resumen",
        "kpis", "dimensiones", "escenarios", "riesgos", "recomendaciones",
        "conclusion_ejecutiva",
    )
    for key in required:
        assert key in result, f"Missing top-level key: {key}"


def test_run_kpis_are_complete():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_REPORT)
        )
        result = agente_viabilidad.run(SAMPLE_PROJECT)
    kpis = result["kpis"]
    required_kpis = (
        "roi", "tir", "vpn", "margen_bruto", "margen_neto", "payback",
        "ingresos_totales", "costo_total", "utilidad_neta", "punto_equilibrio",
        "unidades_equilibrio", "costo_financiero_total", "max_exposicion_caja",
        "deuda_capital_ratio", "precio_promedio_m2", "costo_construccion_m2",
        "superficie_vendible_m2", "absorcion_mensual", "tiempo_comercializacion",
        "terreno_pct_costo_total",
    )
    for kpi in required_kpis:
        assert kpi in kpis, f"Missing KPI: {kpi}"


def test_run_dimensiones_have_six_categories():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_REPORT)
        )
        result = agente_viabilidad.run(SAMPLE_PROJECT)
    dims = result["dimensiones"]
    for dim in ("financiera", "mercado", "tecnica", "legal", "ambiental", "comercial"):
        assert dim in dims, f"Missing dimension: {dim}"
        assert "score" in dims[dim]
        assert "analisis" in dims[dim]


def test_run_escenarios_have_tir_and_utilidad():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_REPORT)
        )
        result = agente_viabilidad.run(SAMPLE_PROJECT)
    for scenario in ("optimista", "base", "pesimista"):
        s = result["escenarios"][scenario]
        assert "tir" in s, f"Missing 'tir' in scenario {scenario}"
        assert "utilidad" in s, f"Missing 'utilidad' in scenario {scenario}"
        assert "descripcion" in s, f"Missing 'descripcion' in scenario {scenario}"


def test_run_riesgos_have_probabilidad_and_impacto():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_REPORT)
        )
        result = agente_viabilidad.run(SAMPLE_PROJECT)
    for risk in result["riesgos"]:
        assert "probabilidad" in risk, "Risk missing 'probabilidad'"
        assert "impacto_financiero" in risk, "Risk missing 'impacto_financiero'"
        assert "mitigacion" in risk, "Risk missing 'mitigacion'"


def test_run_semaforo_is_valid():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_REPORT)
        )
        result = agente_viabilidad.run(SAMPLE_PROJECT)
    assert result["semaforo"] in ("Verde", "Amarillo", "Rojo")


def test_run_score_is_in_range():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_REPORT)
        )
        result = agente_viabilidad.run(SAMPLE_PROJECT)
    assert 0 <= result["viabilidad_score"] <= 100


def test_run_raises_on_invalid_json():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message("not json {{{")
        with pytest.raises(ValueError, match="invalid JSON"):
            agente_viabilidad.run(SAMPLE_PROJECT)


def test_run_strips_markdown_fences():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            "```json\n" + json.dumps(SAMPLE_REPORT) + "\n```"
        )
        result = agente_viabilidad.run(SAMPLE_PROJECT)
    assert isinstance(result, dict)


def test_run_uses_max_tokens_4000():
    with patch("agents.agente_viabilidad.anthropic.Anthropic") as MockClient:
        MockClient().messages.create.return_value = _mock_message(
            json.dumps(SAMPLE_REPORT)
        )
        agente_viabilidad.run(SAMPLE_PROJECT)
        call_kwargs = MockClient().messages.create.call_args[1]
    assert call_kwargs["max_tokens"] == 4000
