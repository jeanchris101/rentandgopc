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
      throw new Error(
        `WAHA ${method} ${path}: ${res.status} ${res.statusText}${detail ? ` - ${detail}` : ''}`
      );
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
      throw new Error(`WAHA ${method} ${path}: sin respuesta en ${TIMEOUT_MS}ms`);
    }
    if (err instanceof Error && err.message.startsWith('WAHA ')) throw err;
    throw new Error(`WAHA ${method} ${path}: ${err?.message || 'network error'}`);
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
