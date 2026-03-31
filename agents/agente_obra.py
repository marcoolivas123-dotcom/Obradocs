"""
Agente de Monitoreo de Obra — ObraDocs
Monitors construction project KPIs and generates prioritized alerts.
"""

import anthropic

DEFAULT_THRESHOLDS = {
    "thr_costo": 5,       # % cost deviation threshold
    "thr_margen": 12,     # minimum net margin %
    "thr_curvas": 5,      # physical vs financial progress diff %
}

SYSTEM_PROMPT = """Eres el Agente de Monitoreo de Obra de ObraDocs, experto en control financiero \
de proyectos de construcción e inmobiliarios en México, con conocimiento profundo de KPIs de obra: \
avance físico, avance financiero, curva S, desviaciones de costo, margen neto y análisis de riesgo.

Tu función principal es:
1. MONITOREAR datos de proyectos de construcción
2. DETECTAR desviaciones de costo, retrasos y riesgos en los KPIs de obra
3. GENERAR alertas priorizadas (Crítica / Media / Baja) con acciones específicas
4. PRODUCIR reportes ejecutivos claros y accionables

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
- Desviación de costo en obra: >{t['thr_costo']}% → alerta
- Margen neto mínimo aceptable: <{t['thr_margen']}% → alerta crítica
- Diferencia avance físico vs. financiero: >{t['thr_curvas']}% → alerta"""


def run(data: str, context: str = "", thresholds: dict = None, stream: bool = True):
    """
    Run the construction monitoring agent.

    Args:
        data: Raw construction project data (CSV, text, or structured content).
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
    user_prompt += "TIPO DE ANÁLISIS: Solo Proyectos de Obra\n\n"
    user_prompt += f"=== DATOS DE PROYECTOS DE OBRA ===\n{data}\n\n"
    user_prompt += (
        "\nGenera el análisis completo con alertas priorizadas, KPIs clave "
        "y recomendaciones accionables para cada proyecto."
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
        "Proyectos:\n"
        "- Torre Cumbres: residencial 120 deptos, avance físico 78%, avance financiero 74%, "
        "costo/m² $19,180 vs $18,400 presupuestado, desviación +4.2%, margen 16.8%\n"
        "- Resi. Bosques: residencial 48 casas, avance físico 41%, avance financiero 49%, "
        "costo/m² $28,600 vs $26,400 presupuestado, desviación +8.2%, margen 9.1%\n"
    )
    run(sample_data)
