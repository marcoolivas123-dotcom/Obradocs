require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');
const { closeDb } = require('./src/models/database');

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Serve static frontend
app.use(express.static(path.join(__dirname, 'public')));

// API Routes
app.use('/api/analysis', require('./src/routes/analysis'));
app.use('/api/dashboard', require('./src/routes/dashboard'));
app.use('/api/onboarding', require('./src/routes/onboarding'));
app.use('/api/chat', require('./src/routes/chat'));

// Health check
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'DocuFin API',
    version: '1.0.0',
    hasApiKey: !!process.env.ANTHROPIC_API_KEY,
  });
});

// SPA fallback — serve index.html for all non-API routes
app.get('*', (req, res) => {
  if (!req.path.startsWith('/api')) {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
  }
});

// Error handler
app.use((err, req, res, _next) => {
  console.error('Server error:', err);
  if (err.message && err.message.includes('Formato no soportado')) {
    return res.status(400).json({ error: err.message });
  }
  res.status(500).json({ error: 'Error interno del servidor' });
});

const server = app.listen(PORT, () => {
  console.log(`DocuFin API corriendo en http://localhost:${PORT}`);
});

process.on('SIGTERM', () => {
  closeDb();
  server.close();
});

process.on('SIGINT', () => {
  closeDb();
  server.close();
});
