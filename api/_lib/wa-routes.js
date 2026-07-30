/**
 * Tabla de rutas de /api/wa/*, tal como la lee api/wa/[action].js.
 *
 * Las claves son los nombres de archivo de antes, asi que las URLs publicas no
 * se mueven: `threads` sigue siendo GET /api/wa/threads.
 *
 * `webhook` NO esta aqui y no debe estarlo: vive en api/wa/webhook.js con su
 * propio `config = { api: { bodyParser: false } }` (necesita el body crudo para
 * el HMAC) y `maxDuration = 300`. Meterlo en el despachador obligaria a los ocho
 * de abajo a vivir sin bodyParser.
 */
import { config } from './wa-config.js';
import { lead } from './wa-lead.js';
import { login } from './wa-login.js';
import { qr } from './wa-qr.js';
import { send } from './wa-send.js';
import { session } from './wa-session.js';
import { thread } from './wa-thread.js';
import { threads } from './wa-threads.js';

export const waRoutes = {
  threads, // GET  /api/wa/threads  — bandeja del panel
  thread, // GET  /api/wa/thread?chatId=... — un hilo + sugerencias
  send, // POST /api/wa/send     — el dueno manda un mensaje
  lead, // POST /api/wa/lead     — correccion manual del lead
  config, // GET/POST /api/wa/config — ajustes del auto-reply
  login, // POST /api/wa/login    — reparte la cookie del panel
  session, // GET  /api/wa/session  — estado de la sesion de WhatsApp
  qr, // GET  /api/wa/qr       — proxy del QR (devuelve BYTES, no JSON)
};
