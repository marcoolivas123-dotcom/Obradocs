"""
Agente Supervisor — ObraDocs
Orchestrates all three monitoring agents (Obra, Ventas, Corretaje) concurrently
and produces a single unified executive dashboard via a final synthesis call.

Usage:
    from agents.agente_supervisor import run
    report = run(data_obra=..., data_ventas=..., data_corretaje=...)
    print(report["resumen_general"])
"""

import json
import concurrent.futures
import anthropic

from agents import agente_obra, agente_ventas, agente_corretaje


SUPERVISOR_SYSTEM = """Eres el Director de Análisis de ObraDocs. Recibirás los reportes JSON \
de tres agentes especializados (Obra, Ventas, Corretaje) y deberás producir un reporte ejecutivo \
unificado para el director general.

IMPORTANTE: Responde ÚNICAMENTE con un objeto JSON válido, sin backticks ni texto adicional:

{
  "dashboard": {
    "semaforo_global": "Verde|Amarillo|Rojo",
    "score_global": número del 0 al 100,
    "resumen_general": "3-4 oraciones con el estado del negocio completo",
    "modulos": {
      "obra":      { "semaforo": "Verde|Amarillo|Rojo", "alertas_criticas": número, "titular": "frase de 1 línea" },
      "ventas":    { "semaforo": "Verde|Amarillo|Rojo", "alertas_criticas": número, "titular": "frase de 1 línea" },
      "corretaje": { "semaforo": "Verde|Amarillo|Rojo", "alertas_criticas": número, "titular": "frase de 1 línea" }
    }
  },
  "alertas_criticas": [
    {
      "modulo": "Obra|Ventas|Corretaje",
      "descripcion": "descripción concisa",
      "impacto": "impacto financiero o operativo",
      "accion_inmediata": "qué hacer hoy"
    }
  ],
  "top_acciones": [
    { "prioridad": número, "modulo": "...", "accion": "acción específica", "responsable": "rol sugerido" }
  ],
  "indicadores_clave": {
    "obra":      { "kpi_principal": "nombre", "valor": "...", "tendencia": "↑|↓|→" },
    "ventas":    { "kpi_principal": "nombre", "valor": "...", "tendencia": "↑|↓|→" },
    "corretaje": { "kpi_principal": "nombre", "valor": "...", "tendencia": "↑|↓|→" }
  }
}"""


def _run_obra(data_obra: str, thresholds_obra: dict) -> dict | str:
    """Run obra agent in structured mode; fall back to text on error."""
    try:
        return agente_obra.run(
            data_obra, thresholds=thresholds_obra, stream=False, structured=True
        )
    except Exception as exc:
        return agente_obra.run(data_obra, thresholds=thresholds_obra, stream=False) or str(exc)


def _run_ventas(data_ventas: str, thresholds_ventas: dict) -> dict | str:
    try:
        return agente_ventas.run(
            data_ventas, thresholds=thresholds_ventas, stream=False, structured=True
        )
    except Exception as exc:
        return agente_ventas.run(data_ventas, thresholds=thresholds_ventas, stream=False) or str(exc)


def _run_corretaje(data_corretaje: str, thresholds_corretaje: dict) -> str:
    return agente_corretaje.run(data_corretaje, thresholds=thresholds_corretaje, stream=False) or ""


def run(
    data_obra: str = "",
    data_ventas: str = "",
    data_corretaje: str = "",
    thresholds_obra: dict = None,
    thresholds_ventas: dict = None,
    thresholds_corretaje: dict = None,
    skip_modules: list[str] = None,
) -> dict:
    """
    Run all three monitoring agents concurrently and synthesize a unified dashboard.

    Args:
        data_obra: Construction project data string (passed to agente_obra).
        data_ventas: CRM/revenue data string (passed to agente_ventas).
        data_corretaje: Brokerage/inventory data string (passed to agente_corretaje).
        thresholds_obra: Optional threshold overrides for obra agent.
        thresholds_ventas: Optional threshold overrides for ventas agent.
        thresholds_corretaje: Optional threshold overrides for corretaje agent.
        skip_modules: List of module names to skip, e.g. ["corretaje"].

    Returns:
        Parsed JSON dict with unified dashboard, critical alerts, and top actions.
    """
    skip = set(skip_modules or [])
    results: dict[str, dict | str] = {}

    # Run agents concurrently
    futures: dict[str, concurrent.futures.Future] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        if "obra" not in skip and data_obra:
            futures["obra"] = pool.submit(_run_obra, data_obra, thresholds_obra or {})
        if "ventas" not in skip and data_ventas:
            futures["ventas"] = pool.submit(_run_ventas, data_ventas, thresholds_ventas or {})
        if "corretaje" not in skip and data_corretaje:
            futures["corretaje"] = pool.submit(
                _run_corretaje, data_corretaje, thresholds_corretaje or {}
            )
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except Exception as exc:
                results[name] = f"Error en módulo {name}: {exc}"

    # Build synthesis prompt
    synthesis_prompt = "Aquí están los reportes de los tres agentes especializados:\n\n"
    for modulo, resultado in results.items():
        synthesis_prompt += f"=== REPORTE {modulo.upper()} ===\n"
        if isinstance(resultado, dict):
            synthesis_prompt += json.dumps(resultado, ensure_ascii=False, indent=2)
        else:
            synthesis_prompt += str(resultado)
        synthesis_prompt += "\n\n"
    synthesis_prompt += (
        "Genera el reporte ejecutivo unificado para el director general, "
        "consolidando alertas críticas, indicadores clave y las top 5 acciones prioritarias."
    )

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SUPERVISOR_SYSTEM,
        messages=[{"role": "user", "content": synthesis_prompt}],
    )

    raw = message.content[0].text.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        dashboard = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Supervisor returned invalid JSON: {exc}\n\nRaw:\n{raw}") from exc

    # Attach raw sub-reports for downstream use
    dashboard["_sub_reports"] = results
    return dashboard


def print_dashboard(report: dict) -> None:
    """Pretty-print the supervisor dashboard to stdout."""
    d = report.get("dashboard", {})
    semaforo_emoji = {"Verde": "🟢", "Amarillo": "🟡", "Rojo": "🔴"}.get(d.get("semaforo_global", ""), "⚪")

    print(f"\n{'='*65}")
    print(f"  {semaforo_emoji}  DASHBOARD EJECUTIVO — Score {d.get('score_global', '?')}/100")
    print(f"{'='*65}")
    print(f"\n{d.get('resumen_general', '')}\n")

    modulos = d.get("modulos", {})
    if modulos:
        print("── Módulos ────────────────────────────────────────────────")
        for nombre, m in modulos.items():
            em = {"Verde": "🟢", "Amarillo": "🟡", "Rojo": "🔴"}.get(m.get("semaforo", ""), "⚪")
            print(f"  {em} {nombre.upper():<12} {m.get('alertas_criticas', 0)} críticas — {m.get('titular', '')}")

    alertas = report.get("alertas_criticas", [])
    if alertas:
        print("\n── Alertas Críticas ───────────────────────────────────────")
        for a in alertas:
            print(f"  [{a.get('modulo','?')}] {a.get('descripcion','')}")
            print(f"         Acción: {a.get('accion_inmediata','')}")

    acciones = report.get("top_acciones", [])
    if acciones:
        print("\n── Top Acciones ───────────────────────────────────────────")
        for a in acciones:
            print(f"  {a.get('prioridad','?')}. [{a.get('modulo','?')}] {a.get('accion','')}")
    print()


if __name__ == "__main__":
    from agents.agente_obra import run as _o
    from agents.agente_ventas import run as _v
    from agents.agente_corretaje import run as _c

    # Reuse sample data from each agent module
    obra_data = (
        "- Torre Cumbres: 120 deptos, avance físico 78%, avance financiero 74%, "
        "AC $108.5M, EV $113.1M, PV $107.3M, costo/m² $19,180 vs $18,400, desviación +4.2%, "
        "margen neto 16.8%, flujo -$3.2M, retenciones $8.4M, días retraso 0\n"
        "- Resi. Bosques: 48 casas, avance físico 41%, avance financiero 49%, "
        "AC $30.4M, EV $25.4M, PV $28.0M, costo/m² $28,600 vs $26,400, desviación +8.2%, "
        "margen neto 9.1%, flujo -$6.1M, retenciones $4.2M, días retraso 22\n"
    )
    ventas_data = (
        "MRR $142,000 USD | ARR $1,704,000 | NRR 96% | Churn 4.4%\n"
        "Pipeline: 14 deals, $312,000 USD total | Cuota mes: $38,000 | Alcanzado 78%\n"
        "Deals estancados: Constructora López $48K (18 días), Grupo Norte $36K (21 días)\n"
        "CAC $4,800 | LTV $11,400 | Win rate 28% | Ciclo venta 47 días\n"
    )
    corretaje_data = (
        "Residencial Punta Norte: 50 casas, 12 vendidas, 7 reservadas, 28 disponibles\n"
        "Absorción real 1.8 u/sem vs 2.5 planeada (72%)\n"
        "6 unidades >90 días en mercado | Descuento promedio 4.6%\n"
        "Comisiones por cobrar $140,000 MXN | Vencidas $68,000 MXN\n"
        "Leads activos 42 | Conversión 8.3%\n"
    )

    report = run(obra_data, ventas_data, corretaje_data)
    print_dashboard(report)
