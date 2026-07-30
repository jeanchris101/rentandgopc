/**
 * Despachador compartido por los tres endpoints agrupados de /api.
 *
 * POR QUE EXISTE ESTO
 * El proyecto esta en el plan Hobby de Vercel, cuyo tope es 12 funciones
 * serverless por despliegue. Con un archivo por ruta ibamos por 16 y el build
 * fallaba entero. Cada carpeta pasa a tener UN archivo `[action].js` que reparte
 * a los handlers, que ahora viven en `api/_lib/` — los archivos de `_lib` no son
 * endpoints, asi que no cuentan como funciones.
 *
 * LAS URLS NO CAMBIAN. Vercel enruta cualquier `/api/wa/loquesea` que no exista
 * como archivo hacia `api/wa/[action].js`. La reescritura que genera el builder
 * (verificada contra @vercel/fs-detectors, no supuesta) es:
 *
 *   { src: "^/api/wa/([^/]+)$", dest: "/api/wa/[action]?action=$1", check: true }
 *
 * Dos consecuencias que conviene tener escritas:
 *
 *   1. El nombre del archivo tiene que ser `[action].js` y NO `[...action].js`.
 *      Con la sintaxis de catch-all el builder genera `?...action=$1` — con los
 *      tres puntos dentro del nombre del parametro — asi que `req.query.action`
 *      llegaria vacio. Ademas `([^/]+)` solo casa UN segmento igualmente, o sea
 *      que el catch-all no compra nada aqui.
 *
 *   2. `check: true` va DESPUES del sistema de archivos, asi que
 *      `/api/wa/webhook` sigue cayendo en `api/wa/webhook.js` (que se quedo
 *      aparte porque necesita `bodyParser: false` para el HMAC y
 *      `maxDuration = 300` para el delay del auto-reply). El despachador nunca
 *      lo ve.
 */

/** Ruta larguisima en el 404 = log ruidoso. El nombre real nunca pasa de esto. */
const MAX_ACTION_LENGTH = 64;

function safeDecode(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value; // %ZZ y demas basura: se usa tal cual y terminara en 404
  }
}

/**
 * El ultimo segmento de la ruta pedida, o '' si lo que hay es el marcador
 * `[action]` (o sea: Vercel ya reescribio la URL y la accion real viaja en la
 * query).
 */
function actionFromPath(req) {
  const raw = typeof req?.url === 'string' ? req.url : '';
  const path = raw.split('?')[0].split('#')[0];
  const last = path.split('/').filter(Boolean).pop() || '';
  const decoded = safeDecode(last).trim();
  return decoded.startsWith('[') ? '' : decoded;
}

/**
 * Que accion se pidio.
 *
 * La ruta manda sobre la query a proposito: es lo que el cliente escribio de
 * verdad, y asi un `/api/wa/threads?action=send` no puede reapuntar la llamada.
 * La query es el respaldo para cuando el runtime entrega la URL ya reescrita.
 * Se leen las dos formas del parametro (`action` y `...action`) para que un
 * futuro renombre del archivo no rompa el despacho en silencio.
 *
 * Nota: aunque el despacho saliera mal, no hay escalada posible — cada handler
 * conserva su propia puerta (requireAuth / requirePanelOrExtensionAuth / la
 * politica publica de lead/capture), ninguna se aplica aqui.
 */
export function resolveAction(req) {
  const fromPath = actionFromPath(req);
  if (fromPath) return fromPath;

  const query = req?.query || {};
  const raw = query.action !== undefined ? query.action : query['...action'];
  const value = Array.isArray(raw) ? raw[0] : raw;
  return typeof value === 'string' ? safeDecode(value).trim() : '';
}

/**
 * `dispatch(routes, req, res, prefix)` — busca el handler y lo llama tal cual.
 *
 * No toca `Content-Type`, ni cabeceras, ni el cuerpo: `qr` devuelve bytes de
 * imagen y `capture` maneja su propio CORS, asi que imponer JSON desde aqui
 * romperia los dos. Cada handler sigue poniendo su `Cache-Control`, su codigo de
 * estado y su auth exactamente como antes.
 */
export async function dispatch(routes, req, res, prefix) {
  const action = resolveAction(req);

  // hasOwnProperty y no `routes[action]` a secas: sin este filtro un
  // `?action=constructor` (o `toString`, o `__proto__`) resolveria a una funcion
  // heredada de Object.prototype y la llamariamos con (req, res).
  const handler = Object.prototype.hasOwnProperty.call(routes, action) ? routes[action] : null;

  if (typeof handler !== 'function') {
    // vercel.json le pone `public, max-age=3600` a TODO. Un 404 cacheado una
    // hora es una ruta nueva que tarda una hora en empezar a existir.
    res.setHeader('Cache-Control', 'no-store');
    const shown = action.slice(0, MAX_ACTION_LENGTH);
    return res.status(404).json({ error: `Ruta desconocida: /${prefix}/${shown}` });
  }

  return handler(req, res);
}
