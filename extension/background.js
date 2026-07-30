/**
 * background.js — el unico que habla con rentandgopc.com.
 *
 * Por que aqui y no en el content script:
 *   1. El token. El content script corre dentro de facebook.com; aunque este en
 *      un mundo aislado, el token NUNCA se le manda. Vive solo en el service
 *      worker y en el popup.
 *   2. CORS. Un fetch desde el service worker con host_permissions no pasa por
 *      CORS ni por preflight, asi que la API no necesita cabeceras nuevas ni
 *      abrirse a facebook.com.
 *
 * Cachea el plan unos minutos en chrome.storage.local (no en memoria: el worker
 * de MV3 se apaga solo cada rato). Si la red falla, sirve la copia vieja marcada
 * como `stale` para que el panel siga funcionando en vez de romper la pagina.
 *
 * Aqui no hay temporizadores, ni alarmas, ni nada que publique: los unicos
 * efectos son leer /api/groups/plan, escribir /api/groups/mark cuando el dueno
 * dice "ya lo publique", y bajar una foto.
 */

const DEFAULT_BASE_URL = 'https://www.rentandgopc.com';

/** Minutos que un plan se considera fresco antes de volver a pedirlo. */
const FRESH_MS = 5 * 60 * 1000;

/** Carpeta dentro de Descargas donde caen las fotos. */
const DOWNLOAD_DIR = 'rentandgo';

const CACHE_KEY = 'planCache';

/* ------------------------------------------------------------------ *
 * Config
 * ------------------------------------------------------------------ */

function cleanBaseUrl(value) {
  const raw = String(value || '').trim().replace(/\/+$/, '');
  if (!raw) return DEFAULT_BASE_URL;
  if (!/^https:\/\/[^/\s]+$/i.test(raw)) return null;
  return raw;
}

async function getConfig() {
  const stored = await chrome.storage.local.get(['baseUrl', 'token']);
  return {
    baseUrl: cleanBaseUrl(stored.baseUrl),
    token: String(stored.token || '').trim(),
  };
}

/** YYYY-MM-DD en hora dominicana, igual que todayInTz() del servidor. */
function todayInDR() {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Santo_Domingo',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date());
  } catch (e) {
    return new Date().toISOString().slice(0, 10);
  }
}

/* ------------------------------------------------------------------ *
 * API
 * ------------------------------------------------------------------ */

/**
 * Devuelve { ok:true, data } o { ok:false, error, code }. Nunca lanza: quien
 * llama es un content script metido en facebook.com y una excepcion suelta ahi
 * no le sirve a nadie.
 *
 * `code` es para el popup, que pinta distinto cada fallo:
 *   no-token | bad-base | offline | unauthorized | not-configured | http | body
 */
async function apiFetch(path, options) {
  const cfg = await getConfig();
  if (cfg.baseUrl === null) {
    return { ok: false, code: 'bad-base', error: 'La URL base tiene que ser https, sin barra final. Revisala en el popup.' };
  }
  if (!cfg.token) {
    return { ok: false, code: 'no-token', error: 'Falta el token. Abre el popup de la extension y pegalo.' };
  }

  const headers = { Authorization: 'Bearer ' + cfg.token, Accept: 'application/json' };
  const init = {
    method: (options && options.method) || 'GET',
    headers,
    // Sin cookies: el token es la unica credencial que mandamos.
    credentials: 'omit',
    cache: 'no-store',
  };
  if (options && options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.body);
  }

  let res;
  try {
    res = await fetch(cfg.baseUrl + path, init);
  } catch (e) {
    return { ok: false, code: 'offline', error: 'No hay conexion con ' + cfg.baseUrl + '.' };
  }

  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    data = null;
  }

  if (res.status === 401 || res.status === 403) {
    return { ok: false, code: 'unauthorized', error: 'El token no sirve. Generalo otra vez y pegalo en el popup.' };
  }
  if (res.status === 503) {
    return {
      ok: false,
      code: 'not-configured',
      error: 'El servidor dice que le falta EXTENSION_TOKEN. Agregalo en Vercel y redespliega.',
    };
  }
  if (!res.ok) {
    const msg = (data && (data.error || data.message)) || 'El servidor respondio ' + res.status + '.';
    return { ok: false, code: 'http', error: String(msg), status: res.status };
  }
  if (!data || typeof data !== 'object') {
    return { ok: false, code: 'body', error: 'Esa URL no devolvio JSON. Revisa la URL base en el popup.' };
  }
  return { ok: true, data };
}

/* ------------------------------------------------------------------ *
 * Plan (con cache)
 * ------------------------------------------------------------------ */

async function readCache() {
  const stored = await chrome.storage.local.get([CACHE_KEY]);
  const cache = stored[CACHE_KEY];
  if (!cache || typeof cache !== 'object' || !cache.plan) return null;
  // Un plan de ayer no sirve ni como copia vieja: el cooldown cambio de dia.
  if (cache.plan.date !== todayInDR()) return null;
  return cache;
}

/**
 * getPlan({ force }) -> { ok, plan, fetchedAt, stale, error, code }
 *
 * `stale:true` significa "esto es lo ultimo que pude bajar, pero el intento de
 * ahora fallo". El panel lo dice en pantalla en vez de mentir con datos viejos.
 */
async function getPlan(params) {
  const force = Boolean(params && params.force);
  const cache = await readCache();

  if (cache && !force && Date.now() - cache.fetchedAt < FRESH_MS) {
    return { ok: true, plan: cache.plan, fetchedAt: cache.fetchedAt, stale: false };
  }

  const res = await apiFetch('/api/groups/plan');
  if (res.ok) {
    const fetchedAt = Date.now();
    await chrome.storage.local.set({ [CACHE_KEY]: { plan: res.data, fetchedAt } });
    return { ok: true, plan: res.data, fetchedAt, stale: false };
  }

  if (cache) {
    return { ok: true, plan: cache.plan, fetchedAt: cache.fetchedAt, stale: true, error: res.error, code: res.code };
  }
  return { ok: false, error: res.error, code: res.code };
}

async function markPosted(params) {
  const body = {
    groupCode: String((params && params.groupCode) || ''),
    propertySlug: String((params && params.propertySlug) || ''),
    ref: String((params && params.ref) || ''),
    skipped: (params && params.skipped) === true,
  };
  if (!body.groupCode || !body.propertySlug) {
    return { ok: false, error: 'Faltan datos para registrar el post.' };
  }

  const res = await apiFetch('/api/groups/mark', { method: 'POST', body });
  if (!res.ok) return res;

  // El plan cambio: el grupo entro en cooldown. Se refresca de una para que el
  // panel y el popup no sigan ofreciendo lo mismo.
  await chrome.storage.local.remove(CACHE_KEY);
  const plan = await getPlan({ force: true });
  return { ok: true, data: res.data, plan: plan.ok ? plan.plan : null };
}

/* ------------------------------------------------------------------ *
 * Descarga de la foto
 * ------------------------------------------------------------------ */

/** Solo letras, numeros, punto, guion y guion bajo. Sin ".." ni rutas. */
function safeFilename(name) {
  const base = String(name || '').split(/[\\/]/).pop().replace(/[^A-Za-z0-9._-]/g, '-').replace(/^\.+/, '');
  return base || 'foto.jpg';
}

/**
 * Baja la foto del post. La URL se valida contra la URL base configurada: asi
 * la extension solo puede bajar archivos del sitio del dueno, aunque alguien
 * lograra mandarle un mensaje raro al worker.
 */
async function downloadImage(params) {
  const cfg = await getConfig();
  if (cfg.baseUrl === null) return { ok: false, error: 'URL base invalida.' };

  const url = String((params && params.url) || '');
  if (!url.startsWith(cfg.baseUrl + '/')) {
    return { ok: false, error: 'Esa foto no es del sitio configurado. No la bajo.' };
  }

  try {
    const id = await chrome.downloads.download({
      url,
      filename: DOWNLOAD_DIR + '/' + safeFilename(params && params.filename ? params.filename : url),
      conflictAction: 'uniquify',
      saveAs: false,
    });
    return { ok: true, id };
  } catch (e) {
    return { ok: false, error: 'No pude bajar la foto: ' + (e && e.message ? e.message : 'error desconocido') };
  }
}

/** Abre la carpeta de Descargas en el archivo recien bajado. */
async function showDownload(params) {
  const id = Number(params && params.id);
  if (!Number.isInteger(id)) return { ok: false, error: 'Descarga desconocida.' };
  try {
    chrome.downloads.show(id);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: 'No pude abrir la carpeta.' };
  }
}

/* ------------------------------------------------------------------ *
 * Mensajes
 * ------------------------------------------------------------------ */

/**
 * Solo se atiende a nuestras propias piezas: el popup (sin tab) y el content
 * script, que por manifest solo corre en grupos de Facebook. Sin
 * `externally_connectable`, ninguna pagina puede mandar mensajes aqui.
 */
function senderAllowed(sender) {
  if (!sender || sender.id !== chrome.runtime.id) return false;
  if (!sender.tab) return true;
  return typeof sender.url === 'string' && sender.url.startsWith('https://www.facebook.com/groups/');
}

const HANDLERS = {
  RGPC_GET_PLAN: getPlan,
  RGPC_MARK: markPosted,
  RGPC_DOWNLOAD_IMAGE: downloadImage,
  RGPC_SHOW_DOWNLOAD: showDownload,
  RGPC_STATUS: async (params) => {
    const cfg = await getConfig();
    const plan = await getPlan({ force: Boolean(params && params.force) });
    return {
      ok: true,
      baseUrl: cfg.baseUrl === null ? '' : cfg.baseUrl,
      hasToken: Boolean(cfg.token),
      plan: plan.ok ? plan.plan : null,
      fetchedAt: plan.fetchedAt || null,
      stale: Boolean(plan.stale),
      error: plan.error || null,
      code: plan.code || null,
    };
  },
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!senderAllowed(sender)) return false;
  const handler = msg && typeof msg.type === 'string' ? HANDLERS[msg.type] : null;
  if (!handler) return false;

  handler(msg.params || {})
    .then((result) => sendResponse(result))
    .catch((e) => sendResponse({ ok: false, error: String((e && e.message) || e) }));
  return true; // respuesta asincrona
});

/** Primera instalacion: deja la URL base por defecto puesta. */
chrome.runtime.onInstalled.addListener(async () => {
  const stored = await chrome.storage.local.get(['baseUrl']);
  if (!stored.baseUrl) await chrome.storage.local.set({ baseUrl: DEFAULT_BASE_URL });
});
