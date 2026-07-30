/**
 * GET/POST /api/groups/settings — los ajustes de la cola de grupos.
 *
 * Dos formas de trabajar, y esto decide cual:
 *
 *   mode: "campaign"  Un dia = UNA propiedad = N grupos, a horas espaciadas.
 *                     Cada slot lleva grupo distinto, estilo de copy distinto,
 *                     foto distinta y el idioma de su grupo. Esa variacion es
 *                     lo que evita que 5 posts de la misma propiedad se lean
 *                     como contenido duplicado.
 *
 *   mode: "spread"    El comportamiento historico: propiedades DISTINTAS el
 *                     mismo dia, una por grupo, tope MAX_GROUPS_PER_DAY.
 *
 * El plan (./plan.js) importa de aqui. La dependencia va en un solo sentido a
 * proposito: este archivo no importa nada de plan.js, asi que no hay ciclo de
 * modulos que dependa del orden de evaluacion de esbuild en Vercel.
 *
 * Retrocompatible: si el blob `groups/settings.json` no existe, readSettings()
 * devuelve DEFAULT_SETTINGS y todo sigue funcionando sin haber guardado nada.
 *
 * Lo que NO hace este endpoint: publicar, programar, disparar nada. Guarda
 * numeros. El unico efecto de subir groupsPerDay es que la cola te ofrezca mas
 * tarjetas; apretar Publicar sigue siendo tuyo.
 */
import { put, list } from '@vercel/blob';

import { requirePanelOrExtensionAuth } from '../_lib/auth.js';
import propertiesFile from '../../automation/data/properties.json' with { type: 'json' };

/* ------------------------------------------------------------------ *
 * Constantes
 * ------------------------------------------------------------------ */

export const SETTINGS_KEY = 'groups/settings.json';

const PUT_OPTS = { access: 'public', addRandomSuffix: false, contentType: 'application/json' };

export const MODES = ['campaign', 'spread'];

/** Los defaults SON la configuracion valida cuando no hay blob. */
export const DEFAULT_SETTINGS = Object.freeze({
  mode: 'campaign',
  groupsPerDay: 5,
  intervalHours: 2,
  startHour: 9, // hora de Santo Domingo
  autoRotateProperty: true,
  activePropertySlug: null,
  campaignSpansDays: 1,
});

/**
 * Rangos duros. No son gustos: 8 grupos al dia con la misma propiedad ya es
 * mucho, un intervalo de mas de 6 horas no cabe en un dia, y antes de las 6 o
 * despues de las 20 no hay nadie leyendo grupos de Punta Cana.
 */
export const LIMITS = Object.freeze({
  groupsPerDay: { min: 1, max: 8 },
  intervalHours: { min: 1, max: 6 },
  startHour: { min: 6, max: 20 },
  campaignSpansDays: { min: 1, max: 7 },
});

const FIELD_LABEL = {
  groupsPerDay: 'Grupos por dia',
  intervalHours: 'Horas entre posts',
  startHour: 'Hora de inicio',
  campaignSpansDays: 'Dias de campana',
};

/**
 * A partir de aqui se avisa, pero NO se bloquea. Un admin puede estar en varios
 * de los 18 grupos: si ve el mismo anuncio 7 veces el mismo dia lo lee como
 * spam aunque el texto y la foto cambien. Es decision del dueno; lo que no vale
 * es que la tome sin verlo.
 */
export const CROWDED_GROUPS_PER_DAY = 6;

/* ------------------------------------------------------------------ *
 * Catalogo de propiedades (para el selector de propiedad fija de la UI)
 *
 * Se lee de properties.json y no de plan.js justamente para no crear el ciclo.
 * plan.js filtra ademas por REF_CODES (sin codigo de ref no hay atribucion): si
 * alguna vez hay una propiedad activa sin codigo, este endpoint la aceptaria y
 * plan.js caeria a la rotacion automatica diciendolo en `campaign.note`.
 * ------------------------------------------------------------------ */

export const SETTINGS_PROPERTIES = (Array.isArray(propertiesFile?.properties) ? propertiesFile.properties : [])
  .filter((p) => p && p.slug && p.active !== false)
  .map((p) => {
    const photos = (Array.isArray(p.post_images) && p.post_images.length ? p.post_images : [p.hero_image]).filter(
      Boolean
    );
    return {
      slug: String(p.slug),
      name: String(p.name || p.slug),
      shortName: String(p.short_name || p.name || p.slug),
      priceDisplay: String(p.price_display || ''),
      type: String(p.type || ''),
      photoCount: photos.length,
    };
  });

const SLUGS = new Set(SETTINGS_PROPERTIES.map((p) => p.slug));

/* ------------------------------------------------------------------ *
 * Coercion y normalizacion (tolerante: nunca lanza)
 * ------------------------------------------------------------------ */

function coerceInt(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

/** Los formularios mandan strings; "false" es truthy y no puede colarse. */
function coerceBool(value, fallback) {
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'boolean') return value;
  return value === 'true' || value === '1' || value === 1;
}

function clamp(n, range) {
  return Math.min(range.max, Math.max(range.min, n));
}

/**
 * Lo que sea que haya en el blob -> una config usable. Recorta en vez de
 * rechazar: un blob editado a mano con groupsPerDay 99 no puede dejar la cola
 * sin plan, solo se lee como 8.
 */
export function normalizeSettings(raw) {
  const r = raw && typeof raw === 'object' ? raw : {};
  const mode = MODES.includes(String(r.mode)) ? String(r.mode) : DEFAULT_SETTINGS.mode;
  const slug = r.activePropertySlug === undefined || r.activePropertySlug === null ? '' : String(r.activePropertySlug);

  const out = {
    mode,
    groupsPerDay: clamp(coerceInt(r.groupsPerDay, DEFAULT_SETTINGS.groupsPerDay), LIMITS.groupsPerDay),
    intervalHours: clamp(coerceInt(r.intervalHours, DEFAULT_SETTINGS.intervalHours), LIMITS.intervalHours),
    startHour: clamp(coerceInt(r.startHour, DEFAULT_SETTINGS.startHour), LIMITS.startHour),
    autoRotateProperty: coerceBool(r.autoRotateProperty, DEFAULT_SETTINGS.autoRotateProperty),
    activePropertySlug: SLUGS.has(slug) ? slug : null,
    campaignSpansDays: clamp(coerceInt(r.campaignSpansDays, DEFAULT_SETTINGS.campaignSpansDays), LIMITS.campaignSpansDays),
  };

  // Rotacion apagada sin propiedad fija valida = campana sin propiedad. Se
  // vuelve a encender la rotacion antes que devolver un dia vacio.
  if (!out.autoRotateProperty && !out.activePropertySlug) out.autoRotateProperty = true;
  return out;
}

/* ------------------------------------------------------------------ *
 * Validacion estricta (la del POST: aqui si se rechaza y se explica)
 * ------------------------------------------------------------------ */

/**
 * validateSettings(patch, base) -> { ok, errors, settings }
 *
 * Patch parcial: lo que no venga se queda como estaba. Fuera de rango NO se
 * recorta en silencio — se responde 400 con el rango, porque el dueno escribio
 * un numero a proposito y merece saber que no se guardo.
 */
export function validateSettings(patch, base) {
  const p = patch && typeof patch === 'object' ? patch : {};
  const current = normalizeSettings(base);
  const next = { ...current };
  const errors = [];

  if (p.mode !== undefined) {
    const mode = String(p.mode);
    if (!MODES.includes(mode)) {
      errors.push(`El modo tiene que ser "campaign" (una propiedad en varios grupos) o "spread" (una propiedad por grupo); llego "${mode}".`);
    } else {
      next.mode = mode;
    }
  }

  for (const key of ['groupsPerDay', 'intervalHours', 'startHour', 'campaignSpansDays']) {
    if (p[key] === undefined || p[key] === null || p[key] === '') continue;
    const n = Number(p[key]);
    const { min, max } = LIMITS[key];
    if (!Number.isInteger(n)) {
      errors.push(`${FIELD_LABEL[key]}: "${p[key]}" no es un numero entero.`);
      continue;
    }
    if (n < min || n > max) {
      errors.push(`${FIELD_LABEL[key]}: ${n} esta fuera de rango. Tiene que estar entre ${min} y ${max}.`);
      continue;
    }
    next[key] = n;
  }

  if (p.autoRotateProperty !== undefined) {
    next.autoRotateProperty = coerceBool(p.autoRotateProperty, current.autoRotateProperty);
  }

  if (p.activePropertySlug !== undefined) {
    const slug = p.activePropertySlug === null || p.activePropertySlug === '' ? null : String(p.activePropertySlug);
    if (slug !== null && !SLUGS.has(slug)) {
      errors.push(`Propiedad desconocida o inactiva: "${slug}". Tiene que estar activa en properties.json.`);
    } else {
      next.activePropertySlug = slug;
    }
  }

  if (next.autoRotateProperty === false && !next.activePropertySlug) {
    errors.push('Si apagas la rotacion automatica tienes que elegir cual propiedad va fija.');
  }

  if (errors.length) return { ok: false, errors, settings: current };
  return { ok: true, errors: [], settings: normalizeSettings(next) };
}

/**
 * El aviso de "esto es mucho, pero es tu decision". Se devuelve como texto
 * listo para pintar: la UI no tiene que saber donde esta el umbral.
 */
export function settingsWarning(settings) {
  const s = normalizeSettings(settings);
  if (s.mode !== 'campaign') return null;
  if (s.groupsPerDay <= CROWDED_GROUPS_PER_DAY) return null;
  return (
    `Vas a publicar la misma propiedad en ${s.groupsPerDay} grupos el mismo dia. ` +
    `Mas de ${CROWDED_GROUPS_PER_DAY} sube el riesgo de que un admin que este en varios de esos grupos ` +
    'vea el mismo anuncio repetido y lo marque como spam, aunque el texto y la foto cambien. ' +
    'No te lo bloqueo: es tu decision, pero tenlo presente.'
  );
}

/* ------------------------------------------------------------------ *
 * Blob
 * ------------------------------------------------------------------ */

/**
 * put() sirve detras de un CDN: sin ?t= y no-store se lee una copia vieja.
 * Mismo apano que api/_lib/wa-store.js y api/groups/plan.js.
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
    // Blob ausente es el arranque en frio normal: se usan los defaults.
    return fallback;
  }
}

/** Nunca falla: sin blob (o con blob roto) devuelve los defaults. */
export async function readSettings() {
  return normalizeSettings(await readJson(SETTINGS_KEY, null));
}

export async function writeSettings(settings) {
  const next = normalizeSettings(settings);
  await put(SETTINGS_KEY, JSON.stringify({ updatedAt: new Date().toISOString(), ...next }), PUT_OPTS);
  return next;
}

/* ------------------------------------------------------------------ *
 * Handler
 * ------------------------------------------------------------------ */

/** Vercel a veces entrega el body como string o Buffer (igual que mark.js). */
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

function payload(settings) {
  return {
    settings,
    defaults: DEFAULT_SETTINGS,
    limits: LIMITS,
    modes: MODES,
    crowdedFrom: CROWDED_GROUPS_PER_DAY,
    warning: settingsWarning(settings),
    properties: SETTINGS_PROPERTIES,
  };
}

export default async function handler(req, res) {
  // Las dos puertas de siempre: cookie del panel o Bearer de la extension.
  if (!requirePanelOrExtensionAuth(req, res)) return;

  // vercel.json le pone `public, max-age=3600` a TODO.
  res.setHeader('Cache-Control', 'no-store, private');

  try {
    if (req.method === 'GET') {
      return res.status(200).json(payload(await readSettings()));
    }

    if (req.method === 'POST') {
      const body = parseBody(req);
      if (!body) return res.status(400).json({ error: 'JSON invalido' });

      const check = validateSettings(body, await readSettings());
      if (!check.ok) {
        return res.status(400).json({ error: check.errors.join(' '), errors: check.errors });
      }
      const saved = await writeSettings(check.settings);
      return res.status(200).json({ ok: true, ...payload(saved) });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (err) {
    console.error('[groups/settings] error:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
