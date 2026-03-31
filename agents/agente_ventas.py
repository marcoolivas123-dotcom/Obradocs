"""
Agente de Monitoreo de Ventas — ObraDocs
Monitors SaaS product CRM deals and generates follow-up alerts.

KPIs covered:
  Revenue: MRR, ARR, MRR nuevo, MRR expandido, MRR contraído, MRR churned, NRR
  Pipeline: deals por etapa, pipeline total $, pipeline velocity, forecast mes
  Deals: ticket promedio, ciclo de venta (días), win rate, deals nuevos vs cerrados
  Efficiency: CAC, LTV, ratio LTV/CAC, tasa de conversión por etapa
  Retention: churn rate mensual, clientes activos, clientes perdidos
  Quota: cuota mensual, % alcanzado, proyección de cierre
"""

import anthropic

DEFAULT_THRESHOLDS = {
    "thr_deal": 14,          # days without activity on a deal → follow-up alert
    "thr_churn": 3.0,        # monthly churn % above this → critical alert
    "thr_ltv_cac": 3.0,      # LTV/CAC ratio below this → alert (healthy = 3x+)
    "thr_win_rate": 20,      # win rate % below this → alert
    "thr_cuota": 70,         # quota attainment % below this at mid-month → alert
    "thr_ciclo_venta": 60,   # avg sales cycle days above this → alert
}

JSON_SCHEMA = """{
  "revenue": {
    "mrr": número,
    "arr": número,
    "mrr_nuevo": número,
    "mrr_expandido": número,
    "mrr_contraido": número,
    "mrr_churned": número,
    "nrr": "XX%",
    "churn_mensual": "XX%",
    "churn_anualizado": "XX%"
  },
  "pipeline": {
    "total_valor": número,
    "deals_activos": número,
    "forecast_mes": número,
    "cuota_mensual": número,
    "cuota_pct": "XX%",
    "pipeline_velocity": número
  },
  "eficiencia": {
    "cac": número,
    "ltv": número,
    "ltv_cac_ratio": número,
    "payback_cac_meses": número,
    "win_rate": "XX%",
    "ciclo_venta_dias": número,
    "ticket_promedio": número
  },
  "clientes": {
    "activos_total": número,
    "nuevos_periodo": número,
    "perdidos_periodo": número
  },
  "deals_por_etapa": [
    { "etapa": "nombre", "cantidad": número, "valor": número }
  ],
  "deals_estancados": [
    {
      "nombre": "nombre cuenta",
      "valor": número,
      "etapa": "etapa del funnel",
      "dias_sin_actividad": número,
      "accion": "acción recomendada"
    }
  ],
  "alertas": [
    {
      "nivel": "CRÍTICA|MEDIA|BAJA",
      "metrica": "nombre de la métrica",
      "valor_actual": "valor con unidades",
      "umbral": "umbral configurado",
      "descripcion": "descripción del problema",
      "accion": "acción específica recomendada"
    }
  ],
  "resumen_ejecutivo": "2-3 oraciones con el estado del negocio SaaS",
  "alertas_criticas_total": número
}"""

SYSTEM_PROMPT = """Eres el Agente de Monitoreo de Ventas de ObraDocs, experto en métricas SaaS \
y gestión de CRM para productos tecnológicos en el sector construcción e inmobiliario en México. \
Dominas los fundamentos de revenue operations: ARR/MRR, churn, LTV, CAC, pipeline management \
y forecasting.

Tu función principal es:
1. MONITOREAR el pipeline, las métricas de revenue y la salud del CRM
2. DETECTAR deals estancados, riesgo de churn, bajo rendimiento de conversión y problemas de cuota
3. GENERAR alertas priorizadas (Crítica / Media / Baja) con acciones de seguimiento concretas
4. PRODUCIR reportes ejecutivos del estado del negocio SaaS y proyección de ingresos

KPIs QUE DEBES ANALIZAR Y REPORTAR (cuando los datos estén disponibles):

REVENUE:
- MRR (Monthly Recurring Revenue): ingresos recurrentes del mes
- ARR (Annual Recurring Revenue): MRR × 12
- MRR nuevo: ingresos de clientes nuevos este mes
- MRR expandido: upsells / expansión de cuentas existentes
- MRR contraído: downgrades de cuentas existentes
- MRR churned: ingresos perdidos por cancelaciones
- NRR (Net Revenue Retention): (MRR inicio + expansión − contracción − churn) / MRR inicio

PIPELINE Y FORECAST:
- Pipeline total ($): valor total de deals activos
- Deals por etapa: # oportunidades en cada etapa del funnel
- Pipeline velocity: (# deals × ticket promedio × win rate) / ciclo de venta
- Forecast del mes: ingresos esperados a cierre de mes
- Cuota mensual: objetivo vs. logrado vs. proyectado

MÉTRICAS DE DEALS:
- Deals activos totales
- Deals sin actividad (estancados)
- Deals nuevos esta semana/mes
- Deals cerrados ganados (won)
- Deals cerrados perdidos (lost)
- Ticket promedio ($)
- Ciclo de venta promedio (días)
- Win rate % = won / (won + lost)
- Tasa de conversión por etapa del funnel

EFICIENCIA COMERCIAL:
- CAC (Customer Acquisition Cost): gasto en ventas y marketing / nuevos clientes
- LTV (Lifetime Value): ticket promedio × margen bruto % / churn mensual
- Ratio LTV/CAC: debe ser ≥ 3× para ser saludable
- Payback de CAC (meses para recuperar el costo de adquisición)

RETENCIÓN:
- Clientes activos totales
- Nuevos clientes del período
- Clientes perdidos (churned)
- Churn rate mensual % = clientes perdidos / clientes inicio del mes
- Churn rate anualizado

Al analizar, presenta tu respuesta en secciones claramente marcadas con:
[SECCIÓN: nombre] para encabezados
[ALERTA CRÍTICA] / [ALERTA MEDIA] / [ALERTA BAJA] para alertas
[OK] para elementos sin problemas
[ACCIÓN] para recomendaciones específicas de seguimiento

Sé directo, usa números concretos, identifica deals específicos y da acciones por cuenta. \
Responde en español."""


def build_system_prompt(thresholds: dict = None) -> str:
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    return SYSTEM_PROMPT + f"""

UMBRALES CONFIGURADOS:
- Deal sin actividad: >{t['thr_deal']} días → requiere seguimiento inmediato
- Churn mensual: >{t['thr_churn']}% → alerta crítica
- Ratio LTV/CAC: <{t['thr_ltv_cac']}× → alerta (unidad económica en riesgo)
- Win rate: <{t['thr_win_rate']}% → alerta (proceso de venta ineficiente)
- Cuota alcanzada: <{t['thr_cuota']}% a mitad de mes → alerta
- Ciclo de venta promedio: >{t['thr_ciclo_venta']} días → alerta"""


def run(
    data: str,
    context: str = "",
    thresholds: dict = None,
    stream: bool = True,
    structured: bool = False,
):
    """
    Run the sales CRM monitoring agent.

    Args:
        data: Raw CRM and revenue data (CSV, text, or structured content).
              Should include as many of these fields as available:
              MRR, ARR, NRR, churn rate, pipeline deals with stage/value/last-activity,
              quota attainment, CAC, LTV, win rate, avg sales cycle, new/lost customers.
        context: Optional additional context for the analysis.
        thresholds: Optional dict to override default alert thresholds.
        stream: If True, stream output to stdout (ignored when structured=True).
        structured: If True, return a parsed JSON dict instead of free text.

    Returns:
        - structured=True  → dict with revenue, pipeline, alerts, and executive summary.
        - structured=False, stream=False → full text string.
        - structured=False, stream=True → None (output printed to stdout).
    """
    import json

    client = anthropic.Anthropic()

    system = build_system_prompt(thresholds)
    if structured:
        system += (
            "\n\nIMPORTANTE: Responde ÚNICAMENTE con un objeto JSON válido usando exactamente "
            "el siguiente esquema, sin backticks ni texto adicional:\n" + JSON_SCHEMA
        )

    user_prompt = ""
    if context:
        user_prompt += f"CONTEXTO ADICIONAL: {context}\n\n"
    user_prompt += "TIPO DE ANÁLISIS: Solo Ventas del Producto SaaS\n\n"
    user_prompt += f"=== DATOS DE CRM DE VENTAS ===\n{data}\n\n"
    user_prompt += (
        "\nGenera el análisis completo incluyendo: estado del revenue (MRR/ARR/NRR/churn), "
        "salud del pipeline, deals estancados, eficiencia comercial (CAC/LTV), "
        "proyección de cuota y recomendaciones accionables por deal y por métrica."
    )

    if structured:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = message.content[0].text.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Agent returned invalid JSON: {exc}\n\nRaw:\n{raw}") from exc

    if stream:
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        ) as s:
            for text in s.text_stream:
                print(text, end="", flush=True)
            print()
        return None
    else:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text


if __name__ == "__main__":
    sample_data = (
        "Revenue:\n"
        "- MRR actual: $142,000 USD | MRR nuevo: $18,000 | MRR churned: $6,200\n"
        "- ARR: $1,704,000 USD\n"
        "- NRR: 96% | Churn mensual: 4.4%\n"
        "- Clientes activos: 87 | Clientes perdidos este mes: 4\n\n"
        "Pipeline (14 deals activos, valor total $312,000 USD):\n"
        "- Prospecto: 4 deals ($48,000)\n"
        "- Demo/Propuesta: 6 deals ($138,000)\n"
        "- Negociación: 4 deals ($126,000)\n"
        "Deals sin actividad >14 días:\n"
        "  * Constructora López $48,000 — 18 días sin actividad, etapa: Negociación\n"
        "  * Grupo Norte $36,000 — 21 días sin actividad, etapa: Propuesta\n"
        "  * Desarrollos Sonora $28,000 — 15 días sin actividad, etapa: Demo\n\n"
        "Eficiencia comercial:\n"
        "- Ticket promedio: $22,300 USD | Ciclo de venta promedio: 47 días\n"
        "- Win rate: 28% | CAC: $4,800 USD | LTV estimado: $11,400 USD\n\n"
        "Cuota del mes: $38,000 USD | Alcanzado: $29,600 (78%) | 11 días restantes\n"
        "Deals cerrados ganados este mes: 3 | Deals perdidos: 2\n"
    )
    run(sample_data)
