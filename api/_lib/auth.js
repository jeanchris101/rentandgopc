import { createHmac, timingSafeEqual } from 'node:crypto';

// Single-owner panel auth: one password (PANEL_PASSWORD) exchanged for a signed
// cookie (PANEL_SECRET). No user table, no sessions to store.
export const COOKIE_NAME = 'rg_panel';
const MAX_AGE_SECONDS = 60 * 60 * 24 * 30; // 30 days

export function isConfigured() {
  return Boolean(process.env.PANEL_PASSWORD && process.env.PANEL_SECRET);
}

function sign(payloadB64) {
  const secret = process.env.PANEL_SECRET;
  if (!secret) throw new Error('PANEL_SECRET no configurado');
  return createHmac('sha256', secret).update(payloadB64).digest('hex');
}

/** base64url({exp}).hexsig — valid for 30 days. Throws if PANEL_SECRET is unset. */
export function makeToken() {
  const payload = Buffer.from(
    JSON.stringify({ exp: Date.now() + MAX_AGE_SECONDS * 1000 })
  ).toString('base64url');
  return `${payload}.${sign(payload)}`;
}

/** Signature + expiry check. Never throws; anything malformed is just false. */
export function verifyToken(token) {
  try {
    if (!process.env.PANEL_SECRET || typeof token !== 'string') return false;

    const dot = token.lastIndexOf('.');
    if (dot <= 0) return false;

    const payloadB64 = token.slice(0, dot);
    const given = Buffer.from(token.slice(dot + 1), 'hex');
    const expected = Buffer.from(sign(payloadB64), 'hex');
    // timingSafeEqual throws on length mismatch, and a wrong length is a fail anyway.
    if (given.length !== expected.length) return false;
    if (!timingSafeEqual(given, expected)) return false;

    const payload = JSON.parse(Buffer.from(payloadB64, 'base64url').toString('utf8'));
    return typeof payload.exp === 'number' && payload.exp > Date.now();
  } catch {
    return false;
  }
}

/** Constant-time password check for the login route. */
export function checkPassword(input) {
  const expected = process.env.PANEL_PASSWORD;
  if (!expected || typeof input !== 'string') return false;
  const a = Buffer.from(input, 'utf8');
  const b = Buffer.from(expected, 'utf8');
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

// Vercel parses cookies for us; the header fallback keeps this usable elsewhere.
function readCookie(req, name) {
  const parsed = req?.cookies?.[name];
  if (parsed) return parsed;

  const header = req?.headers?.cookie;
  if (!header) return null;
  for (const part of header.split(';')) {
    const eq = part.indexOf('=');
    if (eq < 0) continue;
    if (part.slice(0, eq).trim() === name) {
      return decodeURIComponent(part.slice(eq + 1).trim());
    }
  }
  return null;
}

/**
 * Gate for every panel handler: `if (!requireAuth(req, res)) return;`
 * Fail-closed — with PANEL_PASSWORD/PANEL_SECRET missing this denies with 503
 * instead of letting `undefined === undefined` wave requests through.
 */
export function requireAuth(req, res) {
  if (!isConfigured()) {
    console.error('PANEL_PASSWORD/PANEL_SECRET are not set - refusing panel access');
    res.status(503).json({ error: 'Not configured' });
    return false;
  }
  if (!verifyToken(readCookie(req, COOKIE_NAME))) {
    res.status(401).json({ error: 'Unauthorized' });
    return false;
  }
  return true;
}

// Never clobber a Set-Cookie another handler already queued.
function appendSetCookie(res, value) {
  const previous = typeof res.getHeader === 'function' ? res.getHeader('Set-Cookie') : null;
  if (!previous) res.setHeader('Set-Cookie', value);
  else res.setHeader('Set-Cookie', Array.isArray(previous) ? [...previous, value] : [previous, value]);
}

export function setAuthCookie(res, token) {
  appendSetCookie(
    res,
    `${COOKIE_NAME}=${token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=${MAX_AGE_SECONDS}`
  );
}

export function clearAuthCookie(res) {
  appendSetCookie(res, `${COOKIE_NAME}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0`);
}
