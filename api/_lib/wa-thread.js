/**
 * GET /api/wa/thread?chatId=... — un hilo completo mas los botones de respuesta.
 *
 * `suggestions` son los pasos del playbook de esa propiedad, ya renderizados en
 * el idioma del lead y listos para que el dueno los revise y le de enviar. El
 * paso que toca va primero.
 */
import { requireAuth } from './auth.js';
import { getThread } from './wa-store.js';
import { renderStep, findPlaybook, getProperty } from './classify.js';

/**
 * Que paso toca ahora: el siguiente al ultimo enviado. Si nunca se envio nada,
 * el primero del playbook.
 */
function pickSuggestedStep(steps, lead) {
  if (!steps.length) return null;
  const lastSent = lead && lead.lastStepSent;
  if (lastSent) {
    const i = steps.findIndex((s) => s.id === lastSent);
    if (i >= 0 && i + 1 < steps.length) return steps[i + 1].id;
    if (i >= 0) return steps[steps.length - 1].id; // ya se agotaron: dejamos el ultimo
  }
  return steps[0].id;
}

export async function thread(req, res) {
  if (!requireAuth(req, res)) return;

  res.setHeader('Cache-Control', 'no-store, private');

  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const chatId = typeof req.query.chatId === 'string' ? req.query.chatId.trim() : '';
  if (!chatId) return res.status(400).json({ error: 'Falta chatId' });

  try {
    const thread = await getThread(chatId);
    if (!thread || !thread.chatId) return res.status(404).json({ error: 'Hilo no encontrado' });

    const lead = thread.lead || {};
    const playbook = findPlaybook(lead.propertySlug);

    // Sin propiedad asignada no hay guion posible: el panel muestra el selector
    // para que el dueno la marque a mano (POST /api/wa/lead).
    if (!playbook) {
      return res.status(200).json({ ...thread, suggestions: [], needsProperty: true });
    }

    const lang = lead.language || 'es'; // renderStep ya cae a 'es' si no existe
    const property = getProperty(lead.propertySlug);
    const steps = (playbook.steps || []).filter((s) => s && s.id);
    const suggestedId = pickSuggestedStep(steps, lead);

    const suggestions = [];
    for (const step of steps) {
      let text = '';
      try {
        // renderStep devuelve el texto ya con los tokens sustituidos, o '' si no
        // hay guion para ese paso/idioma. Un '' se salta: mejor no ofrecer el
        // boton que ofrecer uno con "{{price}}" dentro.
        const out = renderStep(playbook, step.id, lang, property);
        text = typeof out === 'string' ? out.trim() : String(out?.text || '').trim();
      } catch (err) {
        console.error(`[wa/thread] renderStep fallo en ${step.id}:`, err.message);
      }
      if (!text) continue;
      suggestions.push({
        stepId: step.id,
        label: step[`label_${lang}`] || step.label_es || step.id,
        text,
        sendPhotos: step.send_photos === true,
      });
    }

    // El paso que toca de primero; el resto queda en el orden del playbook.
    const at = suggestions.findIndex((s) => s.stepId === suggestedId);
    if (at > 0) suggestions.unshift(suggestions.splice(at, 1)[0]);

    return res.status(200).json({
      ...thread,
      suggestions,
      needsProperty: false,
      suggestedStep: suggestedId,
      language: lang,
      property: property
        ? { slug: property.slug, name: property.name, refCode: playbook.ref_code || null }
        : null,
    });
  } catch (err) {
    console.error('[wa/thread] error:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
