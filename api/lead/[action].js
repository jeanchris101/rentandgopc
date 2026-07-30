/**
 * /api/lead/* — una sola funcion serverless para capture y list.
 *
 * Comparten proceso pero no politica: `capture` es publico (rate limit, CORS de
 * mismo origen, allowlist de campos) y `list` exige la cookie del panel. El
 * despachador no impone auth a nadie; cada handler conserva la suya. Ver
 * api/_lib/dispatch.js.
 */
import { dispatch } from '../_lib/dispatch.js';
import { leadRoutes } from '../_lib/lead-routes.js';

export default async function handler(req, res) {
  return dispatch(leadRoutes, req, res, 'api/lead');
}
