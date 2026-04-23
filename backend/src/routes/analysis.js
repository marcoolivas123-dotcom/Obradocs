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

    // Use local KPI calculator
    const kpis = calculateKpis(parsed.sheets[0]?.data || [], industry);
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

module.exports = router;
