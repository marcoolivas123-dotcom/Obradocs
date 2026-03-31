"""
Agente de Monitoreo de Obra — ObraDocs
Monitors construction project KPIs and generates prioritized alerts.

KPIs covered:
  Earned Value Management: EV, PV, AC, CPI, SPI, EAC, ETC, VAC
  Cost: costo/m² presupuestado vs real, desviación %, margen bruto, margen neto,
        costo directo, costo indirecto, retenciones pendientes
  Schedule: avance físico %, avance financiero %, días de retraso, curva S
  Cash flow: flujo de caja período, flujo de caja acumulado, consumo de presupuesto %
"""

import anthropic

DEFAULT_THRESHOLDS = {
    "thr_costo": 5,        # % cost deviation → alert
    "thr_margen": 12,      # minimum net margin % → critical alert
    "thr_curvas": 5,       # physical vs financial progress diff % → alert
    "thr_cpi": 0.95,       # CPI below this → alert (< 1.0 = over budget)
    "thr_spi": 0.90,       # SPI below this → alert (< 1.0 = behind schedule)
    "thr_retraso": 10,     # schedule delay in days → alert
}

JSON_SCHEMA = """{
  "proyectos": [
    {
      "nombre": "nombre del proyecto",
      "estado": "Normal|En Riesgo|Crítico",
      "kpis": {
        "avance_fisico": "XX%",
        "avance_financiero": "XX%",
        "desviacion_curvas": "XX%",
        "cpi": número,
        "spi": número,
        "costo_m2_real": número,
        "costo_m2_presupuesto": número,
        "desviacion_costo": "XX%",
        "margen_bruto": "XX%",
        "margen_neto": "XX%",
        "eac": número,
        "vac": número,
        "flujo_periodo": número,
        "retenciones_pendientes": número,
        "dias_retraso": número
      },
      "alertas": [
        {
          "nivel": "CRÍTICA|MEDIA|BAJA",
          "kpi": "nombre del KPI afectado",
          "valor_actual": "valor con unidades",
          "umbral": "umbral configurado",
          "descripcion": "descripción concisa del problema",
          "accion": "acción específica recomendada"
        }
      ]
    }
  ],
  "resumen_ejecutivo": "2-3 oraciones con el estado general de todos los proyectos",
  "alertas_criticas_total": número,
  "alertas_medias_total": número,
  "proyectos_en_riesgo": ["nombre1", "nombre2"]
}"""

SYSTEM_PROMPT = """Eres el Agente de Monitoreo de Obra de ObraDocs, experto en control financiero \
y gestión de proyectos de construcción e inmobiliarios en México, con dominio de Earned Value \
Management (EVM), análisis de curva S, control presupuestal y KPIs de obra.

Tu función principal es:
1. MONITOREAR todos los KPIs de los proyectos de construcción
2. DETECTAR desviaciones de costo, retrasos, riesgos de flujo de caja y problemas de rendimiento
3. GENERAR alertas priorizadas (Crítica / Media / Baja) con acciones específicas
4. PRODUCIR reportes ejecutivos claros y accionables con análisis por proyecto

KPIs QUE DEBES ANALIZAR Y REPORTAR (cuando los datos estén disponibles):

AVANCE Y PROGRAMA:
- Avance físico % (% obra ejecutada)
- Avance financiero % (% presupuesto gastado)
- Diferencia avance físico vs. financiero (desviación curva S)
- Días de retraso vs. programa
- Fecha estimada de terminación vs. fecha programada

EARNED VALUE MANAGEMENT (EVM):
- EV (Earned Value / Valor Ganado): trabajo completado a costo presupuestado
- PV (Planned Value / Valor Planeado): trabajo que debería estar completo a la fecha
- AC (Actual Cost / Costo Real): costo real incurrido
- CPI (Cost Performance Index): EV / AC — >1.0 bajo presupuesto, <1.0 sobre presupuesto
- SPI (Schedule Performance Index): EV / PV — >1.0 adelantado, <1.0 retrasado
- EAC (Estimate at Completion): presupuesto total / CPI — costo estimado final
- ETC (Estimate to Complete): EAC − AC — cuánto falta por gastar
- VAC (Variance at Completion): presupuesto original − EAC — sobrerun/ahorro esperado al cierre
- CV (Cost Variance): EV − AC
- SV (Schedule Variance): EV − PV

COSTOS:
- Presupuesto original total (BAC)
- Costo real acumulado
- Costo/m² presupuestado vs. real
- Desviación de costo %
- Costo directo (mano de obra, materiales, equipo)
- Costo indirecto (generales, honorarios, imprevistos)
- Retenciones pendientes por cobrar/pagar a contratistas

MÁRGENES:
- Margen bruto % = (ingresos − costo directo) / ingresos
- Margen neto % = (ingresos − costo total) / ingresos

FLUJO DE CAJA:
- Flujo de caja del período (entradas − salidas)
- Flujo de caja acumulado
- Consumo de presupuesto % (costo real / presupuesto total)
- Máxima exposición de caja (pico de inversión requerida)

Al analizar, presenta tu respuesta en secciones claramente marcadas con:
[SECCIÓN: nombre] para encabezados
[ALERTA CRÍTICA] / [ALERTA MEDIA] / [ALERTA BAJA] para alertas
[OK] para elementos sin problemas
[ACCIÓN] para recomendaciones específicas

Sé directo, usa números concretos, y da recomendaciones accionables. Responde en español."""


def build_system_prompt(thresholds: dict = None) -> str:
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    return SYSTEM_PROMPT + f"""

UMBRALES CONFIGURADOS:
- Desviación de costo: >{t['thr_costo']}% → alerta
- Margen neto mínimo aceptable: <{t['thr_margen']}% → alerta crítica
- Diferencia avance físico vs. financiero: >{t['thr_curvas']}% → alerta
- CPI por debajo de: {t['thr_cpi']} → alerta (proyecto sobre presupuesto)
- SPI por debajo de: {t['thr_spi']} → alerta (proyecto retrasado)
- Días de retraso: >{t['thr_retraso']} días → alerta"""


def run(
    data: str,
    context: str = "",
    thresholds: dict = None,
    stream: bool = True,
    structured: bool = False,
):
    """
    Run the construction monitoring agent.

    Args:
        data: Raw construction project data (CSV, text, or structured content).
              Should include as many of these fields as available per project:
              avance físico %, avance financiero %, costo/m² real vs presupuestado,
              EV, PV, AC, presupuesto total, margen, flujo de caja, retenciones,
              fecha inicio, fecha programada de terminación.
        context: Optional additional context for the analysis.
        thresholds: Optional dict to override default alert thresholds.
        stream: If True, stream output to stdout (ignored when structured=True).
        structured: If True, return a parsed JSON dict instead of free text.

    Returns:
        - structured=True  → dict with projects, alerts, and executive summary.
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
    user_prompt += "TIPO DE ANÁLISIS: Solo Proyectos de Obra\n\n"
    user_prompt += f"=== DATOS DE PROYECTOS DE OBRA ===\n{data}\n\n"
    user_prompt += (
        "\nGenera el análisis completo por proyecto incluyendo: EVM (CPI, SPI, EAC, VAC), "
        "desviaciones de costo, estado de avance físico vs. financiero, flujo de caja, "
        "márgenes, retenciones y recomendaciones accionables priorizadas."
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
        "Proyectos:\n"
        "- Torre Cumbres: residencial 120 deptos, presupuesto $145M MXN, "
        "avance físico 78%, avance financiero 74%, AC $108.5M, EV $113.1M, PV $107.3M, "
        "costo/m² real $19,180 vs $18,400 presupuestado, desviación +4.2%, "
        "margen bruto 22.1%, margen neto 16.8%, flujo período -$3.2M, "
        "retenciones pendientes $8.4M, días de retraso: 0\n"
        "- Resi. Bosques: residencial 48 casas, presupuesto $62M MXN, "
        "avance físico 41%, avance financiero 49%, AC $30.4M, EV $25.4M, PV $28.0M, "
        "costo/m² real $28,600 vs $26,400 presupuestado, desviación +8.2%, "
        "margen bruto 14.3%, margen neto 9.1%, flujo período -$6.1M, "
        "retenciones pendientes $4.2M, días de retraso: 22\n"
    )
    run(sample_data)
