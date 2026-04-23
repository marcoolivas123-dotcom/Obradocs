const express = require('express');
const { v4: uuidv4 } = require('uuid');
const { getDb } = require('../models/database');
const { calculateKpis } = require('../services/kpiCalculator');
const { generateAlerts } = require('../services/alertEngine');

const router = express.Router();

// GET /api/dashboard/:id — Get full dashboard
router.get('/:id', (req, res) => {
  try {
    const db = getDb();
    const dashboard = db.prepare('SELECT * FROM dashboards WHERE id = ?').get(req.params.id);
    if (!dashboard) return res.status(404).json({ error: 'Dashboard no encontrado' });

    const business = db.prepare('SELECT * FROM businesses WHERE id = ?').get(dashboard.business_id);
    const kpis = db.prepare('SELECT * FROM kpis WHERE dashboard_id = ? ORDER BY category, name').all(req.params.id);
    const alerts = db.prepare('SELECT * FROM alerts WHERE dashboard_id = ? ORDER BY CASE severity WHEN \'critical\' THEN 0 WHEN \'warning\' THEN 1 ELSE 2 END').all(req.params.id);
    const financialData = db.prepare('SELECT * FROM financial_data WHERE dashboard_id = ?').all(req.params.id);

    res.json({
      dashboard,
      business,
      kpis,
      alerts,
      financialData,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// GET /api/dashboard — List all dashboards
router.get('/', (req, res) => {
  try {
    const db = getDb();
    const dashboards = db.prepare(`
      SELECT d.*, b.name as business_name, b.industry,
        (SELECT COUNT(*) FROM alerts WHERE dashboard_id = d.id AND severity = 'critical' AND is_read = 0) as critical_alerts
      FROM dashboards d
      JOIN businesses b ON d.business_id = b.id
      ORDER BY d.updated_at DESC
    `).all();

    res.json({ dashboards });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// POST /api/dashboard — Create dashboard (Mode B)
router.post('/', (req, res) => {
  try {
    const db = getDb();
    const { businessName, industry, financialData } = req.body;

    const businessId = uuidv4();
    const dashboardId = uuidv4();

    db.prepare('INSERT INTO businesses (id, name, industry) VALUES (?, ?, ?)').run(businessId, businessName || 'Mi Negocio', industry);
    db.prepare('INSERT INTO dashboards (id, business_id, mode, currency) VALUES (?, ?, \'B\', \'MXN\')').run(dashboardId, businessId);

    // Insert financial data
    if (financialData && Array.isArray(financialData)) {
      const insert = db.prepare(
        'INSERT INTO financial_data (id, dashboard_id, category, subcategory, label, amount, period) VALUES (?, ?, ?, ?, ?, ?, ?)'
      );
      for (const item of financialData) {
        insert.run(uuidv4(), dashboardId, item.category, item.subcategory || null, item.label, item.amount, item.period || null);
      }

      // Calculate KPIs
      const kpis = calculateKpis(financialData, industry);
      const insertKpi = db.prepare(
        'INSERT INTO kpis (id, dashboard_id, name, value, value_formatted, previous_value, variation, status, category, formula) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
      );
      for (const kpi of kpis) {
        insertKpi.run(uuidv4(), dashboardId, kpi.nombre, kpi.valor, kpi.valor_formateado, kpi.valor_anterior || null, kpi.variacion || null, kpi.status, kpi.categoria, kpi.formula);
      }

      // Generate alerts
      const alerts = generateAlerts(kpis, industry);
      const insertAlert = db.prepare(
        'INSERT INTO alerts (id, dashboard_id, severity, title, description, impact, action, kpi_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
      );
      for (const alert of alerts) {
        insertAlert.run(uuidv4(), dashboardId, alert.severity, alert.title, alert.description, alert.impact, alert.action, alert.kpi_name || null);
      }
    }

    res.json({ success: true, businessId, dashboardId });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// PUT /api/dashboard/:id/data — Update financial data (Mode B live updates)
router.put('/:id/data', (req, res) => {
  try {
    const db = getDb();
    const dashboard = db.prepare('SELECT * FROM dashboards WHERE id = ?').get(req.params.id);
    if (!dashboard) return res.status(404).json({ error: 'Dashboard no encontrado' });

    const business = db.prepare('SELECT * FROM businesses WHERE id = ?').get(dashboard.business_id);
    const { updates } = req.body;

    if (!updates || !Array.isArray(updates)) {
      return res.status(400).json({ error: 'Se requiere un array de actualizaciones' });
    }

    const insert = db.prepare(
      'INSERT INTO financial_data (id, dashboard_id, category, subcategory, label, amount, period) VALUES (?, ?, ?, ?, ?, ?, ?)'
    );

    for (const item of updates) {
      insert.run(uuidv4(), req.params.id, item.category, item.subcategory || null, item.label, item.amount, item.period || null);
    }

    // Recalculate KPIs
    const allData = db.prepare('SELECT * FROM financial_data WHERE dashboard_id = ?').all(req.params.id);
    const kpis = calculateKpis(allData, business.industry);

    // Clear old KPIs and alerts, insert new
    db.prepare('DELETE FROM kpis WHERE dashboard_id = ?').run(req.params.id);
    db.prepare('DELETE FROM alerts WHERE dashboard_id = ?').run(req.params.id);

    const insertKpi = db.prepare(
      'INSERT INTO kpis (id, dashboard_id, name, value, value_formatted, previous_value, variation, status, category, formula) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
    );
    for (const kpi of kpis) {
      insertKpi.run(uuidv4(), req.params.id, kpi.nombre, kpi.valor, kpi.valor_formateado, kpi.valor_anterior || null, kpi.variacion || null, kpi.status, kpi.categoria, kpi.formula);
    }

    const alerts = generateAlerts(kpis, business.industry);
    const insertAlert = db.prepare(
      'INSERT INTO alerts (id, dashboard_id, severity, title, description, impact, action, kpi_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
    );
    for (const alert of alerts) {
      insertAlert.run(uuidv4(), req.params.id, alert.severity, alert.title, alert.description, alert.impact, alert.action, alert.kpi_name || null);
    }

    db.prepare('UPDATE dashboards SET updated_at = datetime(\'now\') WHERE id = ?').run(req.params.id);

    res.json({ success: true, kpis, alerts });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// DELETE /api/dashboard/:id
router.delete('/:id', (req, res) => {
  try {
    const db = getDb();
    const dashboard = db.prepare('SELECT * FROM dashboards WHERE id = ?').get(req.params.id);
    if (!dashboard) return res.status(404).json({ error: 'Dashboard no encontrado' });

    db.prepare('DELETE FROM dashboards WHERE id = ?').run(req.params.id);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
