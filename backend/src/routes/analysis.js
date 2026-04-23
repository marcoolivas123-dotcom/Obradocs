const express = require('express');
const { v4: uuidv4 } = require('uuid');
const fs = require('fs');
const upload = require('../middleware/upload');
const { parseFile } = require('../services/excelParser');
const { analyzeFinancialData, streamAnalysis, detectIndustry } = require('../services/claudeService');
const { calculateKpis } = require('../services/kpiCalculator');
const { generateAlerts } = require('../services/alertEngine');
const { getDb } = require('../models/database');

const router = express.Router();

// POST /api/analysis/upload — Mode A: Upload Excel and get full analysis
router.post('/upload', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No se recibió ningún archivo' });
    }

    if (!process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_API_KEY === 'placeholder') {
      return res.status(503).json({
        error: 'API key de Anthropic no configurada. Edita backend/.env con tu clave real.',
        details: 'ANTHROPIC_API_KEY no está configurada en el servidor',
      });
    }

    const filePath = req.file.path;
    const industryHint = req.body.industry || null;

    // 1. Parse the file
    const parsed = parseFile(filePath);

    // 2. Detect industry from data
    let industry = industryHint;
    if (!industry) {
      try {
        const detection = await detectIndustry(parsed.rawText);
        industry = detection.industria || 'general';
      } catch {
        industry = 'general';
      }
    }

    // 3. Create business + dashboard in DB
    const db = getDb();
    const businessId = uuidv4();
    const dashboardId = uuidv4();

    db.prepare(
      `INSERT INTO businesses (id, name, industry) VALUES (?, ?, ?)`
    ).run(businessId, req.body.businessName || 'Mi Negocio', industry);

    db.prepare(
      `INSERT INTO dashboards (id, business_id, mode, period, currency, raw_data)
       VALUES (?, ?, 'A', ?, ?, ?)`
    ).run(dashboardId, businessId, parsed.summary.detectedPeriod, parsed.summary.detectedCurrency, JSON.stringify(parsed.summary));

    // 4. Send to Claude for analysis
    const analysis = await analyzeFinancialData(parsed.rawText, industry);

    // 5. Store KPIs from Claude response
    if (analysis.kpis && !analysis.parse_error) {
      const insertKpi = db.prepare(
        `INSERT INTO kpis (id, dashboard_id, name, value, value_formatted, previous_value, variation, status, category, formula, period)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      );
      for (const kpi of analysis.kpis) {
        insertKpi.run(
          uuidv4(), dashboardId, kpi.nombre, kpi.valor, kpi.valor_formateado,
          kpi.valor_anterior, kpi.variacion, kpi.status, kpi.categoria, kpi.formula,
          parsed.summary.detectedPeriod
        );
      }
    }

    // 6. Store alerts
    if (analysis.alertas && !analysis.parse_error) {
      const insertAlert = db.prepare(
        `INSERT INTO alerts (id, dashboard_id, severity, title, description, impact, action)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      );
      for (const alert of analysis.alertas) {
        insertAlert.run(
          uuidv4(), dashboardId, alert.severidad, alert.titulo,
          alert.descripcion, alert.impacto, alert.accion
        );
      }
    }

    // Cleanup uploaded file
    fs.unlink(filePath, () => {});

    res.json({
      success: true,
      businessId,
      dashboardId,
      industry,
      summary: parsed.summary,
      analysis,
    });
  } catch (err) {
    console.error('Analysis upload error:', err);
    res.status(500).json({ error: 'Error al procesar el archivo', details: err.message });
  }
});

// POST /api/analysis/stream — Stream analysis (SSE)
router.post('/stream', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No se recibió ningún archivo' });
    }

    const parsed = parseFile(req.file.path);
    const industryHint = req.body.industry || null;

    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    // Send file summary first
    res.write(`data: ${JSON.stringify({ type: 'summary', data: parsed.summary })}\n\n`);

    const stream = await streamAnalysis(parsed.rawText, industryHint);

    stream.on('text', (text) => {
      res.write(`data: ${JSON.stringify({ type: 'text', data: text })}\n\n`);
    });

    stream.on('message', () => {
      res.write(`data: ${JSON.stringify({ type: 'done' })}\n\n`);
      res.end();
    });

    stream.on('error', (err) => {
      res.write(`data: ${JSON.stringify({ type: 'error', data: err.message })}\n\n`);
      res.end();
    });

    // Cleanup
    fs.unlink(req.file.path, () => {});
  } catch (err) {
    console.error('Stream error:', err);
    res.status(500).json({ error: err.message });
  }
});

// POST /api/analysis/quick — Quick analysis without Claude (local KPI engine only)
router.post('/quick', upload.single('file'), (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No se recibió ningún archivo' });
    }

    const parsed = parseFile(req.file.path);
    const industry = req.body.industry || 'general';

    // Map Excel rows to financial data structure
    const financialData = mapExcelToFinancialData(parsed);

    const kpis = calculateKpis(financialData, industry);
    const alerts = generateAlerts(kpis, industry);

    fs.unlink(req.file.path, () => {});

    res.json({
      success: true,
      industry,
      summary: parsed.summary,
      kpis,
      alerts,
    });
  } catch (err) {
    console.error('Quick analysis error:', err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * Auto-map Excel data to financial structure.
 * Handles two common formats:
 *   Format 1 (columns): headers are financial categories (Ingresos, Costos, etc.)
 *   Format 2 (rows): a label column + numeric period columns (Enero, Febrero, etc.)
 */
function mapExcelToFinancialData(parsed) {
  const data = { ingresos: 0, costo_ventas: 0, gastos_operativos: 0, gastos_admin: 0, nomina: 0, deudas: 0, inventario: 0, efectivo: 0 };

  for (const sheet of parsed.sheets) {
    const summary = sheet.numericSummary || {};
    const headers = sheet.headers || [];
    const rows = sheet.data || [];

    // Detect if data is row-based (first column is text labels, rest are numeric periods)
    const firstColType = sheet.columnTypes?.[headers[0]];
    const numericCols = headers.filter(h => ['numeric', 'currency'].includes(sheet.columnTypes?.[h]));
    const isRowBased = firstColType === 'text' && numericCols.length >= 1 && headers.length >= 2;

    if (isRowBased) {
      // Format 2: each row is a category, sum across period columns
      const labelCol = headers[0];
      for (const row of rows) {
        const label = String(row[labelCol] || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
        let rowSum = 0;
        for (const col of numericCols) {
          const val = parseFloat(String(row[col]).replace(/[$,]/g, ''));
          if (!isNaN(val)) rowSum += val;
        }
        if (rowSum === 0) continue;

        if (/costo.*venta|cost.*good|cogs|costo.*direc/.test(label)) data.costo_ventas += rowSum;
        else if (/nomin|salar|sueldo|payroll/.test(label)) data.nomina += rowSum;
        else if (/gasto.*admin|admin/.test(label)) data.gastos_admin += rowSum;
        else if (/gasto|expense|egreso|compra|renta|servicio/.test(label)) data.gastos_operativos += rowSum;
        else if (/ingreso|venta|revenue|factur/.test(label)) data.ingresos += rowSum;
        else if (/deuda|credito|prestamo/.test(label)) data.deudas += rowSum;
        else if (/inventario|stock/.test(label)) data.inventario += rowSum;
        else if (/efectivo|cash|banco/.test(label)) data.efectivo += rowSum;
      }
    } else {
      // Format 1: headers are the financial categories
      for (const header of headers) {
        const h = header.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
        const total = summary[header]?.sum || 0;
        if (total === 0) continue;

        if (/costo.*venta|cost.*good|cogs|costo.*direc/.test(h)) data.costo_ventas += total;
        else if (/nomin|salar|sueldo|payroll|empleado/.test(h)) data.nomina += total;
        else if (/gasto.*admin|admin|indirect/.test(h)) data.gastos_admin += total;
        else if (/gasto|expense|egreso|compra/.test(h)) data.gastos_operativos += total;
        else if (/ingreso|venta|revenue|factur|cobr/.test(h)) data.ingresos += total;
        else if (/deuda|credito|prestamo|loan/.test(h)) data.deudas += total;
        else if (/inventario|stock|almacen/.test(h)) data.inventario += total;
        else if (/efectivo|cash|banco|saldo/.test(h)) data.efectivo += total;
      }
    }
  }

  return data;
}

module.exports = router;
