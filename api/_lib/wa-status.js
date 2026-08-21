/**
 * GET /api/wa/status — el tablero de estado del sistema, para status.html.
 *
 * Una sola llamada que contesta "esta todo bien?" pieza por pieza. La lee el
 * dueno, que no es tecnico, asi que cada pieza sale con su estado, una frase en
 * castellano llano y — solo si algo anda mal — que tocar para arreglarlo.
 *
 * REGLA DE ORO: UNA PIEZA CAIDA NO PUEDE TUMBAR EL REPORTE
 * El momento en que mas se necesita este endpoint es justo cuando algo esta
 * roto. Por eso las lecturas van todas por `settle()` (que nunca rechaza) y cada
 * chequeo corre dentro de `safe()`. Si WAHA no responde, o el Blob no contesta,
 * o un chequeo tiene un bug, esa tarjeta sale en rojo y las otras ocho siguen
 * diciendo la verdad. Este handler solo responde 500 si se rompe el propio
 * res.json().
 *
 * NUNCA SALE UN SECRETO
 * De las variables de entorno solo se reporta si estan puestas o no, jamas su
 * valor. Ademas `summarize()` tacha cualquier tramo largo con pinta de token que
 * venga dentro de un mensaje de error.
 *
 * POR QUE SE PRUEBA EL BLOB CON list() Y NO SOLO CON getConfig()
 * getConfig() y listThreads() se tragan sus errores a proposito (un blob que
 * falta es el arranque en frio normal y no puede tumbar un webhook), asi que un
 * BLOB_READ_WRITE_TOKEN vencido se veria "sano" desde ahi. La unica lectura que
 * de verdad delata el token es la cruda, y por eso el chequeo 3 llama a `list()`
 * directamente ademas de usar los datos que los otros helpers devuelven.
 */
import { list } from '@vercel/blob';

import { requireAuth } from './auth.js';
import { sessionStatus } from './waha.js';
import { getConfig, listThreads, countAutoRepliesToday } from './wa-store.js';
import { buildPlan, readHistory, todayInTz, hourLabel } from './groups-plan.js';
import { readSettings } from './groups-settings.js';
import { listLeads } from './lead-capture.js';
import propertiesFile from '../../automation/data/properties.json' with { type: 'json' };

/* ------------------------------------------------------------------ *
 * Constantes
 * ------------------------------------------------------------------ */

/**
 * Las tres piezas sin las cuales el sistema NO funciona: si WhatsApp esta caido,
 * si el webhook no puede entrar o si no hay donde guardar, no hay negocio
 * automatizado. Cualquier otra en rojo es grave pero no apaga el conjunto, y por
 * eso el semaforo general solo se pone en rojo por estas.
 */
const CRITICAL = new Set(['whatsapp', 'webhook', 'storage']);

const DAY_MS = 24 * 60 * 60 * 1000;

/** Un post sin al menos 3 fotos distintas repite imagen en la rotacion. */
const MIN_POST_IMAGES = 3;

/** Menos de esto y la atribucion esta rota, no "floja". */
const MIN_ATTRIBUTION_RATE = 50;

/** El Blob normalmente contesta en decenas de ms; a partir de aqui va lento. */
const SLOW_BLOB_MS = 2500;

/** Un mensaje de error largo no cabe en una tarjeta ni le sirve al dueno. */
const ERROR_DETAIL_MAX = 160;

/**
 * Tramos con pinta de credencial dentro de un mensaje de error. `@vercel/blob` y
 * WAHA no filtran secretos hoy, pero el mensaje viaja al navegador y no vamos a
 * apostar a que eso siga siendo cierto manana.
 */
const SECRETISH_RE = /\b(?:vercel_blob_rw_[\w-]+|[A-Za-z0-9_-]{32,})\b/g;

const ALL_PROPERTIES = Array.isArray(propertiesFile?.properties) ? propertiesFile.properties : [];

/**
 * Dos slugs que NO son una propiedad: "unknown" (analytics.js no encontro el
 * data-prop) y "gen" (el CTA generico, ref RG-GEN-*). Contarlos como atribuidos
 * dejaria el porcentaje en 100% justo cuando la atribucion esta fallando. Mismo
 * criterio que api/_lib/lead-list.js.
 */
const NOT_A_LISTING = new Set(['unknown', 'gen']);

/* ------------------------------------------------------------------ *
 * Utilidades
 * ------------------------------------------------------------------ */

/**
 * Una pieza del reporte.
 *
 * INVARIANTE: `fix` solo existe cuando hay algo que arreglar (warn o down). En
 * "ok" y en "off" se descarta aunque el llamador lo pase, y asi el panel puede
 * pintar el "que hacer" con un simple `if (piece.fix)` sin decidir nada. Si una
 * pieza apagada necesita explicar como se enciende, eso va en `detail`: es
 * informacion, no una reparacion.
 */
function piece(id, label, state, detail, fix = null) {
  const needsFix = state === 'warn' || state === 'down';
  return {
    id,
    label,
    state,
    detail: String(detail || ''),
    fix: needsFix && fix ? String(fix) : null,
  };
}

/** Nunca rechaza: `{ ok:true, value }` o `{ ok:false, error }`. */
function settle(promise) {
  return Promise.resolve(promise).then(
    (value) => ({ ok: true, value }),
    (error) => ({ ok: false, error })
  );
}

/** Un chequeo con bug se convierte en una tarjeta roja, no en un 500. */
function safe(id, label, build) {
  try {
    return build();
  } catch (err) {
    return piece(
      id,
      label,
      'down',
      `No pudimos revisar esta pieza: ${summarize(err)}.`,
      'Refresca la pagina. Si sigue igual, es un fallo del propio panel y hay que revisar el codigo.'
    );
  }
}

/** Mensaje de error en una linea, corto y sin nada que parezca una credencial. */
function summarize(err) {
  const raw = err instanceof Error ? err.message : String(err ?? '');
  const clean = raw.replace(SECRETISH_RE, '[oculto]').replace(/\s+/g, ' ').trim();
  if (!clean) return 'error desconocido';
  return clean.length > ERROR_DETAIL_MAX ? `${clean.slice(0, ERROR_DETAIL_MAX - 3)}...` : clean;
}

/** "hace 5 minutos", "hace 2 horas", "hace 3 dias". null si la fecha no sirve. */
function humanAgo(value) {
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) return null;
  const diff = Date.now() - ms;
  if (diff < 0) return 'hace un momento';
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'hace un momento';
  if (minutes < 60) return `hace ${minutes} ${minutes === 1 ? 'minuto' : 'minutos'}`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} ${hours === 1 ? 'hora' : 'horas'}`;
  const days = Math.floor(hours / 24);
  return `hace ${days} ${days === 1 ? 'dia' : 'dias'}`;
}

/** ["a","b","c"] -> "a, b y c". Para que las frases suenen a persona. */
function listWords(items) {
  if (items.length <= 1) return items[0] || '';
  return `${items.slice(0, -1).join(', ')} y ${items[items.length - 1]}`;
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

function isListing(slug) {
  return Boolean(slug) && !NOT_A_LISTING.has(String(slug).toLowerCase());
}

/* ------------------------------------------------------------------ *
 * 1. WhatsApp (WAHA)
 * ------------------------------------------------------------------ */

async function readSessionState() {
  const s = await sessionStatus();
  if (typeof s === 'string') return s;
  if (s && typeof s === 'object') return String(s.status || s.state || 'UNKNOWN');
  return 'UNKNOWN';
}

function checkWhatsApp(settled) {
  const id = 'whatsapp';
  const label = 'WhatsApp';

  if (!process.env.WAHA_URL) {
    return piece(
      id,
      label,
      'down',
      'El servidor de WhatsApp no esta configurado: falta la variable WAHA_URL.',
      'En Vercel > Settings > Environment Variables agrega WAHA_URL con la direccion del servicio de Railway y vuelve a desplegar.'
    );
  }

  if (!settled.ok) {
    return piece(
      id,
      label,
      'down',
      `Vercel no alcanza a Railway: el servidor de WhatsApp no contesto (${summarize(settled.error)}).`,
      'Entra a Railway y revisa que el servicio de WAHA este encendido. Si esta arriba, confirma que WAHA_URL y WAHA_API_KEY en Vercel apunten a ese servicio.'
    );
  }

  const raw = settled.value;
  switch (raw) {
    case 'WORKING':
      return piece(id, label, 'ok', `WhatsApp esta conectado y recibiendo mensajes (estado ${raw}).`);

    case 'SCAN_QR_CODE':
      return piece(
        id,
        label,
        'warn',
        `Falta escanear el QR: el telefono todavia no esta emparejado (estado ${raw}).`,
        'Abre el panel de WhatsApp: ahi sale el codigo. En el telefono del negocio ve a WhatsApp > Dispositivos vinculados > Vincular un dispositivo y escanealo.'
      );

    case 'STARTING':
    case 'STOPPING':
      return piece(
        id,
        label,
        'warn',
        `La sesion de WhatsApp esta cambiando de estado (estado ${raw}).`,
        'Espera un minuto y refresca. Si se queda asi, reinicia el servicio de WAHA en Railway.'
      );

    case 'STOPPED':
      return piece(
        id,
        label,
        'down',
        `WhatsApp esta desconectado: la sesion esta parada (estado ${raw}).`,
        'Reinicia el servicio de WAHA en Railway. Al volver puede pedirte escanear el QR otra vez desde el panel de WhatsApp.'
      );

    case 'FAILED':
      return piece(
        id,
        label,
        'down',
        `WhatsApp esta desconectado: la sesion fallo (estado ${raw}).`,
        'Casi siempre es que cerraron la sesion desde el telefono. Reinicia WAHA en Railway y vuelve a escanear el QR desde el panel de WhatsApp.'
      );

    default:
      return piece(
        id,
        label,
        'warn',
        `WhatsApp contesta pero con un estado que no reconocemos (estado ${raw}).`,
        'Abre el panel de WhatsApp y manda un mensaje de prueba. Si sale, no hay problema real; si no sale, reinicia WAHA en Railway.'
      );
  }
}

/* ------------------------------------------------------------------ *
 * 2. Webhook — la puerta por donde ENTRAN los mensajes
 * ------------------------------------------------------------------ */

function checkWebhook() {
  const id = 'webhook';
  const label = 'Entrada de mensajes';

  // Solo si esta puesta. El valor no sale de aqui ni en un log.
  if (process.env.WAHA_WEBHOOK_SECRET) {
    return piece(
      id,
      label,
      'ok',
      'La clave que firma los avisos de WhatsApp esta configurada, asi que los mensajes que te escriben entran al panel.'
    );
  }

  return piece(
    id,
    label,
    'down',
    'No entra ningun mensaje: falta la clave que firma los avisos de WhatsApp. Todo lo que te escriban se pierde antes de llegar al panel.',
    'En Vercel > Settings > Environment Variables agrega WAHA_WEBHOOK_SECRET con el MISMO valor que tiene WHATSAPP_HOOK_HMAC_KEY en Railway, y vuelve a desplegar.'
  );
}

/* ------------------------------------------------------------------ *
 * 3. Almacenamiento (Vercel Blob)
 * ------------------------------------------------------------------ */

function checkStorage(settled) {
  const id = 'storage';
  const label = 'Almacenamiento';

  if (!settled.ok) {
    const tokenMissing = !process.env.BLOB_READ_WRITE_TOKEN;
    return piece(
      id,
      label,
      'down',
      `No podemos leer ni guardar nada: el almacenamiento no contesto (${summarize(settled.error)}). Las conversaciones, los ajustes y los leads que entren ahora no se guardan.`,
      tokenMissing
        ? 'Falta la variable BLOB_READ_WRITE_TOKEN. En Vercel > Storage vuelve a conectar el Blob al proyecto (eso la crea sola) y vuelve a desplegar.'
        : 'En Vercel > Storage abre el Blob del proyecto. Si sale "Needs Attention", vuelve a conectarlo al proyecto y despliega de nuevo para que se renueve BLOB_READ_WRITE_TOKEN.'
    );
  }

  const ms = settled.value;
  if (ms >= SLOW_BLOB_MS) {
    return piece(
      id,
      label,
      'warn',
      `El almacenamiento responde, pero lento: tardo ${(ms / 1000).toFixed(1)} segundos. El panel va a sentirse pesado.`,
      'Casi siempre pasa solo. Refresca en un rato; si sigue lento, revisa el estado de Vercel Blob en vercel-status.com.'
    );
  }

  return piece(
    id,
    label,
    'ok',
    'El almacenamiento responde bien: se guardan las conversaciones, los ajustes y los leads.'
  );
}

/* ------------------------------------------------------------------ *
 * 4. Auto-respuesta
 * ------------------------------------------------------------------ */

function checkAutoReply(configSettled, countSettled) {
  const id = 'autoreply';
  const label = 'Auto-respuesta';

  if (!configSettled.ok) {
    return piece(
      id,
      label,
      'warn',
      `No pudimos leer los ajustes del auto-respuesta (${summarize(configSettled.error)}).`,
      'Es un problema del almacenamiento. Arregla primero esa pieza y vuelve a refrescar.'
    );
  }

  const cfg = configSettled.value || {};
  const cap = Number(cfg.dailyCap) || 0;
  const used = countSettled.ok ? Number(countSettled.value) || 0 : null;
  const window = `de ${hourLabel(cfg.quietHours?.start)} a ${hourLabel(cfg.quietHours?.end)}`;

  // La parada de emergencia manda sobre todo lo demas (asi lo lee el webhook).
  if (cfg.killSwitch === true) {
    return piece(
      id,
      label,
      'off',
      'Parada de emergencia activa: el sistema no le responde solo a nadie. Todo lo que salga tienes que enviarlo tu a mano. Se quita desde el panel de WhatsApp con el boton REANUDAR.'
    );
  }

  if (cfg.autoReplyEnabled !== true) {
    return piece(
      id,
      label,
      'off',
      `El auto-respuesta esta apagado: hoy no sale ningun mensaje solo. Es lo recomendado al principio, mientras revisas a mano lo que llega. Se enciende desde el panel de WhatsApp (el tope quedaria en ${plural(cap, 'mensaje', 'mensajes')} al dia, ${window} hora dominicana).`
    );
  }

  const usedText = used === null ? 'no pudimos contar cuantas van hoy' : `hoy van ${used} de ${cap}`;

  if (used !== null && cap > 0 && used >= cap) {
    return piece(
      id,
      label,
      'warn',
      `El auto-respuesta esta encendido pero ya llego al tope de hoy: ${used} de ${cap}. Lo que entre ahora espera a que contestes tu.`,
      `Si quieres que siga contestando hoy, sube el tope diario en el panel de WhatsApp. Ojo: subirlo mucho de golpe es lo que hace que WhatsApp banee el numero.`
    );
  }

  return piece(
    id,
    label,
    'ok',
    `El auto-respuesta esta encendido y contesta ${window} hora dominicana. Tope de ${plural(cap, 'mensaje', 'mensajes')} al dia y ${usedText}.`
  );
}

/* ------------------------------------------------------------------ *
 * 5. Bandeja
 * ------------------------------------------------------------------ */

function checkInbox(settled) {
  const id = 'inbox';
  const label = 'Bandeja';

  if (!settled.ok) {
    return piece(
      id,
      label,
      'warn',
      `No pudimos leer la bandeja (${summarize(settled.error)}).`,
      'Es un problema del almacenamiento. Arregla primero esa pieza y vuelve a refrescar.'
    );
  }

  const threads = Array.isArray(settled.value) ? settled.value : [];
  if (!threads.length) {
    return piece(
      id,
      label,
      'ok',
      'Todavia no hay ninguna conversacion guardada. En cuanto alguien escriba al WhatsApp del negocio aparece aqui.'
    );
  }

  // "Sin contestar" = el ultimo mensaje del hilo lo mando el cliente, no tu.
  const waiting = threads.filter((t) => t?.lastMessage && t.lastMessage.fromMe !== true);

  let newest = null;
  for (const t of threads) {
    const ts = t?.lastMessage?.ts || t?.updatedAt;
    const ms = Date.parse(ts);
    if (Number.isFinite(ms) && (newest === null || ms > newest)) newest = ms;
  }
  const ago = newest === null ? null : humanAgo(new Date(newest).toISOString());
  const agoText = ago ? ` El ultimo mensaje llego ${ago}.` : '';

  if (waiting.length) {
    return piece(
      id,
      label,
      'warn',
      `${plural(threads.length, 'conversacion', 'conversaciones')} en total, y ${plural(waiting.length, 'sigue', 'siguen')} sin contestar.${agoText}`,
      'Abre el panel de WhatsApp y contesta los hilos que estan esperando. Un lead que espera mas de una hora casi siempre ya escribio a otro.'
    );
  }

  return piece(
    id,
    label,
    'ok',
    `${plural(threads.length, 'conversacion', 'conversaciones')} en total y ninguna sin contestar.${agoText}`
  );
}

/* ------------------------------------------------------------------ *
 * 6. Cola de grupos
 * ------------------------------------------------------------------ */

async function readTodayPlan() {
  const [entries, settings] = await Promise.all([readHistory(), readSettings()]);
  return buildPlan(todayInTz(), entries, settings);
}

function checkGroups(settled) {
  const id = 'groups';
  const label = 'Cola de grupos';

  if (!settled.ok) {
    return piece(
      id,
      label,
      'warn',
      `No pudimos armar la cola de grupos de hoy (${summarize(settled.error)}).`,
      'Abre la Cola de Grupos para ver el error completo. Si el almacenamiento esta en rojo, arregla eso primero.'
    );
  }

  const plan = settled.value || {};
  const stats = plan.stats || {};
  const pending = Number(stats.pendingToday) || 0;
  const posted = Number(stats.postedToday) || 0;
  const cooling = Number(stats.groupsInCooldown) || 0;
  const coolText = cooling
    ? ` ${plural(cooling, 'grupo esta', 'grupos estan')} en descanso.`
    : ' Ningun grupo esta en descanso.';

  if (pending > 0) {
    return piece(
      id,
      label,
      'ok',
      `Hay ${plural(pending, 'publicacion lista', 'publicaciones listas')} para hoy.${coolText}`
    );
  }

  if (posted > 0) {
    return piece(
      id,
      label,
      'ok',
      `Ya publicaste ${plural(posted, 'grupo', 'grupos')} hoy y no queda nada pendiente.${coolText}`
    );
  }

  // Sin trabajo hoy no es una falla: casi siempre es el descanso de 7 dias
  // haciendo su trabajo. El plan ya trae la explicacion escrita en castellano.
  const reason = typeof plan.reason === 'string' && plan.reason.trim()
    ? plan.reason.trim()
    : `Hoy no hay nada que publicar.${coolText}`;
  return piece(id, label, 'off', reason);
}

/* ------------------------------------------------------------------ *
 * 7. Leads
 * ------------------------------------------------------------------ */

function checkLeads(settled) {
  const id = 'leads';
  const label = 'Leads del sitio';

  if (!settled.ok) {
    return piece(
      id,
      label,
      'warn',
      `No pudimos leer el indice de leads (${summarize(settled.error)}).`,
      'Es un problema del almacenamiento. Arregla primero esa pieza y vuelve a refrescar.'
    );
  }

  const index = settled.value || {};
  const entries = Array.isArray(index.leads) ? index.leads : [];
  // El indice se recorta a sus entradas mas nuevas: el total lo lleva el propio
  // indice, no la longitud de la lista.
  const total = Number(index.total) || entries.length;

  if (!total) {
    return piece(
      id,
      label,
      'ok',
      'Todavia no ha entrado ningun lead por el sitio. Los formularios y los botones de WhatsApp estan listos para recibirlos.'
    );
  }

  const cutoff = Date.now() - 7 * DAY_MS;
  let last7 = 0;
  let attributed7 = 0;
  for (const entry of entries) {
    const ms = Date.parse(entry?.receivedAt);
    if (!Number.isFinite(ms) || ms < cutoff) continue;
    last7++;
    if (isListing(entry?.propertySlug)) attributed7++;
  }
  const rate = last7 ? Math.round((attributed7 / last7) * 100) : 0;

  if (!last7) {
    return piece(
      id,
      label,
      'ok',
      `${plural(total, 'lead', 'leads')} desde que empezamos a contar, pero ninguno en los ultimos 7 dias.`
    );
  }

  if (rate < MIN_ATTRIBUTION_RATE) {
    return piece(
      id,
      label,
      'warn',
      `${plural(total, 'lead', 'leads')} en total y ${last7} en los ultimos 7 dias, pero solo del ${rate}% sabemos que propiedad estaban mirando.`,
      'Los botones de contacto mandan la propiedad en su atributo data-prop. Si un lead llega sin ella no podemos saber que aviso funciono: revisa los botones de las paginas de propiedad.'
    );
  }

  return piece(
    id,
    label,
    'ok',
    `${plural(total, 'lead', 'leads')} en total, ${last7} en los ultimos 7 dias, y del ${rate}% sabemos que propiedad estaban mirando.`
  );
}

/* ------------------------------------------------------------------ *
 * 8. Catalogo de propiedades
 * ------------------------------------------------------------------ */

function checkCatalog() {
  const id = 'catalog';
  const label = 'Catalogo';

  const active = ALL_PROPERTIES.filter((p) => p && p.slug && p.active !== false);
  if (!active.length) {
    return piece(
      id,
      label,
      'down',
      'No hay ninguna propiedad activa en el catalogo, asi que no hay nada que publicar ni que responder.',
      'Revisa automation/data/properties.json: ninguna propiedad tiene active en true.'
    );
  }

  const gaps = [];
  for (const prop of active) {
    const name = prop.short_name || prop.name || prop.slug;
    // Cada hueco sabe si se dice en singular o en plural, para que la frase
    // final concuerde ("falta la cuota" pero "faltan los metros cuadrados").
    const missing = [];

    // Los terrenos no llevan size_m2 ni cuota de mantenimiento: miden en area_m2
    // y no tienen condominio. Pedirles esos dos campos seria ruido, no un hueco.
    const isLand = String(prop.type || '').toLowerCase() === 'land';
    if (!isLand && prop.size_m2 == null) missing.push({ text: 'los metros cuadrados', many: true });
    if (!isLand && prop.hoa_monthly_usd == null) {
      missing.push({ text: 'la cuota de mantenimiento', many: false });
    }

    const photos = Array.isArray(prop.post_images) ? prop.post_images.length : 0;
    if (photos < MIN_POST_IMAGES) {
      missing.push({
        text: `fotos para los posts (tiene ${photos} y hacen falta ${MIN_POST_IMAGES})`,
        many: true,
      });
    }

    if (!missing.length) continue;
    const verb = missing.length > 1 || missing[0].many ? 'faltan' : 'falta';
    gaps.push(`a ${name} le ${verb} ${listWords(missing.map((m) => m.text))}`);
  }

  if (!gaps.length) {
    return piece(
      id,
      label,
      'ok',
      `${plural(active.length, 'propiedad activa', 'propiedades activas')} y ninguna con datos a medias.`
    );
  }

  const howMany = gaps.length === 1 ? 'una tiene' : `${gaps.length} tienen`;
  return piece(
    id,
    label,
    'warn',
    `${plural(active.length, 'propiedad activa', 'propiedades activas')}, y ${howMany} datos a medias: ${gaps.join('; ')}.`,
    'Completa esos datos en automation/data/properties.json. Mientras falten, los posts y las respuestas automaticas no pueden mencionarlos, y a un comprador que pregunta la cuota hay que contestarle a mano.'
  );
}

/* ------------------------------------------------------------------ *
 * 9. Bot de Facebook
 *
 * A proposito NO se llama a la Graph API desde aqui: el panel se refresca cada
 * 30 segundos y eso quemaria la cuota de la Pagina en cada carga. Solo se
 * reporta si las variables estan puestas; quien comprueba el token de verdad es
 * `automation/fb_autoposter.py --verify`.
 * ------------------------------------------------------------------ */

function checkFacebook() {
  const id = 'facebook';
  const label = 'Bot de Facebook';

  const hasPage = Boolean(process.env.FB_PAGE_ID);
  const hasToken = Boolean(process.env.FB_PAGE_ACCESS_TOKEN);

  if (hasPage && hasToken) {
    return piece(
      id,
      label,
      'ok',
      'La Pagina y su token estan configurados, asi que el publicador automatico puede salir a Facebook. Desde aqui no lo comprobamos contra Facebook para no gastar cuota en cada carga.'
    );
  }

  if (!hasPage && !hasToken) {
    return piece(
      id,
      label,
      'off',
      'El bot de Facebook no esta configurado: no estan ni FB_PAGE_ID ni FB_PAGE_ACCESS_TOKEN. No se publica solo en la Pagina; los grupos igual van a mano desde la Cola de Grupos.'
    );
  }

  const missing = !hasPage ? 'FB_PAGE_ID' : 'FB_PAGE_ACCESS_TOKEN';
  return piece(
    id,
    label,
    'warn',
    `El bot de Facebook esta a medias: falta ${missing}. Con una sola de las dos variables no puede publicar.`,
    `Agrega ${missing} donde corre el publicador y comprueba el resultado con "python automation/fb_autoposter.py --verify".`
  );
}

/* ------------------------------------------------------------------ *
 * Semaforo general
 * ------------------------------------------------------------------ */

export function overallOf(pieces) {
  if (pieces.some((p) => p.state === 'down' && CRITICAL.has(p.id))) return 'down';
  if (pieces.some((p) => p.state === 'down' || p.state === 'warn')) return 'warn';
  return 'ok';
}

/* ------------------------------------------------------------------ *
 * Handler
 * ------------------------------------------------------------------ */

export async function status(req, res) {
  if (!requireAuth(req, res)) return;

  // vercel.json le pone `public, max-age=3600` a TODO. Un estado del sistema
  // cacheado una hora es exactamente lo contrario de un estado del sistema.
  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const checkedAt = new Date().toISOString();

  // Todas las lecturas a la vez y ninguna puede rechazar: el reporte tarda lo
  // que tarde la mas lenta, no la suma, y ninguna puede tumbar a las demas.
  const blobStart = Date.now();
  const [waha, blob, config, threads, autoToday, plan, leads] = await Promise.all([
    settle(readSessionState()),
    settle(list({ prefix: 'wa/', limit: 1 }).then(() => Date.now() - blobStart)),
    settle(getConfig()),
    settle(listThreads()),
    settle(countAutoRepliesToday()),
    settle(readTodayPlan()),
    settle(listLeads()),
  ]);

  const pieces = [
    safe('whatsapp', 'WhatsApp', () => checkWhatsApp(waha)),
    safe('webhook', 'Entrada de mensajes', () => checkWebhook()),
    safe('storage', 'Almacenamiento', () => checkStorage(blob)),
    safe('autoreply', 'Auto-respuesta', () => checkAutoReply(config, autoToday)),
    safe('inbox', 'Bandeja', () => checkInbox(threads)),
    safe('groups', 'Cola de grupos', () => checkGroups(plan)),
    safe('leads', 'Leads del sitio', () => checkLeads(leads)),
    safe('catalog', 'Catalogo', () => checkCatalog()),
    safe('facebook', 'Bot de Facebook', () => checkFacebook()),
  ];

  return res.status(200).json({ overall: overallOf(pieces), checkedAt, pieces });
}
