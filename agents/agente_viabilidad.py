"""
Agente de Viabilidad — ObraDocs
Performs ultra-detailed real estate project viability analysis with financial modeling.
Returns a structured JSON report across 6 evaluation dimensions.

KPIs covered in the JSON output:
  Financial: ROI, TIR, VPN, margen bruto, margen neto, payback, ingresos totales,
             costo total, utilidad neta, punto de equilibrio, costo financiero total,
             max exposición de caja, relación deuda/capital
  Market: precio/m², absorción mensual, tiempo de comercialización, unidades disponibles
  Structure: superficie vendible, costo/m² construcción, costo terreno como % del total
  Scenarios (optimista/base/pesimista): ROI, TIR, ingresos, margen neto, payback, utilidad
  Risks: categoría, nivel, probabilidad, descripción, mitigación, impacto financiero
  Dimensions (6): financiera, mercado, técnica, legal, ambiental, comercial
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
    "vpn": número en MXN (Valor Presente Neto a tasa de descuento de mercado),
    "margen_bruto": "XX%",
    "margen_neto": "XX%",
    "payback": "XX meses",
    "ingresos_totales": número en MXN,
    "costo_total": número en MXN,
    "utilidad_neta": número en MXN,
    "punto_equilibrio": "XX% de ventas",
    "unidades_equilibrio": número (unidades mínimas a vender para cubrir costos),
    "costo_financiero_total": número en MXN,
    "max_exposicion_caja": número en MXN (pico máximo de inversión requerida),
    "deuda_capital_ratio": "X:1",
    "precio_promedio_m2": número en MXN,
    "costo_construccion_m2": número en MXN,
    "superficie_vendible_m2": número,
    "absorcion_mensual": número (unidades/mes),
    "tiempo_comercializacion": "XX meses",
    "terreno_pct_costo_total": "XX%"
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
    "optimista": {
      "descripcion": "supuestos clave del escenario (precio +X%, absorción +Y u/mes, costo -Z%)",
      "roi": "XX%",
      "tir": "XX%",
      "ingresos": número en MXN,
      "utilidad": número en MXN,
      "margen_neto": "XX%",
      "payback": "XX meses",
      "conclusion": "1-2 oraciones"
    },
    "base": {
      "descripcion": "supuestos del escenario base",
      "roi": "XX%",
      "tir": "XX%",
      "ingresos": número en MXN,
      "utilidad": número en MXN,
      "margen_neto": "XX%",
      "payback": "XX meses",
      "conclusion": "1-2 oraciones"
    },
    "pesimista": {
      "descripcion": "supuestos del escenario pesimista (precio -X%, absorción -Y u/mes, costo +Z%)",
      "roi": "XX%",
      "tir": "XX%",
      "ingresos": número en MXN,
      "utilidad": número en MXN,
      "margen_neto": "XX%",
      "payback": "XX meses",
      "conclusion": "1-2 oraciones"
    }
  },

  "riesgos": [
    {
      "categoria": "nombre del riesgo",
      "nivel": "Alto|Medio|Bajo",
      "probabilidad": "Alta|Media|Baja",
      "descripcion": "descripción concisa del riesgo",
      "impacto_financiero": "impacto estimado en MXN o % de margen",
      "mitigacion": "acción concreta de mitigación"
    }
  ],

  "recomendaciones": ["recomendación 1", "recomendación 2", "..."],

  "conclusion_ejecutiva": "párrafo ejecutivo de 4-6 oraciones con el veredicto final, los KPIs \
decisivos (ROI, TIR, VPN, margen), las condiciones bajo las cuales el proyecto es recomendable o \
no, y los riesgos principales a gestionar"
}

Si faltan datos críticos, haz supuestos razonables basados en promedios del mercado mexicano y \
menciónalos en el análisis. Siempre calcula todos los KPIs aunque sea con estimaciones. \
La tasa de descuento para el VPN debe reflejar el costo de capital del mercado inmobiliario \
mexicano (típicamente 12-18% anual dependiendo del segmento)."""


def run(project_data: str) -> dict:
    """
    Run the viability analysis agent on a real estate project.

    Args:
        project_data: Project description — can be free-form text or structured fields.
                      Key inputs: project type, city, # units, land area (m²),
                      total built area (m²), saleable area (m²), land cost,
                      construction cost/m², indirect costs %, avg sale price/m²,
                      market price/m², bank financing %, expected absorption (units/month),
                      construction timeline (months), competing projects nearby, zoning.

    Returns:
        Parsed JSON dict with the full viability report.

    Raises:
        ValueError: If the API response cannot be parsed as valid JSON.
    """
    client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
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
            print(f"  {k:<30} {v}")

    dims = report.get("dimensiones", {})
    if dims:
        print("\n── Dimensiones ───────────────────────────────────────")
        for name, d in dims.items():
            bar = "█" * (d["score"] // 10) + "░" * (10 - d["score"] // 10)
            print(f"  {name.capitalize():<12} [{bar}] {d['score']}/100")

    escenarios = report.get("escenarios", {})
    if escenarios:
        print("\n── Escenarios ────────────────────────────────────────")
        for name, s in escenarios.items():
            print(f"  {name.upper():<12} ROI {s.get('roi','?')}  TIR {s.get('tir','?')}  "
                  f"Margen {s.get('margen_neto','?')}  Payback {s.get('payback','?')}")

    riesgos = report.get("riesgos", [])
    if riesgos:
        print("\n── Riesgos ───────────────────────────────────────────")
        for r in riesgos:
            print(f"  [{r.get('nivel','?')}] {r.get('categoria','?')} "
                  f"(prob. {r.get('probabilidad','?')}) — {r.get('descripcion','')}")

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
