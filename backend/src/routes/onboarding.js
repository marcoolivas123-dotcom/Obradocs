const express = require('express');
const { v4: uuidv4 } = require('uuid');
const { getDb } = require('../models/database');
const { onboardingStep } = require('../services/claudeService');

const router = express.Router();

// POST /api/onboarding/start — Start Mode B onboarding
router.post('/start', async (req, res) => {
  try {
    const { industry } = req.body;

    if (!industry) {
      return res.status(400).json({ error: 'Se requiere la industria del negocio' });
    }

    const db = getDb();
    const businessId = uuidv4();
    const sessionId = uuidv4();

    db.prepare('INSERT INTO businesses (id, name, industry) VALUES (?, ?, ?)').run(businessId, 'Mi Negocio', industry);
    db.prepare('INSERT INTO onboarding_sessions (id, business_id, industry, current_step, answers) VALUES (?, ?, ?, 1, ?)').run(sessionId, businessId, industry, '{}');

    // Get the first onboarding question from Claude
    const response = await onboardingStep(industry, {}, `Mi negocio es de: ${industry}`);

    // Save chat history
    db.prepare('INSERT INTO chat_history (id, dashboard_id, role, content) VALUES (?, ?, ?, ?)').run(uuidv4(), sessionId, 'user', `Mi negocio es de: ${industry}`);
    db.prepare('INSERT INTO chat_history (id, dashboard_id, role, content) VALUES (?, ?, ?, ?)').run(uuidv4(), sessionId, 'assistant', JSON.stringify(response));

    res.json({
      success: true,
      sessionId,
      businessId,
      response,
    });
  } catch (err) {
    console.error('Onboarding start error:', err);
    res.status(500).json({ error: err.message });
  }
});

// POST /api/onboarding/:sessionId/answer — Answer an onboarding question
router.post('/:sessionId/answer', async (req, res) => {
  try {
    const db = getDb();
    const session = db.prepare('SELECT * FROM onboarding_sessions WHERE id = ?').get(req.params.sessionId);
    if (!session) return res.status(404).json({ error: 'Sesión no encontrada' });

    const { message } = req.body;
    if (!message) return res.status(400).json({ error: 'Se requiere un mensaje' });

    const previousAnswers = JSON.parse(session.answers || '{}');

    // Get Claude's response
    const response = await onboardingStep(session.industry, previousAnswers, message);

    // Update session
    const newStep = session.current_step + 1;
    const updatedAnswers = response.datos_capturados || previousAnswers;

    db.prepare('UPDATE onboarding_sessions SET current_step = ?, answers = ?, updated_at = datetime(\'now\') WHERE id = ?').run(newStep, JSON.stringify(updatedAnswers), req.params.sessionId);

    // Save chat
    db.prepare('INSERT INTO chat_history (id, dashboard_id, role, content) VALUES (?, ?, ?, ?)').run(uuidv4(), req.params.sessionId, 'user', message);
    db.prepare('INSERT INTO chat_history (id, dashboard_id, role, content) VALUES (?, ?, ?, ?)').run(uuidv4(), req.params.sessionId, 'assistant', JSON.stringify(response));

    // If onboarding is complete, create the dashboard
    if (response.onboarding_completo) {
      db.prepare('UPDATE onboarding_sessions SET status = \'completed\' WHERE id = ?').run(req.params.sessionId);

      // The dashboard creation will be triggered by the frontend calling POST /api/dashboard
    }

    res.json({
      success: true,
      step: newStep,
      response,
      complete: response.onboarding_completo || false,
    });
  } catch (err) {
    console.error('Onboarding answer error:', err);
    res.status(500).json({ error: err.message });
  }
});

// GET /api/onboarding/:sessionId — Get session state
router.get('/:sessionId', (req, res) => {
  try {
    const db = getDb();
    const session = db.prepare('SELECT * FROM onboarding_sessions WHERE id = ?').get(req.params.sessionId);
    if (!session) return res.status(404).json({ error: 'Sesión no encontrada' });

    const history = db.prepare('SELECT * FROM chat_history WHERE dashboard_id = ? ORDER BY created_at').all(req.params.sessionId);

    res.json({ session, history });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
