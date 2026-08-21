// Thin HTTP client for WAHA (https://waha.devlike.pro/docs/).
// Env: WAHA_URL, WAHA_API_KEY, WAHA_SESSION (defaults to 'rentandgo').

const DEFAULT_SESSION = 'rentandgo';
const TIMEOUT_MS = 15000;

function env() {
  const base = process.env.WAHA_URL;
  // Fail loudly instead of firing requests at "undefined/api/sendText".
  if (!base) throw new Error('WAHA_URL no configurado');
  return {
    base: base.replace(/\/+$/, ''),
    apiKey: process.env.WAHA_API_KEY || '',
    session: sessionName(),
  };
}

export function sessionName() {
  return process.env.WAHA_SESSION || DEFAULT_SESSION;
}

/**
 * @param {string} path
 * @param {{ method?: string, body?: object, raw?: boolean }} [opts]
 *   raw:true resolves to { contentType, buffer } instead of parsed JSON.
 */
async function request(path, { method = 'POST', body, raw = false } = {}) {
  const { base, apiKey } = env();
  const controller = new AbortController();
  // WAHA hangs when the paired phone is offline; a serverless function cannot.
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(`${base}${path}`, {
      method,
      headers: {
        Accept: raw ? '*/*' : 'application/json',
        ...(body ? { 'Content-Type': 'application/json' } : {}),
        ...(apiKey ? { 'X-Api-Key': apiKey } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (!res.ok) {
      const detail = (await res.text().catch(() => '')).slice(0, 300);
      // El codigo viaja en el Error a proposito: un 404 de /api/sessions/x
      // significa "esa sesion no existe todavia" — que es un ESTADO normal y
      // arreglable — mientras que un fallo de red significa "WAHA esta caido".
      // Sin distinguirlos, la pantalla de emparejamiento no puede decidir si
      // arrancar la sesion o pedirle al dueno que revise el servidor.
      const err = new Error(
        `WAHA ${method} ${path}: ${res.status} ${res.statusText}${detail ? ` - ${detail}` : ''}`
      );
      err.status = res.status;
      err.detail = detail;
      throw err;
    }

    if (raw) {
      return {
        contentType: res.headers.get('content-type') || 'application/octet-stream',
        buffer: Buffer.from(await res.arrayBuffer()),
      };
    }

    const text = await res.text();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      const timeout = new Error(`WAHA ${method} ${path}: sin respuesta en ${TIMEOUT_MS}ms`);
      timeout.status = 0; // 0 = no hubo respuesta HTTP, o sea WAHA no contesta
      throw timeout;
    }
    if (err instanceof Error && err.message.startsWith('WAHA ')) throw err;
    const network = new Error(`WAHA ${method} ${path}: ${err?.message || 'network error'}`);
    network.status = 0;
    throw network;
  } finally {
    clearTimeout(timer);
  }
}

/** POST /api/sendText — opts: { replyTo, linkPreview }. Resolves to the sent message. */
export async function sendText(chatId, text, opts = {}) {
  const { session } = env();
  const body = { session, chatId, text: String(text ?? '') };
  if (opts.replyTo) body.reply_to = opts.replyTo;
  if (opts.linkPreview !== undefined) body.linkPreview = Boolean(opts.linkPreview);
  return await request('/api/sendText', { body });
}

/** POST /api/sendImage — the image must be reachable by the WAHA host, not by us. */
export async function sendImage(chatId, imageUrl, caption = '', opts = {}) {
  const { session } = env();
  const file = { url: imageUrl };
  if (opts.mimetype) file.mimetype = opts.mimetype;
  if (opts.filename) file.filename = opts.filename;
  return await request('/api/sendImage', { body: { session, chatId, file, caption } });
}

/** POST /api/sendSeen — blue ticks. messageIds is optional (marks the whole chat). */
export async function markSeen(chatId, messageIds) {
  const { session } = env();
  const body = { session, chatId };
  if (Array.isArray(messageIds) && messageIds.length) body.messageIds = messageIds;
  return await request('/api/sendSeen', { body });
}

/** startTyping, wait, stopTyping. Capped so it can never eat the function budget. */
export async function typing(chatId, ms = 1500) {
  const { session } = env();
  const wait = Math.min(Math.max(Number(ms) || 0, 0), 8000);
  await request('/api/startTyping', { body: { session, chatId } });
  try {
    await new Promise((resolve) => setTimeout(resolve, wait));
  } finally {
    // A stuck "typing..." bubble looks broken to the lead, so always clear it.
    await request('/api/stopTyping', { body: { session, chatId } }).catch(() => {});
  }
}

/** GET /api/sessions/{session} — .status is WORKING | SCAN_QR_CODE | STOPPED | STARTING | FAILED. */
export async function sessionStatus() {
  const { session } = env();
  const data = await request(`/api/sessions/${encodeURIComponent(session)}`, { method: 'GET' });
  return data && typeof data === 'object' ? data : { name: session, status: 'UNKNOWN' };
}

/** GET URL of the pairing QR. Needs the X-Api-Key header, so proxy it via fetchQr(). */
export function qrUrl() {
  const { base, session } = env();
  return `${base}/api/${encodeURIComponent(session)}/auth/qr?format=image`;
}

/** QR bytes for a panel route to stream back, keeping WAHA_API_KEY server-side. */
export async function fetchQr() {
  const { session } = env();
  return await request(`/api/${encodeURIComponent(session)}/auth/qr?format=image`, {
    method: 'GET',
    raw: true,
  });
}

/* ------------------------------------------------------------------ *
 * Ciclo de vida de la sesion
 *
 * Docs: https://waha.devlike.pro/docs/how-to/sessions/
 *
 *   STOPPED -> STARTING -> SCAN_QR_CODE -> WORKING
 *                              |               ^
 *                              v               |
 *                     PASSKEY_REQUIRED / PASSKEY_CONFIRMATION_REQUIRED
 *                              |
 *                              v
 *                           FAILED   (6 QR vencidos: hay que rearrancar)
 *
 * Lo que faltaba aqui era todo el lado izquierdo: sin una forma de ARRANCAR la
 * sesion, un WAHA recien desplegado (o rearrancado con la sesion borrada) se
 * queda en STOPPED / inexistente para siempre y el panel gira sin decir nada.
 * ------------------------------------------------------------------ */

/**
 * Como GET /api/sessions/{name}, pero un 404 se devuelve como DATO
 * (`status: 'NOT_FOUND'`) en vez de como excepcion: "la sesion no existe" es
 * algo que sabemos arreglar solos, no una caida del servidor.
 * Cualquier otro fallo (red, 500, timeout) sigue lanzando.
 */
export async function sessionInfo() {
  const { session } = env();
  try {
    const data = await request(`/api/sessions/${encodeURIComponent(session)}`, { method: 'GET' });
    if (typeof data === 'string') return { name: session, status: data.toUpperCase() };
    if (data && typeof data === 'object') {
      const raw = data.status || data.state || 'UNKNOWN';
      return { ...data, name: data.name || session, status: String(raw).toUpperCase() };
    }
    return { name: session, status: 'UNKNOWN' };
  } catch (err) {
    if (err?.status === 404) return { name: session, status: 'NOT_FOUND' };
    throw err;
  }
}

/**
 * Arranca la sesion. POST /api/sessions/{name}/start es idempotente segun las
 * docs ("you can call it multiple times, and it'll start the session only if
 * it's not running"), asi que llamarlo de mas no rompe nada.
 *
 * Si la sesion nunca se creo, ese start da 404 y caemos a POST /api/sessions.
 * OJO: se manda `{ name, start: true }` y NADA de `config`. WAHA aplica los
 * WHATSAPP_HOOK_* globales del contenedor a las sesiones que no traen webhooks
 * propios; mandar un `config` vacio los pisaria y el sitio dejaria de recibir
 * los mensajes entrantes.
 *
 * @returns {Promise<{ created: boolean }>}
 */
export async function startSession() {
  const { session } = env();
  try {
    await request(`/api/sessions/${encodeURIComponent(session)}/start`, { method: 'POST' });
    return { created: false };
  } catch (err) {
    if (err?.status !== 404) throw err;
    await request('/api/sessions', { method: 'POST', body: { name: session, start: true } });
    return { created: true };
  }
}

/**
 * POST /api/{session}/auth/request-code — emparejar con el NUMERO en vez del QR.
 * Docs: https://waha.devlike.pro/docs/how-to/sessions/#get-pairing-code
 *
 * El numero va en digitos pelados, con codigo de pais y sin '+' ni espacios
 * (el ejemplo de las docs es "12132132130"). La respuesta es { code: "ABCD-ABCD" },
 * que es lo que el dueno escribe en WhatsApp > Dispositivos vinculados >
 * Vincular con numero de telefono.
 */
export async function requestPairingCode(phoneNumber) {
  const { session } = env();
  const digits = String(phoneNumber ?? '').replace(/\D/g, '');
  if (!digits) throw new Error('WAHA request-code: falta el numero de telefono');
  const data = await request(`/api/${encodeURIComponent(session)}/auth/request-code`, {
    body: { phoneNumber: digits },
  });
  const raw = data && typeof data === 'object' ? data.code : data;
  return { code: raw ? String(raw) : '', phoneNumber: digits };
}

/**
 * Motores que implementan POST /api/{session}/auth/request-code, segun la tabla
 * de https://waha.devlike.pro/docs/how-to/engines/#features — a dia de hoy los
 * cuatro. NOWEB (el nuestro) lo trae desde 2025.7.5 ("NOWEB - login via phone").
 */
const PAIRING_ENGINES = new Set(['NOWEB', 'WEBJS', 'WPP', 'GOWS']);

/** Nombre del motor tal como lo reporta la sesion, con el env como respaldo. */
export function engineOf(info) {
  const fromInfo =
    info && typeof info === 'object'
      ? typeof info.engine === 'string'
        ? info.engine
        : info.engine && typeof info.engine === 'object'
          ? info.engine.engine
          : null
      : null;
  const name = fromInfo || process.env.WAHA_ENGINE || 'NOWEB';
  return String(name).toUpperCase();
}

/** ¿Este motor sabe emparejar por numero? Si no, el panel no ofrece el boton. */
export function engineSupportsPairing(engine) {
  return PAIRING_ENGINES.has(String(engine || '').toUpperCase());
}
