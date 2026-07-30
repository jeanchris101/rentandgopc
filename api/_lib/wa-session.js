/**
 * GET /api/wa/session — estado de la sesion de WhatsApp + QR para emparejar.
 *
 * La pantalla de emparejamiento pregunta aca cada pocos segundos hasta que el
 * estado pasa a WORKING.
 */
import { requireAuth } from './auth.js';
import { sessionStatus } from './waha.js';

export async function session(req, res) {
  if (!requireAuth(req, res)) return;

  // El QR cambia cada pocos segundos: cachearlo seria justo lo contrario de util.
  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  let status = 'UNREACHABLE';
  let details = null;

  // Si WAHA esta caido no rompemos el panel: devolvemos UNREACHABLE y que la
  // pantalla muestre "no puedo hablar con el servidor de WhatsApp".
  try {
    const s = await sessionStatus();
    if (typeof s === 'string') {
      status = s;
    } else if (s && typeof s === 'object') {
      status = s.status || s.state || 'UNKNOWN';
      details = s;
    }
  } catch (err) {
    console.error('[wa/session] WAHA no responde:', err.message);
  }

  // Siempre nuestro proxy, nunca la URL cruda de WAHA: esa exige el header
  // X-Api-Key, que un <img src> no puede mandar y que no debe salir al HTML.
  // Solo tiene sentido pedirlo cuando WhatsApp esta esperando el escaneo.
  const qr = status === 'SCAN_QR_CODE' ? '/api/wa/qr' : null;

  return res.status(200).json({ status, qrUrl: qr, details });
}
