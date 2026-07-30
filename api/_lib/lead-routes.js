/**
 * Tabla de rutas de /api/lead/*, tal como la lee api/lead/[action].js.
 *
 * OJO: las dos NO tienen la misma politica y no deben uniformarse.
 *   capture  PUBLICO. Lo llama el navegador de un visitante que no tiene cookie.
 *            Se defiende solo: tope de tamano, rate limit por IP, allowlist de
 *            campos y CORS de mismo origen.
 *   list     Detras de la cookie del panel (requireAuth): devuelve PII.
 */
import { capture } from './lead-capture.js';
import { list } from './lead-list.js';

export const leadRoutes = {
  capture, // POST/OPTIONS /api/lead/capture — entrada publica de leads
  list, // GET          /api/lead/list    — la bandeja del dueno
};
