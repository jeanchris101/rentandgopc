/**
 * GET /api/groups/plan — la cola de grupos de Facebook para hoy.
 *
 * La Graph API de Meta ya no publica en grupos (la Groups API murio en abril
 * 2024), asi que esto NO publica nada: arma el post y el comentario, dice en que
 * grupo y con que foto, y el dueno pega en dos clics. Lo que el sistema si hace
 * es llevar la cuenta — que grupo recibio que propiedad y cuando — para que a
 * los 30 dias el ref diga que grupos dan compradores de verdad.
 *
 * Reglas de publicacion (hybrid-facebook-strategy.md, NO NEGOCIABLES):
 *   1. Maximo 1 post de listado por grupo por semana (cooldown de 7 dias).
 *   2. Maximo 2-3 grupos por dia (MAX_GROUPS_PER_DAY).
 *   3. Nunca la misma propiedad en dos grupos el mismo dia.
 *   4. El idioma lo decide el `lang` del grupo, no la fecha.
 *   5. El link de wa.me va en el PRIMER COMENTARIO, jamas en el cuerpo del post.
 *
 * La rotacion (propiedad, estilo, highlights, imagen) replica
 * automation/build_queue.py: mismo ordinal de fecha, mismo desempate, mismo
 * filtro de CONFOTUR, mismos 30 dias de descanso por imagen. Lo unico que cambia
 * a proposito esta marcado con "DIFERENCIA vs build_queue".
 *
 * -------------------------------------------------------------------------
 * Los JSON entran con `import ... with { type: 'json' }` por la misma razon que
 * api/_lib/classify.js: en Vercel el bundle de esbuild los deja INLINE, no
 * dependen del file-tracer, y un JSON roto revienta en build y no en la primera
 * llamada. Cero I/O en cold start.
 * -------------------------------------------------------------------------
 *
 * Este archivo tambien es el store del historial: api/groups/mark.js importa de
 * aqui (mismo patron que api/lead/list.js -> api/lead/capture.js).
 */
import { put, list } from '@vercel/blob';

import { requireAuth } from '../_lib/auth.js';
import groupsFile from '../../automation/data/group-assist-config.json' with { type: 'json' };
import propertiesFile from '../../automation/data/properties.json' with { type: 'json' };
import templatesFile from '../../automation/data/post-templates.json' with { type: 'json' };

/* ------------------------------------------------------------------ *
 * Constantes
 * ------------------------------------------------------------------ */

/** Un solo blob: el historial completo cabe de sobra (3 posts/dia x 18 grupos). */
export const HISTORY_KEY = 'groups/history.json';

/** Regla 1: un post de listado por grupo por semana. Jamas se relaja. */
export const GROUP_COOLDOWN_DAYS = 7;

/** Regla 2: el tope diario. 3 es el maximo del doc, no un objetivo a llenar. */
export const MAX_GROUPS_PER_DAY = 3;

/**
 * Descanso preferido por imagen, igual que build_queue.py. Alli SI se cumple
 * (un post al dia entre 5 propiedades = ~6 posts/mes por propiedad, y hay hasta
 * 6 fotos). Aqui salen ~2.57 posts al dia, o sea ~11 por propiedad en 21 dias:
 * la ventana de 30 dias es inalcanzable por aritmetica, no por un fallo. Lo que
 * queda garantizado es el LRU, que es lo que de verdad importa: se recorren
 * TODAS las fotos de la propiedad antes de repetir ninguna.
 */
const IMAGE_REUSE_DAYS = 30;

/** El dueno vive en RD; el dia arranca con su reloj, no con UTC. */
const TZ = 'America/Santo_Domingo';

/** Cuantas entradas de historial devolvemos al panel. */
const HISTORY_PAGE = 80;

const PUT_OPTS = { access: 'public', addRandomSuffix: false, contentType: 'application/json' };

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const LANGS = ['en', 'es', 'fr'];

/**
 * Codigos de propiedad del ref. Los mismos que REF_CODES en build_queue.py y que
 * SLUG_BY_REF_CODE en api/_lib/classify.js: si aqui se inventa otro, el panel de
 * WhatsApp deja de reconocer de donde vino el lead.
 */
export const REF_CODES = {
  'cocotal-2bdr': 'A301',
  'paseo-cocotal': 'PB202',
  'karen-los-corales': 'KLC1',
  'land-autovia-este': 'LAUT',
  'land-cepm-vistacana': 'LCEP',
};

/** Mensaje corto que lleva el ref dentro del link de wa.me (igual a build_queue). */
const WA_PREFILL = {
  en: "Hi! I'm interested in {short_name} ({price}). (Ref: {ref})",
  es: 'Hola! Me interesa {short_name} ({price}). (Ref: {ref})',
  fr: "Bonjour! Je m'interesse a {short_name} ({price}). (Ref: {ref})",
};

/**
 * Ultima linea del POST. Sustituye a la linea del {wa_link} que trae la plantilla:
 * regla 5, el link va al comentario. Sin acentos, como el resto de los datos del
 * proyecto, para que pegar en Facebook no dependa del encoding del portapapeles.
 */
const POST_CTA = {
  en: 'Details in the first comment.',
  es: 'Detalles en el primer comentario.',
  fr: 'Details dans le premier commentaire.',
};

/** El PRIMER COMENTARIO: aqui si va el link, con el ref del grupo dentro. */
const COMMENT_LEAD = {
  en: 'Details, more photos and the full numbers here. WhatsApp me directly:',
  es: 'Detalles, mas fotos y todos los numeros aqui. Escribeme directo por WhatsApp:',
  fr: 'Details, plus de photos et tous les chiffres ici. Ecris-moi directement sur WhatsApp:',
};

/**
 * Guardia de la regla 5. No corta el link: descarta la linea completa y avisa,
 * porque media linea sin su URL queda peor que sin la linea. Con las plantillas
 * de hoy no dispara nunca; existe para que una edicion futura de
 * post-templates.json no meta un link en el cuerpo sin que nadie se entere.
 */
const LINK_RE = /(?:https?:\/\/|www\.|\bwa\.me\b|\b[\w-]+\.(?:com|net|org|do|ca|fr|es)\/)/i;

/* ------------------------------------------------------------------ *
 * Catalogos (validados al importar, no en cada request)
 * ------------------------------------------------------------------ */

/** Los 18 grupos, en el orden del archivo: el indice alimenta los desempates. */
export const GROUPS = (Array.isArray(groupsFile?.groups) ? groupsFile.groups : [])
  .filter((g) => g && g.code && g.url)
  .map((g, index) => ({
    index,
    code: String(g.code).toUpperCase(),
    name: String(g.name || g.code),
    url: String(g.url),
    lang: normalizeLang(g.lang),
  }));

/** Propiedades activas CON codigo de ref. Sin codigo no hay atribucion posible. */
export const PROPERTIES = (Array.isArray(propertiesFile?.properties) ? propertiesFile.properties : [])
  .filter((p) => p && p.slug && p.active !== false && REF_CODES[p.slug]);

const STYLES = Array.isArray(templatesFile?.styles) ? templatesFile.styles : [];

const SITE_BASE = String(propertiesFile?.site_base_url || '').replace(/\/+$/, '');
const WA_NUMBER = String(propertiesFile?.whatsapp_number || '').replace(/\D/g, '');

const GROUP_BY_CODE = new Map(GROUPS.map((g) => [g.code, g]));
const PROP_BY_SLUG = new Map(PROPERTIES.map((p) => [p.slug, p]));
const PROP_INDEX = new Map(PROPERTIES.map((p, i) => [p.slug, i]));

/** Slugs activos sin codigo de ref: se quedan fuera y hay que saberlo. */
const MISSING_REF_CODES = (Array.isArray(propertiesFile?.properties) ? propertiesFile.properties : [])
  .filter((p) => p && p.slug && p.active !== false && !REF_CODES[p.slug])
  .map((p) => p.slug);

if (MISSING_REF_CODES.length) {
  console.error(
    '[groups/plan] sin codigo de ref (fuera de la rotacion): %s. Agregalos a REF_CODES.',
    MISSING_REF_CODES.join(', ')
  );
}

/* ------------------------------------------------------------------ *
 * Fechas
 * ------------------------------------------------------------------ */

export function normalizeLang(value) {
  const l = String(value || '').toLowerCase().slice(0, 2);
  return LANGS.includes(l) ? l : 'en';
}

/** YYYY-MM-DD en hora dominicana. */
export function todayInTz(tz = TZ) {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date());
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

/**
 * El mismo numero que date.toordinal() de Python (1-01-01 -> 1). Hay que
 * replicarlo exacto: build_queue.py elige estilo e highlights con `ordinal % n`,
 * y un desfase de un dia cambiaria el texto que sale.
 */
export function ordinalOf(dateStr) {
  const [y, m, d] = String(dateStr).split('-').map(Number);
  return Math.round(Date.UTC(y, m - 1, d) / 86400000) + 719163;
}

/** Dias de `from` a `to` (positivo si `to` es posterior). */
export function daysBetween(from, to) {
  return ordinalOf(to) - ordinalOf(from);
}

export function addDays(dateStr, n) {
  const [y, m, d] = String(dateStr).split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

function isDate(value) {
  return typeof value === 'string' && DATE_RE.test(value);
}

const MONTHS_ES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/**
 * "2026-08-10" -> "10 ago 2026". Solo para los textos de `reason`: el panel
 * pinta las fechas asi, y mezclar los dos formatos en el mismo parrafo se lee mal.
 */
function humanDate(dateStr) {
  if (!isDate(dateStr)) return String(dateStr || '');
  const [y, m, d] = dateStr.split('-').map(Number);
  return `${d} ${MONTHS_ES[m - 1]} ${y}`;
}

/** Modulo que nunca devuelve negativo (el % de JS si, el de Python no). */
function mod(a, n) {
  return ((a % n) + n) % n;
}

/* ------------------------------------------------------------------ *
 * Ref, wa.me, textos
 * ------------------------------------------------------------------ */

/** RG-<CODIGO PROPIEDAD>-G<NN>: G04 -> RG-A301-G04. Lo lee classify.js tal cual. */
export function buildRef(slug, groupCode) {
  const code = REF_CODES[slug];
  if (!code) return null;
  const digits = String(groupCode || '').replace(/\D/g, '');
  const nn = digits || String(groupCode || '').replace(/[^A-Z0-9]/gi, '').toUpperCase();
  return `RG-${code}-G${nn}`;
}

/**
 * urlencode con el mismo conjunto seguro que `quote(s, safe='')` de Python, para
 * que el link del grupo y el de la Pagina salgan identicos byte a byte.
 * encodeURIComponent deja pasar !'()* y quote no.
 */
function quoteAll(text) {
  return encodeURIComponent(String(text)).replace(
    /[!'()*]/g,
    (c) => '%' + c.charCodeAt(0).toString(16).toUpperCase()
  );
}

export function buildWaLink(prop, lang, ref) {
  const prefill = fill(WA_PREFILL[lang] || WA_PREFILL.en, {
    short_name: prop.short_name || prop.name || '',
    price: prop.price_display || '',
    ref,
  });
  return `https://wa.me/${WA_NUMBER}?text=${quoteAll(prefill)}`;
}

/** Sustituye {clave} por su valor; lo que no este en `values` se queda tal cual. */
function fill(template, values) {
  return String(template).replace(/\{(\w+)\}/g, (m, key) =>
    Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : m
  );
}

/**
 * Dos highlights rotados por fecha, en el idioma del grupo. Copia de
 * pick_highlights() de build_queue.py: highlights_<lang> con fallback al ingles
 * (un post en es no lleva bullets en ingles) y las lineas de CONFOTUR solo si la
 * propiedad tiene confotur === true.
 */
export function pickHighlights(prop, dateStr, lang) {
  const source = prop[`highlights_${lang}`] || prop.highlights || [];
  const highlights = source.filter(
    (h) => prop.confotur === true || !String(h).toLowerCase().includes('confotur')
  );
  if (highlights.length < 2) return null;
  const i = ordinalOf(dateStr) % highlights.length;
  return [highlights[i], highlights[(i + 1) % highlights.length]];
}

/**
 * Estilo rotado, saltando los que no aceptan el tipo de propiedad (daily_life es
 * solo para condo: aplicado a un terreno se lee absurdo). Igual que
 * select_style() de build_queue.py.
 *
 * DIFERENCIA vs build_queue: el arranque es (ordinal + offset) y no solo
 * `ordinal`. build_queue hace UN post al dia, asi que la fecha le basta; aqui
 * salen hasta 3 el mismo dia y sin el offset los tres usarian el mismo estilo
 * ("Vary your post format" del doc). El offset es el indice del grupo en el
 * config — estable — y no la posicion en la cola: si fuera la posicion, saltar
 * una tarjeta le cambiaria el estilo a las de abajo, incluido un texto que el
 * dueno ya pudo haber copiado.
 */
export function selectStyle(prop, dateStr, offset = 0) {
  const n = STYLES.length;
  if (!n) return null;
  const start = mod(ordinalOf(dateStr) + offset, n);
  for (let k = 0; k < n; k++) {
    const style = STYLES[(start + k) % n];
    const allowed = style?.types;
    if (!Array.isArray(allowed) || !allowed.length || allowed.includes(prop.type)) return style;
  }
  return null;
}

/** Un aviso por propiedad y por instancia: no llenar el log con lo mismo. */
const WARNED_SINGLE_IMAGE = new Set();

/**
 * Imagen menos usada de post_images[], prefiriendo las que llevan 30 dias sin
 * salir. Igual que select_image() de build_queue.py, salvo el aviso: alli el
 * fallback "todas usadas dentro de la ventana" era una anomalia, aqui es el
 * estado normal (ver IMAGE_REUSE_DAYS), asi que avisar de eso cada request seria
 * ruido que el dueno no puede arreglar.
 *
 * Lo que si se avisa es lo accionable: una propiedad con una sola foto sale con
 * la MISMA imagen en los 18 grupos, y eso se arregla subiendo fotos
 * (land-cepm-vistacana hoy tiene una; properties.json ya lo anota).
 */
export function selectImage(prop, imageLastUsed, dateStr) {
  const images = (Array.isArray(prop.post_images) && prop.post_images.length
    ? prop.post_images
    : [prop.hero_image]
  ).filter(Boolean);
  if (!images.length) return null;

  if (images.length < 2 && !WARNED_SINGLE_IMAGE.has(prop.slug)) {
    WARNED_SINGLE_IMAGE.add(prop.slug);
    console.warn(
      '[groups/plan] %s solo tiene 1 foto en post_images: sale la misma en todos los grupos. Agrega mas.',
      prop.slug
    );
  }

  const used = imageLastUsed?.[prop.slug] || {};
  const ranked = images
    .map((img, idx) => ({ img, idx, last: isDate(used[img]) ? used[img] : null }))
    .sort((a, b) => (a.last ? ordinalOf(a.last) : 0) - (b.last ? ordinalOf(b.last) : 0) || a.idx - b.idx);

  // Preferencia: fuera de la ventana de 30 dias. Si no hay ninguna, la mas
  // antigua — que por el orden del LRU es la que lleva mas tiempo sin salir.
  const fresh = ranked.filter((r) => !r.last || daysBetween(r.last, dateStr) >= IMAGE_REUSE_DAYS);
  return (fresh.length ? fresh[0] : ranked[0]).img;
}

/**
 * El cuerpo del POST: la plantilla sin la linea del {wa_link} y con la linea de
 * "detalles en el comentario" en su lugar. Regla 5.
 */
function renderPostText(template, prop, lang, highlights) {
  const values = {
    name: prop.name,
    price: prop.price_display,
    neighborhood: prop[`neighborhood_${lang}`] || prop.neighborhood || '',
    highlight_1: highlights[0],
    highlight_2: highlights[1],
  };

  const kept = [];
  for (const raw of String(template).split('\n')) {
    if (raw.includes('{wa_link}')) continue; // regla 5: el link va al comentario
    const line = fill(raw, values);
    if (LINK_RE.test(line)) {
      console.warn('[groups/plan] linea con link descartada del cuerpo del post: %s', line);
      continue;
    }
    kept.push(line);
  }

  const body = kept.join('\n').replace(/\n{3,}/g, '\n\n').trim();
  return `${body}\n\n${POST_CTA[lang] || POST_CTA.en}`;
}

/** El PRIMER COMENTARIO: lead-in + wa.me con el ref del grupo. */
function renderCommentText(prop, lang, ref) {
  return `${COMMENT_LEAD[lang] || COMMENT_LEAD.en}\n${buildWaLink(prop, lang, ref)}`;
}

/* ------------------------------------------------------------------ *
 * Historial en Blob
 * ------------------------------------------------------------------ */

/**
 * put() sirve detras de un CDN: sin ?t= y no-store se lee una copia vieja y se
 * escribe encima. Mismo apano que api/track.js y api/_lib/wa-store.js.
 */
async function readJson(key, fallback) {
  try {
    const { blobs } = await list({ prefix: key });
    const blob = blobs.find((b) => b.pathname === key);
    if (!blob) return fallback;
    const res = await fetch(`${blob.url}?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return fallback;
    return await res.json();
  } catch {
    // Blob ausente es el arranque en frio normal, no un error.
    return fallback;
  }
}

/** Clave de idempotencia: un grupo, una propiedad, un dia. */
export function entryId(date, groupCode, propertySlug) {
  return `${date}|${String(groupCode).toUpperCase()}|${propertySlug}`;
}

/** Descarta lo que no se pueda usar para calcular cooldowns. Nunca lanza. */
export function normalizeEntry(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const date = String(raw.date || '').slice(0, 10);
  const groupCode = String(raw.groupCode || '').toUpperCase();
  const propertySlug = String(raw.propertySlug || '');
  if (!isDate(date) || !groupCode || !propertySlug) return null;

  const group = GROUP_BY_CODE.get(groupCode);
  const prop = PROP_BY_SLUG.get(propertySlug);

  return {
    id: entryId(date, groupCode, propertySlug),
    date,
    groupCode,
    groupName: String(raw.groupName || group?.name || groupCode),
    propertySlug,
    propertyName: String(raw.propertyName || prop?.short_name || prop?.name || propertySlug),
    lang: normalizeLang(raw.lang || group?.lang),
    ref: raw.ref ? String(raw.ref) : buildRef(propertySlug, groupCode),
    image: raw.image ? String(raw.image) : null,
    skipped: raw.skipped === true,
    markedAt: raw.markedAt || raw.ts || null,
  };
}

/** Entradas del historial, mas viejas primero. Tolera un array pelado. */
export async function readHistory() {
  const raw = await readJson(HISTORY_KEY, null);
  const list_ = Array.isArray(raw) ? raw : Array.isArray(raw?.entries) ? raw.entries : [];
  return list_
    .map(normalizeEntry)
    .filter(Boolean)
    .sort((a, b) => a.date.localeCompare(b.date) || String(a.markedAt).localeCompare(String(b.markedAt)));
}

export async function writeHistory(entries) {
  await put(
    HISTORY_KEY,
    JSON.stringify({ updatedAt: new Date().toISOString(), entries }),
    PUT_OPTS
  );
  return entries;
}

/**
 * Fecha del ultimo uso de cada imagen por propiedad. Solo cuenta lo PUBLICADO:
 * si lo salto, la foto no salio y no gasta sus 30 dias de descanso.
 */
export function imageLastUsedFrom(entries) {
  const map = {};
  for (const e of entries) {
    if (e.skipped || !e.image) continue;
    const perProp = map[e.propertySlug] || (map[e.propertySlug] = {});
    if (!perProp[e.image] || e.date > perProp[e.image]) perProp[e.image] = e.date;
  }
  return map;
}

/* ------------------------------------------------------------------ *
 * Plan del dia (funcion pura: entra la fecha y el historial, sale el plan)
 * ------------------------------------------------------------------ */

function assignmentOf(group, prop, dateStr, imageLastUsed, recorded) {
  const lang = group.lang;
  const highlights = pickHighlights(prop, dateStr, lang);
  if (!highlights) {
    console.error('[groups/plan] %s no tiene 2 highlights usables en %s', prop.slug, lang);
    return null;
  }
  const style = selectStyle(prop, dateStr, group.index);
  const template = style?.templates?.[lang];
  if (!template) {
    console.error('[groups/plan] sin plantilla para %s en %s', prop.slug, lang);
    return null;
  }

  const ref = recorded?.ref || buildRef(prop.slug, group.code);
  const image = recorded?.image || selectImage(prop, imageLastUsed, dateStr);

  return {
    groupCode: group.code,
    groupName: group.name,
    groupUrl: group.url,
    lang,
    propertySlug: prop.slug,
    propertyName: prop.name,
    propertyShortName: prop.short_name || prop.name,
    priceDisplay: prop.price_display || '',
    // Absoluta a proposito: la baja o la arrastra desde el telefono.
    imageUrl: image ? `${SITE_BASE}/${image}` : null,
    imagePath: image,
    imageFilename: image ? image.split('/').pop() : null,
    styleId: style.id || null,
    postText: renderPostText(template, prop, lang, highlights),
    commentText: renderCommentText(prop, lang, ref),
    ref,
    alreadyPosted: Boolean(recorded && !recorded.skipped),
    markedAt: recorded?.markedAt || null,
  };
}

/**
 * Propiedades ordenadas por "menos publicada recientemente EN ESE GRUPO".
 * Nunca publicada en el grupo va primero (como date.min en build_queue). El
 * desempate rota por fecha y por grupo, asi que en el dia 1 (sin historial) los
 * grupos no piden todos la misma propiedad.
 */
function rankProperties(group, dateStr, lastByGroupProp) {
  const ord = ordinalOf(dateStr);
  const n = PROPERTIES.length;
  return PROPERTIES.map((p) => {
    const last = lastByGroupProp.get(`${group.code}|${p.slug}`) || null;
    return {
      prop: p,
      last,
      key0: last ? ordinalOf(last) : 0,
      key1: mod(PROP_INDEX.get(p.slug) - ord - group.index, n),
    };
  })
    .sort((a, b) => a.key0 - b.key0 || a.key1 - b.key1)
    .map((x) => x.prop);
}

/**
 * buildPlan(dateStr, entries) -> el plan del dia, sin tocar red.
 *
 * Determinista y estable: el plan es funcion de (fecha, historial). Marcar una
 * tarjeta solo agrega la entrada que este mismo calculo ya habia elegido, asi
 * que recargar a media manana no le cambia el texto a las tarjetas que quedan.
 */
export function buildPlan(dateStr, entries) {
  const history = (Array.isArray(entries) ? entries : []).filter(Boolean);

  const lastPostedByGroup = new Map(); // code -> fecha del ultimo post (sin saltados)
  const lastPropByGroup = new Map(); // code -> { slug, name } de ese ultimo post
  const lastByGroupProp = new Map(); // `code|slug` -> fecha
  let postsLast7Days = 0;
  let totalPosts = 0;

  for (const e of history) {
    if (e.skipped) continue; // saltar no gasta cooldown de nada
    totalPosts++;
    if (daysBetween(e.date, dateStr) < 7 && e.date <= dateStr) postsLast7Days++;

    const prevGroup = lastPostedByGroup.get(e.groupCode);
    if (!prevGroup || e.date > prevGroup) {
      lastPostedByGroup.set(e.groupCode, e.date);
      lastPropByGroup.set(e.groupCode, { slug: e.propertySlug, name: e.propertyName });
    }
    const key = `${e.groupCode}|${e.propertySlug}`;
    const prevPair = lastByGroupProp.get(key);
    if (!prevPair || e.date > prevPair) lastByGroupProp.set(key, e.date);
  }

  const todays = history.filter((e) => e.date === dateStr);
  const postedToday = todays.filter((e) => !e.skipped);
  const skippedToday = todays.filter((e) => e.skipped);
  const skippedTodayCodes = new Set(skippedToday.map((e) => e.groupCode));
  const imageLastUsed = imageLastUsedFrom(history);

  // Estado por grupo: lo que el panel pinta como cooldown.
  const groups = GROUPS.map((g) => {
    const last = lastPostedByGroup.get(g.code) || null;
    const daysSince = last ? daysBetween(last, dateStr) : null;
    const cooling = last !== null && daysSince < GROUP_COOLDOWN_DAYS;
    return {
      code: g.code,
      name: g.name,
      url: g.url,
      lang: g.lang,
      lastPostedDate: last,
      lastPropertySlug: lastPropByGroup.get(g.code)?.slug || null,
      lastPropertyName: lastPropByGroup.get(g.code)?.name || null,
      daysSinceLastPost: daysSince,
      cooldown: cooling,
      daysUntilFree: cooling ? GROUP_COOLDOWN_DAYS - daysSince : 0,
      freeOn: cooling ? addDays(last, GROUP_COOLDOWN_DAYS) : null,
      postedToday: postedToday.some((e) => e.groupCode === g.code),
      skippedToday: skippedTodayCodes.has(g.code),
    };
  });

  // Ya publicado hoy: se muestra igual, marcado, con la foto y el ref que quedaron
  // grabados. Consume slot del dia.
  const done = [];
  for (const e of postedToday) {
    const group = GROUP_BY_CODE.get(e.groupCode);
    const prop = PROP_BY_SLUG.get(e.propertySlug);
    if (!group || !prop) continue; // grupo o propiedad retirados del config
    const a = assignmentOf(group, prop, dateStr, imageLastUsed, e);
    if (a) done.push(a);
  }

  const slotsLeft = Math.max(0, MAX_GROUPS_PER_DAY - postedToday.length);

  // Candidatos a trabajo nuevo: fuera de cooldown y no saltados hoy. El que lleva
  // mas tiempo sin recibir nada va primero; desempate rotado por fecha, como en
  // select_property() de build_queue.py.
  const ord = ordinalOf(dateStr);
  const candidates = groups
    .filter((g) => !g.cooldown && !g.skippedToday)
    .map((g) => ({
      g,
      key0: g.lastPostedDate ? ordinalOf(g.lastPostedDate) : 0,
      key1: mod(GROUP_BY_CODE.get(g.code).index - ord, GROUPS.length),
    }))
    .sort((a, b) => a.key0 - b.key0 || a.key1 - b.key1)
    .map((x) => x.g);

  // Regla 3: una propiedad no se repite el mismo dia en otro grupo.
  const claimed = new Set(postedToday.map((e) => e.propertySlug));
  const pending = [];
  for (const status of candidates) {
    if (pending.length >= slotsLeft) break;
    const group = GROUP_BY_CODE.get(status.code);
    for (const prop of rankProperties(group, dateStr, lastByGroupProp)) {
      if (claimed.has(prop.slug)) continue;
      const a = assignmentOf(group, prop, dateStr, imageLastUsed, null);
      if (!a) continue; // sin highlights o sin plantilla: siguiente propiedad
      claimed.add(prop.slug);
      pending.push(a);
      break;
    }
  }

  const assignments = [...pending, ...done];
  const cooling = groups.filter((g) => g.cooldown).sort((a, b) => a.freeOn.localeCompare(b.freeOn));
  const nextFree = cooling.length ? cooling[0] : null;

  return {
    date: dateStr,
    assignments,
    reason: buildReason({
      dateStr,
      pending,
      done,
      groups,
      candidates,
      slotsLeft,
      skippedToday,
      nextFree,
    }),
    groups,
    stats: {
      date: dateStr,
      totalGroups: GROUPS.length,
      totalProperties: PROPERTIES.length,
      dailyMax: MAX_GROUPS_PER_DAY,
      cooldownDays: GROUP_COOLDOWN_DAYS,
      pendingToday: pending.length,
      postedToday: postedToday.length,
      skippedToday: skippedToday.length,
      slotsLeft,
      groupsFree: groups.filter((g) => !g.cooldown).length,
      groupsInCooldown: cooling.length,
      nextFreeDate: nextFree ? nextFree.freeOn : null,
      nextFreeGroup: nextFree ? nextFree.name : null,
      postsLast7Days,
      totalPosts,
    },
    // Lo mas nuevo primero. Se ordena aqui en vez de confiar en que el llamador
    // ya venga ordenado: readHistory() si lo hace, pero un blob editado a mano no.
    history: history
      .slice()
      .sort((a, b) => b.date.localeCompare(a.date) || String(b.markedAt).localeCompare(String(a.markedAt)))
      .slice(0, HISTORY_PAGE)
      .map((e) => ({
        date: e.date,
        groupCode: e.groupCode,
        groupName: e.groupName,
        propertySlug: e.propertySlug,
        propertyName: e.propertyName,
        lang: e.lang,
        ref: e.ref,
        skipped: e.skipped,
        markedAt: e.markedAt,
      })),
  };
}

/**
 * Por que no hay (o hay poco) trabajo hoy. En espanol y con fechas: el estado
 * vacio tiene que ser honesto, no inventar tareas ni relajar el cooldown en
 * silencio.
 */
function buildReason({ dateStr, pending, done, groups, candidates, slotsLeft, skippedToday, nextFree }) {
  if (!GROUPS.length) return 'No hay grupos en automation/data/group-assist-config.json.';
  if (!PROPERTIES.length) {
    return 'No hay propiedades activas con codigo de ref en properties.json. Revisa REF_CODES.';
  }
  if (!WA_NUMBER || !SITE_BASE) {
    return 'properties.json necesita site_base_url y whatsapp_number para armar el link y la foto.';
  }
  if (pending.length) return null;

  if (slotsLeft === 0) {
    return `Ya publicaste en ${done.length} ${done.length === 1 ? 'grupo' : 'grupos'} hoy. ` +
      `El maximo es ${MAX_GROUPS_PER_DAY} al dia (regla 2): mas que eso y Facebook lo lee como spam. ` +
      'Vuelve manana.';
  }

  if (!candidates.length) {
    const cooling = groups.filter((g) => g.cooldown);
    if (cooling.length === groups.length) {
      return `Los ${groups.length} grupos recibieron un post de listado en los ultimos ` +
        `${GROUP_COOLDOWN_DAYS} dias. El primero que se libera es ${nextFree.name} el ${humanDate(nextFree.freeOn)}. ` +
        'Hoy no toca publicar listados: es el momento de comentar y aportar valor (regla 1).';
    }
    const bits = [];
    if (skippedToday.length) {
      bits.push(`saltaste ${skippedToday.length} ${skippedToday.length === 1 ? 'grupo' : 'grupos'} hoy`);
    }
    if (cooling.length) {
      bits.push(`${cooling.length} ${cooling.length === 1 ? 'esta' : 'estan'} en cooldown de ${GROUP_COOLDOWN_DAYS} dias`);
    }
    return `No queda grupo elegible hoy${bits.length ? ': ' + bits.join(' y ') : ''}.` +
      (nextFree ? ` El proximo se libera el ${humanDate(nextFree.freeOn)}.` : '');
  }

  // Hay grupo libre pero no salio ninguna asignacion. Con 5 propiedades y tope 3
  // al dia la regla 3 no puede agotarlas, asi que esto huele a plantilla o
  // highlights rotos: el log del servidor lo dice linea por linea.
  return 'Hay grupos libres pero no pude armar ninguna asignacion: o no quedan propiedades sin ' +
    'usar hoy (regla 3), o una propiedad se quedo sin plantilla o sin 2 highlights en el idioma ' +
    'del grupo. Revisa los logs del servidor.';
}

/* ------------------------------------------------------------------ *
 * Handler
 * ------------------------------------------------------------------ */

export default async function handler(req, res) {
  if (!requireAuth(req, res)) return;

  // vercel.json le pone `public, max-age=3600` a TODO. Sin esto el plan quedaria
  // cacheado una hora (y potencialmente compartido).
  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const date = todayInTz();
    const entries = await readHistory();
    return res.status(200).json(buildPlan(date, entries));
  } catch (err) {
    console.error('[groups/plan] error:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
