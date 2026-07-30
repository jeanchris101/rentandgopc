/**
 * popup.js — configuracion y estado. Aqui NO se publica nada: se pega el token,
 * se ve el plan del dia y se abre cada grupo con un enlace normal.
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

  function renderPlan(plan) {
    const list = $('planList');
    const note = $('planNote');
    list.textContent = '';
    note.textContent = '';

    if (!plan) {
      note.textContent = 'Sin plan todavia.';
      return;
    }

    const pending = (plan.assignments || []).filter((a) => !a.alreadyPosted);
    const done = (plan.assignments || []).filter((a) => a.alreadyPosted);

    for (const a of pending) {
      const li = el('li');
      li.appendChild(el('span', 'rgpc-badge', a.groupCode));

      const box = el('span', 'rgpc-plan-group');
      if (typeof a.groupUrl === 'string' && a.groupUrl.startsWith('https://www.facebook.com/groups/')) {
        const link = el('a', null, a.groupName);
        link.href = a.groupUrl;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        box.appendChild(link);
      } else {
        box.appendChild(el('span', null, a.groupName));
      }
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
      const n = (res.plan.assignments || []).filter((a) => !a.alreadyPosted).length;
      if (res.stale) {
        setStatus('warn', 'Plan viejo (no pude actualizar): ' + (res.error || 'sin conexion'));
      } else {
        setStatus('ok', 'Conectado. Hoy toca ' + n + (n === 1 ? ' grupo.' : ' grupos.'));
      }
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
