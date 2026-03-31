"""Tests for notificaciones — no network calls, no env vars required."""

import pytest
from agents.notificaciones import (
    Alert,
    extract_alerts_from_text,
    extract_alerts_from_report,
    dispatch,
    NotificationResult,
)


# ── Alert dataclass ───────────────────────────────────────────────────────────

def test_alert_is_critical():
    assert Alert(nivel="CRÍTICA", modulo="Obra", descripcion="test").is_critical
    assert Alert(nivel="CRITICA", modulo="Obra", descripcion="test").is_critical
    assert not Alert(nivel="MEDIA", modulo="Obra", descripcion="test").is_critical
    assert not Alert(nivel="BAJA", modulo="Obra", descripcion="test").is_critical


def test_alert_str_includes_accion():
    a = Alert(nivel="CRÍTICA", modulo="Obra", descripcion="Margen bajo", accion="Revisar contratos")
    s = str(a)
    assert "Margen bajo" in s
    assert "Revisar contratos" in s


# ── extract_alerts_from_text ──────────────────────────────────────────────────

SAMPLE_TEXT = """
[SECCIÓN: Proyectos de Obra]
[ALERTA CRÍTICA] Resi. Bosques: margen neto 9.1% por debajo del umbral de 12%.
[ACCIÓN] Revisar contratos de subcontratistas y renegociar precios.
[ALERTA MEDIA] Torre Cumbres: desviación de costo +4.2%.
[ACCIÓN] Auditar partidas de acabados.
[OK] Torre Cumbres: curva S dentro de rango.
"""


def test_extract_finds_critica():
    alerts = extract_alerts_from_text(SAMPLE_TEXT, source="Obra")
    criticas = [a for a in alerts if a.is_critical]
    assert len(criticas) >= 1


def test_extract_finds_media():
    alerts = extract_alerts_from_text(SAMPLE_TEXT, source="Obra")
    medias = [a for a in alerts if a.nivel == "MEDIA"]
    assert len(medias) >= 1


def test_extract_captures_source():
    alerts = extract_alerts_from_text(SAMPLE_TEXT, source="Obra")
    assert all(a.modulo == "Obra" for a in alerts)


def test_extract_empty_text():
    alerts = extract_alerts_from_text("", source="Obra")
    assert alerts == []


def test_extract_no_alerts():
    alerts = extract_alerts_from_text("[OK] Todo bien.\n[OK] Sin problemas.", source="Obra")
    assert alerts == []


def test_extract_accion_captured():
    alerts = extract_alerts_from_text(SAMPLE_TEXT, source="Obra")
    critica = next(a for a in alerts if a.is_critical)
    assert "subcontratistas" in critica.accion or "contratos" in critica.accion.lower()


# ── extract_alerts_from_report ────────────────────────────────────────────────

SAMPLE_OBRA_REPORT = {
    "proyectos": [
        {
            "nombre": "Resi. Bosques",
            "alertas": [
                {
                    "nivel": "CRÍTICA",
                    "kpi": "margen_neto",
                    "descripcion": "Margen neto 9.1%",
                    "accion": "Revisar costos",
                }
            ],
        }
    ]
}

SAMPLE_SUPERVISOR_REPORT = {
    "alertas_criticas": [
        {
            "modulo": "Obra",
            "descripcion": "Margen crítico en Resi. Bosques",
            "accion_inmediata": "Reunión urgente con director de obra",
        }
    ]
}

SAMPLE_VENTAS_REPORT = {
    "alertas": [
        {
            "nivel": "CRÍTICA",
            "metrica": "churn_mensual",
            "descripcion": "Churn al 4.4%",
            "accion": "Activar retención",
        }
    ]
}


def test_extract_from_obra_report():
    alerts = extract_alerts_from_report(SAMPLE_OBRA_REPORT, source="Obra")
    assert len(alerts) == 1
    assert alerts[0].is_critical
    assert "9.1%" in alerts[0].descripcion


def test_extract_from_supervisor_report():
    alerts = extract_alerts_from_report(SAMPLE_SUPERVISOR_REPORT, source="Supervisor")
    assert len(alerts) == 1
    assert alerts[0].modulo == "Obra"
    assert "reunión" in alerts[0].accion.lower() or "urgente" in alerts[0].accion.lower()


def test_extract_from_ventas_report():
    alerts = extract_alerts_from_report(SAMPLE_VENTAS_REPORT, source="Ventas")
    assert len(alerts) == 1
    assert alerts[0].nivel == "CRÍTICA"


def test_extract_from_empty_report():
    alerts = extract_alerts_from_report({}, source="X")
    assert alerts == []


# ── dispatch — no channels configured ────────────────────────────────────────

def test_dispatch_returns_empty_when_no_critical_alerts(monkeypatch):
    """With only_critical=True and no critical alerts, dispatch should return []."""
    monkeypatch.delenv("OBRADOCS_NOTIFY_EMAIL_TO", raising=False)
    monkeypatch.delenv("OBRADOCS_TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("OBRADOCS_WEBHOOK_URL", raising=False)
    results = dispatch(text="[OK] Todo bien.", source="Obra", only_critical=True)
    assert results == []


def test_dispatch_returns_results_when_no_env_vars(monkeypatch):
    """Channels with missing env vars return NotificationResult with success=False."""
    monkeypatch.delenv("OBRADOCS_NOTIFY_EMAIL_TO", raising=False)
    monkeypatch.delenv("OBRADOCS_TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("OBRADOCS_WEBHOOK_URL", raising=False)
    results = dispatch(
        text=SAMPLE_TEXT,
        source="Obra",
        only_critical=True,
        channels=["email", "whatsapp", "webhook"],
    )
    assert len(results) == 3
    assert all(isinstance(r, NotificationResult) for r in results)
    # All should fail gracefully since env vars are not set
    assert all(not r.success for r in results)
    assert all(r.error for r in results)


def test_dispatch_only_critical_filters_media():
    """only_critical=True should not trigger on MEDIA alerts."""
    text_only_media = "[ALERTA MEDIA] Algo menor.\n[ACCIÓN] Revisar."
    results = dispatch(text=text_only_media, source="Ventas", only_critical=True, channels=["email"])
    assert results == []
