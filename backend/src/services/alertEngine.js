/**
 * Alert Engine — Genera alertas y desviaciones automáticas
 * basándose en umbrales configurables y benchmarks de industria
 */

const DEFAULT_THRESHOLDS = {
  margen_neto_critico: 5,
  margen_neto_atencion: 15,
  margen_bruto_critico: 10,
  margen_bruto_atencion: 25,
  costos_sobre_ingresos_critico: 85,
  flujo_negativo: 0,
  crecimiento_critico: -10,
  crecimiento_atencion: -5,
  concentracion_clientes: 60,
  // Industry-specific
  food_cost_critico: 35,
  food_cost_atencion: 30,
  labor_cost_critico: 35,
  labor_cost_atencion: 28,
  rotacion_inventario_min: 4,
};

/**
 * Genera alertas a partir de los KPIs calculados
 */
function generateAlerts(kpis, industry, customThresholds) {
  const thresholds = { ...DEFAULT_THRESHOLDS, ...customThresholds };
  const alerts = [];

  for (const kpi of kpis) {
    const kpiAlerts = evaluateKpi(kpi, thresholds, industry);
    alerts.push(...kpiAlerts);
  }

  // Alertas cruzadas (relaciones entre KPIs)
  alerts.push(...crossAnalysis(kpis, thresholds));

  // Ordenar por severidad: critical > warning > positive
  const severityOrder = { critical: 0, warning: 1, positive: 2 };
  alerts.sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);

  return alerts;
}

/**
 * Evalúa un KPI individual contra los umbrales
 */
function evaluateKpi(kpi, thresholds, industry) {
  const alerts = [];
  const nombre = kpi.nombre.toLowerCase();
  const valor = kpi.valor;

  // Margen Neto
  if (nombre.includes('margen neto')) {
    if (valor < 0) {
      alerts.push({
        severity: 'critical',
        title: 'Margen neto negativo',
        description: `Tu margen neto es ${kpi.valor_formateado}. Estás perdiendo dinero en cada venta.`,
        impact: 'El negocio no es sostenible con márgenes negativos. Cada mes que pase así erosiona tu capital.',
        action: 'Revisa tu estructura de costos de inmediato. Identifica los 3 gastos más grandes y negocia o elimina al menos uno esta semana.',
        kpi_name: kpi.nombre,
      });
    } else if (valor < thresholds.margen_neto_critico) {
      alerts.push({
        severity: 'critical',
        title: `Margen neto peligrosamente bajo: ${kpi.valor_formateado}`,
        description: `Tu margen neto es ${kpi.valor_formateado}, por debajo del mínimo recomendado (${thresholds.margen_neto_critico}%).`,
        impact: 'Con un margen tan bajo, cualquier imprevisto (aumento de costos, baja en ventas) puede llevarte a pérdidas.',
        action: 'Enfócate en dos frentes: sube precios donde el mercado lo permita y reduce costos variables en al menos 5%.',
        kpi_name: kpi.nombre,
      });
    } else if (valor < thresholds.margen_neto_atencion) {
      alerts.push({
        severity: 'warning',
        title: `Margen neto por debajo del benchmark: ${kpi.valor_formateado}`,
        description: `Tu margen neto es ${kpi.valor_formateado}. El promedio saludable para tu industria está arriba de ${thresholds.margen_neto_atencion}%.`,
        impact: 'Tienes poco margen de maniobra ante cambios en el mercado o costos inesperados.',
        action: 'Analiza tus productos/servicios más rentables y enfoca tu esfuerzo comercial ahí.',
        kpi_name: kpi.nombre,
      });
    } else {
      alerts.push({
        severity: 'positive',
        title: `Margen neto saludable: ${kpi.valor_formateado}`,
        description: `Tu margen neto de ${kpi.valor_formateado} está por encima del promedio de la industria.`,
        impact: 'Buen indicador de salud financiera. Tienes espacio para reinvertir o amortiguar imprevistos.',
        action: 'Considera destinar parte del excedente a un fondo de reserva o a crecimiento.',
        kpi_name: kpi.nombre,
      });
    }
  }

  // Flujo de Caja
  if (nombre.includes('flujo') && nombre.includes('caja')) {
    if (valor < 0) {
      alerts.push({
        severity: 'critical',
        title: `Flujo de caja negativo: ${kpi.valor_formateado}`,
        description: `Estás gastando más de lo que ingresa. Flujo operativo: ${kpi.valor_formateado}.`,
        impact: 'Si continúa, en pocas semanas no tendrás liquidez para operar. Nómina y proveedores en riesgo.',
        action: 'Acelera cobros pendientes, negocia plazos con proveedores y frena cualquier gasto no esencial hoy.',
        kpi_name: kpi.nombre,
      });
    }
  }

  // EBITDA
  if (nombre.includes('ebitda') && valor < 0) {
    alerts.push({
      severity: 'critical',
      title: `EBITDA negativo: ${kpi.valor_formateado}`,
      description: `Tu EBITDA es ${kpi.valor_formateado}. La operación del negocio no genera valor.`,
      impact: 'El negocio destruye valor antes de considerar financiamiento e impuestos.',
      action: 'Revisa si puedes reducir gastos operativos o si necesitas reestructurar el modelo de negocio.',
      kpi_name: kpi.nombre,
    });
  }

  // Crecimiento de Ingresos
  if (nombre.includes('crecimiento') && kpi.variacion !== null) {
    if (valor < thresholds.crecimiento_critico) {
      alerts.push({
        severity: 'critical',
        title: `Caída fuerte en ingresos: ${kpi.valor_formateado}`,
        description: `Los ingresos cayeron ${kpi.valor_formateado} vs. el período anterior.`,
        impact: 'Una caída de más del 10% puede indicar pérdida de clientes o problemas de mercado serios.',
        action: 'Habla con tus 5 clientes principales esta semana. Identifica si hay un problema recurrente.',
        kpi_name: kpi.nombre,
      });
    } else if (valor < thresholds.crecimiento_atencion) {
      alerts.push({
        severity: 'warning',
        title: `Ingresos a la baja: ${kpi.valor_formateado}`,
        description: `Los ingresos disminuyeron ${kpi.valor_formateado} vs. el período anterior.`,
        impact: 'Tendencia negativa que si no se revierte, podría comprometer la rentabilidad.',
        action: 'Revisa tu embudo de ventas y evalúa si necesitas reforzar la prospección.',
        kpi_name: kpi.nombre,
      });
    }
  }

  // Food Cost (Restaurantes)
  if (nombre.includes('food cost')) {
    if (valor > thresholds.food_cost_critico) {
      alerts.push({
        severity: 'critical',
        title: `Food cost fuera de control: ${kpi.valor_formateado}`,
        description: `Tu costo de alimentos es ${kpi.valor_formateado}, muy por encima del máximo recomendado (${thresholds.food_cost_critico}%).`,
        impact: 'Estás dejando muy poco margen para cubrir nómina, renta y utilidad.',
        action: 'Renegocia con proveedores, revisa porciones y elimina platillos con margen negativo.',
        kpi_name: kpi.nombre,
      });
    }
  }

  // Rotación de inventario (Retail)
  if (nombre.includes('rotación') && nombre.includes('inventario')) {
    if (valor < thresholds.rotacion_inventario_min) {
      alerts.push({
        severity: 'warning',
        title: `Inventario estancado: rotación ${kpi.valor_formateado}`,
        description: `Tu inventario solo rota ${kpi.valor_formateado}. Lo ideal es 8+ veces al año.`,
        impact: 'Capital atrapado en mercancía que no se vende. Riesgo de obsolescencia y merma.',
        action: 'Identifica los productos con menor rotación y lanza promociones para moverlos. Ajusta tu compra.',
        kpi_name: kpi.nombre,
      });
    }
  }

  return alerts;
}

/**
 * Análisis cruzado entre múltiples KPIs
 */
function crossAnalysis(kpis, thresholds) {
  const alerts = [];
  const kpiMap = {};
  for (const kpi of kpis) {
    kpiMap[kpi.nombre.toLowerCase()] = kpi;
  }

  // Costos vs Ingresos
  const ingresos = kpiMap['ingresos totales'];
  const costos = kpiMap['costo de ventas'];
  if (ingresos && costos && ingresos.valor > 0) {
    const ratio = (costos.valor / ingresos.valor) * 100;
    if (ratio > thresholds.costos_sobre_ingresos_critico) {
      alerts.push({
        severity: 'critical',
        title: `Costos consumen el ${ratio.toFixed(0)}% de los ingresos`,
        description: `El costo de ventas representa ${ratio.toFixed(1)}% de tus ingresos (umbral: ${thresholds.costos_sobre_ingresos_critico}%).`,
        impact: 'Apenas queda margen para cubrir gastos fijos. El negocio opera al límite.',
        action: 'Es urgente renegociar con proveedores o revisar tu estrategia de precios.',
      });
    }
  }

  // Punto de equilibrio vs ingresos actuales
  const pe = kpiMap['punto de equilibrio'];
  if (pe && ingresos) {
    const cobertura = ((ingresos.valor / pe.valor) * 100).toFixed(0);
    if (ingresos.valor < pe.valor) {
      alerts.push({
        severity: 'critical',
        title: `Por debajo del punto de equilibrio`,
        description: `Tus ingresos (${ingresos.valor_formateado}) están por debajo del punto de equilibrio (${pe.valor_formateado}). Cubres solo el ${cobertura}%.`,
        impact: 'No estás generando suficientes ingresos para cubrir tus costos fijos.',
        action: `Necesitas vender ${pe.valor_formateado} mínimo para no perder. Busca cómo incrementar volumen o precio.`,
      });
    } else if (ingresos.valor < pe.valor * 1.2) {
      alerts.push({
        severity: 'warning',
        title: `Muy cerca del punto de equilibrio`,
        description: `Tus ingresos superan el punto de equilibrio por solo ${(((ingresos.valor / pe.valor) - 1) * 100).toFixed(0)}%.`,
        impact: 'Cualquier variación en ventas o costos puede dejarte por debajo.',
        action: 'Trabaja en aumentar tu margen de seguridad. Meta: superar el PE por al menos 30%.',
      });
    }
  }

  return alerts;
}

module.exports = { generateAlerts, DEFAULT_THRESHOLDS };
