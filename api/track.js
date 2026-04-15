import { put, list } from '@vercel/blob';

const BLOB_KEY = 'analytics/stats.json';

async function getStats() {
  try {
    const { blobs } = await list({ prefix: BLOB_KEY });
    if (blobs.length) {
      const url = `${blobs[0].url}?t=${Date.now()}`;
      const res = await fetch(url, { cache: 'no-store' });
      if (res.ok) return await res.json();
    }
  } catch {}
  return { clicks: {}, daily: {}, pages: {} };
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  try {
    // Parse body - sendBeacon may send as text/plain instead of application/json
    let body = req.body;
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch { return res.status(400).json({ error: 'Invalid JSON' }); }
    }
    const { category, label, page } = body;
    if (!category) return res.status(400).json({ error: 'Missing category' });

    const stats = await getStats();
    const today = new Date().toISOString().split('T')[0];

    // Increment click counters
    if (!stats.clicks[category]) stats.clicks[category] = {};
    const key = label || 'unknown';
    stats.clicks[category][key] = (stats.clicks[category][key] || 0) + 1;

    // Daily totals
    if (!stats.daily[today]) stats.daily[today] = {};
    stats.daily[today][category] = (stats.daily[today][category] || 0) + 1;

    // Page views
    if (page) {
      if (!stats.pages[page]) stats.pages[page] = 0;
      stats.pages[page]++;
    }

    // Total counter
    stats.totalClicks = (stats.totalClicks || 0) + 1;
    stats.lastUpdated = new Date().toISOString();

    // Save back to blob
    await put(BLOB_KEY, JSON.stringify(stats), {
      access: 'public',
      addRandomSuffix: false,
      contentType: 'application/json',
    });

    return res.status(200).json({ ok: true });
  } catch (err) {
    console.error('Track error:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
