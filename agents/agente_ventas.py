"""
Agente de Monitoreo de Ventas — ObraDocs
Monitors SaaS product CRM deals and generates follow-up alerts.
"""

import anthropic

DEFAULT_THRESHOLDS = {
    "thr_margen": 12,   # minimum net margin %
    "thr_deal": 14,     # days without activity on a deal before alert
}

SYSTEM_PROMPT = """Eres el Agente de Monitoreo de Ventas de ObraDocs, experto en CRM y ventas de \
productos SaaS para el sector construcción e inmobiliario en México. Analizas pipelines de venta, \
tasas de conversión, actividad de deals y métricas de cuota para identificar riesgos y oportunidades.

Tu función principal es:
1. MONITOREAR el CRM de ventas del producto SaaS
2. DETECTAR deals estancados, riesgos de pérdida y oportunidades de cierre
3. GENERAR alertas priorizadas (Crítica / Media / Baja) con acciones de seguimiento concretas
4. PRODUCIR reportes ejecutivos del estado del pipeline y proyección de cierre

Al analizar, presenta tu respuesta en secciones claramente marcadas con:
[SECCIÓN: nombre] para encabezados
[ALERTA CRÍTICA] / [ALERTA MEDIA] / [ALERTA BAJA] para alertas
[OK] para elementos sin problemas
[ACCIÓN] para recomendaciones específicas de seguimiento

Sé directo, usa números concretos, y da acciones específicas por deal. Responde en español."""


def build_system_prompt(thresholds: dict = None) -> str:
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    return SYSTEM_PROMPT + f"""

UMBRALES CONFIGURADOS:
- Margen neto mínimo aceptable: <{t['thr_margen']}% → alerta crítica
- Deal sin actividad: >{t['thr_deal']} días → requiere seguimiento inmediato"""


def run(data: str, context: str = "", thresholds: dict = None, stream: bool = True):
    """
    Run the sales CRM monitoring agent.

    Args:
        data: Raw CRM deal data (CSV, text, or structured content).
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
    user_prompt += "TIPO DE ANÁLISIS: Solo Ventas del Producto SaaS\n\n"
    user_prompt += f"=== DATOS DE CRM DE VENTAS ===\n{data}\n\n"
    user_prompt += (
        "\nGenera el análisis completo con alertas priorizadas, estado del pipeline, "
        "proyección de cuota y recomendaciones accionables por deal."
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
    # Example with sample data (mirrors the HTML fallback data)
    sample_data = (
        "Pipeline de ventas:\n"
        "- Total deals activos: 14\n"
        "- Deals sin actividad >14 días:\n"
        "  * Constructora López: $48,000 USD — última actividad hace 18 días\n"
        "  * Grupo Norte: $36,000 USD — última actividad hace 21 días\n"
        "  * Desarrollos Sonora: $28,000 USD — última actividad hace 15 días\n"
        "- Cuota mensual: 78% alcanzada (11 días restantes del mes)\n"
    )
    run(sample_data)
