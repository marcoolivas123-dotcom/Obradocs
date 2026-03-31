"""
ObraDocs Agents
===============
A suite of Claude-powered agents for real estate and construction management.

Monitoring agents (streaming or structured JSON output):
    agente_obra        — construction project KPIs and EVM analysis
    agente_ventas      — SaaS CRM pipeline and revenue metrics
    agente_corretaje   — brokerage inventory, absorption and commissions

Analysis agent (structured JSON output):
    agente_viabilidad  — full real estate project viability report

Orchestration:
    agente_supervisor  — runs monitoring agents concurrently, produces unified dashboard

Support modules:
    notificaciones     — dispatch critical alerts via email, WhatsApp, or webhook
    historial          — persist and compare agent runs over time

Quick start
-----------
>>> from agents import agente_supervisor
>>> report = agente_supervisor.run(data_obra=..., data_ventas=..., data_corretaje=...)
>>> agente_supervisor.print_dashboard(report)

>>> from agents import agente_viabilidad
>>> result = agente_viabilidad.run(project_data="Tipo: Residencial medio, Ciudad: QRO, ...")
>>> agente_viabilidad.print_report(result)

>>> from agents.notificaciones import dispatch
>>> dispatch(report=report, source="Supervisor")

>>> from agents.historial import save, summary
>>> save("supervisor", data=report)
>>> summary("supervisor")
"""

from agents import (  # noqa: F401 — re-export for convenience
    agente_obra,
    agente_ventas,
    agente_corretaje,
    agente_viabilidad,
    agente_supervisor,
    notificaciones,
    historial,
)

__all__ = [
    "agente_obra",
    "agente_ventas",
    "agente_corretaje",
    "agente_viabilidad",
    "agente_supervisor",
    "notificaciones",
    "historial",
]
