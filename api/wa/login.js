/**
 * POST /api/wa/login — entrada al panel. Body: { password }
 *
 * Unico endpoint junto al webhook que no exige cookie (es el que la reparte).
 */
import { createHash, timingSafeEqual } from 'node:crypto';

import { makeToken, setAuthCookie } from '../_lib/auth.js';

const WINDOW_MS = 60_000;
const MAX_ATTEMPTS = 5;

/**
 * Rate-limit en memoria del modulo. Vive lo que viva la instancia y no se
 * comparte entre regiones, asi que no es una defensa perfecta — pero corta en
 * seco el script tonto que prueba mil contrasenas seguidas, que es el caso real.
 */
const attempts = new Map(); // ip -> { count, resetAt }

function clientIp(req) {
  const fwd = req.headers['x-forwarded-for'];
  if (typeof fwd === 'string' && fwd.trim()) return fwd.split(',')[0].trim();
  if (Array.isArray(fwd) && fwd.length) return String(fwd[0]).split(',')[0].trim();
  const real = req.headers['x-real-ip'];
  if (typeof real === 'string' && real.trim()) return real.trim();
  return (req.socket && req.socket.remoteAddress) || 'unknown';
}

function takeAttempt(ip) {
  const now = Date.now();

  // Limpieza perezosa para que el Map no crezca sin freno.
  if (attempts.size > 200) {
    for (const [key, entry] of attempts) if (entry.resetAt <= now) attempts.delete(key);
  }

  const entry = attempts.get(ip);
  if (!entry || entry.resetAt <= now) {
    attempts.set(ip, { count: 1, resetAt: now + WINDOW_MS });
    return { allowed: true, retryAfter: 0 };
  }
  entry.count++;
  if (entry.count > MAX_ATTEMPTS) {
    return { allowed: false, retryAfter: Math.max(1, Math.ceil((entry.resetAt - now) / 1000)) };
  }
  return { allowed: true, retryAfter: 0 };
}

/**
 * Comparamos los SHA-256, no las cadenas: asi los dos buffers miden siempre 32
 * bytes (timingSafeEqual explota si difieren) y de paso el tiempo de comparacion
 * no filtra cuantos caracteres acertaste.
 */
function samePassword(a, b) {
  const ha = createHash('sha256').update(String(a), 'utf8').digest();
  const hb = createHash('sha256').update(String(b), 'utf8').digest();
  return timingSafeEqual(ha, hb);
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
  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const ip = clientIp(req);
  const gate = takeAttempt(ip);
  if (!gate.allowed) {
    res.setHeader('Retry-After', String(gate.retryAfter));
    return res.status(429).json({ error: 'Demasiados intentos. Espera un minuto.' });
  }

  const body = parseBody(req);
  if (!body) return res.status(400).json({ error: 'JSON invalido' });

  const password = typeof body.password === 'string' ? body.password : '';
  const expected = process.env.PANEL_PASSWORD;

  // Si PANEL_PASSWORD no esta puesto contestamos igual que con clave mala:
  // desde afuera no se distingue "mal configurado" de "te equivocaste", que es
  // justo lo que no queremos regalar. El aviso queda en los logs del servidor.
  if (!expected) {
    console.error('[wa/login] PANEL_PASSWORD no esta configurado — nadie puede entrar');
    return res.status(401).json({ error: 'Contrasena incorrecta' });
  }

  if (!password || !samePassword(password, expected)) {
    console.warn(`[wa/login] intento fallido desde ${ip}`);
    return res.status(401).json({ error: 'Contrasena incorrecta' });
  }

  try {
    const token = await makeToken();
    setAuthCookie(res, token);
    // Login bueno: le devolvemos el presupuesto de intentos al dueno.
    attempts.delete(ip);
    return res.status(200).json({ ok: true });
  } catch (err) {
    console.error('[wa/login] no pude emitir el token:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
