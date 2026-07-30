/**
 * POST /api/groups/mark — registra que un grupo ya recibio su post (o que el
 * dueno lo salto). Body: { groupCode, propertySlug, ref, skipped? }
 *
 * Esto es lo que hace que el sistema sirva: el historial es la unica fuente del
 * cooldown de 7 dias por grupo y, con el ref RG-<PROP>-G<NN>, lo que a los 30
 * dias dice que grupos dan compradores de verdad y cuales no.
 *
 *   skipped !== true  -> post publicado. Arranca el cooldown semanal del grupo y
 *                        gasta los 30 dias de descanso de la foto.
 *   skipped === true  -> lo salto. Se guarda para no volver a ofrecerle hoy el
 *                        mismo grupo, pero NO gasta el cooldown ni la foto: no
 *                        publico nada.
 *
 * Idempotente por (grupo, propiedad, dia): marcar dos veces no duplica. La
 * segunda marca actualiza la entrada, asi que "lo salte" -> "no, si lo publique"
 * funciona sin dejar dos filas contradictorias en el historial.
 *
 * El store (blob, normalizacion, seleccion de imagen) vive en ./plan.js, mismo
 * patron que api/lead/list.js importando de api/lead/capture.js.
 */
import { requirePanelOrExtensionAuth } from '../_lib/auth.js';
import {
  GROUPS,
  GROUP_COOLDOWN_DAYS,
  PROPERTIES,
  addDays,
  buildRef,
  entryId,
  imageLastUsedFrom,
  readHistory,
  selectImage,
  todayInTz,
  writeHistory,
} from './plan.js';

/** El historial es la memoria del negocio: se poda alto y por los mas viejos. */
const MAX_ENTRIES = 4000;

const GROUP_BY_CODE = new Map(GROUPS.map((g) => [g.code, g]));
const PROP_BY_SLUG = new Map(PROPERTIES.map((p) => [p.slug, p]));

/** Vercel a veces entrega el body como string o Buffer. */
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

export default async function handler(req, res) {
  // Igual que plan.js: cookie del panel o Bearer de la extension de Chrome.
  if (!requirePanelOrExtensionAuth(req, res)) return;

  // vercel.json le pone `public, max-age=3600` a todo.
  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const body = parseBody(req);
  if (!body) return res.status(400).json({ error: 'JSON invalido' });

  const groupCode = String(body.groupCode || '').trim().toUpperCase();
  const propertySlug = String(body.propertySlug || '').trim();
  const skipped = body.skipped === true || body.skipped === 'true';

  const group = GROUP_BY_CODE.get(groupCode);
  if (!group) {
    return res.status(400).json({
      error: `Grupo desconocido: ${groupCode || '(vacio)'}. Tiene que estar en group-assist-config.json.`,
    });
  }

  const prop = PROP_BY_SLUG.get(propertySlug);
  if (!prop) {
    return res.status(400).json({
      error: `Propiedad desconocida o inactiva: ${propertySlug || '(vacia)'}.`,
    });
  }

  // El ref se deriva de (propiedad, grupo), asi que se puede recalcular. Si el
  // cliente manda uno que no cuadra NO lo corregimos en silencio: un ref torcido
  // en el historial es atribucion perdida, y perdida sin que nadie lo note.
  const expectedRef = buildRef(propertySlug, groupCode);
  const givenRef = body.ref === undefined || body.ref === null ? '' : String(body.ref).trim().toUpperCase();
  if (givenRef && givenRef !== expectedRef) {
    return res.status(400).json({
      error: `El ref no cuadra con (${groupCode}, ${propertySlug}): llego ${givenRef}, tocaba ${expectedRef}.`,
    });
  }
  const ref = expectedRef;

  try {
    const date = todayInTz();
    const entries = await readHistory();
    const id = entryId(date, groupCode, propertySlug);
    const now = new Date().toISOString();

    // La foto que REALMENTE salio.
    //
    // Recalcularla aca solo acierta en el primer slot del dia: en modo campana
    // los 5 slots comparten propiedad y cada uno lleva una foto distinta, pero
    // la recalculada siempre es la cabeza del LRU. Guardar la equivocada hace
    // que la campana de manana crea que esa foto ya descanso y repita otra
    // antes de tiempo — y la variedad de fotos es justo lo que evita que 5
    // posts de la misma propiedad se lean como contenido duplicado.
    //
    // Por eso el cliente manda `image` (el plan se lo dio) y se acepta solo si
    // es una de las post_images de esa propiedad. Si no viene, se recalcula
    // como antes: el panel viejo sigue funcionando.
    const existing = entries.find((e) => e.id === id) || null;
    const claimed =
      typeof body.image === 'string' && body.image.trim() ? body.image.trim() : null;
    const allowed = Array.isArray(prop.post_images) ? prop.post_images : [];
    const claimedOk = claimed
      ? allowed.find((c) => c === claimed || claimed.endsWith(c)) || null
      : null;
    if (claimed && !claimedOk) {
      console.warn('[groups/mark] image "%s" no pertenece a %s; la recalculo', claimed, propertySlug);
    }
    const image =
      claimedOk ||
      existing?.image ||
      selectImage(prop, imageLastUsedFrom(entries.filter((e) => e.id !== id)), date) ||
      null;

    const entry = {
      id,
      date,
      groupCode,
      groupName: group.name,
      propertySlug,
      propertyName: prop.short_name || prop.name,
      lang: group.lang,
      ref,
      image,
      skipped,
      markedAt: now,
      firstMarkedAt: existing?.firstMarkedAt || existing?.markedAt || now,
    };

    const next = entries.filter((e) => e.id !== id);
    next.push(entry);
    next.sort((a, b) => a.date.localeCompare(b.date) || String(a.markedAt).localeCompare(String(b.markedAt)));

    const trimmed = next.length > MAX_ENTRIES ? next.slice(next.length - MAX_ENTRIES) : next;
    await writeHistory(trimmed);

    return res.status(200).json({
      ok: true,
      duplicate: Boolean(existing),
      entry,
      // Cuando se libera el grupo. Si lo salto, sigue libre hoy mismo.
      cooldownUntil: skipped ? null : addDays(date, GROUP_COOLDOWN_DAYS),
      total: trimmed.length,
    });
  } catch (err) {
    console.error('[groups/mark] error:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
