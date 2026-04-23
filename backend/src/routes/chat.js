const express = require('express');
const { v4: uuidv4 } = require('uuid');
const { getDb } = require('../models/database');
const { processChatUpdate } = require('../services/claudeService');

const router = express.Router();

// POST /api/chat/:dashboardId — Send a natural language message to update dashboard
router.post('/:dashboardId', async (req, res) => {
  try {
    const db = getDb();
    const dashboard = db.prepare('SELECT * FROM dashboards WHERE id = ?').get(req.params.dashboardId);
    if (!dashboard) return res.status(404).json({ error: 'Dashboard no encontrado' });

    const { message } = req.body;
    if (!message) return res.status(400).json({ error: 'Se requiere un mensaje' });

    const business = db.prepare('SELECT * FROM businesses WHERE id = ?').get(dashboard.business_id);
    const kpis = db.prepare('SELECT * FROM kpis WHERE dashboard_id = ?').all(req.params.dashboardId);
    const financialData = db.prepare('SELECT * FROM financial_data WHERE dashboard_id = ?').all(req.params.dashboardId);
    const recentHistory = db.prepare('SELECT role, content FROM chat_history WHERE dashboard_id = ? ORDER BY created_at DESC LIMIT 10').all(req.params.dashboardId).reverse();

    const dashboardContext = {
      industry: business.industry,
      businessName: business.name,
      currentKpis: kpis.map((k) => ({ nombre: k.name, valor: k.value, formateado: k.value_formatted })),
      financialData: financialData.map((f) => ({ categoria: f.category, label: f.label, monto: f.amount })),
    };

    const response = await processChatUpdate(dashboardContext, recentHistory, message);

    // Save chat
    db.prepare('INSERT INTO chat_history (id, dashboard_id, role, content) VALUES (?, ?, ?, ?)').run(uuidv4(), req.params.dashboardId, 'user', message);
    db.prepare('INSERT INTO chat_history (id, dashboard_id, role, content, metadata) VALUES (?, ?, ?, ?, ?)').run(uuidv4(), req.params.dashboardId, 'assistant', response.mensaje || JSON.stringify(response), JSON.stringify(response));

    // Apply updates if present
    if (response.actualizaciones && Array.isArray(response.actualizaciones)) {
      const insert = db.prepare(
        'INSERT INTO financial_data (id, dashboard_id, category, subcategory, label, amount) VALUES (?, ?, ?, ?, ?, ?)'
      );
      for (const update of response.actualizaciones) {
        insert.run(uuidv4(), req.params.dashboardId, update.categoria, update.subcategoria || null, update.label, update.valor_nuevo);
      }
    }

    db.prepare('UPDATE dashboards SET updated_at = datetime(\'now\') WHERE id = ?').run(req.params.dashboardId);

    res.json({ success: true, response });
  } catch (err) {
    console.error('Chat error:', err);
    res.status(500).json({ error: err.message });
  }
});

// GET /api/chat/:dashboardId/history — Get chat history
router.get('/:dashboardId/history', (req, res) => {
  try {
    const db = getDb();
    const history = db.prepare('SELECT * FROM chat_history WHERE dashboard_id = ? ORDER BY created_at').all(req.params.dashboardId);
    res.json({ history });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
