/**
 * GET  /api/wa/session — estado de la sesion de WhatsApp + QR para emparejar.
 * POST /api/wa/pair    — pide el codigo de emparejamiento por numero.
 *
 * QUE ESTABA ROTO
 * La version anterior hacia dos cosas y le faltaba una tercera:
 *
 *   const qr = status === 'SCAN_QR_CODE' ? '/api/wa/qr' : null;
 *
 * Si WAHA contestaba STARTING, o STOPPED, o la sesion ni existia (404), el
 * campo `qrUrl` salia null, la pantalla pintaba "preparando el codigo" y ahi se
 * quedaba PARA SIEMPRE: nadie arrancaba la sesion, asi que nunca iba a llegar a
 * SCAN_QR_CODE por su cuenta. Y como el 404 se trataba igual que "WAHA caido",
 * el dueno tampoco tenia forma de enterarse de cual de las dos cosas pasaba.
 *
 * QUE HACE AHORA
 *   1. Si la sesion no existe, esta STOPPED o quedo FAILED, LA ARRANCA
 *      (POST /api/sessions/{name}/start, y si nunca se creo, POST /api/sessions).
 *   2. Vuelve a leer el estado y devuelve el QR en cuanto el estado lo permite.
 *   3. Devuelve `message` y `expect` en castellano llano: que esta pasando y que
 *      se espera que pase, para que la pantalla nunca tenga que adivinar.
 *   4. Cuando algo anda mal, devuelve `checks`: la lista corta de que revisar.
 *
 * Ciclo de vida (docs: https://waha.devlike.pro/docs/how-to/sessions/):
 *   STOPPED -> STARTING -> SCAN_QR_CODE -> [PASSKEY_*] -> WORKING
 *   y FAILED cuando se vencen los 6 QR (el primero dura 60s, los demas 20s).
 */
import { requireAuth } from './auth.js';
import {
  sessionInfo,
  startSession,
  requestPairingCode,
  engineOf,
  engineSupportsPairing,
  sessionName,
} from './waha.js';

/* ------------------------------------------------------------------ *
 * Estados
 * ------------------------------------------------------------------ */

/** Ya conectado: no hay nada que emparejar. */
const CONNECTED = 'WORKING';

/** Nuestro estado inventado para "no pude ni hablar con WAHA". */
const UNREACHABLE = 'UNREACHABLE';

/**
 * Estados desde los que arrancar la sesion es lo correcto.
 *
 * FAILED esta aqui porque las docs lo dicen tal cual: cuando se vencen los seis
 * QR "the session moves to the FAILED status and needs to be restarted". Sin
 * esto, dejar la pantalla abierta dos minutos condenaba al dueno a un FAILED
 * eterno que solo se arreglaba entrando al dashboard de WAHA.
 */
const NEEDS_START = new Set(['NOT_FOUND', 'STOPPED', 'FAILED', 'UNKNOWN']);

/**
 * ¿En este estado hay un QR que pedir?
 *
 * Se compara de forma tolerante en vez de con la cadena exacta: distintas
 * versiones de WAHA han escrito este estado de varias formas y una comparacion
 * literal fallada se ve, desde el sofa del dueno, exactamente igual que el bug
 * que estamos arreglando — una pantalla girando sin explicacion.
 */
function hasQr(status) {
  const s = String(status || '').toUpperCase().replace(/[^A-Z]/g, '_');
  return s.includes('QR');
}

/** Estados en los que WhatsApp esta esperando que lo autentiquen. */
function isPairing(status) {
  const s = String(status || '').toUpperCase();
  return hasQr(s) || s.startsWith('PASSKEY');
}

/* ------------------------------------------------------------------ *
 * Lenguaje humano
 *
 * Cada estado sale con DOS frases: `message` (que esta pasando ahora mismo) y
 * `expect` (que se espera que pase, para que la espera tenga final). Y cuando
 * algo esta mal, `checks`: que tocar. Nunca se devuelve un estado sin frase —
 * un estado desconocido tambien tiene la suya.
 * ------------------------------------------------------------------ */

/** Que revisar cuando WAHA no contesta. Son las tres cosas que fallan siempre. */
const SERVER_CHECKS = [
  'Que el servidor de WhatsApp (Railway) este prendido.',
  'Que WAHA_URL en Vercel apunte a la direccion correcta de ese servidor.',
  'Que la API key sea la MISMA en los dos lados: WAHA_API_KEY en Vercel y en Railway.',
];

function describe(status, extra = {}) {
  const s = String(status || '').toUpperCase();

  if (s === UNREACHABLE) {
    return {
      message: 'No puedo hablar con el servidor de WhatsApp.',
      expect: 'Mientras no responda, no se puede vincular ni enviar nada.',
      checks: SERVER_CHECKS,
    };
  }
  if (s === CONNECTED) {
    return {
      message: 'WhatsApp esta conectado.',
      expect: 'Ya puedes cerrar esta pantalla: los mensajes entran solos.',
      checks: [],
    };
  }
  if (s === 'STARTING') {
    return {
      message: 'Arrancando WhatsApp, esto toma unos 20 segundos.',
      expect: 'En cuanto arranque aparece el codigo QR aqui mismo.',
      checks: [],
    };
  }
  if (hasQr(s)) {
    return {
      message: 'Listo para vincular.',
      expect: 'Escanea el codigo con el telefono del +1 809 486 5386, o pide el codigo por numero.',
      checks: [],
    };
  }
  if (s.startsWith('PASSKEY')) {
    return {
      message: 'WhatsApp esta pidiendo confirmacion en el telefono.',
      expect: 'Mira la pantalla del telefono y confirma ahi para terminar de vincular.',
      checks: [],
    };
  }
  if (s === 'STOPPED' || s === 'NOT_FOUND') {
    // Si llegamos aqui es que el arranque no prendio: ya se intento antes.
    return {
      message:
        s === 'NOT_FOUND'
          ? `La sesion "${extra.session || ''}" no existe todavia en el servidor.`.trim()
          : 'La sesion de WhatsApp esta apagada.',
      expect: 'La estoy arrancando. Si en un minuto sigue igual, algo la esta tumbando.',
      checks: [
        'Que WAHA_SESSION en Vercel diga el MISMO nombre de sesion que el servidor.',
        'Los logs de Railway, para ver por que la sesion no levanta.',
      ],
    };
  }
  if (s === 'FAILED') {
    return {
      message: 'La vinculacion fallo y WhatsApp cerro la sesion.',
      expect: 'La estoy rearrancando para darte un codigo nuevo. Espera unos segundos.',
      checks: [
        'Escanea el codigo apenas aparezca: el primero dura 60 segundos y los siguientes 20.',
        'Si vuelve a fallar varias veces, revisa los logs de Railway.',
      ],
    };
  }
  return {
    message: `WhatsApp reporta el estado "${s || 'desconocido'}".`,
    expect: 'Sigo consultando cada 5 segundos.',
    checks: [],
  };
}

/* ------------------------------------------------------------------ *
 * Freno del auto-arranque
 *
 * La pantalla pregunta cada 5 segundos. Sin freno, un WAHA lento comeria un
 * POST /start por consulta — 12 por minuto contra un servidor que ya esta
 * arrancando. El contador vive en memoria del lambda: no es perfecto entre
 * instancias, pero corta el caso que importa, que es el mismo lambda caliente
 * atendiendo el mismo panel abierto.
 * ------------------------------------------------------------------ */
const START_COOLDOWN_MS = 20000;
let lastStartAt = 0;

/** Devuelve `null` si arranco bien, o el mensaje del fallo. */
async function tryStart() {
  const now = Date.now();
  if (now - lastStartAt < START_COOLDOWN_MS) return null; // ya lo pedimos hace nada
  lastStartAt = now;
  try {
    await startSession();
    return null;
  } catch (err) {
    console.error('[wa/session] no pude arrancar la sesion:', err.message);
    return err.message;
  }
}

/**
 * Lee el estado y, si hace falta y se puede, arranca la sesion y lo relee.
 * @returns {Promise<{ status: string, info: object|null, startError: string|null, started: boolean }>}
 */
async function readState({ autoStart = true } = {}) {
  let info = null;
  try {
    info = await sessionInfo();
  } catch (err) {
    // Aca solo caen fallos de verdad (red, timeout, 500): el 404 lo convierte
    // sessionInfo() en NOT_FOUND, que si sabemos arreglar.
    console.error('[wa/session] WAHA no responde:', err.message);
    return { status: UNREACHABLE, info: null, startError: err.message, started: false };
  }

  let status = info.status;
  if (!autoStart || !NEEDS_START.has(status)) {
    return { status, info, startError: null, started: false };
  }

  const startError = await tryStart();
  if (startError) return { status, info, startError, started: false };

  // Releer: WAHA suele pasar a STARTING en el acto, y asi la primera respuesta
  // ya trae "arrancando" en vez del STOPPED que el dueno acaba de dejar atras.
  try {
    info = await sessionInfo();
    status = info.status;
  } catch (err) {
    console.error('[wa/session] arranque pedido pero no pude releer:', err.message);
  }
  return { status, info, startError: null, started: true };
}

/** El cuerpo que consume whatsapp.html. Un solo sitio que lo arma. */
function payload({ status, info, startError, started }) {
  const engine = engineOf(info);
  const words = describe(status, { session: sessionName() });
  const checks = words.checks.slice();

  // Un arranque que revienta es informacion util, no ruido: sin esto el dueno
  // ve "arrancando..." indefinidamente sin saber que el arranque ya fallo.
  if (startError && status !== UNREACHABLE) {
    checks.push('El servidor rechazo el arranque de la sesion: ' + startError);
  }

  return {
    status,
    // Siempre nuestro proxy, nunca la URL cruda de WAHA: esa exige el header
    // X-Api-Key, que un <img src> no puede mandar y que no debe salir al HTML.
    qrUrl: hasQr(status) ? '/api/wa/qr' : null,
    connected: status === CONNECTED,
    pairing: isPairing(status),
    starting: status === 'STARTING' || started,
    engine,
    canPairByPhone: engineSupportsPairing(engine) && status !== CONNECTED,
    message: words.message,
    expect: words.expect,
    checks,
    sessionName: sessionName(),
    details: info,
  };
}

export async function session(req, res) {
  if (!requireAuth(req, res)) return;

  // El QR cambia cada pocos segundos: cachearlo seria justo lo contrario de util.
  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const state = await readState();
  return res.status(200).json(payload(state));
}

/* ------------------------------------------------------------------ *
 * POST /api/wa/pair — emparejar con el numero
 *
 * Vive en este archivo y no en uno propio porque es la misma maquina de
 * estados: para pedir un codigo hay que asegurarse primero de que la sesion
 * este arrancada y esperando autenticacion.
 * ------------------------------------------------------------------ */

/** Numero del dueno. Es el que va precargado en la pantalla. */
export const OWNER_PHONE = '18094865386';

const NANP_LENGTH = 10; // 809/829/849 sin el 1 de pais
const MIN_DIGITS = 8;
const MAX_DIGITS = 15; // tope de E.164

/**
 * Normaliza a digitos con codigo de pais y sin '+', que es lo que pide WAHA
 * ("phoneNumber": "12132132130").
 *
 * El caso real de aqui: el dueno escribe 809-486-5386 como lo tiene en la
 * agenda. Eso son 10 digitos NANP, asi que le anteponemos el 1. Mandarlo sin el
 * 1 hace que WhatsApp busque un numero que no existe y devuelva un codigo que
 * nunca va a funcionar — un fallo silencioso, el peor tipo.
 */
export function normalizePhone(input) {
  const digits = String(input ?? '').replace(/\D/g, '');
  if (!digits) return { error: 'Escribe el numero de WhatsApp.' };
  const withCode = digits.length === NANP_LENGTH ? '1' + digits : digits;
  if (withCode.length < MIN_DIGITS || withCode.length > MAX_DIGITS) {
    return { error: 'Ese numero no tiene forma de numero de telefono. Revisalo.' };
  }
  if (withCode.startsWith('0')) {
    return { error: 'Quita el 0 del principio y pon el codigo de pais (1 para Republica Dominicana).' };
  }
  return { phone: withCode };
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

/**
 * Cuanto dura el codigo. Las docs de WAHA NO lo dicen; son los ~3 minutos que
 * da WhatsApp. Por eso la pantalla lo presenta como aproximado y siempre deja
 * pedir otro: mejor un numero honesto y un boton, que una promesa exacta falsa.
 */
const CODE_TTL_SECONDS = 180;

/** Espera corta a que la sesion quede lista para autenticar. */
const READY_TRIES = 3;
const READY_DELAY_MS = 1800;

export async function pair(req, res) {
  if (!requireAuth(req, res)) return;

  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const body = parseBody(req);
  if (!body) return res.status(400).json({ error: 'JSON invalido' });

  const { phone, error } = normalizePhone(
    body.phoneNumber === undefined || body.phoneNumber === '' ? OWNER_PHONE : body.phoneNumber
  );
  if (error) return res.status(400).json({ error });

  let state = await readState();

  if (state.status === UNREACHABLE) {
    const words = describe(UNREACHABLE);
    return res.status(503).json({ error: words.message, checks: words.checks });
  }
  if (state.status === CONNECTED) {
    return res.status(409).json({
      error: 'WhatsApp ya esta conectado. No hace falta vincular otra vez.',
      status: CONNECTED,
    });
  }

  // WhatsApp solo entrega un codigo mientras la sesion esta esperando que la
  // autentiquen. Si acaba de arrancar, le damos unos segundos — pero pocos: un
  // handler serverless que se pasa de tiempo se corta solo y el dueno ve un
  // error de red en vez de una explicacion.
  for (let i = 0; i < READY_TRIES && !isPairing(state.status); i++) {
    await new Promise((r) => setTimeout(r, READY_DELAY_MS));
    state = await readState({ autoStart: false });
    if (state.status === UNREACHABLE) break; // se cayo a mitad: no insistas
  }

  if (state.status === UNREACHABLE) {
    const words = describe(UNREACHABLE);
    return res.status(503).json({ error: words.message, checks: words.checks });
  }

  if (!engineSupportsPairing(engineOf(state.info))) {
    return res.status(400).json({
      error: 'Este motor de WhatsApp no sabe vincular por numero. Usa el codigo QR.',
      engine: engineOf(state.info),
    });
  }

  if (!isPairing(state.status)) {
    const words = describe(state.status, { session: sessionName() });
    return res.status(503).json({
      error: 'WhatsApp todavia esta arrancando. Espera unos segundos y vuelve a pedir el codigo.',
      status: state.status,
      checks: words.checks,
    });
  }

  try {
    const { code } = await requestPairingCode(phone);
    if (!code) {
      return res.status(502).json({
        error: 'El servidor no devolvio ningun codigo. Prueba con el codigo QR.',
      });
    }
    return res.status(200).json({
      code,
      phoneNumber: phone,
      expiresInSeconds: CODE_TTL_SECONDS,
      status: state.status,
      message: 'Escribe este codigo en WhatsApp, en Dispositivos vinculados.',
    });
  } catch (err) {
    console.error('[wa/pair] no pude pedir el codigo:', err.message);
    const down = err?.status === 0;
    return res.status(down ? 503 : 502).json({
      error: down
        ? 'No puedo hablar con el servidor de WhatsApp.'
        : 'El servidor no pudo generar el codigo. Usa el codigo QR mientras tanto.',
      checks: down ? SERVER_CHECKS : [],
    });
  }
}
