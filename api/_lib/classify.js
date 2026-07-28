/**
 * api/_lib/classify.js — Clasificador de mensajes entrantes de WhatsApp (Rent & Go PC).
 *
 * El sistema NUNCA envia solo. Este modulo solo dice: que quiere el lead, de que
 * propiedad habla, en que idioma, que paso del guion toca, y si el panel puede
 * ofrecer una auto-respuesta o si Jean tiene que contestar a mano.
 *
 * Regla dura del negocio: solo `availability` y `property_interest` son
 * auto-respondibles. Precio/negociacion, cliente existente, agentes, legal,
 * impuestos, ROI, financiamiento, etc. los contesta el dueno.
 *
 * -------------------------------------------------------------------------
 * Por que `import ... with { type: 'json' }` y no fs.readFileSync:
 *
 *   1. Node 24 (y 22) soportan JSON modules con import attributes de forma
 *      estable, sin flags. Este archivo ya es ESM, asi que no cuesta nada.
 *   2. En Vercel las funciones de `api/` se empaquetan con esbuild. Un import
 *      estatico de JSON queda INLINE dentro del bundle: no depende de que el
 *      file-tracer decida copiar `automation/data/*.json` al lado del archivo
 *      compilado. Con `fs.readFileSync(new URL('../../automation/data/x.json',
 *      import.meta.url))` la ruta se resuelve contra la UBICACION DEL BUNDLE,
 *      que no es la del fuente: es exactamente el caso donde revienta en
 *      produccion y funciona en local.
 *   3. Si un JSON no existe o esta corrupto, el import falla en BUILD y no en
 *      la primera llamada del webhook.
 *   4. Cero I/O en cold start.
 *
 *   Unico requisito: `automation/data/*.json` debe seguir versionado en el repo
 *   y fuera de .vercelignore (hoy lo esta).
 * -------------------------------------------------------------------------
 *
 * Exporta: classify(input), renderStep(playbook, stepId, lang, property),
 *          detectFromRef(ref), y utilidades (normalize, listIntents...).
 * Sin dependencias externas.
 */

import intentsFile from '../../automation/data/intents.json' with { type: 'json' };
import playbooksFile from '../../automation/data/playbooks.json' with { type: 'json' };
import propertiesFile from '../../automation/data/properties.json' with { type: 'json' };

/* ------------------------------------------------------------------ *
 * Constantes
 * ------------------------------------------------------------------ */

/** RG-<CODIGO>-<LETRA DE ORIGEN><SUFIJO>. Ej: RG-PB202-F5L6C */
export const REF_RE = /\bRG-([A-Z0-9]{2,6})-([FGPWID])([A-Z0-9]{1,5})\b/i;

/** Letra de origen del ref -> canal. F es el unico que build_queue.py emite hoy. */
const SOURCE_BY_LETTER = {
  F: 'facebook_page',
  G: 'facebook_group',
  P: 'paid_ad',
  W: 'website',
  I: 'instagram',
  D: 'direct',
};

/** Solo se puede auto-responder al principio del embudo. */
const AUTO_REPLY_STEPS = new Set(['step1_immediate', 'step2_qualify']);

const LANGS = ['es', 'en'];

/** Mensaje completo == opt-out. Palabras sueltas que fuera de contexto no lo son. */
const OPT_OUT_EXACT = new Set([
  'stop', 'stop stop', 'baja', 'dar de baja', 'darme de baja', 'de baja',
  'unsubscribe', 'desuscribir', 'desuscribirme', 'cancelar suscripcion',
  'no me escriban', 'no me escriba', 'no me escribas', 'no me escriban mas',
  'no me escribas mas', 'no escriban mas', 'no me contacten', 'no me contacte',
  'borrame', 'borrame de la lista', 'quitame', 'quitame de la lista',
  'sacame', 'sacame de la lista', 'no insista', 'no insistan',
  'remove', 'remove me', 'opt out', 'stop messages', 'leave me alone',
  'no molestar', 'dejame en paz',
]);

/** Marcadores funcionales para el conteo de idioma (nada ambiguo es/en). */
const ES_MARKERS = new Set([
  'que', 'para', 'como', 'esta', 'estan', 'tiene', 'tienen', 'quiero', 'quisiera',
  'el', 'la', 'los', 'las', 'del', 'por', 'con', 'pero', 'esto', 'eso', 'ese',
  'donde', 'cuanto', 'cuanta', 'cuando', 'cual', 'cuales', 'porque', 'sigue',
  'todavia', 'aun', 'disponible', 'precio', 'gracias', 'hola', 'buenas', 'mas',
  'muy', 'soy', 'estoy', 'usted', 'ustedes', 'tambien', 'si', 'interesa',
  'apartamento', 'terreno', 'habitaciones', 'ustedes', 'seria', 'hay',
]);

const EN_MARKERS = new Set([
  'the', 'is', 'are', 'was', 'want', 'how', 'still', 'you', 'your', 'yours',
  'do', 'does', 'did', 'can', 'could', 'would', 'what', 'where', 'when', 'why',
  'have', 'has', 'this', 'that', 'with', 'and', 'my', 'im', 'its', 'available',
  'price', 'thanks', 'hi', 'hello', 'please', 'send', 'about', 'there', 'been',
  'looking', 'apartment', 'land', 'bedroom', 'i', 'we', 'they', 'of', 'from',
]);

/** Palabras que empujan una respuesta de calificacion hacia la rama 3a o 3b. */
const BRANCH_A_MARKERS = [
  'inversion', 'invertir', 'airbnb', 'rentar', 'rentarlo', 'alquilar', 'alquilarlo',
  'renta', 'rentabilidad', 'roi', 'negocio', 'investment', 'invest', 'rental',
  'rent it out', 'income', 'cash flow', 'proyecto', 'desarrollar', 'desarrollo',
  'construir', 'residencial', 'uso mixto', 'comercial', 'project', 'develop',
  'build', 'mixed use',
];

const BRANCH_B_MARKERS = [
  'uso personal', 'personal', 'para mi', 'para mi familia', 'familia', 'vivir',
  'vivirlo', 'vacacionar', 'vacaciones', 'retiro', 'retirarme', 'myself',
  'my own use', 'my family', 'vacation', 'retire', 'second home', 'live there',
  'plusvalia', 'largo plazo', 'reserva de valor', 'guardar', 'appreciation',
  'hold it', 'long term', 'land bank',
];

/* ------------------------------------------------------------------ *
 * Normalizacion
 * ------------------------------------------------------------------ */

/**
 * minusculas + sin acentos (NFD y strip de diacriticos) + sin apostrofes
 * (i'm -> im) + m² -> m2 + espacios colapsados.
 */
// Rangos construidos con fromCharCode a proposito: el fuente queda 100% ASCII y
// ningun editor/bundler puede mezclar un diacritico combinante con el corchete.
const RE_APOSTROPHE = new RegExp(
  `[${String.fromCharCode(0x27, 0x60, 0xb4, 0x2018, 0x2019, 0x02bc)}]`, 'g',
);
const RE_SUPER_TWO = new RegExp(String.fromCharCode(0xb2), 'g');
const RE_DIACRITIC = new RegExp(
  `[${String.fromCharCode(0x300)}-${String.fromCharCode(0x36f)}]`, 'g',
);

export function normalize(input) {
  if (input === null || input === undefined) return '';
  return String(input)
    .replace(RE_APOSTROPHE, '')   // i'm -> im, don't -> dont
    .replace(RE_SUPER_TWO, '2')   // m<superindice 2> -> m2
    .normalize('NFD')
    .replace(RE_DIACRITIC, '')    // quita acentos: bavaro == bavaro
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

/** Solo alfanumericos y espacios, para comparaciones de "mensaje completo". */
function bareWords(text) {
  return text.replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
}

const RE_ESCAPE = /[.*+?^${}()|[\]\\]/g;
const SEP = '[^a-z0-9]+';

/**
 * Frase -> regex tolerante: la puntuacion entre palabras es flexible
 * ("hola, buenas" matchea "hola buenas") y los bordes son alfanumericos
 * ("quiero alquilar" NO matchea dentro de "quiero alquilarlo").
 */
function phraseRegex(phrase, flags = '') {
  const chunks = normalize(phrase).split(/[^a-z0-9]+/).filter(Boolean);
  if (!chunks.length) return null;
  const body = chunks.map((c) => c.replace(RE_ESCAPE, '\\$&')).join(SEP);
  return new RegExp(`(?<![a-z0-9])${body}(?![a-z0-9])`, flags);
}

/* ------------------------------------------------------------------ *
 * Indices (se construyen una vez por proceso)
 * ------------------------------------------------------------------ */

const PLAYBOOKS = Array.isArray(playbooksFile?.playbooks) ? playbooksFile.playbooks : [];
const PROPERTIES = Array.isArray(propertiesFile?.properties) ? propertiesFile.properties : [];
const RAW_INTENTS = Array.isArray(intentsFile)
  ? intentsFile
  : Array.isArray(intentsFile?.intents)
    ? intentsFile.intents
    : [];

const PLAYBOOK_BY_SLUG = new Map(PLAYBOOKS.filter((p) => p?.slug).map((p) => [p.slug, p]));
const PROPERTY_BY_SLUG = new Map(PROPERTIES.filter((p) => p?.slug).map((p) => [p.slug, p]));

const SLUG_BY_REF_CODE = new Map(
  PLAYBOOKS.filter((p) => p?.ref_code && p?.slug).map((p) => [String(p.ref_code).toUpperCase(), p.slug]),
);

/** Intenciones ordenadas por prioridad ascendente (menor gana) y precompiladas. */
const INTENTS = RAW_INTENTS
  .filter((i) => i && i.id)
  .slice()
  .sort((a, b) => (a.priority ?? 9999) - (b.priority ?? 9999))
  .map((intent) => {
    const matchers = [];
    for (const lang of LANGS) {
      for (const pattern of intent[`patterns_${lang}`] || []) {
        const re = phraseRegex(pattern);
        if (!re) continue;
        matchers.push({ pattern: normalize(pattern), lang, re, reAll: phraseRegex(pattern, 'g') });
      }
    }
    // Para match_whole_message hay que consumir las frases largas antes que las
    // cortas ("buenas tardes" antes que "buenas") o queda residuo fantasma.
    matchers.sort((a, b) => b.pattern.length - a.pattern.length);
    return { intent, matchers };
  });

const INTENT_BY_ID = new Map(INTENTS.map((e) => [e.intent.id, e.intent]));

const UNKNOWN_INTENT = INTENT_BY_ID.get('unknown') || {
  id: 'unknown', priority: 9999, auto_reply_ok: false, routes_to: 'GEN:ask_clarify',
};

/**
 * Indice de keywords de playbooks.json.
 * Una keyword normalizada compartida por 2+ propiedades es GENERICA y no decide
 * ("Cocotal", "Bavaro", "US$45 / m2"...). Solo las unicas resuelven.
 */
const KEYWORDS = (() => {
  const bySlug = new Map();
  for (const pb of PLAYBOOKS) {
    for (const kw of pb?.keywords || []) {
      const key = normalize(kw);
      if (key.replace(/[^a-z0-9]/g, '').length < 3) continue;
      if (!bySlug.has(key)) bySlug.set(key, new Set());
      bySlug.get(key).add(pb.slug);
    }
  }
  const out = [];
  for (const [key, slugs] of bySlug) {
    const re = phraseRegex(key);
    if (!re) continue;
    out.push({ key, re, slugs: [...slugs], unique: slugs.size === 1 });
  }
  // Primero las mas largas: la razon que se le muestra al dueno cita la mejor.
  out.sort((a, b) => b.key.length - a.key.length);
  return out;
})();

function compileMarkers(list) {
  return list.map((marker) => ({ marker, re: phraseRegex(marker) })).filter((m) => m.re);
}

const BRANCH_A = compileMarkers(BRANCH_A_MARKERS);
const BRANCH_B = compileMarkers(BRANCH_B_MARKERS);

/* ------------------------------------------------------------------ *
 * API publica auxiliar
 * ------------------------------------------------------------------ */

export function listIntents() {
  return INTENTS.map((e) => e.intent);
}

export function getProperty(slugOrObject) {
  if (!slugOrObject) return null;
  if (typeof slugOrObject === 'object') {
    return slugOrObject.slug ? PROPERTY_BY_SLUG.get(slugOrObject.slug) || slugOrObject : slugOrObject;
  }
  return PROPERTY_BY_SLUG.get(String(slugOrObject)) || null;
}

export function findPlaybook(slugOrObject) {
  if (!slugOrObject) return null;
  if (typeof slugOrObject === 'object') {
    if (Array.isArray(slugOrObject.steps)) return slugOrObject;
    return slugOrObject.slug ? PLAYBOOK_BY_SLUG.get(slugOrObject.slug) || null : null;
  }
  return PLAYBOOK_BY_SLUG.get(String(slugOrObject)) || null;
}

/**
 * detectFromRef('RG-A301-F5L6C') -> { propertySlug: 'cocotal-2bdr', source: 'facebook_page' }
 * Acepta el ref suelto o cualquier texto que lo contenga. Sin match -> nulls.
 */
export function detectFromRef(ref) {
  const m = REF_RE.exec(String(ref ?? '').toUpperCase());
  if (!m) return { propertySlug: null, source: null };
  return {
    propertySlug: SLUG_BY_REF_CODE.get(m[1].toUpperCase()) ?? null,
    source: SOURCE_BY_LETTER[m[2].toUpperCase()] ?? null,
  };
}

/**
 * renderStep(playbook, stepId, lang, property) -> texto listo para enviar.
 * `playbook` puede ser el objeto del playbook o el slug. `property` puede ser el
 * objeto de properties.json o el slug (si falta se resuelve por el slug del
 * playbook). Si el paso o el idioma no existen cae a es, y devuelve '' si no hay
 * nada que enviar (el panel debe tratar '' como "no hay guion para esto").
 */
export function renderStep(playbook, stepId, lang = 'es', property = null) {
  const pb = findPlaybook(playbook);
  if (!pb || !Array.isArray(pb.steps)) return '';

  const step = pb.steps.find((s) => s && s.id === stepId);
  if (!step) return '';

  const language = LANGS.includes(lang) ? lang : 'es';
  const text = step[language] || step.es || step.en || '';
  if (!text) return '';

  const prop = getProperty(property) || getProperty(pb.slug);
  const tokens = {
    name: prop?.name ?? '',
    short_name: prop?.short_name ?? '',
    price: prop?.price_display ?? '',
    price_display: prop?.price_display ?? '',
    neighborhood: (language === 'es' ? prop?.neighborhood_es : null) ?? prop?.neighborhood ?? '',
    bedrooms: prop?.bedrooms ?? '',
    size_m2: prop?.size_m2 ?? prop?.area_m2 ?? '',
    ref_code: pb.ref_code ?? '',
    slug: pb.slug ?? '',
    site: propertiesFile?.site_base_url ?? '',
    whatsapp: propertiesFile?.whatsapp_number ?? '',
  };

  // Solo se sustituyen tokens conocidos; cualquier otra llave queda intacta.
  return String(text)
    .replace(/\{\{?\s*([a-z0-9_]+)\s*\}?\}/gi, (match, key) => {
      const k = String(key).toLowerCase();
      return Object.prototype.hasOwnProperty.call(tokens, k) ? String(tokens[k]) : match;
    })
    .trim();
}

/* ------------------------------------------------------------------ *
 * Pipeline interno
 * ------------------------------------------------------------------ */

function readLead(thread) {
  const l = (thread && (thread.lead || thread.contact)) || {};
  const rawLang = normalize(l.language ?? l.lang ?? '');
  return {
    language: LANGS.includes(rawLang.slice(0, 2)) ? rawLang.slice(0, 2) : null,
    lastStepSent: l.lastStepSent ?? l.last_step_sent ?? l.lastStep ?? null,
    propertySlug: l.propertySlug ?? l.property_slug ?? l.slug ?? null,
    source: l.source ?? null,
  };
}

function isOutbound(m) {
  if (!m || typeof m !== 'object') return false;
  if (m.fromMe === true || m.from_me === true || m.outbound === true) return true;
  const d = normalize(m.direction ?? m.dir ?? '');
  return d === 'out' || d === 'outbound' || d === 'sent';
}

function countOutbound(thread) {
  if (!thread) return 0;
  if (Number.isFinite(thread.outboundCount)) return thread.outboundCount;
  if (Number.isFinite(thread.outbound_count)) return thread.outbound_count;
  const msgs = thread.messages ?? thread.msgs ?? [];
  return Array.isArray(msgs) ? msgs.filter(isOutbound).length : 0;
}

/** Paso 4: propiedad por keywords, con la regla de desempate obligatoria. */
function detectPropertyByKeywords(text) {
  const uniqueBySlug = new Map();   // slug -> keyword que lo decide
  const genericHits = [];           // { key, slugs }

  for (const kw of KEYWORDS) {
    if (!kw.re.test(text)) continue;
    if (kw.unique) {
      if (!uniqueBySlug.has(kw.slugs[0])) uniqueBySlug.set(kw.slugs[0], kw.key);
    } else {
      genericHits.push(kw);
    }
  }

  const winners = [...uniqueBySlug.keys()];
  if (winners.length === 1) {
    return { slug: winners[0], keyword: uniqueBySlug.get(winners[0]), status: 'unique', genericHits };
  }
  if (winners.length > 1) {
    return {
      slug: null,
      status: 'tie',
      genericHits,
      tied: winners.map((s) => ({ slug: s, keyword: uniqueBySlug.get(s) })),
    };
  }
  if (genericHits.length) return { slug: null, status: 'generic_only', genericHits };
  return { slug: null, status: 'none', genericHits: [] };
}

/** Paso 5: idioma por marcadores funcionales. */
function detectLanguage(text) {
  let es = 0;
  let en = 0;
  for (const tok of text.split(/[^a-z0-9]+/)) {
    if (!tok) continue;
    if (ES_MARKERS.has(tok)) es += 1;
    if (EN_MARKERS.has(tok)) en += 1;
  }
  const detected = en > es ? 'en' : es > en ? 'es' : null;
  return { detected, es, en };
}

/** Paso 6: intencion. Gana la de menor priority. */
function detectIntent(text) {
  for (const entry of INTENTS) {
    if (!entry.matchers.length) continue;

    if (entry.intent.match_whole_message) {
      let residue = ` ${text} `;
      let hit = null;
      for (const m of entry.matchers) {
        const before = residue;
        residue = residue.replace(m.reAll, ' ');
        if (residue !== before && !hit) hit = m;
      }
      if (hit && residue.replace(/[^a-z0-9]/g, '') === '') {
        return { intent: entry.intent, matcher: hit, whole: true };
      }
      continue;
    }

    for (const m of entry.matchers) {
      if (m.re.test(text)) return { intent: entry.intent, matcher: m, whole: false };
    }
  }
  return null;
}

function hasAny(text, compiled) {
  for (const m of compiled) {
    if (m.re.test(text)) return m.marker;
  }
  return null;
}

/** Rama 3a/3b segun el audience de la propiedad y lo que dijo el lead. */
function qualifyBranch(text, slug) {
  const property = getProperty(slug);
  const audience = property?.audience === 'developer' ? 'developer' : 'buyer';
  const a = hasAny(text, BRANCH_A);
  const b = hasAny(text, BRANCH_B);

  let branch;
  if (a && !b) branch = 'a';
  else if (b && !a) branch = 'b';
  else branch = 'a'; // ambiguo o mixto: 3a es la rama por defecto del guion

  const stepId = audience === 'developer'
    ? (branch === 'a' ? 'step3a_developer' : 'step3b_investor')
    : (branch === 'a' ? 'step3a_investment' : 'step3b_personal');

  return { stepId, audience, marker: branch === 'a' ? a : b, ambiguous: !a && !b };
}

/** Paso 7: etapa sugerida. Las reglas por intencion pisan a las de secuencia. */
function decideStep({ intentId, thread, lead, slug, text, reasons }) {
  const outbound = countOutbound(thread);
  const last = lead.lastStepSent ? String(lead.lastStepSent) : null;

  let step;
  if (!thread || outbound === 0) {
    step = 'step1_immediate';
    reasons.push(`Etapa step1_immediate: primer contacto (${thread ? '0 mensajes salientes en el hilo' : 'sin hilo previo'}).`);
  } else if (last === 'step1_immediate') {
    step = 'step2_qualify';
    reasons.push('Etapa step2_qualify: el ultimo paso enviado fue step1_immediate.');
  } else if (last && last.startsWith('step3')) {
    step = 'step4_close';
    reasons.push(`Etapa step4_close: el hilo ya iba por ${last}.`);
  } else if (last && last.startsWith('followup')) {
    step = 'step2_qualify';
    reasons.push(`Etapa step2_qualify: reactivacion despues de ${last}.`);
  } else {
    step = 'step2_qualify';
    reasons.push(`Etapa step2_qualify: hilo en curso (${outbound} mensajes salientes${last ? `, ultimo paso ${last}` : ', sin paso registrado'}).`);
  }

  if (intentId === 'qualify_answer') {
    if (slug) {
      const { stepId, audience, marker, ambiguous } = qualifyBranch(text, slug);
      step = stepId;
      reasons.push(
        `Etapa ${stepId}: respuesta de calificacion sobre una propiedad de audiencia "${audience}"` +
        (ambiguous ? ' (rama por defecto: no dijo claramente inversion ni uso personal).' : ` (senal: "${marker}").`),
      );
    } else {
      reasons.push('Respuesta de calificacion pero sin propiedad identificada: no se puede elegir rama 3a/3b, se deja la etapa de secuencia.');
    }
  } else if (intentId === 'visit_or_call' || intentId === 'purchase_intent') {
    step = 'step4_close';
    reasons.push(`Etapa step4_close: la intencion "${intentId}" pide cerrar a llamada o visita.`);
  }

  // Si el playbook de esa propiedad no tiene ese paso, se avisa (no se inventa).
  const pb = findPlaybook(slug);
  if (pb && Array.isArray(pb.steps) && !pb.steps.some((s) => s.id === step)) {
    reasons.push(`Ojo: el playbook de ${slug} no tiene el paso ${step}; hay que elegirlo a mano.`);
  }

  return step;
}

/* ------------------------------------------------------------------ *
 * classify()
 * ------------------------------------------------------------------ */

/**
 * @param {{ body?: string, hasMedia?: boolean, mediaType?: string|null, thread?: object|null }} input
 * @returns {{ intent: string, language: 'es'|'en', ref: string|null, propertySlug: string|null,
 *             source: string|null, confidence: 'high'|'medium'|'low', autoReplyAllowed: boolean,
 *             suggestedStep: string|null, reasons: string[] }}
 */
export function classify(input = {}) {
  const {
    body = '',
    hasMedia = false,
    mediaType = null,
    thread = null,
  } = input || {};

  const raw = typeof body === 'string' ? body : String(body ?? '');
  const text = normalize(raw);
  const reasons = [];
  const lead = readLead(thread);
  const media = Boolean(hasMedia);

  const base = {
    intent: 'unknown',
    language: lead.language || 'es',
    ref: null,
    propertySlug: lead.propertySlug && PROPERTY_BY_SLUG.has(lead.propertySlug) ? lead.propertySlug : null,
    source: lead.source || null,
    confidence: 'low',
    autoReplyAllowed: false,
    suggestedStep: null,
    reasons,
  };

  /* --- 1. opt-out (mensaje completo) -------------------------------- */
  if (OPT_OUT_EXACT.has(bareWords(text))) {
    reasons.push(`El mensaje completo es una baja ("${bareWords(text)}").`);
    reasons.push('Auto-respuesta BLOQUEADA: opt-out. No se le vuelve a escribir; marcar el lead como baja.');
    return { ...base, intent: 'opt_out', suggestedStep: null, autoReplyAllowed: false, confidence: 'high' };
  }

  /* --- 2. media sin texto ------------------------------------------- */
  if (media && !text) {
    reasons.push(`Llego ${mediaType ? `un adjunto de tipo "${mediaType}"` : 'un adjunto'} sin texto: no se clasifica el contenido.`);
    reasons.push('Auto-respuesta BLOQUEADA: audio/imagen sin texto lo revisa Jean.');
    return { ...base, intent: 'voice_or_media_only', suggestedStep: null, autoReplyAllowed: false, confidence: 'high' };
  }

  /* --- 3. ref RG-XXXX-Y --------------------------------------------- */
  const refMatch = REF_RE.exec(raw.toUpperCase());
  let propertySlug = null;
  let source = lead.source || null;
  let confidence = 'low';
  let ambiguousProperty = false;

  if (refMatch) {
    base.ref = refMatch[0].toUpperCase();
    const fromRef = detectFromRef(refMatch[0]);
    source = fromRef.source || source;
    if (fromRef.propertySlug) {
      propertySlug = fromRef.propertySlug;
      confidence = 'high';
      reasons.push(`Ref ${base.ref} detectada: propiedad ${propertySlug}, origen ${source || 'desconocido'}.`);
    } else {
      reasons.push(`Ref ${base.ref} detectada pero el codigo "${refMatch[1].toUpperCase()}" no esta en playbooks.json: se sigue por keywords.`);
    }
  }

  /* --- 4. propiedad por keywords ------------------------------------ */
  if (!propertySlug) {
    const kw = detectPropertyByKeywords(text);
    if (kw.status === 'unique') {
      propertySlug = kw.slug;
      confidence = 'high';
      reasons.push(`Propiedad ${propertySlug} por keyword unico "${kw.keyword}".`);
    } else if (kw.status === 'tie') {
      ambiguousProperty = true;
      confidence = 'low';
      reasons.push(
        'Empate de keywords: ' +
        kw.tied.map((t) => `"${t.keyword}" apunta a ${t.slug}`).join(' y ') +
        '. No se decide propiedad.',
      );
    } else if (kw.status === 'generic_only') {
      ambiguousProperty = true;
      confidence = 'low';
      const g = kw.genericHits[0];
      reasons.push(
        `Solo keywords genericos ("${g.key}" lo comparten ${g.slugs.length} propiedades: ${g.slugs.join(', ')}). ` +
        'Hace falta algo unico (A301, B202, Arboleda, Paseo, el precio o los m2) para decidir.',
      );
    } else {
      reasons.push('El mensaje no menciona ninguna propiedad del catalogo.');
    }

    // Fallback: la propiedad que ya venia del hilo (el lead ya preguntaba por ella).
    if (!propertySlug && base.propertySlug) {
      propertySlug = base.propertySlug;
      source = source || lead.source || null;
      confidence = ambiguousProperty ? 'low' : 'high';
      reasons.push(
        `Propiedad ${propertySlug} tomada del hilo (lead.propertySlug)` +
        (ambiguousProperty ? ', pero el mensaje es ambiguo: confianza baja.' : '.'),
      );
    }
  }

  /* --- 5. idioma ---------------------------------------------------- */
  const langCount = detectLanguage(text);
  let language = langCount.detected || lead.language || 'es';

  if (lead.language && lead.language !== language) {
    const detectedScore = language === 'en' ? langCount.en : langCount.es;
    const leadScore = lead.language === 'en' ? langCount.en : langCount.es;
    const strong = detectedScore >= 2 && detectedScore - leadScore >= 2;
    if (strong) {
      reasons.push(`Idioma ${language}: el hilo estaba en ${lead.language} pero hay evidencia fuerte (es=${langCount.es}, en=${langCount.en}).`);
    } else {
      language = lead.language;
      reasons.push(`Idioma ${language}: manda el idioma del hilo (marcadores del mensaje: es=${langCount.es}, en=${langCount.en}).`);
    }
  } else if (langCount.detected) {
    reasons.push(`Idioma ${language} por marcadores (es=${langCount.es}, en=${langCount.en}).`);
  } else {
    reasons.push(`Idioma ${language} por defecto (sin marcadores claros: es=${langCount.es}, en=${langCount.en}).`);
  }

  /* --- 6. intencion -------------------------------------------------- */
  const hit = detectIntent(text);
  const intent = hit ? hit.intent : UNKNOWN_INTENT;

  if (hit) {
    reasons.push(
      `Intencion ${intent.id} (prioridad ${intent.priority}) por el patron ${hit.matcher.lang} "${hit.matcher.pattern}"` +
      (hit.whole ? ' que agota el mensaje completo.' : '.'),
    );
  } else {
    reasons.push('Ningun patron de intents.json matcheo: intencion unknown.');
  }
  if (intent.routes_to) reasons.push(`Ruta sugerida: ${intent.routes_to}.`);

  if (confidence === 'high' && intent.id === 'unknown') confidence = 'medium';

  /* --- 7. etapa ------------------------------------------------------ */
  const suggestedStep = decideStep({ intentId: intent.id, thread, lead, slug: propertySlug, text, reasons });

  /* --- 8. veredicto de auto-respuesta -------------------------------- */
  const blockers = [];
  if (!intent.auto_reply_ok) blockers.push(`la intencion "${intent.id}" la contesta el dueno a mano`);
  if (confidence !== 'high') blockers.push(`la confianza es "${confidence}"`);
  if (!propertySlug) blockers.push('no se identifico la propiedad');
  if (intent.id === 'opt_out') blockers.push('es un opt-out');
  if (media) blockers.push(`el mensaje trae adjunto${mediaType ? ` (${mediaType})` : ''}`);
  if (!AUTO_REPLY_STEPS.has(suggestedStep)) blockers.push(`la etapa sugerida (${suggestedStep}) no es de apertura`);

  const autoReplyAllowed = blockers.length === 0;

  if (autoReplyAllowed) {
    reasons.push(
      `Auto-respuesta PERMITIDA: intencion "${intent.id}" es auto-respondible, propiedad ${propertySlug} con confianza alta, ` +
      `sin adjuntos, y toca ${suggestedStep} en ${language}.`,
    );
  } else {
    reasons.push(`Auto-respuesta BLOQUEADA: ${blockers.join('; ')}.`);
  }

  return {
    intent: intent.id,
    language,
    ref: base.ref,
    propertySlug,
    source: source || null,
    confidence,
    autoReplyAllowed,
    suggestedStep,
    reasons,
  };
}

export default classify;
