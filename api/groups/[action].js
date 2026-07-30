/**
 * /api/groups/* — una sola funcion serverless para plan, mark y settings.
 *
 * Los handlers se mudaron a api/_lib/groups-*.js sin tocarles la logica; el
 * import cruzado que ya existia (mark -> plan -> settings) sigue igual, solo que
 * ahora resuelve dentro de _lib. Ver api/_lib/dispatch.js.
 */
import { dispatch } from '../_lib/dispatch.js';
import { groupsRoutes } from '../_lib/groups-routes.js';

export default async function handler(req, res) {
  return dispatch(groupsRoutes, req, res, 'api/groups');
}
