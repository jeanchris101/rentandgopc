/**
 * POST /api/wa/webhook — receptor de eventos de WAHA.
 *
 * No lleva auth de cookie (WAHA no es un navegador): se autentica con HMAC-SHA256
 * del cuerpo CRUDO usando WAHA_WEBHOOK_SECRET. Si el secreto no esta configurado
 * respondemos 503 (fail-closed): preferimos no procesar nada antes que aceptar
 * eventos de cualquiera que descubra la URL.
 *
 * Contesta 200 de inmediato y hace el trabajo pesado con waitUntil, porque el
 * auto-reply espera 45-120 segundos a proposito (ver ANTI-BANEO mas abajo) y
 * WAHA no puede quedarse esperando tanto por la respuesta HTTP.
 */
import { createHmac, timingSafeEqual, randomUUID } from 'node:crypto';

import {
  getThread,
  appendMessage,
  getConfig,
  isOptedOut,
  addOptOut,
  countAutoRepliesToday,
  STAGES,
} from '../_lib/wa-store.js';
import { sendText, markSeen, typing } from '../_lib/waha.js';
import { classify, renderStep, findPlaybook, getProperty } from '../_lib/classify.js';

// Necesitamos el body crudo, byte por byte, para que el HMAC cuadre.
// Cualquier re-serializacion (orden de llaves, espacios) rompe la firma.
// Formato Web (Request -> Response), NO el de Node (req, res).
//
// Es la unica forma fiable de leer el cuerpo SIN PARSEAR, que es sobre lo que
// WAHA calcula el HMAC. Antes esto era `export const config = { api: {
// bodyParser: false } }`, pero esa es sintaxis de Next.js: este proyecto no usa
// Next, Vercel la ignoraba, parseaba el JSON, y el handler respondia
// "Raw body unavailable" a CADA mensaje entrante. Re-serializar el objeto no
// sirve: cambia bytes y la firma deja de cuadrar.

// El auto-reply duerme hasta 120s dentro de waitUntil; sin esto la invocacion
// se corta a la mitad y el mensaje nunca sale.
// OJO al desplegar: pasar de 60s exige Fluid Compute activo en el proyecto. Si
// el build se queja de maxDuration, activa Fluid en Vercel (Settings > Functions)
// en vez de bajar este numero: con 60s se perderian las esperas mas largas, y en
// silencio, que es la peor forma de fallar.
export const maxDuration = 300;

const DAY_MS = 24 * 60 * 60 * 1000;

// Ventana anti-baneo: nunca contestamos antes de 45s ni despues de 120s.
const MIN_DELAY_MS = 45_000;
const MAX_DELAY_MS = 120_000;
const TYPING_MS = 3000;

/* ------------------------------------------------------------------ *
 * Utilidades
 * ------------------------------------------------------------------ */

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// WAHA signs the raw body with SHA-512 (not SHA-256) and sends it hex-encoded
// in X-Webhook-Hmac. Getting the algorithm wrong rejects every real message
// while still passing any test that signs with the same wrong algorithm — so
// this is pinned to what the WAHA docs specify, not to what we assumed.
const HMAC_ALGO = 'sha512';

function verifyHmac(raw, header, secret) {
  if (!header || typeof header !== 'string') return false;
  const expected = createHmac(HMAC_ALGO, secret).update(raw).digest();
  const received = Buffer.from(header.trim(), 'hex');
  // timingSafeEqual explota si los largos difieren, asi que filtramos antes.
  if (received.length !== expected.length) return false;
  return timingSafeEqual(received, expected);
}

/** Hora local (0-23) en la zona del negocio, sin depender del TZ del servidor. */
function hourInTz(timeZone) {
  try {
    const h = parseInt(
      new Intl.DateTimeFormat('en-US', { timeZone, hour: 'numeric', hour12: false }).format(new Date()),
      10,
    );
    if (Number.isFinite(h)) return h % 24; // algunos ICU devuelven 24 a medianoche
  } catch {
    /* zona invalida: caemos al reloj del servidor */
  }
  return new Date().getHours();
}

/** wa-store guarda los ts como ISO; WAHA los manda en segundos. Aceptamos ambos. */
function tsToMs(ts) {
  if (ts == null) return 0;
  const n = Number(ts);
  if (Number.isFinite(n) && n > 0) return n < 1e12 ? Math.round(n * 1000) : Math.round(n);
  const parsed = Date.parse(ts);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalizeText(s) {
  return String(s || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

// classify() ya detecta la baja cuando el mensaje ENTERO es la palabra clave.
// Esta lista cubre las variantes largas ("no me escribas mas, por favor") que
// no son un match exacto. Las dos rutas terminan igual: alta en la lista y silencio.
const OPT_OUT_PHRASES = [
  'no me escribas',
  'no me escriban',
  'no me contactes',
  'no me contacten',
  'no me vuelvas a escribir',
  'dejen de escribirme',
  'deja de escribirme',
  'dejame en paz',
  'no quiero mas informacion',
  'no quiero mas mensajes',
  'no me mandes mas',
  'quitame de la lista',
  'sacame de la lista',
  'borrar mis datos',
  'cancelar suscripcion',
  'stop messaging me',
  'do not contact me',
  'dont contact me',
  'remove me from',
  'take me off',
  'no more messages',
  'unsubscribe me',
];
const OPT_OUT_WORDS = ['stop', 'baja', 'unsubscribe', 'desuscribir', 'desuscribirme'];

function isOptOutMessage(body) {
  const t = normalizeText(body);
  if (!t) return false;
  if (OPT_OUT_PHRASES.some((p) => t.includes(p))) return true;
  // Mensaje corto que es basicamente la palabra clave sola.
  if (t.length <= 20) {
    const words = t.replace(/[^a-z0-9 ]/g, ' ').split(' ').filter(Boolean);
    if (words.length <= 2 && words.some((w) => OPT_OUT_WORDS.includes(w))) return true;
  }
  return false;
}

// Escalera de progreso del lead. 'cold' no esta aqui a proposito: no es un
// escalon, es un lead dormido — si vuelve a escribir, cualquier paso lo revive.
const LADDER = ['new', 'awaiting_qualify', 'qualified', 'closing'];

function stageForStep(stepId) {
  if (!stepId) return null;
  if (stepId.startsWith('step1') || stepId.startsWith('step2')) return 'awaiting_qualify';
  if (stepId.startsWith('step3')) return 'qualified';
  if (stepId.startsWith('step4')) return 'closing';
  return null; // los followups no mueven la etapa
}

/** Devuelve la nueva etapa solo si es un avance; nunca retrocede un lead. */
function advanceStage(current, next) {
  if (!next || !STAGES.includes(next)) return null;
  if (current === 'cold') return next; // volvio a escribir: se reactiva
  const ci = LADDER.indexOf(current || 'new');
  const ni = LADDER.indexOf(next);
  if (ci < 0 || ni < 0) return null;
  return ni > ci ? next : null;
}

/**
 * renderStep devuelve el texto ya con los tokens sustituidos, o '' si no hay
 * guion. No inventamos un fallback con el texto crudo del paso: mandaria
 * "{{price}}" literal a un cliente, y eso es peor que no contestar.
 */
function renderedText(playbook, stepId, lang, property) {
  try {
    const out = renderStep(playbook, stepId, lang, property);
    if (typeof out === 'string') return out.trim();
    // Tolerancia por si algun dia devuelve un objeto.
    if (out && typeof out === 'object') return String(out.text || out.body || '').trim();
  } catch (err) {
    console.error('[wa/webhook] renderStep fallo:', err.message);
  }
  return '';
}

/**
 * waitUntil vive en @vercel/functions. Lo cargamos de forma perezosa para que
 * un despliegue sin la dependencia no tumbe el webhook entero: en ese caso
 * simplemente esperamos el trabajo dentro del handler (la respuesta 200 ya salio).
 */
let _waitUntilPromise = null;
function getWaitUntil() {
  if (!_waitUntilPromise) {
    _waitUntilPromise = import('@vercel/functions')
      .then((m) => (typeof m.waitUntil === 'function' ? m.waitUntil : null))
      .catch(() => null);
  }
  return _waitUntilPromise;
}

/* ------------------------------------------------------------------ *
 * Reglas de auto-reply
 * ------------------------------------------------------------------ */

function denied(rule, why, chatId) {
  console.log(`[wa/webhook] auto-reply bloqueado — REGLA ${rule} (${why}) chat=${chatId}`);
  return { ok: false, rule, why };
}

/**
 * Las 7 reglas, en orden. La primera que falla corta y queda registrada.
 * `skipSlow` reevalua solo las baratas (se usa justo antes de enviar, despues
 * de la espera larga, por si el dueno intervino mientras tanto).
 */
async function evaluateRules({ cfg, classification, thread, chatId, playbook, step, skipSlow }) {
  const lead = (thread && thread.lead) || {};

  // REGLA 1 — el interruptor general del panel.
  if (cfg.autoReplyEnabled !== true) return denied(1, 'autoReplyEnabled=false', chatId);
  if (cfg.killSwitch === true) return denied(1, 'killSwitch activo', chatId);

  // REGLA 2 — el clasificador tiene que dar permiso (intencion y confianza).
  // MODO ESTRICTO (por defecto): sin ref, no hay auto-respuesta.
  //
  // El clasificador tambien da confianza alta por un keyword unico ("A301",
  // "Arboleda"), y eso alcanza para un numero de negocio. Este es el numero
  // PERSONAL del dueno: un conocido que pregunte "sigue disponible el de
  // Arboleda?" recibiria el pitch completo de un bot, y eso no se deshace.
  // Exigir el ref significa: solo contesta solo a quien llego por un link
  // nuestro (post, grupo o anuncio). El resto aparece en la bandeja y lo
  // contesta el dueno.
  if (cfg.requireRefForAutoReply !== false && !classification?.ref) {
    return denied(2, 'modo estricto: el mensaje no trae ref de un link nuestro', chatId);
  }

  if (!classification || classification.autoReplyAllowed !== true) {
    return denied(2, 'classify.autoReplyAllowed=false', chatId);
  }

  // REGLA 3 — maximo un auto-reply cada 24h por hilo.
  const last = tsToMs(lead.autoRepliedAt);
  if (last && Date.now() - last < DAY_MS) {
    return denied(3, `ultimo auto-reply ${lead.autoRepliedAt}`, chatId);
  }

  // REGLA 4 — si el dueno tomo el hilo a mano, el bot no vuelve a meterse.
  if (lead.manualOverride === true) return denied(4, 'manualOverride=true', chatId);

  // REGLA 5 — tope diario global.
  if (!skipSlow) {
    const usedToday = await countAutoRepliesToday();
    if (Number(usedToday) >= Number(cfg.dailyCap)) {
      return denied(5, `dailyCap ${usedToday}/${cfg.dailyCap}`, chatId);
    }
  }

  // REGLA 6 — horario permitido en hora dominicana, intervalo [start, end).
  // DECISION: fuera de horario NO se encola nada para el dia siguiente. El mensaje
  // queda en el panel marcado como sin responder y el dueno lo ve al levantarse.
  // Una cola nocturna dispararia una rafaga de mensajes a las 8:00 a.m. — el patron
  // exacto que WhatsApp marca como automatizacion — y ademas contestaria cosas que
  // a esa hora ya estan frias o resueltas.
  const start = Number(cfg.quietHours?.start);
  const end = Number(cfg.quietHours?.end);
  const h = hourInTz(cfg.timezone);
  if (!(h >= start && h < end)) {
    return denied(6, `hora ${h}h RD fuera de [${start}, ${end})`, chatId);
  }

  // REGLA 7 — tiene que existir el paso concreto para esa propiedad e idioma.
  if (!playbook) return denied(7, 'sin playbook para la propiedad', chatId);
  if (!step) return denied(7, 'el paso sugerido no existe en el playbook', chatId);

  return { ok: true };
}

/* ------------------------------------------------------------------ *
 * Procesamiento (corre en background)
 * ------------------------------------------------------------------ */

async function processMessage({ chatId, phone, name, body, hasMedia, mediaType, msgId, ts, type }) {
  // Un contacto dado de baja no se guarda ni se contesta. Punto.
  if (await isOptedOut(phone)) {
    console.log(`[wa/webhook] ${chatId} esta opt-out — ignorado`);
    return;
  }

  const existing = await getThread(chatId);
  const classification = classify({ body, hasMedia, mediaType, thread: existing });

  // Baja: la registramos y NO mandamos ni un "listo, te doy de baja".
  // Cualquier respuesta automatica a un "stop" es justo lo que dispara reportes.
  // El mensaje si se guarda, para que quede constancia de cuando pidio la baja.
  if (classification.intent === 'opt_out' || isOptOutMessage(body)) {
    await addOptOut(phone);
    try {
      await appendMessage(
        chatId,
        { id: msgId, ts, fromMe: false, type, body, intent: 'opt_out', hasMedia, name },
        { stage: 'cold', optedOutAt: new Date().toISOString() },
      );
    } catch (err) {
      console.error('[wa/webhook] no pude guardar el mensaje de baja:', err.message);
    }
    console.log(`[wa/webhook] opt-out registrado para ${phone}`);
    return;
  }

  // La correccion humana manda: si el dueno fijo la propiedad a mano, el
  // clasificador no la puede pisar.
  const prevLead = (existing && existing.lead) || {};
  const leadPatch = {};
  if (prevLead.manualOverride === true) {
    if (!prevLead.language && classification.language) leadPatch.language = classification.language;
  } else {
    if (classification.propertySlug) leadPatch.propertySlug = classification.propertySlug;
    if (classification.ref) leadPatch.ref = classification.ref;
    if (classification.language) leadPatch.language = classification.language;
    if (classification.confidence) leadPatch.confidence = classification.confidence;
  }
  if (classification.source && !prevLead.source) leadPatch.source = classification.source;

  const thread = await appendMessage(
    chatId,
    {
      id: msgId,
      ts,
      fromMe: false,
      type,
      body,
      intent: classification.intent,
      hasMedia,
      name, // pista para el nombre del contacto; no se guarda en el mensaje
    },
    Object.keys(leadPatch).length ? leadPatch : null,
  );

  const lead = (thread && thread.lead) || {};
  const cfg = await getConfig();

  const lang = lead.language || classification.language || 'es';
  const slug = lead.propertySlug || classification.propertySlug || null;
  const playbook = findPlaybook(slug);
  const property = getProperty(slug);
  const stepId = classification.suggestedStep || 'step1_immediate';
  const step = playbook ? (playbook.steps || []).find((s) => s && s.id === stepId) : null;

  const verdict = await evaluateRules({ cfg, classification, thread, chatId, playbook, step });
  if (!verdict.ok) return;

  const text = renderedText(playbook, stepId, lang, property);
  // Segunda mitad de la REGLA 7: el paso existe pero no tiene texto usable.
  if (!text) return void denied(7, `paso ${stepId} sin texto en '${lang}'`, chatId);

  await markSeen(chatId);

  // ---- ANTI-BANEO ------------------------------------------------------
  // Contestar en 2 segundos, exacto, las 24 horas, es la huella mas obvia de un
  // bot y es justo lo que detecta WhatsApp para banear numeros. Por eso:
  //   1) esperamos un rato ALEATORIO entre 45 y 120 segundos (nunca el mismo), y
  //   2) mostramos "escribiendo..." unos segundos antes de mandar,
  // que es como se ve una persona que leyo el mensaje y se puso a responder.
  // El costo es que el lead espera un minuto; a cambio la linea sobrevive.
  const delay = MIN_DELAY_MS + Math.floor(Math.random() * (MAX_DELAY_MS - MIN_DELAY_MS + 1));
  console.log(`[wa/webhook] auto-reply a ${chatId} en ${Math.round(delay / 1000)}s (paso ${stepId})`);
  await sleep(delay);

  // Durante esa espera el dueno pudo contestar a mano, apagar el bot o marcar
  // manualOverride. Revisamos otra vez antes de mandar.
  const fresh = (await getThread(chatId)) || thread;
  const recheck = await evaluateRules({
    cfg: await getConfig(),
    classification,
    thread: fresh,
    chatId,
    playbook,
    step,
    skipSlow: true,
  });
  if (!recheck.ok) return;
  if ((fresh.messages || []).some((m) => m && m.fromMe && tsToMs(m.ts) > ts)) {
    console.log(`[wa/webhook] auto-reply cancelado: el dueno ya respondio ${chatId}`);
    return;
  }
  if (await isOptedOut(phone)) return;

  // typing(chatId, ms) mantiene el indicador ese tiempo antes de soltar el texto.
  try {
    await typing(chatId, TYPING_MS);
  } catch (err) {
    console.error('[wa/webhook] typing fallo (sigo):', err.message);
  }

  await sendText(chatId, text);

  const nowIso = new Date().toISOString();
  const outPatch = {
    autoRepliedAt: nowIso,
    autoReplyCount: Number((fresh.lead && fresh.lead.autoReplyCount) || 0) + 1,
    lastStepSent: stepId,
  };
  if (!(fresh.lead && fresh.lead.firstReplyAt)) outPatch.firstReplyAt = nowIso;
  const nextStage = advanceStage(fresh.lead && fresh.lead.stage, stageForStep(stepId));
  if (nextStage) outPatch.stage = nextStage;

  await appendMessage(
    chatId,
    {
      id: randomUUID(),
      ts: Date.now(),
      fromMe: true,
      type: 'chat',
      body: text,
      intent: 'auto_reply',
      hasMedia: false,
    },
    outPatch,
  );

  console.log(`[wa/webhook] auto-reply enviado a ${chatId} (paso ${stepId}, ${lang})`);
}

/* ------------------------------------------------------------------ *
 * Handler
 * ------------------------------------------------------------------ */

// Objeto con `fetch`, que es la forma documentada del Web Handler en Vercel.
// Con `export default async function handler(request)` Vercel lo toma por el
// handler de Node, lo invoca como (req, res), ignora el Response devuelto y
// nadie cierra la respuesta: la peticion se queda colgada hasta el timeout.
export default {
  async fetch(request) {
    const json = (status, body) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
      });

    if (request.method !== 'POST') return json(405, { error: 'Method not allowed' });

    const secret = process.env.WAHA_WEBHOOK_SECRET;
    if (!secret) {
      // Fail-closed: sin secreto no hay forma de saber quien nos escribe.
      console.error('[wa/webhook] WAHA_WEBHOOK_SECRET no esta configurado — rechazando');
      return json(503, { error: 'Not configured' });
    }

    let rawText;
    try {
      rawText = await request.text();
    } catch (err) {
      console.error('[wa/webhook] no pude leer el body:', err.message);
      return json(400, { error: 'Invalid body' });
    }
    const raw = Buffer.from(rawText || '', 'utf8');
    if (!raw.length) return json(400, { error: 'Empty body' });

    if (!verifyHmac(raw, request.headers.get('x-webhook-hmac'), secret)) {
      return json(401, { error: 'Invalid signature' });
    }

    let event;
    try {
      event = JSON.parse(rawText);
    } catch {
      return json(400, { error: 'Invalid JSON' });
    }

    const payload = (event && event.payload) || {};

    // Solo nos interesan mensajes entrantes 1 a 1. Todo lo demas (acks, presencia,
    // llamadas, grupos, estados) se ignora con 200 para que WAHA no reintente.
    // Los grupos quedan fuera a proposito: el panel gestiona leads privados y
    // contestar solo dentro de un grupo es un reporte por spam asegurado.
    const chatId = typeof payload.from === 'string' ? payload.from : '';
    if (event.event !== 'message' || payload.fromMe !== false || !chatId.endsWith('@c.us')) {
      return json(200, { ok: true, ignored: true });
    }

    const data = {
      chatId,
      phone: chatId.split('@')[0],
      name:
        (payload._data && (payload._data.notifyName || payload._data.pushName)) ||
        payload.notifyName ||
        payload.pushName ||
        (payload.chat && payload.chat.name) ||
        '',
      body: String(payload.body || payload.caption || ''),
      hasMedia: payload.hasMedia === true,
      mediaType:
        (payload.media && payload.media.mimetype) ||
        (payload._data && payload._data.mimetype) ||
        payload.type ||
        null,
      // El id sostiene la deduplicacion de wa-store ante los reintentos de WAHA,
      // asi que tiene que ser una cadena estable.
      msgId: payload.id ? String(payload.id) : randomUUID(),
      ts: tsToMs(payload.timestamp) || Date.now(),
      type: payload.type || 'chat',
    };

    const work = processMessage(data).catch((err) => {
      console.error('[wa/webhook] error procesando mensaje:', err);
    });

    // Responder ya: WAHA no espera el minuto de delay del auto-reply. waitUntil
    // mantiene viva la invocacion mientras el trabajo termina en segundo plano.
    const waitUntil = await getWaitUntil();
    if (waitUntil) waitUntil(work);
    else await work; // sin @vercel/functions: se completa antes de responder

    return json(200, { ok: true });
  },
};
