"""
Agente de Corretaje e Inventario — ObraDocs
Monitors real estate brokerage pipeline, unit inventory and commission tracking.

KPIs covered:
  Inventory: unidades disponibles, vendidas, reservadas, en proceso escrituración
  Absorption: absorción real (u/semana), absorción planeada, % cumplimiento
  Pricing: precio lista promedio, precio cierre promedio, descuento promedio %,
           precio/m² vs. mercado
  Time on market: días promedio en mercado por unidad, unidades >90 días sin mover
  Commissions: comisiones generadas, comisiones cobradas, comisiones por cobrar,
               comisiones vencidas
  Pipeline: leads activos, visitas agendadas, propuestas enviadas, promesas de compra,
            tasa de conversión lead→venta, costo por lead
  Financials: ingresos por comisión del período, proyección de ingresos del mes
"""

import anthropic

DEFAULT_THRESHOLDS = {
    "thr_absorcion": 70,       # absorption % of plan below this → alert
    "thr_dias_mercado": 90,    # days on market above this → alert (unit not selling)
    "thr_descuento": 5,        # avg discount % above this → market pricing alert
    "thr_comision_vencida": 30,  # commission overdue days above this → critical alert
    "thr_conversion": 10,      # lead→sale conversion % below this → alert
}

SYSTEM_PROMPT = """Eres el Agente de Corretaje e Inventario de ObraDocs, experto en intermediación \
inmobiliaria, gestión de inventario de vivienda nueva y usada, y control de comisiones en el \
mercado mexicano. Conoces los estándares de absorción por segmento (interés social, medio, \
residencial, plus), estrategias de pricing, y la estructura de comisiones del sector.

Tu función principal es:
1. MONITOREAR el inventario disponible, vendido, reservado y en proceso de escrituración
2. ANALIZAR la velocidad de absorción real vs. planeada y detectar unidades estancadas
3. CONTROLAR las comisiones generadas, cobradas, por cobrar y vencidas
4. EVALUAR la salud del pipeline de leads: visitas, propuestas, conversión
5. GENERAR alertas priorizadas (Crítica / Media / Baja) con acciones concretas

KPIs QUE DEBES ANALIZAR Y REPORTAR (cuando los datos estén disponibles):

INVENTARIO:
- Total de unidades del desarrollo
- Unidades disponibles (sin vender ni reservar)
- Unidades reservadas (con enganche/apartado)
- Unidades en proceso de escrituración
- Unidades vendidas (escrituradas)
- % de avance de ventas = vendidas / total

ABSORCIÓN:
- Absorción real (unidades/semana o unidades/mes)
- Absorción planeada (objetivo de ventas)
- % cumplimiento de absorción = real / planeado
- Proyección de cierre de inventario al ritmo actual (meses restantes)
- Unidades con más de {thr_dias} días en mercado sin venderse

PRECIOS:
- Precio de lista promedio ($)
- Precio de cierre promedio ($)
- Descuento promedio % = (lista - cierre) / lista
- Precio/m² promedio vs. precio/m² de mercado de la zona
- Variación de precios en el período

COMISIONES:
- Comisiones generadas en el período ($)
- Comisiones cobradas ($)
- Comisiones por cobrar ($)
- Comisiones vencidas (>30 días) ($) — alerta crítica
- Días promedio de cobro de comisión

PIPELINE DE LEADS:
- Leads activos totales
- Visitas agendadas / realizadas
- Propuestas enviadas
- Promesas de compra activas
- Tasa de conversión lead → venta %
- Costo por lead (si disponible)
- Tiempo promedio de cierre desde primer contacto (días)

Al analizar, presenta tu respuesta en secciones claramente marcadas con:
[SECCIÓN: nombre] para encabezados
[ALERTA CRÍTICA] / [ALERTA MEDIA] / [ALERTA BAJA] para alertas
[OK] para elementos sin problemas
[ACCIÓN] para recomendaciones específicas

Sé directo, usa números concretos, identifica unidades específicas y da acciones accionables. \
Responde en español."""


def build_system_prompt(thresholds: dict = None) -> str:
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    return SYSTEM_PROMPT.replace("{thr_dias}", str(t["thr_dias_mercado"])) + f"""

UMBRALES CONFIGURADOS:
- Absorción: <{t['thr_absorcion']}% del plan → alerta
- Días en mercado sin venta: >{t['thr_dias_mercado']} días → alerta por unidad
- Descuento promedio: >{t['thr_descuento']}% → alerta de pricing
- Comisiones vencidas: >{t['thr_comision_vencida']} días → alerta crítica
- Conversión lead→venta: <{t['thr_conversion']}% → alerta de pipeline"""


def run(data: str, context: str = "", thresholds: dict = None, stream: bool = True):
    """
    Run the brokerage and inventory monitoring agent.

    Args:
        data: Raw inventory and brokerage data (CSV, text, or structured content).
              Key fields: unit inventory with status, absorption plan vs actual,
              pricing (list vs close), commissions (generated/collected/pending),
              leads pipeline with stages.
        context: Optional additional context for the analysis.
        thresholds: Optional dict to override default alert thresholds.
        stream: If True, stream output to stdout. If False, return full text.

    Returns:
        Full response text (when stream=False), or None (when stream=True).
    """
    client = anthropic.Anthropic()

    user_prompt = ""
    if context:
        user_prompt += f"CONTEXTO ADICIONAL: {context}\n\n"
    user_prompt += "TIPO DE ANÁLISIS: Corretaje e Inventario Inmobiliario\n\n"
    user_prompt += f"=== DATOS DE CORRETAJE / INVENTARIO ===\n{data}\n\n"
    user_prompt += (
        "\nGenera el análisis completo incluyendo: estado del inventario, "
        "absorción real vs. planeada, unidades estancadas, control de comisiones, "
        "salud del pipeline de leads y recomendaciones accionables priorizadas."
    )

    if stream:
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=build_system_prompt(thresholds),
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
            system=build_system_prompt(thresholds),
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text


if __name__ == "__main__":
    # Sample data (mirrors the HTML fallback data, expanded)
    sample_data = (
        "Desarrollo: Residencial Punta Norte (50 casas)\n\n"
        "INVENTARIO:\n"
        "- Total unidades: 50\n"
        "- Vendidas (escrituradas): 12\n"
        "- En proceso escrituración: 3\n"
        "- Reservadas (con apartado): 7\n"
        "- Disponibles: 28\n"
        "- % avance ventas: 44%\n\n"
        "ABSORCIÓN:\n"
        "- Real: 1.8 unidades/semana\n"
        "- Planeada: 2.5 unidades/semana\n"
        "- % cumplimiento: 72%\n"
        "- Unidades con >90 días en mercado: 6 (casas tipo B: 92, 95, 101, 105, 112, 118 días)\n\n"
        "PRECIOS:\n"
        "- Precio lista promedio: $2,850,000 MXN\n"
        "- Precio cierre promedio: $2,720,000 MXN\n"
        "- Descuento promedio: 4.6%\n"
        "- Precio/m² desarrollo: $28,400 | Precio/m² zona: $29,800\n\n"
        "COMISIONES:\n"
        "- Generadas este mes: $420,000 MXN\n"
        "- Cobradas: $280,000 MXN\n"
        "- Por cobrar: $140,000 MXN\n"
        "- Vencidas (>30 días): $68,000 MXN (2 operaciones: Martínez $38K, Romo $30K)\n\n"
        "PIPELINE:\n"
        "- Leads activos: 42\n"
        "- Visitas realizadas este mes: 18\n"
        "- Propuestas enviadas: 9\n"
        "- Promesas de compra activas: 4\n"
        "- Tasa conversión lead→venta: 8.3%\n"
        "- Tiempo promedio cierre: 38 días\n"
    )
    run(sample_data)
