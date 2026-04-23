/**
 * KPI Calculator Engine — Calcula KPIs universales y por industria
 * a partir de datos financieros estructurados.
 */

/**
 * Calcula todos los KPIs aplicables según la industria y los datos disponibles
 */
function calculateKpis(financialData, industry) {
  const kpis = [];

  // Extraer datos base
  const data = normalizeData(financialData);

  // KPIs universales
  kpis.push(...calculateUniversalKpis(data));

  // KPIs por industria
  const industryKpis = getIndustryCalculator(industry);
  if (industryKpis) {
    kpis.push(...industryKpis(data));
  }

  // Asignar semáforos
  return kpis.map((kpi) => ({
    ...kpi,
    status: kpi.status || assignStatus(kpi),
  }));
}

/**
 * Normaliza datos financieros a un formato estándar
 */
function normalizeData(financialData) {
  const data = {
    ingresos: 0,
    ingresos_anterior: null,
    costo_ventas: 0,
    gastos_operativos: 0,
    gastos_admin: 0,
    nomina: 0,
    depreciacion: 0,
    intereses: 0,
    impuestos: 0,
    deudas: 0,
    efectivo: 0,
    inventario: 0,
    cuentas_cobrar: 0,
    cuentas_pagar: 0,
    costos_fijos: 0,
    // Industry-specific
    empleados: 0,
    hectareas: 0,
    unidades_producidas: 0,
    m2_construidos: 0,
    horas_facturables: 0,
    unidades_flota: 0,
    habitaciones: 0,
    consultas: 0,
    tickets_dia: 0,
    costo_materiales: 0,
    km_recorridos: 0,
    combustible: 0,
    clientes_activos: 0,
  };

  if (Array.isArray(financialData)) {
    for (const item of financialData) {
      const key = mapCategoryToKey(item.category, item.subcategory, item.label);
      if (key && key in data) {
        data[key] = (data[key] || 0) + (item.amount || 0);
      }
    }
  } else if (typeof financialData === 'object') {
    Object.assign(data, financialData);
  }

  return data;
}

function mapCategoryToKey(category, subcategory, label) {
  const map = {
    ingresos: 'ingresos',
    ventas: 'ingresos',
    costos: 'costo_ventas',
    costo_ventas: 'costo_ventas',
    gastos_operativos: 'gastos_operativos',
    gastos: 'gastos_operativos',
    nomina: 'nomina',
    deudas: 'deudas',
    inventario: 'inventario',
    efectivo: 'efectivo',
  };
  const cat = (category || '').toLowerCase().replace(/\s+/g, '_');
  return map[cat] || null;
}

// ═══════════════════════════════════
// KPIs UNIVERSALES
// ═══════════════════════════════════

function calculateUniversalKpis(data) {
  const kpis = [];

  // Ingresos totales
  if (data.ingresos > 0) {
    const crecimiento =
      data.ingresos_anterior > 0
        ? ((data.ingresos - data.ingresos_anterior) / data.ingresos_anterior) * 100
        : null;

    kpis.push({
      nombre: 'Ingresos Totales',
      valor: data.ingresos,
      valor_formateado: formatCurrency(data.ingresos),
      valor_anterior: data.ingresos_anterior,
      variacion: crecimiento,
      categoria: 'ingresos',
      formula: 'Suma de todos los ingresos del período',
    });

    if (crecimiento !== null) {
      kpis.push({
        nombre: 'Crecimiento de Ingresos',
        valor: crecimiento,
        valor_formateado: formatPercent(crecimiento),
        valor_anterior: null,
        variacion: null,
        categoria: 'ingresos',
        formula: '(Ingresos actual - Ingresos anterior) / Ingresos anterior × 100',
      });
    }
  }

  // Margen bruto
  if (data.ingresos > 0 && data.costo_ventas >= 0) {
    const utilidadBruta = data.ingresos - data.costo_ventas;
    const margenBruto = (utilidadBruta / data.ingresos) * 100;

    kpis.push({
      nombre: 'Costo de Ventas',
      valor: data.costo_ventas,
      valor_formateado: formatCurrency(data.costo_ventas),
      valor_anterior: null,
      variacion: null,
      categoria: 'costos',
      formula: 'Suma de costos directos de ventas',
    });

    kpis.push({
      nombre: 'Margen Bruto',
      valor: margenBruto,
      valor_formateado: formatPercent(margenBruto),
      valor_anterior: null,
      variacion: null,
      categoria: 'rentabilidad',
      formula: '(Ingresos - Costo de Ventas) / Ingresos × 100',
    });
  }

  // Margen neto
  const gastosTotal = data.costo_ventas + data.gastos_operativos + data.gastos_admin + data.nomina;
  if (data.ingresos > 0 && gastosTotal > 0) {
    const utilidadNeta = data.ingresos - gastosTotal - data.intereses - data.impuestos;
    const margenNeto = (utilidadNeta / data.ingresos) * 100;

    kpis.push({
      nombre: 'Margen Neto',
      valor: margenNeto,
      valor_formateado: formatPercent(margenNeto),
      valor_anterior: null,
      variacion: null,
      categoria: 'rentabilidad',
      formula: '(Ingresos - Todos los gastos - Intereses - Impuestos) / Ingresos × 100',
    });
  }

  // EBITDA
  if (data.ingresos > 0) {
    const ebitda = data.ingresos - data.costo_ventas - data.gastos_operativos - data.gastos_admin - data.nomina + data.depreciacion;

    kpis.push({
      nombre: 'EBITDA',
      valor: ebitda,
      valor_formateado: formatCurrency(ebitda),
      valor_anterior: null,
      variacion: null,
      categoria: 'rentabilidad',
      formula: 'Ingresos - Costos operativos + Depreciación y amortización',
    });
  }

  // Punto de equilibrio
  const costosFijos = data.gastos_admin + data.nomina + data.depreciacion;
  if (data.ingresos > 0 && data.costo_ventas > 0 && costosFijos > 0) {
    const margenContribucion = 1 - data.costo_ventas / data.ingresos;
    if (margenContribucion > 0) {
      const puntoEquilibrio = costosFijos / margenContribucion;
      kpis.push({
        nombre: 'Punto de Equilibrio',
        valor: puntoEquilibrio,
        valor_formateado: formatCurrency(puntoEquilibrio),
        valor_anterior: null,
        variacion: null,
        categoria: 'rentabilidad',
        formula: 'Costos Fijos / (1 - Costo Variable / Ingresos)',
      });
    }
  }

  // Flujo de caja operativo (estimado)
  if (data.ingresos > 0) {
    const flujoCaja = data.ingresos - data.costo_ventas - data.gastos_operativos - data.nomina;
    kpis.push({
      nombre: 'Flujo de Caja Operativo',
      valor: flujoCaja,
      valor_formateado: formatCurrency(flujoCaja),
      valor_anterior: null,
      variacion: null,
      categoria: 'liquidez',
      formula: 'Ingresos - Costos de ventas - Gastos operativos - Nómina',
    });
  }

  return kpis;
}

// ═══════════════════════════════════
// KPIs POR INDUSTRIA
// ═══════════════════════════════════

function getIndustryCalculator(industry) {
  const normalized = (industry || '').toLowerCase();

  const calculators = {
    restaurante: restauranteKpis,
    alimentos: restauranteKpis,
    construccion: construccionKpis,
    inmobiliaria: construccionKpis,
    retail: retailKpis,
    comercio: retailKpis,
    manufactura: manufacturaKpis,
    maquiladora: manufacturaKpis,
    servicios: serviciosKpis,
    despacho: serviciosKpis,
    agricultura: agriculturaKpis,
    agroindustria: agriculturaKpis,
    transporte: transporteKpis,
    logistica: transporteKpis,
    hoteleria: hoteleriaKpis,
    turismo: hoteleriaKpis,
    salud: saludKpis,
    clinica: saludKpis,
  };

  for (const [key, calc] of Object.entries(calculators)) {
    if (normalized.includes(key)) return calc;
  }

  return null;
}

function restauranteKpis(data) {
  const kpis = [];

  if (data.ingresos > 0 && data.costo_materiales > 0) {
    const foodCost = (data.costo_materiales / data.ingresos) * 100;
    kpis.push({
      nombre: 'Food Cost %',
      valor: foodCost,
      valor_formateado: formatPercent(foodCost),
      categoria: 'operacion',
      formula: 'Costo de alimentos e ingredientes / Ingresos × 100',
      status: foodCost > 35 ? 'red' : foodCost > 30 ? 'yellow' : 'green',
    });
  }

  if (data.ingresos > 0 && data.nomina > 0) {
    const laborCost = (data.nomina / data.ingresos) * 100;
    kpis.push({
      nombre: 'Labor Cost %',
      valor: laborCost,
      valor_formateado: formatPercent(laborCost),
      categoria: 'operacion',
      formula: 'Nómina total / Ingresos × 100',
      status: laborCost > 35 ? 'red' : laborCost > 28 ? 'yellow' : 'green',
    });
  }

  if (data.ingresos > 0 && data.tickets_dia > 0) {
    const ticketPromedio = data.ingresos / (data.tickets_dia * 30);
    kpis.push({
      nombre: 'Ticket Promedio',
      valor: ticketPromedio,
      valor_formateado: formatCurrency(ticketPromedio),
      categoria: 'ingresos',
      formula: 'Ingresos mensuales / (Tickets por día × 30 días)',
    });
  }

  return kpis;
}

function construccionKpis(data) {
  const kpis = [];

  if (data.costo_ventas > 0 && data.m2_construidos > 0) {
    const costoM2 = data.costo_ventas / data.m2_construidos;
    kpis.push({
      nombre: 'Costo por m²',
      valor: costoM2,
      valor_formateado: formatCurrency(costoM2),
      categoria: 'costos',
      formula: 'Costo total de construcción / m² construidos',
    });
  }

  return kpis;
}

function retailKpis(data) {
  const kpis = [];

  if (data.inventario > 0 && data.costo_ventas > 0) {
    const rotacion = data.costo_ventas / data.inventario;
    const diasInventario = rotacion > 0 ? 365 / rotacion : 0;

    kpis.push({
      nombre: 'Rotación de Inventario',
      valor: rotacion,
      valor_formateado: `${rotacion.toFixed(1)} veces/año`,
      categoria: 'operacion',
      formula: 'Costo de ventas / Inventario promedio',
      status: rotacion < 4 ? 'red' : rotacion < 8 ? 'yellow' : 'green',
    });

    kpis.push({
      nombre: 'Días de Inventario',
      valor: diasInventario,
      valor_formateado: `${Math.round(diasInventario)} días`,
      categoria: 'operacion',
      formula: '365 / Rotación de inventario',
    });
  }

  return kpis;
}

function manufacturaKpis(data) {
  const kpis = [];

  if (data.costo_ventas > 0 && data.unidades_producidas > 0) {
    const costoUnidad = data.costo_ventas / data.unidades_producidas;
    kpis.push({
      nombre: 'Costo por Unidad',
      valor: costoUnidad,
      valor_formateado: formatCurrency(costoUnidad),
      categoria: 'costos',
      formula: 'Costo total de producción / Unidades producidas',
    });
  }

  if (data.ingresos > 0 && data.nomina > 0) {
    const modRatio = (data.nomina / data.ingresos) * 100;
    kpis.push({
      nombre: 'MOD / Ingresos',
      valor: modRatio,
      valor_formateado: formatPercent(modRatio),
      categoria: 'costos',
      formula: 'Mano de obra directa / Ingresos × 100',
    });
  }

  return kpis;
}

function serviciosKpis(data) {
  const kpis = [];

  if (data.ingresos > 0 && data.empleados > 0) {
    const ingresoPorEmpleado = data.ingresos / data.empleados;
    kpis.push({
      nombre: 'Ingreso por Empleado',
      valor: ingresoPorEmpleado,
      valor_formateado: formatCurrency(ingresoPorEmpleado),
      categoria: 'operacion',
      formula: 'Ingresos totales / Número de empleados',
    });
  }

  if (data.horas_facturables > 0 && data.ingresos > 0) {
    const tarifaHora = data.ingresos / data.horas_facturables;
    kpis.push({
      nombre: 'Tarifa por Hora',
      valor: tarifaHora,
      valor_formateado: formatCurrency(tarifaHora),
      categoria: 'ingresos',
      formula: 'Ingresos totales / Horas facturables',
    });
  }

  return kpis;
}

function agriculturaKpis(data) {
  const kpis = [];

  if (data.costo_ventas > 0 && data.hectareas > 0) {
    const costoHa = data.costo_ventas / data.hectareas;
    kpis.push({
      nombre: 'Costo por Hectárea',
      valor: costoHa,
      valor_formateado: formatCurrency(costoHa),
      categoria: 'costos',
      formula: 'Costos totales / Hectáreas en producción',
    });
  }

  if (data.ingresos > 0 && data.costo_materiales > 0) {
    const insumosRatio = (data.costo_materiales / data.ingresos) * 100;
    kpis.push({
      nombre: 'Costo de Insumos %',
      valor: insumosRatio,
      valor_formateado: formatPercent(insumosRatio),
      categoria: 'costos',
      formula: 'Costo de insumos / Ingresos × 100',
    });
  }

  return kpis;
}

function transporteKpis(data) {
  const kpis = [];

  if (data.gastos_operativos > 0 && data.km_recorridos > 0) {
    const costoKm = data.gastos_operativos / data.km_recorridos;
    kpis.push({
      nombre: 'Costo por Km',
      valor: costoKm,
      valor_formateado: `$${costoKm.toFixed(2)}/km`,
      categoria: 'costos',
      formula: 'Gastos operativos / Kilómetros recorridos',
    });
  }

  if (data.combustible > 0 && data.km_recorridos > 0) {
    const rendimiento = data.km_recorridos / data.combustible;
    kpis.push({
      nombre: 'Rendimiento de Combustible',
      valor: rendimiento,
      valor_formateado: `${rendimiento.toFixed(1)} km/L`,
      categoria: 'operacion',
      formula: 'Kilómetros recorridos / Litros de combustible',
    });
  }

  return kpis;
}

function hoteleriaKpis(data) {
  const kpis = [];

  if (data.ingresos > 0 && data.habitaciones > 0) {
    const revpar = data.ingresos / (data.habitaciones * 30);
    kpis.push({
      nombre: 'RevPAR',
      valor: revpar,
      valor_formateado: formatCurrency(revpar),
      categoria: 'ingresos',
      formula: 'Ingresos por habitación / (Habitaciones × días)',
    });
  }

  return kpis;
}

function saludKpis(data) {
  const kpis = [];

  if (data.gastos_operativos > 0 && data.consultas > 0) {
    const costoConsulta = data.gastos_operativos / data.consultas;
    kpis.push({
      nombre: 'Costo por Consulta',
      valor: costoConsulta,
      valor_formateado: formatCurrency(costoConsulta),
      categoria: 'costos',
      formula: 'Gastos operativos / Número de consultas',
    });
  }

  return kpis;
}

// ═══════════════════════════════════
// SEMÁFOROS
// ═══════════════════════════════════

function assignStatus(kpi) {
  const nombre = kpi.nombre.toLowerCase();
  const valor = kpi.valor;

  if (nombre.includes('margen neto')) {
    if (valor < 0) return 'red';
    if (valor < 5) return 'red';
    if (valor < 15) return 'yellow';
    return 'green';
  }

  if (nombre.includes('margen bruto')) {
    if (valor < 10) return 'red';
    if (valor < 25) return 'yellow';
    return 'green';
  }

  if (nombre.includes('flujo') || nombre.includes('ebitda')) {
    if (valor < 0) return 'red';
    return 'green';
  }

  if (nombre.includes('crecimiento')) {
    if (valor < -10) return 'red';
    if (valor < 0) return 'yellow';
    return 'green';
  }

  // Default: variación based
  if (kpi.variacion !== null && kpi.variacion !== undefined) {
    if (kpi.variacion < -15) return 'red';
    if (kpi.variacion < -5) return 'yellow';
    return 'green';
  }

  return 'green';
}

// ═══════════════════════════════════
// FORMATEO
// ═══════════════════════════════════

function formatCurrency(value) {
  if (value === null || value === undefined) return '-';
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(2)}`;
}

function formatPercent(value) {
  if (value === null || value === undefined) return '-';
  return `${value.toFixed(1)}%`;
}

module.exports = { calculateKpis, formatCurrency, formatPercent };
