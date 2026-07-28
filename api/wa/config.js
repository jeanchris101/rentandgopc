/**
 * GET/POST /api/wa/config — ajustes del auto-reply.
 *
 * autoReplyEnabled  el bot contesta o no
 * killSwitch        freno de mano: apaga todo sin perder el resto de ajustes
 * dailyCap          tope de auto-respuestas por dia (1-100)
 * quietHours        ventana en que SI se contesta, hora dominicana: [start, end)
 */
import { requireAuth } from '../_lib/auth.js';
import { getConfig, saveConfig } from '../_lib/wa-store.js';

const CAP_MIN = 1;
const CAP_MAX = 100;

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

function isHour(n) {
  return Number.isInteger(n) && n >= 0 && n <= 23;
}

export default async function handler(req, res) {
  if (!requireAuth(req, res)) return;

  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method === 'GET') {
    try {
      // getConfig ya mezcla los valores por defecto y coacciona los tipos.
      return res.status(200).json(await getConfig());
    } catch (err) {
      console.error('[wa/config] error leyendo config:', err);
      return res.status(500).json({ error: 'Internal error' });
    }
  }

  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const body = parseBody(req);
  if (!body) return res.status(400).json({ error: 'JSON invalido' });

  // Solo tomamos los campos conocidos; lo que venga de mas se ignora.
  const patch = {};

  if (body.autoReplyEnabled !== undefined) {
    if (typeof body.autoReplyEnabled !== 'boolean') {
      return res.status(400).json({ error: 'autoReplyEnabled tiene que ser true o false' });
    }
    patch.autoReplyEnabled = body.autoReplyEnabled;
  }

  if (body.killSwitch !== undefined) {
    if (typeof body.killSwitch !== 'boolean') {
      return res.status(400).json({ error: 'killSwitch tiene que ser true o false' });
    }
    patch.killSwitch = body.killSwitch;
  }

  if (body.dailyCap !== undefined) {
    const cap = Number(body.dailyCap);
    if (!Number.isInteger(cap) || cap < CAP_MIN || cap > CAP_MAX) {
      return res
        .status(400)
        .json({ error: `dailyCap tiene que ser un entero entre ${CAP_MIN} y ${CAP_MAX}` });
    }
    patch.dailyCap = cap;
  }

  if (body.quietHours !== undefined) {
    const qh = body.quietHours;
    if (!qh || typeof qh !== 'object') {
      return res.status(400).json({ error: 'quietHours tiene que ser {start, end}' });
    }
    const start = Number(qh.start);
    const end = Number(qh.end);
    if (!isHour(start) || !isHour(end)) {
      return res.status(400).json({ error: 'quietHours.start y quietHours.end van de 0 a 23' });
    }
    if (start >= end) {
      // La ventana no cruza medianoche a proposito: nadie deberia estar
      // auto-respondiendo leads a las 3 de la manana.
      return res.status(400).json({ error: 'quietHours.start tiene que ser menor que quietHours.end' });
    }
    patch.quietHours = { start, end };
  }

  if (!Object.keys(patch).length) {
    return res.status(400).json({ error: 'No mandaste nada que cambiar' });
  }

  try {
    // saveConfig devuelve la config ya guardada y normalizada.
    const saved = await saveConfig(patch);
    return res.status(200).json(saved && typeof saved === 'object' ? saved : await getConfig());
  } catch (err) {
    console.error('[wa/config] error guardando config:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
