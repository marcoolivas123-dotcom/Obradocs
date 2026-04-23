const Anthropic = require('@anthropic-ai/sdk');
const {
  DOCUFIN_SYSTEM_PROMPT,
  ANALYSIS_PROMPT,
  ONBOARDING_PROMPT,
  CHAT_UPDATE_PROMPT,
} = require('../prompts/systemPrompt');

let client;

function getClient() {
  if (!client) {
    client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  }
  return client;
}

const MODEL = () => process.env.CLAUDE_MODEL || 'claude-sonnet-4-20250514';

/**
 * Analyze financial data from an Excel upload (Mode A)
 */
async function analyzeFinancialData(extractedData, industryHint) {
  const anthropic = getClient();

  const userMessage = `DATOS DEL ARCHIVO:
${extractedData}

${industryHint ? `NOTA: El usuario indica que su industria es: ${industryHint}` : ''}

Analiza estos datos financieros siguiendo las instrucciones del sistema.`;

  const response = await anthropic.messages.create({
    model: MODEL(),
    max_tokens: 4096,
    system: `${DOCUFIN_SYSTEM_PROMPT}\n\n${ANALYSIS_PROMPT}`,
    messages: [{ role: 'user', content: userMessage }],
  });

  const text = response.content[0].text;
  return parseJsonResponse(text);
}

/**
 * Stream financial analysis (for real-time UI updates)
 */
async function streamAnalysis(extractedData, industryHint) {
  const anthropic = getClient();

  const userMessage = `DATOS DEL ARCHIVO:
${extractedData}

${industryHint ? `NOTA: El usuario indica que su industria es: ${industryHint}` : ''}

Analiza estos datos financieros siguiendo las instrucciones del sistema.`;

  const stream = await anthropic.messages.stream({
    model: MODEL(),
    max_tokens: 4096,
    system: `${DOCUFIN_SYSTEM_PROMPT}\n\n${ANALYSIS_PROMPT}`,
    messages: [{ role: 'user', content: userMessage }],
  });

  return stream;
}

/**
 * Onboarding conversation (Mode B) - one question at a time
 */
async function onboardingStep(industry, previousAnswers, userMessage) {
  const anthropic = getClient();

  const context = `INDUSTRIA DETECTADA: ${industry}
RESPUESTAS ANTERIORES DEL USUARIO: ${JSON.stringify(previousAnswers)}`;

  const messages = [
    { role: 'user', content: `${context}\n\nMensaje del usuario: ${userMessage}` },
  ];

  const response = await anthropic.messages.create({
    model: MODEL(),
    max_tokens: 1024,
    system: `${DOCUFIN_SYSTEM_PROMPT}\n\n${ONBOARDING_PROMPT}`,
    messages,
  });

  const text = response.content[0].text;
  return parseJsonResponse(text);
}

/**
 * Process natural language dashboard updates (Mode B live updates)
 */
async function processChatUpdate(dashboardContext, chatHistory, userMessage) {
  const anthropic = getClient();

  const context = `CONTEXTO DEL DASHBOARD ACTUAL:
${JSON.stringify(dashboardContext)}`;

  const messages = chatHistory.map((msg) => ({
    role: msg.role,
    content: msg.content,
  }));
  messages.push({
    role: 'user',
    content: `${context}\n\nMensaje del usuario: ${userMessage}`,
  });

  const response = await anthropic.messages.create({
    model: MODEL(),
    max_tokens: 2048,
    system: `${DOCUFIN_SYSTEM_PROMPT}\n\n${CHAT_UPDATE_PROMPT}`,
    messages,
  });

  const text = response.content[0].text;
  return parseJsonResponse(text);
}

/**
 * Detect industry from raw data
 */
async function detectIndustry(sampleData) {
  const anthropic = getClient();

  const response = await anthropic.messages.create({
    model: MODEL(),
    max_tokens: 256,
    system: DOCUFIN_SYSTEM_PROMPT,
    messages: [
      {
        role: 'user',
        content: `Analiza estos datos y detecta la industria/giro del negocio. Responde SOLO en JSON:
{"industria": "nombre", "confianza": "alta|media|baja", "tipo_documento": "ventas|costos|flujo|nómina|inventario|mixto", "periodo": "período detectado"}

DATOS:
${sampleData.substring(0, 2000)}`,
      },
    ],
  });

  const text = response.content[0].text;
  return parseJsonResponse(text);
}

/**
 * Parse JSON from Claude response, handling markdown code blocks
 */
function parseJsonResponse(text) {
  let cleaned = text.trim();

  // Remove markdown code block wrapper if present
  const jsonBlockMatch = cleaned.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (jsonBlockMatch) {
    cleaned = jsonBlockMatch[1].trim();
  }

  try {
    return JSON.parse(cleaned);
  } catch {
    // Try to find JSON object in the text
    const jsonMatch = cleaned.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try {
        return JSON.parse(jsonMatch[0]);
      } catch {
        return { raw_response: text, parse_error: true };
      }
    }
    return { raw_response: text, parse_error: true };
  }
}

module.exports = {
  analyzeFinancialData,
  streamAnalysis,
  onboardingStep,
  processChatUpdate,
  detectIndustry,
};
