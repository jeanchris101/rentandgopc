/**
 * POST /api/wa/lead — correccion manual del dueno sobre un lead.
 *
 * Body: { chatId, propertySlug?, stage?, language?, manualOverride? }
 *
 * Cuando el dueno asigna la propiedad a mano queda `manualOverride: true` y
 * `confidence: 'high'`: a partir de ahi el clasificador ya no toca ese hilo.
 * La persona que hablo con el cliente sabe mas que el matcher de palabras.
 */
import { requireAuth } from './auth.js';
import { getThread, saveThread, STAGES } from './wa-store.js';
import { findPlaybook } from './classify.js';

// Los guiones solo existen en estos dos idiomas (playbooks.json).
const LANGUAGES = ['es', 'en'];

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

export async function lead(req, res) {
  if (!requireAuth(req, res)) return;

  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const body = parseBody(req);
  if (!body) return res.status(400).json({ error: 'JSON invalido' });

  const chatId = typeof body.chatId === 'string' ? body.chatId.trim() : '';
  if (!chatId) return res.status(400).json({ error: 'Falta chatId' });

  const patch = {};

  if (body.propertySlug !== undefined) {
    if (body.propertySlug === null || body.propertySlug === '') {
      // Quitar la propiedad tambien devuelve el hilo al clasificador.
      patch.propertySlug = null;
      patch.ref = null;
      patch.manualOverride = false;
      patch.confidence = 'low';
    } else {
      const slug = String(body.propertySlug).trim();
      // findPlaybook es la fuente de verdad: si no hay guion para esa propiedad,
      // asignarla dejaria el hilo sin nada que enviar.
      const playbook = findPlaybook(slug);
      if (!playbook) return res.status(400).json({ error: `Propiedad desconocida: ${slug}` });
      patch.propertySlug = slug;
      if (playbook.ref_code) patch.ref = playbook.ref_code;
      // La correccion humana manda para siempre en este hilo.
      patch.manualOverride = true;
      patch.confidence = 'high';
    }
  }

  if (body.stage !== undefined) {
    const stage = String(body.stage).trim();
    if (!STAGES.includes(stage)) {
      return res.status(400).json({ error: `Etapa invalida: ${stage}`, allowed: STAGES });
    }
    patch.stage = stage;
  }

  if (body.language !== undefined) {
    const language = String(body.language).trim().toLowerCase();
    if (!LANGUAGES.includes(language)) {
      return res
        .status(400)
        .json({ error: `Idioma sin guiones: ${language}`, allowed: LANGUAGES });
    }
    patch.language = language;
  }

  // Va de ultimo a proposito: si el dueno lo manda explicito, gana sobre el
  // true automatico que pone la asignacion de propiedad (asi puede soltar el
  // hilo y dejar que el bot lo retome).
  if (body.manualOverride !== undefined) {
    if (typeof body.manualOverride !== 'boolean') {
      return res.status(400).json({ error: 'manualOverride tiene que ser true o false' });
    }
    patch.manualOverride = body.manualOverride;
  }

  if (!Object.keys(patch).length) {
    return res.status(400).json({ error: 'No mandaste nada que cambiar' });
  }

  try {
    const thread = await getThread(chatId);
    if (!thread || !thread.chatId) return res.status(404).json({ error: 'Hilo no encontrado' });

    // saveThread pone updatedAt y refresca el indice.
    const updated = { ...thread, lead: { ...(thread.lead || {}), ...patch, updatedBy: 'panel' } };
    return res.status(200).json(await saveThread(updated));
  } catch (err) {
    console.error('[wa/lead] error:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
