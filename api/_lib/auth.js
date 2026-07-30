import { createHash, createHmac, timingSafeEqual } from 'node:crypto';

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

/* ------------------------------------------------------------------ *
 * Token de la extension de Chrome
 *
 * La cookie del panel es SameSite=Strict a proposito, asi que NO viaja en una
 * peticion que sale desde facebook.com ni desde el service worker de la
 * extension. Para eso existe EXTENSION_TOKEN: un secreto aparte, solo para los
 * dos endpoints de grupos, que el dueno pega una vez en el popup.
 *
 * Es un secreto distinto de PANEL_PASSWORD a proposito: vive en el disco de una
 * extension de Chrome, y si se filtra se rota solo (cambiar el env) sin tocar la
 * clave del panel ni cerrar la sesion del navegador.
 * ------------------------------------------------------------------ */

/**
 * Un token corto es un token adivinable. 24 caracteres es el minimo que
 * aceptamos; lo recomendado es `openssl rand -hex 32` (64 chars).
 */
const EXTENSION_TOKEN_MIN_LENGTH = 24;

/** `Authorization: Bearer xxx` -> "xxx". null si no vino la cabecera. */
function readBearer(req) {
  const header = req?.headers?.authorization;
  if (typeof header !== 'string') return null;
  const m = /^Bearer[ \t]+(.+)$/i.exec(header.trim());
  return m ? m[1].trim() : null;
}

/** Fail-closed: sin EXTENSION_TOKEN (o demasiado corto) este camino no existe. */
export function isExtensionConfigured() {
  const token = process.env.EXTENSION_TOKEN;
  return typeof token === 'string' && token.trim().length >= EXTENSION_TOKEN_MIN_LENGTH;
}

/**
 * Comparacion en tiempo constante. Se compara el sha256 de cada lado y no las
 * cadenas: timingSafeEqual exige la misma longitud, y chequear longitudes antes
 * filtraria el largo del secreto. Los digests siempre miden 32 bytes.
 */
export function verifyExtensionToken(given) {
  if (!isExtensionConfigured() || typeof given !== 'string' || !given) return false;
  const a = createHash('sha256').update(given, 'utf8').digest();
  const b = createHash('sha256').update(process.env.EXTENSION_TOKEN.trim(), 'utf8').digest();
  return timingSafeEqual(a, b);
}

/**
 * Gate de los endpoints que tambien usa la extension:
 * `if (!requirePanelOrExtensionAuth(req, res)) return;`
 *
 * Con cabecera Authorization manda el token y NO se cae a la cookie: un Bearer
 * invalido es un intento explicito y se responde 401 en vez de dejarlo seguir
 * probando por otra puerta. Sin cabecera, es la cookie del panel de siempre.
 */
export function requirePanelOrExtensionAuth(req, res) {
  const bearer = readBearer(req);
  if (bearer === null) return requireAuth(req, res);

  if (!isExtensionConfigured()) {
    console.error(
      '[auth] EXTENSION_TOKEN no esta configurado (o mide menos de %d caracteres): se rechaza el Bearer.',
      EXTENSION_TOKEN_MIN_LENGTH
    );
    res.status(503).json({ error: 'EXTENSION_TOKEN no configurado en el servidor' });
    return false;
  }
  if (!verifyExtensionToken(bearer)) {
    res.status(401).json({ error: 'Token de extension invalido' });
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
