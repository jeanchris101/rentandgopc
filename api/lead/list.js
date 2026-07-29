/**
 * GET /api/lead/list — where the leads came from, for the owner.
 *
 * Same cookie as the WhatsApp panel (api/_lib/auth.js). The point is that the
 * owner can see the source of every lead without opening the Vercel dashboard.
 *
 * Returns the newest leads with their contact details, plus counters computed
 * over the whole index — `?limit=` only trims the list, never the stats.
 *
 * The index holds no PII (see indexEntry in capture.js), so the returned page
 * is hydrated from the individual lead blobs, in parallel. That is the reason
 * the default page is small: each entry costs one read.
 */
import { requireAuth } from '../_lib/auth.js';
import { listLeads, readLead } from './capture.js';

const DAY_MS = 24 * 60 * 60 * 1000;
// Small on purpose: every returned lead is one blob read (PII is not in the
// index). The counters below still cover the whole index regardless of limit.
const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;

function toMs(value) {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

// Two values mean "no listing": "unknown" (analytics.js found no data-prop and
// the page is not a listing) and "GEN" (the markup's marker for a generic
// contact CTA, ref RG-GEN-*). Both still show up in byProperty — you want to see
// how many generic clicks you get — but counting them as attributed would make
// the rate look perfect exactly when attribution is failing.
const NOT_A_LISTING = new Set(['unknown', 'gen']);

function attributed(slug) {
  return Boolean(slug) && !NOT_A_LISTING.has(String(slug).toLowerCase());
}

export default async function handler(req, res) {
  if (!requireAuth(req, res)) return;

  // vercel.json puts `public, max-age=3600` on everything. Without this the
  // lead list would be cached (and potentially shared) for an hour.
  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const requested = Number(req.query.limit);
  const limit = Number.isFinite(requested) && requested > 0
    ? Math.min(Math.trunc(requested), MAX_LIMIT)
    : DEFAULT_LIMIT;

  try {
    const index = await listLeads();
    const all = (Array.isArray(index?.leads) ? index.leads : [])
      .filter((e) => e && e.id)
      .sort((a, b) => toMs(b.receivedAt) - toMs(a.receivedAt));

    const cutoff7d = Date.now() - 7 * DAY_MS;
    const bySource = {};
    const byProperty = {};
    let last7d = 0;
    let attributed7d = 0;

    for (const lead of all) {
      const source = lead.source || 'unknown';
      bySource[source] = (bySource[source] || 0) + 1;

      const slug = lead.propertySlug || 'unknown';
      byProperty[slug] = (byProperty[slug] || 0) + 1;

      if (toMs(lead.receivedAt) >= cutoff7d) {
        last7d++;
        if (attributed(lead.propertySlug)) attributed7d++;
      }
    }

    // Hydrate only the page we return, in parallel. A lead whose blob is gone
    // still appears with its index fields rather than vanishing from the list.
    const page = all.slice(0, limit);
    const hydrated = await Promise.all(page.map(async (entry) => {
      try {
        const full = await readLead(entry.key);
        if (!full) return entry;
        return {
          ...entry,
          name: full.name || null,
          email: full.email || null,
          phone: full.phone || null,
          page: full.page || null,
          referrer: full.referrer || null,
          meta: full.meta || null,
        };
      } catch {
        return entry;
      }
    }));

    return res.status(200).json({
      leads: hydrated,
      stats: {
        // The index is trimmed to its newest entries, so `total` is the counter
        // the index carries, not the length of what we just returned.
        total: Number(index?.total) || all.length,
        last7d,
        bySource,
        byProperty,
        // Integer 0-100: share of the last 7 days we could tie to a listing.
        attributionRate7d: last7d ? Math.round((attributed7d / last7d) * 100) : 0,
      },
    });
  } catch (err) {
    console.error('[lead/list] error:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
