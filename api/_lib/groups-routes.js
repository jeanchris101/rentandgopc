/**
 * Tabla de rutas de /api/groups/*, tal como la lee api/groups/[action].js.
 *
 * Las tres comparten puerta (cookie del panel o Bearer de la extension de
 * Chrome), pero cada handler la aplica por su cuenta: aqui no se decide nada.
 */
import { mark } from './groups-mark.js';
import { plan } from './groups-plan.js';
import { settings } from './groups-settings.js';

export const groupsRoutes = {
  plan, // GET      /api/groups/plan     — la cola de grupos de hoy
  mark, // POST     /api/groups/mark     — marcar publicado / saltado
  settings, // GET/POST /api/groups/settings — modo campana vs spread
};
