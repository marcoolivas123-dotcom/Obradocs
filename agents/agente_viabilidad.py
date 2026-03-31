"""
Agente de Viabilidad — ObraDocs
Performs ultra-detailed real estate project viability analysis with financial modeling.
Returns a structured JSON report across 6 evaluation dimensions.
"""

import json
import anthropic

SYSTEM_PROMPT = """Eres el Agente de Viabilidad de ObraDocs, un experto analista financiero \
inmobiliario con 20 años de experiencia en el mercado mexicano (CDMX, GDM, MTY, QRO y principales \
ciudades).

Tu tarea es analizar la viabilidad de proyectos inmobiliarios y de construcción con rigor \
profesional. Conoces profundamente: tasas hipotecarias mexicanas, costos de construcción por \
región, velocidades de absorción por segmento, marco legal (uso de suelo CDMX, SEDESOL, \
NOM-001-CONAVI), financiamiento bancario e infonavit, impacto de inflación en costos de \
materiales, y los principales riesgos del sector constructor en México 2024-2025.

IMPORTANTE: Responde ÚNICAMENTE con un objeto JSON válido, sin backticks, sin markdown, sin texto \
antes o después. El JSON debe tener EXACTAMENTE esta estructura:

{
  "viabilidad_score": número del 0 al 100,
  "semaforo": "Verde" | "Amarillo" | "Rojo",
  "veredicto_titulo": "título ejecutivo corto de 5-8 palabras",
  "veredicto_resumen": "2-3 oraciones de diagnóstico general del proyecto",
  "kpis": {
    "roi": "XX%",
    "tir": "XX%",
    "margen_bruto": "XX%",
    "margen_neto": "XX%",
    "payback": "XX meses",
    "ingresos_totales": número en MXN,
    "costo_total": número en MXN,
    "utilidad": número en MXN,
    "punto_equilibrio": "XX% de ventas"
  },
  "dimensiones": {
    "financiera":  { "score": 0-100, "analisis": "análisis de 2-3 oraciones" },
    "mercado":     { "score": 0-100, "analisis": "análisis de 2-3 oraciones" },
    "tecnica":     { "score": 0-100, "analisis": "análisis de 2-3 oraciones" },
    "legal":       { "score": 0-100, "analisis": "análisis de 2-3 oraciones" },
    "ambiental":   { "score": 0-100, "analisis": "análisis de 2-3 oraciones" },
    "comercial":   { "score": 0-100, "analisis": "análisis de 2-3 oraciones" }
  },
  "escenarios": {
    "optimista":  { "roi": "XX%", "ingresos": número, "margen": "XX%", "payback": "XX meses", "conclusion": "1-2 oraciones" },
    "base":       { "roi": "XX%", "ingresos": número, "margen": "XX%", "payback": "XX meses", "conclusion": "1-2 oraciones" },
    "pesimista":  { "roi": "XX%", "ingresos": número, "margen": "XX%", "payback": "XX meses", "conclusion": "1-2 oraciones" }
  },
  "riesgos": [
    { "categoria": "nombre", "nivel": "Alto|Medio|Bajo", "descripcion": "descripción concisa", "mitigacion": "acción de mitigación" }
  ],
  "recomendaciones": ["recomendación 1", "recomendación 2", "..."],
  "conclusion_ejecutiva": "párrafo ejecutivo de 4-6 oraciones con el veredicto final, los factores decisivos y las condiciones bajo las cuales el proyecto es recomendable o no"
}

Si faltan datos críticos, haz supuestos razonables basados en promedios del mercado mexicano y \
menciónalos en el análisis. Siempre calcula los KPIs aunque sea con estimaciones."""


def run(project_data: str) -> dict:
    """
    Run the viability analysis agent on a real estate project.

    Args:
        project_data: Project description — can be free-form text or structured fields
                      (e.g. type, city, units, land area, construction cost, sale price, etc.)

    Returns:
        Parsed JSON dict with the full viability report.

    Raises:
        ValueError: If the API response cannot be parsed as valid JSON.
    """
    client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Analiza la viabilidad del siguiente proyecto inmobiliario:\n\n{project_data}",
            }
        ],
    )

    raw = message.content[0].text.strip()
    # Strip accidental markdown fences
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent returned invalid JSON: {exc}\n\nRaw output:\n{raw}") from exc


def print_report(report: dict) -> None:
    """Pretty-print the viability report to stdout."""
    semaforo_emoji = {"Verde": "🟢", "Amarillo": "🟡", "Rojo": "🔴"}.get(
        report.get("semaforo", ""), "⚪"
    )
    score = report.get("viabilidad_score", "N/A")
    titulo = report.get("veredicto_titulo", "")
    resumen = report.get("veredicto_resumen", "")

    print(f"\n{'='*60}")
    print(f"  {semaforo_emoji}  VIABILIDAD: {score}/100 — {titulo}")
    print(f"{'='*60}")
    print(f"\n{resumen}\n")

    kpis = report.get("kpis", {})
    if kpis:
        print("── KPIs ──────────────────────────────────────────────")
        for k, v in kpis.items():
            print(f"  {k:<22} {v}")

    dims = report.get("dimensiones", {})
    if dims:
        print("\n── Dimensiones ───────────────────────────────────────")
        for name, d in dims.items():
            bar = "█" * (d["score"] // 10) + "░" * (10 - d["score"] // 10)
            print(f"  {name.capitalize():<12} [{bar}] {d['score']}/100")

    conclusion = report.get("conclusion_ejecutiva", "")
    if conclusion:
        print(f"\n── Conclusión Ejecutiva ──────────────────────────────")
        print(f"  {conclusion}\n")


if __name__ == "__main__":
    # Example project (residential, Querétaro)
    sample_project = """
Nombre: Torre Insurgentes QRO
Tipo: Residencial medio
Ciudad: Querétaro, QRO
Unidades: 80 departamentos
Plazo de construcción: 24 meses
Superficie de terreno: 2,200 m²
Superficie construida total: 9,600 m²
Superficie vendible: 7,800 m²
Costo de terreno: $18,000,000 MXN
Costo de construcción: $14,500 / m²
Costos indirectos: 18% del costo directo
Precio de venta promedio: $42,000 / m²
Precio de mercado zona: $39,000 / m²
Financiamiento bancario: 50% del proyecto
Velocidad de absorción esperada: 4 unidades/mes
Proyectos competidores en radio 1 km: 3
Uso de suelo: Habitacional Plurifamiliar
"""
    report = run(sample_project)
    print_report(report)
