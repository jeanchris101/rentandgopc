/**
 * Las 14 rutas de /api tienen que seguir respondiendo igual despues de meterlas
 * en 3 funciones serverless.
 *
 *   node --test test/api-routes.test.mjs
 *
 * POR QUE HAY UN SANDBOX Y NO SE IMPORTA `../api/...` DIRECTAMENTE
 * Los handlers son ESM en archivos `.js` y el package.json de la raiz no dice
 * `"type": "module"` — en Vercel da igual (el builder los detecta y los empaqueta
 * con esbuild), pero `node` local los leeria como CommonJS y reventaria en el
 * primer `export`. Anadir `"type": "module"` a la raiz cambiaria como Vercel
 * construye el proyecto, y lo ultimo que queremos mientras arreglamos un build
 * roto es tocar como se construye.
 *
 * Asi que la prueba se copia `api/` y `automation/data/` a un directorio
 * temporal con su propio package.json `"type": "module"` y un `@vercel/blob` de
 * mentira. Efecto util de paso: ninguna prueba habla con Blob ni con WAHA de
 * verdad.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

/* ------------------------------------------------------------------ *
 * Sandbox
 * ------------------------------------------------------------------ */

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SANDBOX = fs.mkdtempSync(path.join(os.tmpdir(), 'rg-api-test-'));

process.on('exit', () => {
  try {
    fs.rmSync(SANDBOX, { recursive: true, force: true });
  } catch {
    /* un temp que no se borra no puede tumbar la suite */
  }
});

function write(relative, contents) {
  const target = path.join(SANDBOX, relative);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, contents);
}

fs.cpSync(path.join(REPO, 'api'), path.join(SANDBOX, 'api'), { recursive: true });
fs.cpSync(
  path.join(REPO, 'automation', 'data'),
  path.join(SANDBOX, 'automation', 'data'),
  { recursive: true }
);

write('package.json', JSON.stringify({ name: 'rg-api-sandbox', private: true, type: 'module' }));

// @vercel/blob de mentira: devuelve "no hay nada guardado", que es justo el
// arranque en frio que los handlers ya saben manejar.
write(
  'node_modules/@vercel/blob/package.json',
  JSON.stringify({ name: '@vercel/blob', version: '0.0.0-test', type: 'module', main: 'index.js' })
);
write(
  'node_modules/@vercel/blob/index.js',
  `export const calls = { put: [], list: [] };
export async function put(pathname, body, options) {
  calls.put.push({ pathname, body, options });
  return { pathname, url: 'https://blob.test/' + pathname };
}
export async function list(options) {
  calls.list.push(options);
  return { blobs: [], hasMore: false, cursor: undefined };
}
export async function head() { return null; }
export async function del() {}
`
);

write(
  'node_modules/@vercel/functions/package.json',
  JSON.stringify({ name: '@vercel/functions', version: '0.0.0-test', type: 'module', main: 'index.js' })
);
write(
  'node_modules/@vercel/functions/index.js',
  `export function waitUntil(promise) { Promise.resolve(promise).catch(() => {}); }
`
);

const load = (relative) => import(pathToFileURL(path.join(SANDBOX, relative)).href);

const waEndpoint = (await load('api/wa/[action].js')).default;
const groupsEndpoint = (await load('api/groups/[action].js')).default;
const leadEndpoint = (await load('api/lead/[action].js')).default;
const { resolveAction } = await load('api/_lib/dispatch.js');
const { COOKIE_NAME } = await load('api/_lib/auth.js');

/* ------------------------------------------------------------------ *
 * Dobles de req / res
 * ------------------------------------------------------------------ */

const HOST = 'rentandgopuntacana.com';
const PASSWORD = 'clave-de-prueba-larga';
const SECRET = 'secreto-de-prueba-para-firmar-el-token';

/**
 * Un req como el que arma Vercel DESPUES de la reescritura: la accion llega en
 * `req.query.action` y la URL trae el marcador `[action]`. Es el caso que mas
 * importa que funcione, asi que es el que se usa por defecto.
 */
function makeReq({ prefix, action, method = 'GET', headers = {}, query = {}, body, cookie, ip }) {
  return {
    method,
    url: `/${prefix}/[action]?action=${encodeURIComponent(action)}`,
    headers: {
      host: HOST,
      ...(cookie ? { cookie: `${COOKIE_NAME}=${cookie}` } : {}),
      ...(ip ? { 'x-forwarded-for': ip } : {}),
      ...headers,
    },
    query: { action, ...query },
    cookies: {},
    socket: { remoteAddress: ip || '127.0.0.1' },
    body,
  };
}

function makeRes() {
  return {
    statusCode: null,
    headers: {},
    body: undefined,
    ended: false,
    setHeader(key, value) {
      this.headers[String(key).toLowerCase()] = value;
      return this;
    },
    getHeader(key) {
      return this.headers[String(key).toLowerCase()];
    },
    status(code) {
      this.statusCode = code;
      return this;
    },
    json(payload) {
      this.body = payload;
      this.ended = true;
      return this;
    },
    send(payload) {
      this.body = payload;
      this.ended = true;
      return this;
    },
    end() {
      this.ended = true;
      return this;
    },
  };
}

/** Llama al endpoint agrupado que corresponde y devuelve el res ya escrito. */
async function call(prefix, options) {
  const endpoint =
    prefix === 'api/wa' ? waEndpoint : prefix === 'api/groups' ? groupsEndpoint : leadEndpoint;
  const res = makeRes();
  await endpoint(makeReq({ prefix, ...options }), res);
  return res;
}

const wa = (options) => call('api/wa', options);
const groups = (options) => call('api/groups', options);
const lead = (options) => call('api/lead', options);

function configureAuth() {
  process.env.PANEL_PASSWORD = PASSWORD;
  process.env.PANEL_SECRET = SECRET;
}

function unconfigureAuth() {
  delete process.env.PANEL_PASSWORD;
  delete process.env.PANEL_SECRET;
}

/** Cookie real, emitida por POST /api/wa/login. Nada de firmar a mano. */
async function loginCookie() {
  configureAuth();
  const res = await wa({
    action: 'login',
    method: 'POST',
    body: { password: PASSWORD },
    ip: '10.0.0.250',
  });
  assert.equal(res.statusCode, 200, 'el login de prueba tiene que funcionar');
  const header = res.getHeader('Set-Cookie');
  const raw = Array.isArray(header) ? header[0] : header;
  return String(raw).split(';')[0].slice(COOKIE_NAME.length + 1);
}

configureAuth();
const COOKIE = await loginCookie();

/* ------------------------------------------------------------------ *
 * resolveAction
 * ------------------------------------------------------------------ */

test('resolveAction lee la accion de la URL reescrita por Vercel', () => {
  assert.equal(
    resolveAction({ url: '/api/wa/[action]?action=threads', query: { action: 'threads' } }),
    'threads'
  );
});

test('resolveAction lee la accion de la ruta cuando la URL llega sin reescribir', () => {
  assert.equal(resolveAction({ url: '/api/wa/threads', query: {} }), 'threads');
  assert.equal(resolveAction({ url: '/api/wa/threads/', query: {} }), 'threads');
  assert.equal(resolveAction({ url: '/api/wa/thread?chatId=1@c.us', query: {} }), 'thread');
});

test('resolveAction acepta la forma "...action" del catch-all', () => {
  assert.equal(
    resolveAction({ url: '/api/wa/[...action]', query: { '...action': 'threads' } }),
    'threads'
  );
});

test('resolveAction: la ruta manda sobre la query', () => {
  // Un ?action= inyectado no puede reapuntar la llamada a otro handler.
  assert.equal(
    resolveAction({ url: '/api/wa/threads?action=send', query: { action: ['send'] } }),
    'threads'
  );
});

/* ------------------------------------------------------------------ *
 * Ruta inexistente -> 404
 * ------------------------------------------------------------------ */

test('ruta inexistente devuelve 404 con {error} y sin cachear', async () => {
  for (const [prefix, fn] of [
    ['api/wa', wa],
    ['api/groups', groups],
    ['api/lead', lead],
  ]) {
    const res = await fn({ action: 'no-existe' });
    assert.equal(res.statusCode, 404, prefix);
    assert.match(res.body.error, /Ruta desconocida/);
    assert.equal(res.getHeader('Cache-Control'), 'no-store');
  }
});

test('el 404 no impone Content-Type (qr devuelve bytes, no JSON)', async () => {
  const res = await wa({ action: 'no-existe' });
  assert.deepEqual(Object.keys(res.headers), ['cache-control']);
});

test('una propiedad heredada de Object.prototype no resuelve a un handler', async () => {
  for (const action of ['constructor', '__proto__', 'toString', 'hasOwnProperty']) {
    const res = await wa({ action });
    assert.equal(res.statusCode, 404, action);
  }
});

test('el webhook no es alcanzable por el despachador', async () => {
  // En produccion nunca llega aqui: api/wa/webhook.js existe como archivo y el
  // sistema de archivos se consulta antes que la ruta dinamica. Esta prueba fija
  // que el despachador tampoco lo sirve por accidente (necesita bodyParser:false
  // y maxDuration=300, que aqui no existen).
  const res = await wa({ action: 'webhook', method: 'POST' });
  assert.equal(res.statusCode, 404);
});

/* ------------------------------------------------------------------ *
 * Sin cookie -> 401 (y 503 si falta la config)
 * ------------------------------------------------------------------ */

const PRIVATE_WA = [
  ['threads', 'GET'],
  ['thread', 'GET'],
  ['send', 'POST'],
  ['lead', 'POST'],
  ['config', 'GET'],
  ['session', 'GET'],
  ['qr', 'GET'],
];

test('las rutas privadas de /api/wa piden cookie', async () => {
  configureAuth();
  for (const [action, method] of PRIVATE_WA) {
    const res = await wa({ action, method, body: {} });
    assert.equal(res.statusCode, 401, `${action} deberia responder 401 sin cookie`);
    assert.equal(res.body.error, 'Unauthorized');
  }
});

test('las rutas de /api/groups piden cookie (o Bearer de la extension)', async () => {
  configureAuth();
  for (const [action, method] of [
    ['plan', 'GET'],
    ['mark', 'POST'],
    ['settings', 'GET'],
  ]) {
    const res = await groups({ action, method, body: {} });
    assert.equal(res.statusCode, 401, `${action} deberia responder 401 sin cookie`);
  }
});

test('/api/lead/list pide cookie', async () => {
  configureAuth();
  const res = await lead({ action: 'list' });
  assert.equal(res.statusCode, 401);
});

test('un Bearer invalido en /api/groups es 401, no se cae a la cookie', async () => {
  configureAuth();
  process.env.EXTENSION_TOKEN = 'x'.repeat(40);
  try {
    const res = await groups({
      action: 'plan',
      headers: { authorization: 'Bearer no-es-el-token' },
      cookie: COOKIE,
    });
    assert.equal(res.statusCode, 401);
  } finally {
    delete process.env.EXTENSION_TOKEN;
  }
});

test('sin PANEL_PASSWORD/PANEL_SECRET las rutas privadas responden 503, no 401', async () => {
  unconfigureAuth();
  try {
    const threads = await wa({ action: 'threads' });
    assert.equal(threads.statusCode, 503);
    assert.equal(threads.body.error, 'Not configured');

    const list = await lead({ action: 'list' });
    assert.equal(list.statusCode, 503);

    const plan = await groups({ action: 'plan' });
    assert.equal(plan.statusCode, 503);
  } finally {
    configureAuth();
  }
});

/* ------------------------------------------------------------------ *
 * Metodo equivocado -> 405
 * ------------------------------------------------------------------ */

test('metodo equivocado devuelve 405 (con cookie valida, para pasar el auth)', async () => {
  const cases = [
    ['api/wa', 'threads', 'POST'],
    ['api/wa', 'thread', 'POST'],
    ['api/wa', 'send', 'GET'],
    ['api/wa', 'lead', 'GET'],
    ['api/wa', 'config', 'DELETE'],
    ['api/wa', 'session', 'POST'],
    ['api/wa', 'status', 'POST'],
    ['api/wa', 'qr', 'POST'],
    ['api/groups', 'plan', 'POST'],
    ['api/groups', 'mark', 'GET'],
    ['api/groups', 'settings', 'DELETE'],
    ['api/lead', 'list', 'POST'],
  ];
  for (const [prefix, action, method] of cases) {
    const res = await call(prefix, { action, method, cookie: COOKIE, body: {} });
    assert.equal(res.statusCode, 405, `${prefix}/${action} con ${method}`);
    assert.equal(res.body.error, 'Method not allowed');
  }
});

test('/api/wa/login rechaza GET con 405 antes de mirar la contrasena', async () => {
  const res = await wa({ action: 'login', method: 'GET' });
  assert.equal(res.statusCode, 405);
});

test('/api/lead/capture rechaza GET con 405', async () => {
  const res = await lead({ action: 'capture', method: 'GET' });
  assert.equal(res.statusCode, 405);
});

/* ------------------------------------------------------------------ *
 * Validaciones de cada handler (prueba de que la logica llego entera)
 * ------------------------------------------------------------------ */

test('las validaciones de cuerpo siguen dando 400 con su mensaje', async () => {
  const cases = [
    ['api/wa', 'thread', 'GET', undefined, /Falta chatId/],
    ['api/wa', 'send', 'POST', {}, /Falta chatId/],
    ['api/wa', 'send', 'POST', { chatId: '1@c.us' }, /vacio/],
    ['api/wa', 'lead', 'POST', {}, /Falta chatId/],
    ['api/wa', 'config', 'POST', {}, /No mandaste nada que cambiar/],
    ['api/wa', 'config', 'POST', { dailyCap: 999 }, /dailyCap/],
    ['api/groups', 'mark', 'POST', {}, /Grupo desconocido/],
    ['api/groups', 'settings', 'POST', { groupsPerDay: 99 }, /fuera de rango/],
    // Filtro de idiomas: sin idiomas no queda ningun grupo al que publicar, asi
    // que se rechaza en vez de guardar una cola que no puede dar trabajo nunca.
    ['api/groups', 'settings', 'POST', { languages: [] }, /al menos uno/],
    ['api/groups', 'settings', 'POST', { languages: ['de'] }, /no es un idioma valido/],
    ['api/groups', 'settings', 'POST', { languages: ['es', 'es'] }, /repetido/],
  ];
  for (const [prefix, action, method, body, pattern] of cases) {
    const res = await call(prefix, { action, method, body, cookie: COOKIE });
    assert.equal(res.statusCode, 400, `${prefix}/${action}`);
    assert.match(res.body.error, pattern);
  }
});

test('todas las respuestas privadas van con Cache-Control no-store', async () => {
  const res = await wa({ action: 'send', method: 'POST', body: {}, cookie: COOKIE });
  assert.equal(res.getHeader('Cache-Control'), 'no-store, private');
});

/* ------------------------------------------------------------------ *
 * Login
 * ------------------------------------------------------------------ */

test('login con clave mala es 401; con la buena, 200 y cookie', async () => {
  const malo = await wa({
    action: 'login',
    method: 'POST',
    body: { password: 'no-es' },
    ip: '10.0.0.1',
  });
  assert.equal(malo.statusCode, 401);
  assert.equal(malo.body.error, 'Contrasena incorrecta');

  const bueno = await wa({
    action: 'login',
    method: 'POST',
    body: { password: PASSWORD },
    ip: '10.0.0.2',
  });
  assert.equal(bueno.statusCode, 200);
  assert.deepEqual(bueno.body, { ok: true });
  const cookie = String(bueno.getHeader('Set-Cookie'));
  assert.match(cookie, /HttpOnly/);
  assert.match(cookie, /SameSite=Strict/);
});

test('el rate limit del login sigue vivo tras compartir funcion', async () => {
  const ip = '10.0.0.99';
  let last;
  for (let i = 0; i < 6; i++) {
    last = await wa({ action: 'login', method: 'POST', body: { password: 'mala' }, ip });
  }
  assert.equal(last.statusCode, 429);
  assert.ok(last.getHeader('Retry-After'));
});

/* ------------------------------------------------------------------ *
 * /api/lead/capture — PUBLICO, y tiene que seguir siendolo
 * ------------------------------------------------------------------ */

test('POST /api/lead/capture funciona sin ninguna cookie', async () => {
  const res = await lead({
    action: 'capture',
    method: 'POST',
    body: { source: 'suite', propertySlug: 'cocotal-2bdr' },
    ip: '203.0.113.10',
  });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.ok, true);
  assert.ok(res.body.id);
  assert.equal(res.getHeader('Cache-Control'), 'no-store');
});

test('capture sigue exigiendo source', async () => {
  const res = await lead({
    action: 'capture',
    method: 'POST',
    body: { name: 'sin source' },
    ip: '203.0.113.11',
  });
  assert.equal(res.statusCode, 400);
  assert.equal(res.body.error, 'Missing source');
});

test('capture rechaza un Origin de otro sitio', async () => {
  const res = await lead({
    action: 'capture',
    method: 'POST',
    body: { source: 'suite' },
    headers: { origin: 'https://otro-sitio.example' },
    ip: '203.0.113.12',
  });
  assert.equal(res.statusCode, 403);
  assert.equal(res.getHeader('Access-Control-Allow-Origin'), undefined);
});

test('capture acepta el Origin propio y responde el preflight', async () => {
  const res = await lead({
    action: 'capture',
    method: 'OPTIONS',
    headers: { origin: `https://${HOST}` },
    ip: '203.0.113.13',
  });
  assert.equal(res.statusCode, 204);
  assert.equal(res.getHeader('Access-Control-Allow-Origin'), `https://${HOST}`);
});

test('el rate limit de capture sigue vivo', async () => {
  const ip = '203.0.113.99';
  let last;
  for (let i = 0; i < 31; i++) {
    last = await lead({ action: 'capture', method: 'POST', body: { source: 'flood' }, ip });
  }
  assert.equal(last.statusCode, 429);
});

/* ------------------------------------------------------------------ *
 * Camino feliz con cookie: los modulos grandes siguen armando su respuesta
 * ------------------------------------------------------------------ */

test('GET /api/groups/plan arma el plan del dia con cookie valida', async () => {
  const res = await groups({ action: 'plan', cookie: COOKIE });
  assert.equal(res.statusCode, 200);
  assert.ok(Array.isArray(res.body.assignments));
  assert.ok(Array.isArray(res.body.groups));
  assert.equal(res.body.groups.length, 18);
  assert.ok(res.body.stats);
  assert.equal(res.getHeader('Cache-Control'), 'no-store, private');
});

test('GET /api/groups/settings devuelve ajustes, limites y propiedades', async () => {
  const res = await groups({ action: 'settings', cookie: COOKIE });
  assert.equal(res.statusCode, 200);
  assert.ok(res.body.settings);
  assert.ok(res.body.limits);
  assert.ok(Array.isArray(res.body.properties));

  // Filtro de idiomas: los ajustes traen la lista encendida y el catalogo de
  // las tres casillas con cuantos grupos se lleva cada una (apagar el frances
  // son 4 grupos fuera del plan, no una casilla menos).
  assert.deepEqual(res.body.settings.languages, ['es', 'en'], 'fr sigue apagado por defecto');
  assert.deepEqual(
    res.body.languages.map((l) => [l.code, l.groupCount]),
    [['es', 5], ['en', 9], ['fr', 4]]
  );
});

test('el plan salta los grupos cuyo idioma esta apagado y lo explica', async () => {
  const { buildPlan, GROUPS } = await load('api/_lib/groups-plan.js');

  // Solo espanol: los 9 en ingles y los 4 en frances quedan fuera del plan.
  const soloEs = buildPlan('2026-09-01', [], { mode: 'campaign', groupsPerDay: 5, languages: ['es'] });
  assert.ok(soloEs.assignments.length > 0);
  assert.deepEqual([...new Set(soloEs.assignments.map((a) => a.lang))], ['es']);
  assert.equal(soloEs.stats.groupsOffLanguage, GROUPS.filter((g) => g.lang !== 'es').length);

  // Todos los grupos es/en publicaron anteayer: los unicos libres son los 4 en
  // frances, que esta apagado. El plan sale vacio pero DICE por que.
  const history = GROUPS.filter((g) => g.lang !== 'fr').map((g) => ({
    date: '2026-09-08',
    groupCode: g.code,
    propertySlug: 'cocotal-2bdr',
    lang: g.lang,
    skipped: false,
  }));
  const bloqueado = buildPlan('2026-09-10', history, { mode: 'campaign', languages: ['es', 'en'] });
  assert.equal(bloqueado.assignments.length, 0);
  assert.match(bloqueado.reason, /frances/i);
  assert.match(bloqueado.reason, /Ajustes/);
});

/* ------------------------------------------------------------------ *
 * /api/wa/status — el panel de estado del sistema (status.html)
 * ------------------------------------------------------------------ */

const STATUS_PIECES = [
  'whatsapp',
  'webhook',
  'storage',
  'autoreply',
  'inbox',
  'groups',
  'leads',
  'catalog',
  'facebook',
];

test('GET /api/wa/status pide cookie', async () => {
  configureAuth();
  const res = await wa({ action: 'status' });
  assert.equal(res.statusCode, 401);
  assert.equal(res.body.error, 'Unauthorized');
});

test('GET /api/wa/status reporta las 9 piezas y no filtra ningun secreto', async () => {
  // Valores centinela: si alguno aparece en la respuesta, el endpoint esta
  // devolviendo el CONTENIDO de una variable y no solo si esta configurada.
  process.env.WAHA_WEBHOOK_SECRET = 'centinela-del-webhook-no-debe-salir';
  process.env.FB_PAGE_ID = '1234567890';
  process.env.FB_PAGE_ACCESS_TOKEN = 'centinela-del-token-de-facebook';
  try {
    const res = await wa({ action: 'status', cookie: COOKIE });
    assert.equal(res.statusCode, 200);
    assert.equal(res.getHeader('Cache-Control'), 'no-store, private');

    assert.ok(['ok', 'warn', 'down'].includes(res.body.overall), 'overall');
    assert.ok(Number.isFinite(Date.parse(res.body.checkedAt)), 'checkedAt');

    assert.deepEqual(res.body.pieces.map((p) => p.id), STATUS_PIECES);
    for (const p of res.body.pieces) {
      assert.deepEqual(Object.keys(p), ['id', 'label', 'state', 'detail', 'fix'], p.id);
      assert.ok(['ok', 'warn', 'down', 'off'].includes(p.state), `${p.id}: ${p.state}`);
      assert.ok(p.detail.length > 0, `${p.id} sin detalle`);
      // El "que hacer" solo existe cuando hay algo que hacer: el panel lo pinta
      // con un `if (piece.fix)` y no deberia tener que decidir nada mas.
      if (p.state === 'ok' || p.state === 'off') assert.equal(p.fix, null, `${p.id}`);
      else assert.ok(p.fix, `${p.id} en ${p.state} tendria que decir que hacer`);
    }

    const serialized = JSON.stringify(res.body);
    assert.ok(!serialized.includes('centinela-del-webhook'), 'se filtro WAHA_WEBHOOK_SECRET');
    assert.ok(!serialized.includes('centinela-del-token'), 'se filtro FB_PAGE_ACCESS_TOKEN');
    // Configurado != revelado: el webhook tiene que verse sano igual.
    assert.equal(res.body.pieces.find((p) => p.id === 'webhook').state, 'ok');
  } finally {
    delete process.env.WAHA_WEBHOOK_SECRET;
    delete process.env.FB_PAGE_ID;
    delete process.env.FB_PAGE_ACCESS_TOKEN;
  }
});

test('una pieza caida no tumba el reporte de status', async () => {
  // El puerto 1 de localhost rechaza al instante: es un WAHA inalcanzable de
  // verdad, sin esperar el timeout de 15s del cliente.
  process.env.WAHA_URL = 'http://127.0.0.1:1';
  try {
    const res = await wa({ action: 'status', cookie: COOKIE });
    // Lo que se esta probando: sigue siendo 200 y siguen viniendo las 9 piezas.
    assert.equal(res.statusCode, 200);
    assert.equal(res.body.pieces.length, STATUS_PIECES.length);

    const whatsapp = res.body.pieces.find((p) => p.id === 'whatsapp');
    assert.equal(whatsapp.state, 'down');
    assert.match(whatsapp.detail, /no alcanza/i);
    assert.ok(whatsapp.fix, 'una pieza caida tiene que decir que hacer');

    // Y las que no dependen de WAHA siguen calculandose: el catalogo se lee del
    // repo, asi que reporta las 5 propiedades activas pase lo que pase.
    const catalog = res.body.pieces.find((p) => p.id === 'catalog');
    assert.match(catalog.detail, /5 propiedades activas/);

    // WhatsApp es una pieza critica: el semaforo general se pone en rojo.
    assert.equal(res.body.overall, 'down');
  } finally {
    delete process.env.WAHA_URL;
  }
});

test('GET /api/lead/list devuelve la bandeja con cookie valida', async () => {
  const res = await lead({ action: 'list', cookie: COOKIE });
  assert.equal(res.statusCode, 200);
  assert.ok(Array.isArray(res.body.leads));
  assert.ok(res.body.stats);
  assert.equal(res.getHeader('Cache-Control'), 'no-store, private');
});

/* ------------------------------------------------------------------ *
 * La URL sin reescribir tiene que despachar igual
 * ------------------------------------------------------------------ */

test('la misma ruta despacha igual si la URL llega sin reescribir', async () => {
  const res = makeRes();
  await waEndpoint(
    {
      method: 'GET',
      url: '/api/wa/threads',
      headers: { host: HOST },
      query: {}, // sin ?action=: solo queda la ruta
      cookies: {},
      socket: { remoteAddress: '127.0.0.1' },
    },
    res
  );
  // Llego al handler de threads (401 por falta de cookie), no al 404 del despachador.
  assert.equal(res.statusCode, 401);
  assert.equal(res.body.error, 'Unauthorized');
});
