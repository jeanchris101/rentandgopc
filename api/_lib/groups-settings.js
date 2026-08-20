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
 * Y el filtro de idiomas (`languages`): un grupo cuyo `lang` no este encendido
 * se queda FUERA del plan, no se le publica en otro idioma. Es un control
 * DISTINTO al `content.languages` de automation/config.json, que manda sobre el
 * bot de la Pagina. Ver SETTING_LANGS mas abajo.
 *
 * El plan (./groups-plan.js) importa de aqui. La dependencia va en un solo
 * sentido a proposito: este archivo no importa nada de groups-plan.js, asi que
 * no hay ciclo de modulos que dependa del orden de evaluacion de esbuild en
 * Vercel.
 *
 * Retrocompatible: si el blob `groups/settings.json` no existe, readSettings()
 * devuelve DEFAULT_SETTINGS y todo sigue funcionando sin haber guardado nada.
 *
 * Lo que NO hace este endpoint: publicar, programar, disparar nada. Guarda
 * numeros. El unico efecto de subir groupsPerDay es que la cola te ofrezca mas
 * tarjetas; apretar Publicar sigue siendo tuyo.
 */
import { put, list } from '@vercel/blob';

import { requirePanelOrExtensionAuth } from './auth.js';
import groupsFile from '../../automation/data/group-assist-config.json' with { type: 'json' };
import propertiesFile from '../../automation/data/properties.json' with { type: 'json' };

/* ------------------------------------------------------------------ *
 * Constantes
 * ------------------------------------------------------------------ */

export const SETTINGS_KEY = 'groups/settings.json';

const PUT_OPTS = { access: 'public', addRandomSuffix: false, contentType: 'application/json' };

export const MODES = ['campaign', 'spread'];

/**
 * Los idiomas que el dueno puede encender o apagar para los GRUPOS.
 *
 * OJO, SON DOS CONTROLES DISTINTOS:
 *   - `content.languages` de automation/config.json manda sobre el bot de la
 *     PAGINA (build_queue.py: un post al dia, el idioma rota por fecha).
 *   - `languages` de aqui manda sobre la COLA DE GRUPOS: un grupo cuyo `lang`
 *     no este encendido se queda FUERA del plan. No se le publica en otro
 *     idioma — publicar en ingles en un grupo francofono es peor que no
 *     publicar.
 * Tocar uno no toca el otro, a proposito: la Pagina es publico general, los
 * grupos son 18 audiencias con idioma propio.
 */
export const SETTING_LANGS = ['es', 'en', 'fr'];

/** Como se nombran en el 400 del POST y en el motivo del plan. */
export const LANG_LABEL = Object.freeze({ es: 'espanol', en: 'ingles', fr: 'frances' });

/** Los defaults SON la configuracion valida cuando no hay blob. */
export const DEFAULT_SETTINGS = Object.freeze({
  mode: 'campaign',
  groupsPerDay: 5,
  intervalHours: 2,
  startHour: 9, // hora de Santo Domingo
  autoRotateProperty: true,
  activePropertySlug: null,
  campaignSpansDays: 1,
  // fr apagado hoy por la misma razon que en config.json: los guiones de
  // respuesta de WhatsApp solo existen en es/en y no se traen leads que no se
  // puedan atender en su idioma. Las plantillas fr siguen en post-templates.json
  // listas para el dia que se encienda.
  languages: Object.freeze(['es', 'en']),
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

/** Lista legible: ["es","en"] -> "espanol e ingles". */
export function langList(langs) {
  const names = (Array.isArray(langs) ? langs : []).map((l) => LANG_LABEL[l] || l);
  if (!names.length) return 'ninguno';
  if (names.length === 1) return names[0];
  const last = names[names.length - 1];
  // "e ingles", no "y ingles": la y delante de i- suena mal y el dueno lo lee.
  const conj = /^i/.test(last) ? ' e ' : ' y ';
  return names.slice(0, -1).join(', ') + conj + last;
}

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
 * Catalogo de idiomas (para las casillas de la UI)
 *
 * El conteo de grupos por idioma sale de group-assist-config.json, igual que en
 * plan.js. Se lee el JSON directo — no plan.js — para no crear el ciclo, y el
 * numero importa: apagar el frances no es "una casilla menos", son 4 de los 18
 * grupos fuera del plan, y el dueno tiene que verlo antes de guardar.
 * ------------------------------------------------------------------ */

const GROUP_LANGS = (Array.isArray(groupsFile?.groups) ? groupsFile.groups : [])
  .filter((g) => g && g.code && g.url)
  // Misma regla que normalizeLang() de groups-plan.js: un `lang` que no
  // reconocemos cuenta como ingles alli, asi que tiene que contar como ingles
  // aqui o el numero de la UI mentiria.
  .map((g) => {
    const l = String(g.lang || '').toLowerCase().slice(0, 2);
    return SETTING_LANGS.includes(l) ? l : 'en';
  });

export const SETTINGS_LANGUAGES = SETTING_LANGS.map((code) => ({
  code,
  label: LANG_LABEL[code],
  groupCount: GROUP_LANGS.filter((l) => l === code).length,
}));

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
 * Lo que sea -> una lista de idiomas usable. Tolerante como el resto de
 * normalizeSettings(): tira lo que no reconoce, quita duplicados y si no queda
 * nada vuelve a los defaults. Un blob con `languages: []` no puede dejar la cola
 * sin grupos en silencio; el que SI rechaza una lista vacia es el POST
 * (validateSettings), que es donde el dueno la escribio a proposito.
 */
function coerceLangs(value, fallback) {
  const raw = Array.isArray(value)
    ? value
    : typeof value === 'string'
      ? value.split(',')
      : null;
  if (!raw) return [...fallback];
  const out = [];
  for (const item of raw) {
    const lang = String(item || '').trim().toLowerCase().slice(0, 2);
    if (SETTING_LANGS.includes(lang) && !out.includes(lang)) out.push(lang);
  }
  return out.length ? out : [...fallback];
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
    languages: coerceLangs(r.languages, DEFAULT_SETTINGS.languages),
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

  // Idiomas: aqui NO se recorta en silencio. Si el dueno desmarca los tres, lo
  // que quiere no es "publicar en todos", es que no publiquemos — y eso se
  // apaga con el modo, no vaciando la lista. Se responde 400 y se explica.
  if (p.languages !== undefined) {
    const raw = Array.isArray(p.languages)
      ? p.languages
      : typeof p.languages === 'string'
        ? p.languages.split(',')
        : null;
    if (raw === null) {
      errors.push('Idiomas: manda una lista, por ejemplo ["es","en"].');
    } else {
      const seen = [];
      const unknown = [];
      const dupes = [];
      for (const item of raw) {
        const lang = String(item ?? '').trim().toLowerCase();
        if (!SETTING_LANGS.includes(lang)) {
          unknown.push(String(item ?? ''));
          continue;
        }
        if (seen.includes(lang)) dupes.push(lang);
        else seen.push(lang);
      }
      if (unknown.length) {
        errors.push(
          `Idiomas: "${unknown.join('", "')}" no es un idioma valido. ` +
            `Solo ${SETTING_LANGS.map((l) => `"${l}" (${LANG_LABEL[l]})`).join(', ')}.`
        );
      } else if (dupes.length) {
        errors.push(`Idiomas: "${dupes.join('", "')}" viene repetido. Manda cada idioma una sola vez.`);
      } else if (!seen.length) {
        errors.push(
          'Idiomas: tienes que dejar al menos uno encendido. Con los tres apagados no queda ningun ' +
            'grupo al que publicar. Si lo que quieres es parar unos dias, no publiques: no vacies la lista.'
        );
      } else {
        next.languages = seen;
      }
    }
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
  const bits = [];

  // El filtro de idiomas deja menos grupos de los que pide la campana: no es un
  // error (nadie escribio un numero fuera de rango) pero el cupo es imposible
  // desde el minuto cero y eso se dice antes, no cuando la cola sale corta.
  const reach = SETTINGS_LANGUAGES.filter((l) => s.languages.includes(l.code)).reduce(
    (n, l) => n + l.groupCount,
    0
  );
  if (s.mode === 'campaign' && reach < s.groupsPerDay) {
    bits.push(
      `Con ${langList(s.languages)} encendido${s.languages.length > 1 ? 's' : ''} solo hay ` +
        `${reach} ${reach === 1 ? 'grupo' : 'grupos'} de los ${GROUP_LANGS.length}, y pides ` +
        `${s.groupsPerDay} al dia: la campana nunca va a llegar a ${s.groupsPerDay}. ` +
        'Enciende otro idioma o baja los grupos por dia.'
    );
  }

  if (s.mode === 'campaign' && s.groupsPerDay > CROWDED_GROUPS_PER_DAY) {
    bits.push(
      `Vas a publicar la misma propiedad en ${s.groupsPerDay} grupos el mismo dia. ` +
        `Mas de ${CROWDED_GROUPS_PER_DAY} sube el riesgo de que un admin que este en varios de esos grupos ` +
        'vea el mismo anuncio repetido y lo marque como spam, aunque el texto y la foto cambien. ' +
        'No te lo bloqueo: es tu decision, pero tenlo presente.'
    );
  }

  return bits.length ? bits.join(' ') : null;
}

/* ------------------------------------------------------------------ *
 * Blob
 * ------------------------------------------------------------------ */

/**
 * put() sirve detras de un CDN: sin ?t= y no-store se lee una copia vieja.
 * Mismo apano que api/_lib/wa-store.js y api/_lib/groups-plan.js.
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
    // Las tres casillas de idioma, con cuantos grupos se lleva cada una: apagar
    // el frances son 4 grupos fuera del plan, no una casilla menos.
    languages: SETTINGS_LANGUAGES,
    totalGroups: GROUP_LANGS.length,
  };
}

export async function settings(req, res) {
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
