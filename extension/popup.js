/**
 * popup.js — configuracion y estado. Aqui NO se publica nada: se pega el token,
 * se ve la campana del dia con sus horas y se abre cada grupo con un enlace
 * normal.
 *
 * En modo campana la lista es la LINEA DE TIEMPO del dia: una propiedad, varios
 * grupos, cada uno con su hora, su estilo y su foto. La hora es un recordatorio
 * en pantalla — no hay temporizadores ni alarmas en ninguna parte de esta
 * extension, y el slot marcado "AHORA" es solo el que te conviene hacer ya.
 *
 * El popup es el unico sitio donde se escribe el token. El content script que
 * corre dentro de facebook.com nunca lo recibe.
 *
 * Cero innerHTML: todo se arma con createElement/textContent.
 */
(function () {
  'use strict';

  const DEFAULT_BASE_URL = 'https://www.rentandgopc.com';
  const MIN_TOKEN = 24; // el servidor rechaza tokens mas cortos
  const LANG_NAME = { en: 'Ingles', es: 'Espanol', fr: 'Frances' };

  /** Estado de un slot -> lo que se lee al lado del grupo. */
  const SLOT_LABEL = {
    posted: 'ya publicado',
    skipped: 'saltado hoy',
    missed: 'su hora paso',
    pending: 'pendiente',
  };

  const $ = (id) => document.getElementById(id);

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function cleanBaseUrl(value) {
    const raw = String(value || '').trim().replace(/\/+$/, '');
    if (!raw) return null;
    return /^https:\/\/[^/\s]+$/i.test(raw) ? raw : null;
  }

  /** Avisa si la URL base no esta en host_permissions: el fetch fallaria. */
  function isAllowedHost(baseUrl) {
    const hosts = chrome.runtime.getManifest().host_permissions || [];
    return hosts.some((pattern) => {
      const origin = pattern.replace(/\/\*$/, '');
      return baseUrl.toLowerCase() === origin.toLowerCase();
    });
  }

  function setStatus(kind, text) {
    const dot = $('dot');
    dot.className = 'rgpc-dot' + (kind ? ' rgpc-dot-' + kind : '');
    $('statusText').textContent = text;
  }

  function setMsg(text, kind) {
    const node = $('msg');
    node.textContent = text || '';
    node.className = 'rgpc-msg' + (kind ? ' rgpc-msg-' + kind : '');
    node.hidden = !text;
  }

  /* ------------------------------------------------------------------ *
   * Plan del dia
   * ------------------------------------------------------------------ */

  /** Enlace al grupo, o texto pelado si la URL no es de un grupo de Facebook. */
  function groupNode(name, url) {
    if (typeof url === 'string' && url.startsWith('https://www.facebook.com/groups/')) {
      const link = el('a', null, name);
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      return link;
    }
    return el('span', null, name);
  }

  /**
   * La hora del slot. Va en gris salvo la del que toca ahora, que se queda con
   * el pill dorado: es lo unico que hay que ver al abrir el popup.
   */
  function timeBadge(text, highlight) {
    const badge = el('span', 'rgpc-badge', text);
    if (!highlight) {
      badge.style.background = '#eef1ec';
      badge.style.color = '#55645b';
    }
    return badge;
  }

  /** Modo campana: la linea de tiempo del dia, con estado por slot. */
  function renderCampaign(plan) {
    const list = $('planList');
    const c = plan.campaign || {};
    const slots = Array.isArray(plan.slots) ? plan.slots : [];

    // Nada de mezclar `textContent =` con appendChild en el mismo nodo: se limpia
    // y se cuelgan nodos explicitos, como en el resto del popup.
    const head = $('campHead');
    head.textContent = '';
    const bits = [];
    if (c.propertyShortName || c.propertyName) bits.push(c.propertyShortName || c.propertyName);
    if (c.priceDisplay) bits.push(c.priceDisplay);
    if (bits.length) head.appendChild(el('span', null, bits.join(' · ')));

    const sub = [];
    sub.push(c.size + ' de ' + c.requested + (c.requested === 1 ? ' grupo' : ' grupos'));
    if (c.size > 1) sub.push('cada ' + c.intervalHours + ' h');
    if (c.spansDays > 1) sub.push('dia ' + c.dayNumber + ' de ' + c.spansDays);
    if (c.nowTime) sub.push('son las ' + c.nowTime);
    if (sub.length) head.appendChild(el('span', 'rgpc-plan-prop', sub.join(' · ')));

    const now = $('campNow');
    const next = slots.find((s) => s.isNext) || null;
    if (next) {
      now.hidden = false;
      now.className = 'rgpc-msg rgpc-msg-ok';
      now.textContent =
        (next.isPast ? 'Vas tarde. Toca el slot de las ' : 'Ahora toca el slot de las ') +
        next.slotTime + ': ' + next.groupCode + ' — ' + next.groupName + '.';
    } else {
      now.hidden = true;
      now.textContent = '';
    }

    for (const s of slots) {
      const li = el('li');
      if (s.isNext) {
        // Sin clases nuevas (styles.css no cambia): una barra dorada a la izquierda.
        li.style.boxShadow = 'inset 3px 0 0 #c8a45e';
        li.style.paddingLeft = '7px';
      } else if (s.status === 'posted' || s.status === 'skipped') {
        li.style.opacity = '0.6';
      }
      li.appendChild(timeBadge(s.slotTime, Boolean(s.isNext)));

      const box = el('span', 'rgpc-plan-group');
      box.appendChild(groupNode(s.groupCode + ' — ' + s.groupName, s.groupUrl));
      const meta = [LANG_NAME[s.lang] || s.lang];
      meta.push(s.isNext ? (s.isPast ? 'TOCA YA' : 'TOCA AHORA') : SLOT_LABEL[s.status] || s.status);
      if (s.styleId) meta.push(s.styleId);
      box.appendChild(el('span', 'rgpc-plan-prop', meta.join(' · ')));
      li.appendChild(box);
      list.appendChild(li);
    }

    const cap = $('campCap');
    cap.textContent = c.cappedMessage || '';

    const note = $('planNote');
    if (!slots.length) note.textContent = plan.reason || 'Hoy no hay campana.';
    else if (!c.pending) note.textContent = plan.reason || 'Campana de hoy terminada.';
    else note.textContent = '';
  }

  /** Modo spread: la lista de siempre, una propiedad distinta por grupo. */
  function renderSpread(plan) {
    const list = $('planList');
    const note = $('planNote');
    const pending = (plan.assignments || []).filter((a) => !a.alreadyPosted);
    const done = (plan.assignments || []).filter((a) => a.alreadyPosted);

    for (const a of pending) {
      const li = el('li');
      li.appendChild(el('span', 'rgpc-badge', a.groupCode));
      const box = el('span', 'rgpc-plan-group');
      box.appendChild(groupNode(a.groupName, a.groupUrl));
      box.appendChild(
        el(
          'span',
          'rgpc-plan-prop',
          (a.propertyShortName || a.propertyName) + ' · ' + a.priceDisplay + ' · ' + (LANG_NAME[a.lang] || a.lang)
        )
      );
      li.appendChild(box);
      list.appendChild(li);
    }

    if (!pending.length) {
      note.textContent = plan.reason || 'No queda nada por publicar hoy.';
    } else if (done.length) {
      note.textContent = 'Ya publicaste en ' + done.length + (done.length === 1 ? ' grupo' : ' grupos') + ' hoy.';
    }
  }

  function renderPlan(plan) {
    const list = $('planList');
    list.textContent = '';
    $('planNote').textContent = '';
    $('campHead').textContent = '';
    $('campCap').textContent = '';
    $('campNow').hidden = true;
    $('campNow').textContent = '';

    if (!plan) {
      $('planNote').textContent = 'Sin plan todavia.';
      return;
    }
    if (plan.mode === 'campaign') renderCampaign(plan);
    else renderSpread(plan);
  }

  /* ------------------------------------------------------------------ *
   * Estado
   * ------------------------------------------------------------------ */

  async function loadStatus(force) {
    setStatus('', 'Revisando...');
    let res = null;
    try {
      res = await chrome.runtime.sendMessage({ type: 'RGPC_STATUS', params: { force: Boolean(force) } });
    } catch (e) {
      res = null;
    }

    if (!res) {
      setStatus('bad', 'No responde el service worker. Recarga la extension en chrome://extensions.');
      renderPlan(null);
      return;
    }

    if (res.plan) {
      renderPlan(res.plan);
      if (res.stale) {
        setStatus('warn', 'Plan viejo (no pude actualizar): ' + (res.error || 'sin conexion'));
        return;
      }
      const plan = res.plan;
      const next = (Array.isArray(plan.slots) ? plan.slots : []).find((s) => s.isNext) || null;
      if (plan.mode === 'campaign' && next) {
        setStatus('ok', 'Conectado. ' + (next.isPast ? 'Atrasado: toca' : 'Ahora toca') +
          ' el slot de las ' + next.slotTime + ' (' + next.groupCode + ').');
        return;
      }
      const n = (plan.assignments || []).filter((a) => !a.alreadyPosted).length;
      setStatus('ok', 'Conectado. Hoy toca ' + n + (n === 1 ? ' grupo.' : ' grupos.'));
      return;
    }

    renderPlan(null);
    if (res.code === 'no-token' || res.hasToken === false) {
      setStatus('warn', 'Falta el token. Pegalo abajo y dale a Guardar.');
      return;
    }
    setStatus('bad', res.error || 'No pude traer el plan.');
  }

  /* ------------------------------------------------------------------ *
   * Ajustes
   * ------------------------------------------------------------------ */

  async function loadConfig() {
    const stored = await chrome.storage.local.get(['baseUrl', 'token']);
    const baseUrl = stored.baseUrl || DEFAULT_BASE_URL;
    $('baseUrl').value = baseUrl;
    $('token').value = stored.token || '';
    $('queueLink').href = (cleanBaseUrl(baseUrl) || DEFAULT_BASE_URL) + '/group-queue.html';
  }

  async function save() {
    const baseUrl = cleanBaseUrl($('baseUrl').value);
    const token = String($('token').value || '').trim();

    if (!baseUrl) {
      setMsg('La URL tiene que ser https y sin barra final. Ej: ' + DEFAULT_BASE_URL, 'bad');
      return;
    }
    if (!isAllowedHost(baseUrl)) {
      setMsg(
        'Esa URL no esta en los permisos de la extension (manifest.json > host_permissions). ' +
          'Con otra URL el fetch va a fallar.',
        'bad'
      );
      return;
    }
    if (!token) {
      setMsg('Pega el token.', 'bad');
      return;
    }
    if (token.length < MIN_TOKEN) {
      setMsg('Ese token es muy corto. El servidor pide ' + MIN_TOKEN + ' caracteres o mas.', 'bad');
      return;
    }

    await chrome.storage.local.set({ baseUrl, token });
    await chrome.storage.local.remove('planCache');
    $('queueLink').href = baseUrl + '/group-queue.html';
    setMsg('Guardado.', 'ok');
    loadStatus(true);
  }

  /* ------------------------------------------------------------------ *
   * Arranque
   * ------------------------------------------------------------------ */

  document.addEventListener('DOMContentLoaded', async () => {
    $('version').textContent = 'v' + chrome.runtime.getManifest().version;
    $('save').addEventListener('click', save);
    $('refresh').addEventListener('click', () => {
      setMsg('');
      loadStatus(true);
    });
    $('showToken').addEventListener('change', (ev) => {
      $('token').type = ev.target.checked ? 'text' : 'password';
    });

    await loadConfig();
    loadStatus(false);
  });
})();
