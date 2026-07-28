/**
 * POST /api/wa/send — el dueno manda un mensaje desde el panel.
 *
 * Body: { chatId, text, stepId? }
 * Si viene stepId lo anotamos como ultimo paso enviado y avanzamos la etapa.
 */
import { randomUUID } from 'node:crypto';

import { requireAuth } from '../_lib/auth.js';
import { getThread, appendMessage, isOptedOut, STAGES } from '../_lib/wa-store.js';
import { sendText } from '../_lib/waha.js';

const MAX_LEN = 4096; // limite practico de un mensaje de WhatsApp

// Escalera de progreso del lead. 'cold' no esta aqui a proposito: no es un
// escalon, es un lead dormido — si le volvemos a escribir, se reactiva.
const LADDER = ['new', 'awaiting_qualify', 'qualified', 'closing'];

function stageForStep(stepId) {
  if (!stepId) return null;
  if (stepId.startsWith('step1') || stepId.startsWith('step2')) return 'awaiting_qualify';
  if (stepId.startsWith('step3')) return 'qualified';
  if (stepId.startsWith('step4')) return 'closing';
  return null; // los followups no mueven la etapa
}

/** Solo avanza; nunca devuelve un lead a una etapa anterior. */
function advanceStage(current, next) {
  if (!next || !STAGES.includes(next)) return null;
  if (current === 'cold') return next; // le escribimos de nuevo: se reactiva
  const ci = LADDER.indexOf(current || 'new');
  const ni = LADDER.indexOf(next);
  if (ci < 0 || ni < 0) return null;
  return ni > ci ? next : null;
}

function parseBody(req) {
  let b = req.body;
  if (Buffer.isBuffer(b)) b = b.toString('utf8');
  if (typeof b === 'string') {
    try {
      b = JSON.parse(b || '{}');
    } catch {
      return null;
    }
  }
  return b && typeof b === 'object' ? b : {};
}

export default async function handler(req, res) {
  if (!requireAuth(req, res)) return;

  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const body = parseBody(req);
  if (!body) return res.status(400).json({ error: 'JSON invalido' });

  const chatId = typeof body.chatId === 'string' ? body.chatId.trim() : '';
  const text = typeof body.text === 'string' ? body.text.trim() : '';
  const stepId = typeof body.stepId === 'string' && body.stepId.trim() ? body.stepId.trim() : null;

  if (!chatId) return res.status(400).json({ error: 'Falta chatId' });
  if (!text) return res.status(400).json({ error: 'El mensaje esta vacio' });
  if (text.length > MAX_LEN) {
    return res.status(400).json({ error: `El mensaje pasa de ${MAX_LEN} caracteres` });
  }

  try {
    const thread = await getThread(chatId);
    if (!thread || !thread.chatId) return res.status(404).json({ error: 'Hilo no encontrado' });

    const phone = thread.phone || chatId.split('@')[0];
    // Si el contacto pidio la baja no le escribimos ni a mano desde el panel.
    if (await isOptedOut(phone)) {
      return res.status(403).json({ error: 'Este contacto pidio no recibir mas mensajes' });
    }

    await sendText(chatId, text);

    const lead = thread.lead || {};
    const nowIso = new Date().toISOString();
    const patch = {};
    if (stepId) {
      patch.lastStepSent = stepId;
      const nextStage = advanceStage(lead.stage, stageForStep(stepId));
      if (nextStage) patch.stage = nextStage;
    }
    // Aunque el dueno escriba libre, sin elegir paso: si ya le contestamos, el
    // lead deja de estar "nuevo" y pasa a estar pendiente de calificar.
    if (!patch.stage) {
      const nextStage = advanceStage(lead.stage, 'awaiting_qualify');
      if (nextStage) patch.stage = nextStage;
    }
    if (!lead.firstReplyAt) patch.firstReplyAt = nowIso;

    const stored = await appendMessage(
      chatId,
      {
        id: randomUUID(),
        ts: Date.now(),
        fromMe: true,
        type: 'chat',
        body: text,
        intent: stepId ? `playbook:${stepId}` : 'manual_reply',
        hasMedia: false,
      },
      patch,
    );

    const updated = stored && stored.chatId ? stored : await getThread(chatId);
    return res.status(200).json(updated);
  } catch (err) {
    console.error('[wa/send] error:', err);
    return res.status(502).json({ error: 'No se pudo enviar el mensaje' });
  }
}
