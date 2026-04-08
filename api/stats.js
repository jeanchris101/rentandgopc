import { list } from '@vercel/blob';

const BLOB_KEY = 'analytics/stats.json';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');

  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  // Simple password protection
  const pass = req.query.key;
  if (pass !== process.env.ADMIN_KEY) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    // Find the blob
    const { blobs } = await list({ prefix: BLOB_KEY });
    if (!blobs.length) {
      return res.status(200).json({ clicks: {}, daily: {}, pages: {}, totalClicks: 0 });
    }

    const response = await fetch(blobs[0].url);
    const stats = await response.json();
    return res.status(200).json(stats);
  } catch (err) {
    console.error('Stats error:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
