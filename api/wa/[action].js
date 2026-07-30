/**
 * /api/wa/* — una sola funcion serverless para threads, thread, send, lead,
 * config, login, session y qr.
 *
 * Ocho archivos eran ocho funciones, y el plan Hobby solo da 12 en total. Los
 * handlers no cambiaron: se mudaron a api/_lib/wa-*.js (que no son endpoints y
 * por eso no cuentan) y aqui solo se reparte. Ver api/_lib/dispatch.js para el
 * detalle de la reescritura de Vercel y de por que el archivo se llama
 * `[action].js` y no `[...action].js`.
 *
 * `/api/wa/webhook` NO pasa por aqui: api/wa/webhook.js existe como archivo, y
 * el sistema de archivos se consulta antes que esta ruta dinamica.
 */
import { dispatch } from '../_lib/dispatch.js';
import { waRoutes } from '../_lib/wa-routes.js';

export default async function handler(req, res) {
  return dispatch(waRoutes, req, res, 'api/wa');
}
