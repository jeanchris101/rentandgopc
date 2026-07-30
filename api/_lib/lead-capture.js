/**
 * POST /api/lead/capture — public lead intake.
 *
 * Called straight from the browser: site forms and every WhatsApp click
 * (analytics.js sends a beacon here before the tab leaves). No auth by design —
 * a visitor filling a form has no cookie — so the hardening lives here instead:
 * body size cap, per-IP rate limit, top-level key allowlist, same-origin CORS.
 *
 * It also answers ok when storage fails. Losing a lead in the logs is bad;
 * showing an error to someone who just typed their phone number is worse.
 *
 * Blob layout mirrors api/_lib/wa-store.js:
 *   leads/{YYYY-MM}/{ts}-{rand}.json   one blob per lead
 *   leads/index.json                   summary of every lead, so the panel reads once
 *
 * api/_lib/lead-list.js imports the read helpers from here on purpose: the two
 * routes are the only consumers, and a third _lib file for 40 lines would just
 * add a place for the shape of an index entry to drift.
 */
import { put, list } from '@vercel/blob';
import { randomUUID } from 'node:crypto';

const LEADS_PREFIX = 'leads/';
const INDEX_KEY = 'leads/index.json';
const PUT_OPTS = { access: 'public', addRandomSuffix: false, contentType: 'application/json' };

/** Anything past this is not a lead, it is someone testing what we accept. */
const MAX_BODY_BYTES = 8 * 1024;
const MAX_STR = 500;
const MAX_META_KEYS = 20;

const RATE_LIMIT = 30;
const RATE_WINDOW_MS = 60 * 1000;

/** Top-level fields we keep. Everything else the client sends is dropped. */
const STRING_FIELDS = [
  'source',
  'name',
  'email',
  'phone',
  'propertySlug',
  'ref',
  'page',
  'referrer',
  'fbclid',
  'visitorId',
  'utm_source',
  'utm_medium',
  'utm_campaign',
  'utm_content',
  'utm_term',
];

// The index is rewritten on every capture, so it cannot grow forever: at some
// point a click would be reading and writing megabytes. Full records stay in the
// monthly blobs and rebuildIndex() can always bring the old ones back.
const MAX_INDEX_ENTRIES = 2000;

/* ------------------------------------------------------------------ blob io */

// put() URLs sit behind a CDN, so re-reads need the ?t= + no-store combo that
// api/track.js already relies on, otherwise we write into a stale copy.
async function readJson(key, fallback) {
  try {
    const { blobs } = await list({ prefix: key });
    const blob = blobs.find((b) => b.pathname === key);
    if (!blob) return fallback;
    const res = await fetch(`${blob.url}?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return fallback;
    return await res.json();
  } catch {
    // A missing index is the normal cold-start case.
    return fallback;
  }
}

async function writeJson(key, data) {
  await put(key, JSON.stringify(data), PUT_OPTS);
}

/* ------------------------------------------------------------------ index */

// The index deliberately carries NO personal data.
//
// This store is a public-read Vercel Blob store (that is a property of the
// store, fixed at creation — it cannot be flipped per-file), and the index
// lives at a fixed, guessable pathname while each lead record gets a random
// suffix. So the index is the one object an outsider could plausibly reach by
// URL. Keeping names, emails and phone numbers out of it means reaching it
// leaks counts and property interest, not a contact list of real buyers.
//
// The full record, PII included, stays in the per-lead blob and is read by
// api/_lib/lead-list.js, which is behind the panel cookie.
export function indexEntry(record) {
  return {
    id: record.id,
    key: record.key,
    receivedAt: record.receivedAt,
    source: record.source,
    propertySlug: record.propertySlug || null,
    ref: record.ref || null,
    // Enough to triage the inbox without exposing who the person is.
    hasContact: Boolean(record.name || record.email || record.phone),
  };
}

// Tolerates a bare array in case the blob was written by hand.
async function readIndex() {
  const raw = await readJson(INDEX_KEY, null);
  if (!raw) return null;
  if (Array.isArray(raw)) return { total: raw.length, leads: raw };
  if (!Array.isArray(raw.leads)) return { total: 0, leads: [] };
  return { total: Number(raw.total) || raw.leads.length, leads: raw.leads };
}

async function writeIndex(leads, total) {
  const sorted = [...leads].sort((a, b) =>
    String(b.receivedAt || '').localeCompare(String(a.receivedAt || ''))
  );
  const kept = sorted.slice(0, MAX_INDEX_ENTRIES);
  // `total` survives the trim so the panel keeps reporting the real lifetime count.
  const doc = {
    updatedAt: new Date().toISOString(),
    total: Math.max(Number(total) || 0, kept.length),
    leads: kept,
  };
  await writeJson(INDEX_KEY, doc);
  return doc;
}

/**
 * Read one full lead record — PII included — by the key stored in the index.
 *
 * Only api/_lib/lead-list.js calls this, and only behind the panel cookie. Contact
 * details deliberately live here and not in the index; see indexEntry().
 */
export async function readLead(key) {
  if (!key || typeof key !== 'string' || !key.startsWith(LEADS_PREFIX)) return null;
  return readJson(key, null);
}

/** Rebuilds leads/index.json from the lead blobs. Also the recovery path. */
export async function rebuildIndex() {
  const entries = [];
  try {
    let cursor;
    do {
      const page = await list({ prefix: LEADS_PREFIX, cursor });
      for (const blob of page.blobs) {
        if (blob.pathname === INDEX_KEY) continue;
        try {
          const res = await fetch(`${blob.url}?t=${Date.now()}`, { cache: 'no-store' });
          if (!res.ok) continue;
          const record = await res.json();
          if (record && record.id) entries.push(indexEntry(record));
        } catch {
          // One unreadable lead must not abort the whole rebuild.
        }
      }
      cursor = page.hasMore ? page.cursor : undefined;
    } while (cursor);
    return await writeIndex(entries, entries.length);
  } catch {
    return { updatedAt: new Date().toISOString(), total: entries.length, leads: entries };
  }
}

/** Lead summaries, newest first. Rebuilds the index if it is missing. */
export async function listLeads() {
  const index = await readIndex();
  if (index) return index;
  return await rebuildIndex();
}

// Read-modify-write on one blob is racy, but this is a single-owner site with a
// handful of leads a day: the worst case is that one entry loses the race and
// only shows up after the next rebuild. The full record is already saved.
async function appendToIndex(record) {
  const index = (await readIndex()) || { total: 0, leads: [] };
  const leads = [indexEntry(record), ...index.leads.filter((e) => e && e.id !== record.id)];
  await writeIndex(leads, index.total + 1);
}

/* ------------------------------------------------------------------ input */

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
  return b && typeof b === 'object' && !Array.isArray(b) ? b : null;
}

// Control characters would corrupt the panel view, and unbounded strings are
// how a public endpoint turns into free storage.
function cleanString(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return '';
  return String(value)
    .replace(/[\u0000-\u001f\u007f]/g, ' ')
    .trim()
    .slice(0, MAX_STR);
}

// `meta` is free-form by contract, so it only gets a shallow clean: scalars
// only, capped count. Nested objects are dropped rather than walked.
function cleanMeta(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const out = {};
  let n = 0;
  for (const [k, v] of Object.entries(value)) {
    if (n >= MAX_META_KEYS) break;
    const key = cleanString(k).slice(0, 100);
    if (!key) continue;
    if (typeof v === 'number' || typeof v === 'boolean') out[key] = v;
    else if (typeof v === 'string') out[key] = cleanString(v);
    else continue;
    n++;
  }
  return n ? out : null;
}

function clientIp(req) {
  const xff = req.headers['x-forwarded-for'];
  const first = String(Array.isArray(xff) ? xff[0] : xff || '')
    .split(',')[0]
    .trim();
  return first || req.headers['x-real-ip'] || req.socket?.remoteAddress || 'unknown';
}

/* ------------------------------------------------------------------ abuse */

// Per-instance memory: serverless gives every warm instance its own map, so this
// is a speed bump against one noisy client, not a WAF. It is still what stops a
// single loop from filling the Blob store, which is the realistic threat here.
const hits = new Map();

function rateLimited(ip) {
  const now = Date.now();

  // Sweep on write; otherwise the map grows one entry per IP for the life of
  // the instance.
  if (hits.size > 5000) {
    for (const [key, times] of hits) {
      if (!times.length || now - times[times.length - 1] > RATE_WINDOW_MS) hits.delete(key);
    }
  }

  const times = (hits.get(ip) || []).filter((t) => now - t < RATE_WINDOW_MS);
  times.push(now);
  hits.set(ip, times);
  return times.length > RATE_LIMIT;
}

function tooBig(req, body) {
  const declared = Number(req.headers['content-length'] || 0);
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) return true;
  try {
    return Buffer.byteLength(JSON.stringify(body) || '') > MAX_BODY_BYTES;
  } catch {
    return true;
  }
}

/**
 * Same-origin only, never `*`: this endpoint writes. Echoing the caller's Origin
 * back is what makes it "only us" — a request from another site gets no
 * Access-Control-Allow-Origin at all and the browser drops the response.
 * A missing Origin header is a same-origin form post or a server-side call.
 */
function applyCors(req, res) {
  const origin = req.headers.origin;
  if (!origin) return true;

  const host = req.headers['x-forwarded-host'] || req.headers.host;
  let allowed = false;
  try {
    allowed = new URL(origin).host === String(host);
  } catch {
    allowed = false;
  }

  res.setHeader('Vary', 'Origin');
  if (allowed) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  }
  return allowed;
}

/**
 * waitUntil lives in @vercel/functions. Loaded lazily so a deploy without the
 * dependency still captures leads — it just holds the invocation open instead.
 * Same pattern as api/wa/webhook.js.
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

/* ------------------------------------------------------------------ handler */

export async function capture(req, res) {
  const sameOrigin = applyCors(req, res);

  // vercel.json puts `public, max-age=3600` on everything.
  res.setHeader('Cache-Control', 'no-store');

  if (req.method === 'OPTIONS') return res.status(sameOrigin ? 204 : 403).end();
  if (!sameOrigin) return res.status(403).json({ error: 'Forbidden' });
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const ip = clientIp(req);
  if (rateLimited(ip)) return res.status(429).json({ error: 'Too many requests' });

  const body = parseBody(req);
  if (!body) return res.status(400).json({ error: 'Invalid JSON' });
  if (tooBig(req, body)) return res.status(413).json({ error: 'Payload too large' });

  // The one case worth a 400: a lead with no source is unattributable noise, and
  // it can only come from a caller we wrote wrong.
  const source = cleanString(body.source);
  if (!source) return res.status(400).json({ error: 'Missing source' });

  const now = new Date();
  const receivedAt = now.toISOString();
  const id = `${now.getTime()}-${randomUUID().slice(0, 8)}`;
  const key = `${LEADS_PREFIX}${receivedAt.slice(0, 7)}/${id}.json`;

  // Allowlist walk: anything the client sent outside STRING_FIELDS is gone here.
  const record = { id, key, receivedAt };
  for (const field of STRING_FIELDS) {
    const value = cleanString(body[field]);
    if (value) record[field] = value;
  }

  const meta = cleanMeta(body.meta);
  if (meta) record.meta = meta;

  record.ip = ip;
  record.userAgent = cleanString(req.headers['user-agent']);

  // Answer first, then persist: for a wa-click the browser is already leaving,
  // and for a form the visitor should not wait on two blob round-trips.
  res.status(200).json({ ok: true, id });

  const work = (async () => {
    await writeJson(key, record);
    await appendToIndex(record);
  })().catch((err) => {
    // Never surfaced to the visitor. This log line is the last copy of the lead.
    console.error('[lead/capture] storage failed, lead only exists in this log:', err);
    console.error('[lead/capture] lost lead:', JSON.stringify(record));
  });

  const waitUntil = await getWaitUntil();
  if (waitUntil) waitUntil(work);
  else await work; // no @vercel/functions: keep the invocation alive by hand
}
