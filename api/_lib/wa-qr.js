/**
 * GET /api/wa/qr — proxy del codigo QR de emparejamiento.
 *
 * WAHA exige el header X-Api-Key para servir el QR, y un <img src> del
 * navegador no puede mandarlo. Apuntar la imagen directo a WAHA obligaria a
 * poner la API key en el HTML del panel, o sea publicarla. Este proxy pide el
 * QR desde el servidor (con la key, que nunca sale de Vercel) y devuelve los
 * bytes ya autenticados, detras de la misma cookie que protege el panel.
 */
import { requireAuth } from './auth.js';
import { fetchQr } from './waha.js';

export async function qr(req, res) {
  if (!requireAuth(req, res)) return;

  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  // El QR rota cada pocos segundos; cachearlo mostraria uno ya vencido.
  res.setHeader('Cache-Control', 'no-store, private');

  try {
    const { contentType, buffer } = await fetchQr();
    res.setHeader('Content-Type', contentType || 'image/png');
    return res.status(200).send(buffer);
  } catch (err) {
    console.error('[wa/qr] no pude obtener el QR:', err.message);
    // Responder JSON aca romperia el <img>, pero un 503 limpio deja que el
    // panel muestre su propio mensaje de "WhatsApp no responde".
    return res.status(503).json({ error: 'No pude obtener el codigo QR de WhatsApp' });
  }
}
