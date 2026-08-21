import { put, list } from '@vercel/blob';
import { randomUUID } from 'node:crypto';

// Blob layout:
//   wa/threads/{chatIdSafe}.json  one blob per conversation
//   wa/index.json                 summary of every thread, so the panel loads in one read
//   wa/config.json                panel settings
//   wa/optout.json                phones that asked to stop
const THREADS_PREFIX = 'wa/threads/';
const INDEX_KEY = 'wa/index.json';
const CONFIG_KEY = 'wa/config.json';
const OPTOUT_KEY = 'wa/optout.json';

const PUT_OPTS = { access: 'public', addRandomSuffix: false, contentType: 'application/json' };

// Auto-reply ships OFF: a fresh deploy must never message leads before the
// owner has paired the phone and flipped the switch in the panel.
export const DEFAULT_CONFIG = {
  autoReplyEnabled: false,
  killSwitch: false,
  dailyCap: 20,
  quietHours: { start: 8, end: 21 },
  timezone: 'America/Santo_Domingo',
  // Estricto por defecto: solo se auto-responde a quien llego por un link
  // nuestro (trae ref RG-XXXX-XX). El clasificador tambien da confianza alta
  // por un keyword unico, pero este es el numero PERSONAL del dueno: un
  // conocido preguntando "sigue disponible el de Arboleda?" no puede recibir
  // el pitch de un bot. Ponerlo en false vuelve al comportamiento anterior.
  requireRefForAutoReply: true,
};

export const STAGES = ['new', 'awaiting_qualify', 'qualified', 'closing', 'cold'];

// Every thread blob is re-read on each incoming webhook, so keep it bounded.
const MAX_MESSAGES = 500;

const TZ = DEFAULT_CONFIG.timezone;

/* ------------------------------------------------------------------ keys */

export function chatIdSafe(chatId) {
  return String(chatId || '').replace(/[@.]/g, '_');
}

export function normalizePhone(value) {
  return String(value || '').replace(/\D/g, '');
}

// DR numbers get written both ways (8095551234 and 18095551234, chatIds always
// carry the 1), so match on the shared tail instead of exact digits.
export function samePhone(a, b) {
  const x = normalizePhone(a);
  const y = normalizePhone(b);
  if (!x || !y) return false;
  if (x === y) return true;
  return x.length >= 8 && y.length >= 8 && (x.endsWith(y) || y.endsWith(x));
}

function threadKey(chatId) {
  return `${THREADS_PREFIX}${chatIdSafe(chatId)}.json`;
}

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
    // A missing blob is the normal cold-start case; never let it break a webhook.
    return fallback;
  }
}

async function writeJson(key, data) {
  await put(key, JSON.stringify(data), PUT_OPTS);
}

/* ------------------------------------------------------------------ time */

// DR does not observe DST, but Intl keeps the day boundary correct without
// hardcoding an offset that could bite us later.
function rdDate(value) {
  const d = value ? new Date(value) : new Date();
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d);
}

// WAHA sends epoch seconds; the panel wants ISO strings everywhere.
function toIso(ts) {
  if (!ts) return new Date().toISOString();
  if (typeof ts === 'number') return new Date(ts < 1e12 ? ts * 1000 : ts).toISOString();
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? new Date().toISOString() : d.toISOString();
}

/* ------------------------------------------------------------------ threads */

function emptyThread(chatId) {
  const now = new Date().toISOString();
  return {
    chatId,
    phone: normalizePhone(chatId),
    name: '',
    createdAt: now,
    updatedAt: now,
    lead: {
      ref: null,
      propertySlug: null,
      source: null,
      language: null,
      stage: 'new',
      lastStepSent: null,
      autoRepliedAt: null,
      autoReplyCount: 0,
      confidence: 'low',
      manualOverride: false,
      firstReplyAt: null,
    },
    messages: [],
  };
}

// Old blobs predate whatever field we add next; merging over the defaults keeps
// callers from having to null-check every lead property.
function withDefaults(raw, chatId) {
  const base = emptyThread(raw?.chatId || chatId || '');
  const thread = { ...base, ...(raw || {}) };
  thread.lead = { ...base.lead, ...(raw?.lead || {}) };
  thread.messages = Array.isArray(raw?.messages) ? raw.messages : [];
  if (!thread.phone) thread.phone = normalizePhone(thread.chatId);
  return thread;
}

/** @returns the thread, or null when we have never seen this chat. */
export async function getThread(chatId) {
  const raw = await readJson(threadKey(chatId), null);
  return raw ? withDefaults(raw, chatId) : null;
}

/** Writes the thread blob and refreshes its index entry. Returns the saved thread. */
export async function saveThread(thread) {
  const next = withDefaults(thread);
  if (!next.chatId) throw new Error('saveThread: thread.chatId is required');
  next.updatedAt = new Date().toISOString();
  await writeJson(threadKey(next.chatId), next);
  await upsertIndex(next);
  return next;
}

/**
 * Read-modify-write append. Creates the thread when missing, merges `patchLead`
 * into `lead`, bumps `updatedAt` and the index. `msg.name` is an optional hint
 * used to fill the contact name; it is not stored on the message itself.
 */
export async function appendMessage(chatId, msg = {}, patchLead = null) {
  const thread = (await getThread(chatId)) || emptyThread(chatId);

  const message = {
    id: msg.id || randomUUID(),
    ts: toIso(msg.ts),
    fromMe: Boolean(msg.fromMe),
    type: msg.type || 'chat',
    body: msg.body ?? '',
    intent: msg.intent ?? null,
    hasMedia: Boolean(msg.hasMedia),
  };

  // WAHA retries webhook deliveries, so the same message id can land twice.
  if (!thread.messages.some((m) => m.id === message.id)) {
    thread.messages.push(message);
    if (thread.messages.length > MAX_MESSAGES) {
      thread.messages = thread.messages.slice(-MAX_MESSAGES);
    }
  }

  if (msg.name && !thread.name) thread.name = String(msg.name);
  if (patchLead && typeof patchLead === 'object') {
    thread.lead = { ...thread.lead, ...patchLead };
  }

  return await saveThread(thread);
}

/* ------------------------------------------------------------------ index */

function indexEntry(thread) {
  const last = thread.messages[thread.messages.length - 1] || null;
  return {
    chatId: thread.chatId,
    phone: thread.phone,
    name: thread.name,
    createdAt: thread.createdAt,
    updatedAt: thread.updatedAt,
    stage: thread.lead.stage,
    ref: thread.lead.ref,
    propertySlug: thread.lead.propertySlug,
    source: thread.lead.source,
    language: thread.lead.language,
    confidence: thread.lead.confidence,
    manualOverride: thread.lead.manualOverride,
    autoRepliedAt: thread.lead.autoRepliedAt,
    autoReplyCount: thread.lead.autoReplyCount,
    messageCount: thread.messages.length,
    lastMessage: last
      ? { ts: last.ts, fromMe: last.fromMe, type: last.type, body: String(last.body).slice(0, 160) }
      : null,
  };
}

// Tolerates a bare array in case the blob was written by hand.
async function readIndex() {
  const raw = await readJson(INDEX_KEY, null);
  if (!raw) return null;
  if (Array.isArray(raw)) return raw;
  return Array.isArray(raw.threads) ? raw.threads : [];
}

async function writeIndex(entries) {
  const sorted = [...entries].sort((a, b) =>
    String(b.updatedAt || '').localeCompare(String(a.updatedAt || ''))
  );
  await writeJson(INDEX_KEY, { updatedAt: new Date().toISOString(), threads: sorted });
  return sorted;
}

// Read-modify-write on one blob is racy, but this is a single-owner inbox:
// the worst case is that the list view lags one message behind.
async function upsertIndex(thread) {
  const entries = (await readIndex()) || [];
  const entry = indexEntry(thread);
  const i = entries.findIndex((e) => e.chatId === entry.chatId);
  if (i >= 0) entries[i] = entry;
  else entries.push(entry);
  await writeIndex(entries);
}

/** Rebuilds wa/index.json from the thread blobs. Also the recovery path. */
export async function rebuildIndex() {
  const entries = [];
  try {
    let cursor;
    do {
      const page = await list({ prefix: THREADS_PREFIX, cursor });
      for (const blob of page.blobs) {
        try {
          const res = await fetch(`${blob.url}?t=${Date.now()}`, { cache: 'no-store' });
          if (!res.ok) continue;
          entries.push(indexEntry(withDefaults(await res.json())));
        } catch {
          // One unreadable thread must not abort the whole rebuild.
        }
      }
      cursor = page.hasMore ? page.cursor : undefined;
    } while (cursor);
    return await writeIndex(entries);
  } catch {
    return entries;
  }
}

/** Thread summaries, newest first. Rebuilds the index if it is missing. */
export async function listThreads() {
  const entries = await readIndex();
  if (entries) return entries;
  return await rebuildIndex();
}

/** Threads auto-replied today (RD time) — feeds the daily cap. */
export async function countAutoRepliesToday() {
  const today = rdDate();
  const threads = await listThreads();
  return threads.filter((t) => {
    const at = t.autoRepliedAt || t.lead?.autoRepliedAt;
    return at && rdDate(at) === today;
  }).length;
}

/* ------------------------------------------------------------------ config */

// Panel forms post strings; "false" is truthy, and a truthy autoReplyEnabled
// would start messaging leads. Coerce the dangerous fields explicitly.
function coerceBool(value, fallback) {
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'boolean') return value;
  return value === 'true' || value === '1' || value === 1;
}

function coerceInt(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

function mergeConfig(base, patch) {
  const p = patch && typeof patch === 'object' ? patch : {};
  const merged = { ...base, ...p, quietHours: { ...base.quietHours, ...(p.quietHours || {}) } };
  merged.autoReplyEnabled = coerceBool(merged.autoReplyEnabled, DEFAULT_CONFIG.autoReplyEnabled);
  merged.killSwitch = coerceBool(merged.killSwitch, DEFAULT_CONFIG.killSwitch);
  // Sin coerción, un "false" que llegue como cadena seria truthy y apagaria
  // el modo estricto sin que nadie lo pidiera.
  merged.requireRefForAutoReply = coerceBool(
    merged.requireRefForAutoReply,
    DEFAULT_CONFIG.requireRefForAutoReply,
  );
  merged.dailyCap = Math.max(0, coerceInt(merged.dailyCap, DEFAULT_CONFIG.dailyCap));
  merged.quietHours = {
    start: coerceInt(merged.quietHours.start, DEFAULT_CONFIG.quietHours.start),
    end: coerceInt(merged.quietHours.end, DEFAULT_CONFIG.quietHours.end),
  };
  merged.timezone = merged.timezone || DEFAULT_CONFIG.timezone;
  return merged;
}

export async function getConfig() {
  return mergeConfig(DEFAULT_CONFIG, await readJson(CONFIG_KEY, null));
}

/** Shallow patch (quietHours merges one level deep). Returns the saved config. */
export async function saveConfig(patch = {}) {
  const next = mergeConfig(await getConfig(), patch);
  await writeJson(CONFIG_KEY, next);
  return next;
}

/* ------------------------------------------------------------------ opt-out */

async function readOptOuts() {
  const raw = await readJson(OPTOUT_KEY, []);
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizePhone).filter(Boolean);
}

/** Accepts a phone or a chatId, in any format. */
export async function isOptedOut(phone) {
  const target = normalizePhone(phone);
  if (!target) return false;
  return (await readOptOuts()).some((p) => samePhone(p, target));
}

export async function addOptOut(phone) {
  const target = normalizePhone(phone);
  const current = await readOptOuts();
  if (!target || current.some((p) => samePhone(p, target))) return current;
  current.push(target);
  await writeJson(OPTOUT_KEY, current);
  return current;
}

export async function listOptOuts() {
  return await readOptOuts();
}
