/**
 * GET /api/wa/threads — bandeja del panel.
 *
 * Devuelve el resumen de cada hilo, los numeros de arriba, la config actual y el
 * estado de la sesion de WhatsApp.
 *
 * OJO: wa-store.listThreads() no devuelve hilos completos, devuelve las entradas
 * del indice (wa/index.json), que traen los campos del lead aplanados y solo el
 * ultimo mensaje. Aqui los volvemos a armar con la forma que espera el panel.
 */
import { requireAuth } from './auth.js';
import {
  listThreads,
  getConfig,
  countAutoRepliesToday,
  DEFAULT_CONFIG,
} from './wa-store.js';
import { sessionStatus } from './waha.js';

const DAY_MS = 24 * 60 * 60 * 1000;

function toMs(value) {
  if (value == null) return 0;
  const n = Number(value);
  if (Number.isFinite(n) && n > 0) return n < 1e12 ? Math.round(n * 1000) : Math.round(n);
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Fecha YYYY-MM-DD en hora dominicana, no en UTC ni en la del servidor. */
function dayInTz(ms, timeZone) {
  if (!ms) return null;
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date(ms));
  } catch {
    return null;
  }
}

function summarize(entry) {
  const last = entry.lastMessage || null;
  const lastTs = toMs(last && last.ts) || toMs(entry.updatedAt);

  // El indice no guarda la lista de mensajes, asi que no hay un conteo exacto de
  // no leidos: lo que importa para la bandeja es si el ultimo mensaje es del
  // cliente (hilo pendiente) o nuestro (al dia).
  const unread = last && !last.fromMe ? 1 : 0;

  return {
    chatId: entry.chatId,
    name: entry.name || '',
    phone: entry.phone || String(entry.chatId || '').split('@')[0],
    lastMessage: last ? String(last.body || '') || (last.type !== 'chat' ? '[adjunto]' : '') : '',
    lastTs,
    lastFromMe: !!(last && last.fromMe),
    unread,
    createdAt: entry.createdAt || null,
    updatedAt: entry.updatedAt || null,
    messageCount: entry.messageCount || 0,
    lead: {
      ref: entry.ref ?? null,
      propertySlug: entry.propertySlug ?? null,
      source: entry.source ?? null,
      language: entry.language ?? null,
      stage: entry.stage ?? 'new',
      autoRepliedAt: entry.autoRepliedAt ?? null,
      autoReplyCount: entry.autoReplyCount ?? 0,
      confidence: entry.confidence ?? 'low',
      manualOverride: entry.manualOverride === true,
    },
  };
}

export async function threads(req, res) {
  if (!requireAuth(req, res)) return;

  // vercel.json pone `public, max-age=3600` a TODO. Sin esto la bandeja se
  // quedaria cacheada (y potencialmente compartida) una hora.
  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const [rawEntries, config] = await Promise.all([listThreads(), getConfig()]);
    const tz = config.timezone || DEFAULT_CONFIG.timezone;

    const threads = (Array.isArray(rawEntries) ? rawEntries : [])
      .filter((e) => e && e.chatId)
      .map(summarize)
      .sort((a, b) => b.lastTs - a.lastTs);

    const today = dayInTz(Date.now(), tz);
    const cutoff7d = Date.now() - 7 * DAY_MS;

    let todayCount = 0;
    let unanswered = 0;
    let leads7d = 0;
    let attributed7d = 0;

    for (const t of threads) {
      const created = toMs(t.createdAt) || t.lastTs;
      // "hoy" = leads nuevos hoy, que es lo que el dueno mira al lado del total.
      if (today && dayInTz(created, tz) === today) todayCount++;
      if (t.unread > 0) unanswered++;
      if (created >= cutoff7d) {
        leads7d++;
        if (t.lead.propertySlug) attributed7d++;
      }
    }

    // Estado de WAHA: si el contenedor esta caido el panel tiene que seguir
    // abriendo igual, con los hilos ya guardados. Por eso va en su propio try.
    let session = { status: 'UNREACHABLE' };
    try {
      const s = await sessionStatus();
      if (typeof s === 'string') session = { status: s };
      else if (s && typeof s === 'object') session = s;
    } catch (err) {
      console.error('[wa/threads] WAHA no responde:', err.message);
    }

    // Cuantas auto-respuestas van hoy contra el tope. El panel pinta la barra
    // con esto; sin el dato el dueno no puede ver que el bot se freno solo.
    let autoRepliesToday = 0;
    try {
      autoRepliesToday = await countAutoRepliesToday();
    } catch (err) {
      console.error('[wa/threads] no pude contar auto-respuestas:', err.message);
    }

    return res.status(200).json({
      threads,
      stats: {
        total: threads.length,
        today: todayCount,
        unanswered,
        autoRepliesToday,
        dailyCap: config.dailyCap,
        // Porcentaje entero 0-100 de leads de los ultimos 7 dias a los que
        // pudimos asignarle una propiedad. Van tambien los crudos por si acaso.
        attributionRate7d: leads7d ? Math.round((attributed7d / leads7d) * 100) : 0,
        leads7d,
        attributed7d,
      },
      config,
      session,
    });
  } catch (err) {
    console.error('[wa/threads] error:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
