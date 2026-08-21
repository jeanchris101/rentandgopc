/**
 * content.js — el panel que sale dentro de un grupo de Facebook.
 *
 * =====================================================================
 * LO QUE ES: un llenador de formularios con el humano en el lazo.
 * Te dice que toca publicar en ESTE grupo y te escribe el texto en el
 * compositor. Tu lo lees, lo arreglas si quieres, y TU aprietas Publicar.
 *
 * LO QUE NO ES: un bot. No publica sola, no recorre grupos en tanda, no
 * programa envios, no hace clic en Publicar y no corre sin ti delante.
 *
 * La linea es deliberada y no es cosmetica. Automatizar el ENVIO viola los
 * Terminos de Meta y arriesga la cuenta personal del dueno — que ademas
 * administra la Pagina de Rent & Go, o sea que perderla se lleva el negocio
 * por delante. Llenar un campo que un humano revisa y manda, no: es lo mismo
 * que pegar con Ctrl+V, solo que sin equivocarse de grupo ni de foto.
 *
 * Por eso en este archivo:
 *   - No existe ninguna llamada que apriete el boton Publicar. La unica
 *     funcion que hace clic es safeClick(), y se niega en seco si el nombre
 *     del control se parece a Publicar / Publish / Publier / Compartir.
 *   - No hay setTimeout que dispare un envio, ni cola, ni "siguiente grupo".
 *   - Marcar "ya lo publique" lo aprieta el dueno DESPUES de publicar; es un
 *     registro para el cooldown, no un disparador.
 * Si alguna vez alguien viene a "automatizar el ultimo clic": ese es
 * exactamente el clic que no se automatiza.
 *
 * MODO CAMPANA: el panel te dice la HORA asignada a este grupo y si es el turno
 * de ahora o si te adelantaste. Es informativo y nunca bloqueante — los botones
 * funcionan igual a cualquier hora, porque el dueno del negocio decide cuando
 * publica. Y sigue sin haber temporizadores: la hora se PINTA, no se espera.
 * =====================================================================
 */
(function () {
  'use strict';

  if (window.__rgpcAssistLoaded) return;
  window.__rgpcAssistLoaded = true;

  const PANEL_ID = 'rgpc-panel';
  const UI_KEY = 'ui';
  // clave de URL -> codigo de grupo, para los grupos que Facebook sirve con una
  // direccion distinta a la que esta en group-assist-config.json
  const ALIAS_KEY = 'groupAliases';

  const LANG_NAME = { en: 'Ingles', es: 'Espanol', fr: 'Frances' };
  const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

  /** Segmentos de /groups/<x> que no son un grupo. */
  const NOT_A_GROUP = new Set(['feed', 'discover', 'create', 'joins', 'your_groups', 'search']);

  const state = {
    plan: null,
    stale: false,
    groupKey: null,
    group: null,
    assignment: null,
    slot: null, // el slot de campana de ESTE grupo, si tiene uno
    nextSlot: null, // el slot que toca ahora en la campana del dia
    ui: { collapsed: false, dismissedDate: null },
    aliases: {}, // clave de URL -> codigo, para grupos que Facebook sirve con otra direccion
    note: null, // { text, kind }
    busy: false,
    lastDownloadId: null,
  };

  /* ================================================================== *
   * Utilidades
   * ================================================================== */

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function button(cls, label, onClick) {
    const b = el('button', 'rgpc-btn ' + cls, label);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function humanDate(value) {
    const s = String(value || '');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    const p = s.split('-').map(Number);
    return p[2] + ' ' + MONTHS[p[1] - 1] + ' ' + p[0];
  }

  /** Habla con el service worker. Nunca lanza: devuelve null si algo se cayo. */
  async function send(type, params) {
    try {
      const res = await chrome.runtime.sendMessage({ type, params: params || {} });
      return res || null;
    } catch (e) {
      // Pasa cuando recargas la extension con la pestana abierta.
      return null;
    }
  }

  /* ================================================================== *
   * Que grupo es este
   * ================================================================== */

  function groupKeyFromUrl(href) {
    try {
      const u = new URL(href);
      if (u.hostname !== 'www.facebook.com') return null;
      const m = /^\/groups\/([^/?#]+)/.exec(u.pathname);
      if (!m) return null;
      const key = decodeURIComponent(m[1]).toLowerCase();
      return NOT_A_GROUP.has(key) ? null : key;
    } catch (e) {
      return null;
    }
  }

  function findGroup(plan, key) {
    if (!plan || !Array.isArray(plan.groups) || !key) return null;
    for (const g of plan.groups) {
      if (groupKeyFromUrl(g.url) === key) return g;
    }
    // Sin coincidencia por URL, mira si ya dijiste a mano cual grupo es este.
    const code = state.aliases[key];
    if (code) return plan.groups.find((g) => g.code === code) || null;
    return null;
  }

  function findAssignment(plan, code) {
    if (!plan || !Array.isArray(plan.assignments)) return null;
    return plan.assignments.find((a) => a.groupCode === code) || null;
  }

  function findSlot(plan, code) {
    if (!plan || !Array.isArray(plan.slots)) return null;
    return plan.slots.find((s) => s.groupCode === code) || null;
  }

  function findNextSlot(plan) {
    if (!plan || !Array.isArray(plan.slots)) return null;
    return plan.slots.find((s) => s.isNext) || null;
  }

  /* ================================================================== *
   * EL COMPOSITOR DE FACEBOOK
   *
   * Facebook escribe con Lexical sobre un contenteditable. Escribir en
   * textContent no dispara nada: Lexical mantiene su propio estado y en el
   * siguiente render te borra lo que metiste.
   *
   * Lo que SI funciona es hacer que el navegador genere los mismos eventos que
   * genera una tecla. Por orden de fiabilidad:
   *
   *   1. document.execCommand('insertText'). Deprecado pero implementado en
   *      todos los navegadores; el navegador modifica el DOM Y dispara
   *      beforeinput/input de verdad (isTrusted), que es lo que Lexical
   *      escucha. Se manda linea por linea porque el onBeforeInput de Lexical
   *      trata data === '\n' como INSERT_LINE_BREAK; un bloque entero con
   *      saltos cae en CONTROLLED_TEXT_INSERTION y puede quedar en una sola
   *      linea.
   *   2. Un evento 'paste' sintetico con un DataTransfer propio. El handler de
   *      pegado de Lexical lee event.clipboardData, y no mira isTrusted.
   *   3. InputEvent('beforeinput', {inputType:'insertText'}) a mano. Lexical
   *      tampoco mira isTrusted aqui, hace preventDefault e inserta el.
   *
   * Despues de cada intento se VERIFICA leyendo el innerText del compositor, y
   * si no cuadra se limpia antes del siguiente para no dejar texto duplicado.
   * Si fallan los tres, no se inventa nada: se copia al portapapeles y se te
   * dice que pegues con Ctrl+V.
   * ================================================================== */

  const COMPOSER_SELECTORS = [
    'div[role="dialog"] div[data-lexical-editor="true"][contenteditable="true"]',
    'div[role="dialog"] div[role="textbox"][contenteditable="true"]',
    'div[data-lexical-editor="true"][contenteditable="true"]',
    'div[role="textbox"][contenteditable="true"]',
    '[contenteditable="true"]',
  ];

  /** Cajas de texto que NO son el compositor del post. */
  const NOT_COMPOSER_RE = /buscar|search|rechercher|comentar|comentario|comment|commentaire|responder|reply|repondre|mensaje|message|nombre|title|titulo/i;

  /** Textos del boton que abre el compositor, en los 3 idiomas de los grupos. */
  const OPENER_RE = /(escribe algo|escribi algo|que estas pensando|qu[eé] est[aá]s pensando|crea (una )?publicaci|crear publicaci|write something|what's on your mind|whats on your mind|create (a )?post|quoi de neuf|[eé]crivez quelque chose|cr[eé]er une publication|commencer une publication)/i;

  /**
   * LA LINEA ROJA. Ningun clic de esta extension puede caer en un control que
   * envie el post. Se compara el nombre accesible completo, no un pedazo.
   */
  const PUBLISH_RE = /^(publicar|publicar ahora|publish|post|posting|publier|share|share now|compartir|partager|enviar|send|comentar|comment)$/i;

  function isVisible(node) {
    return Boolean(node && node.getClientRects && node.getClientRects().length > 0);
  }

  function accessibleName(node) {
    if (!node || !node.getAttribute) return '';
    const label =
      node.getAttribute('aria-label') ||
      node.getAttribute('aria-placeholder') ||
      node.getAttribute('data-text') ||
      node.getAttribute('placeholder') ||
      '';
    if (label) return String(label).trim();
    const text = String(node.textContent || '').trim();
    return text.length <= 80 ? text : text.slice(0, 80);
  }

  /**
   * El unico clic que hace la extension. Se niega si el control se llama
   * Publicar (o su traduccion): ese boton lo aprieta el dueno.
   */
  function safeClick(node) {
    if (!node) return false;
    const name = accessibleName(node);
    if (PUBLISH_RE.test(name)) {
      console.warn('[Rent & Go] no hago clic en "%s": ese boton lo aprietas tu.', name);
      return false;
    }
    try {
      node.click();
      return true;
    } catch (e) {
      return false;
    }
  }

  function composerScore(node) {
    let s = 0;
    if (node.closest('div[role="dialog"]')) s += 100;
    if (node.getAttribute('data-lexical-editor') === 'true') s += 20;
    if (node.getAttribute('role') === 'textbox') s += 10;
    const r = node.getBoundingClientRect();
    s += Math.min(20, Math.round((r.width * r.height) / 20000));
    return s;
  }

  function findComposer() {
    const seen = new Set();
    const found = [];
    for (const sel of COMPOSER_SELECTORS) {
      let nodes;
      try {
        nodes = document.querySelectorAll(sel);
      } catch (e) {
        continue;
      }
      for (const node of nodes) {
        if (seen.has(node)) continue;
        seen.add(node);
        if (!isVisible(node)) continue;
        if (NOT_COMPOSER_RE.test(accessibleName(node))) continue;
        found.push(node);
      }
    }
    if (!found.length) return null;
    found.sort((a, b) => composerScore(b) - composerScore(a));
    return found[0];
  }

  function findOpener() {
    // Facebook lo pinta como div, span o a segun la version; role="button" es
    // lo unico estable, y de paso no puede matchear un <button> de enviar.
    const nodes = document.querySelectorAll('[role="button"]');
    for (const node of nodes) {
      if (!isVisible(node)) continue;
      const name = accessibleName(node);
      if (!name || name.length > 80) continue;
      if (PUBLISH_RE.test(name)) continue;
      if (OPENER_RE.test(name)) return node;
    }
    return null;
  }

  async function waitFor(fn, timeoutMs) {
    const until = Date.now() + (timeoutMs || 6000);
    while (Date.now() < until) {
      const value = fn();
      if (value) return value;
      await sleep(150);
    }
    return null;
  }

  function selectAllIn(box) {
    const range = document.createRange();
    range.selectNodeContents(box);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    return sel;
  }

  function focusComposer(box) {
    try {
      box.focus({ preventScroll: false });
      if (document.activeElement !== box) {
        safeClick(box);
        box.focus();
      }
      const sel = selectAllIn(box);
      sel.collapseToEnd();
    } catch (e) {
      /* si falla, el verify de abajo lo cachea */
    }
    return document.activeElement === box || box.contains(document.activeElement);
  }

  function clearComposer(box) {
    try {
      focusComposer(box);
      selectAllIn(box);
      document.execCommand('delete');
    } catch (e) {
      /* no pasa nada: el intento siguiente lo verifica igual */
    }
  }

  /** Compara ignorando lineas en blanco: Lexical mezcla parrafos y saltos. */
  function normalizeText(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/[\u00A0\u200B\uFEFF]/g, ' ')
      .replace(/\r/g, '')
      .split('\n')
      .map((line) => line.replace(/[ \t]+/g, ' ').trim())
      .filter((line) => line.length > 0)
      .join('\n');
  }

  function composerText(box) {
    return normalizeText(box.innerText || box.textContent || '');
  }

  function insertWithExecCommand(box, text) {
    const lines = text.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (i > 0) document.execCommand('insertText', false, '\n');
      if (lines[i]) document.execCommand('insertText', false, lines[i]);
    }
  }

  function insertWithPaste(box, text) {
    const dt = new DataTransfer();
    dt.setData('text/plain', text);
    box.dispatchEvent(
      new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true, composed: true })
    );
  }

  function insertWithBeforeInput(box, text) {
    const lines = text.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (i > 0) fireBeforeInput(box, '\n');
      if (lines[i]) fireBeforeInput(box, lines[i]);
    }
  }

  function fireBeforeInput(box, data) {
    // Solo 'beforeinput': Lexical hace preventDefault e inserta el mismo. Un
    // 'input' encima le pediria reconciliar contra un DOM que el navegador no
    // toco, y ahi si se lia.
    box.dispatchEvent(
      new InputEvent('beforeinput', {
        inputType: 'insertText',
        data,
        bubbles: true,
        cancelable: true,
        composed: true,
      })
    );
  }

  const STRATEGIES = [
    { name: 'execCommand', run: insertWithExecCommand },
    { name: 'paste', run: insertWithPaste },
    { name: 'beforeinput', run: insertWithBeforeInput },
  ];

  /**
   * fillComposer(text) -> { ok, method } | { ok:false, code }
   * codes: no-composer | busy | focus | insert
   */
  async function fillComposer(text) {
    let box = findComposer();

    if (!box) {
      const opener = findOpener();
      if (opener) {
        safeClick(opener);
        box = await waitFor(findComposer, 7000);
      }
    }
    if (!box) return { ok: false, code: 'no-composer' };

    const want = normalizeText(text);
    const already = composerText(box);
    // Si ya escribiste algo tuyo, no te lo piso. Lo que si se limpia es un
    // intento anterior a medias (un pedazo de este mismo texto).
    if (already && !want.startsWith(already) && !want.includes(already)) {
      return { ok: false, code: 'busy' };
    }

    if (!focusComposer(box)) return { ok: false, code: 'focus' };

    for (const strategy of STRATEGIES) {
      if (composerText(box)) clearComposer(box);
      focusComposer(box);
      try {
        strategy.run(box, text);
      } catch (e) {
        continue;
      }
      await sleep(120);
      const got = composerText(box);
      if (got === want || got.includes(want)) return { ok: true, method: strategy.name };
    }

    if (composerText(box)) clearComposer(box);
    return { ok: false, code: 'insert' };
  }

  /* ================================================================== *
   * Portapapeles
   * ================================================================== */

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      /* Facebook puede bloquear la API con Permissions-Policy */
    }
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.top = '-1000px';
      ta.style.opacity = '0';
      document.documentElement.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      return ok;
    } catch (e) {
      return false;
    }
  }

  /* ================================================================== *
   * Panel
   * ================================================================== */

  function panelRoot() {
    return document.getElementById(PANEL_ID);
  }

  function removePanel() {
    const node = panelRoot();
    if (node) node.remove();
  }

  function setNote(text, kind) {
    state.note = text ? { text, kind: kind || 'info' } : null;
    render();
  }

  async function saveUi() {
    try {
      await chrome.storage.local.set({ [UI_KEY]: state.ui });
    } catch (e) {
      /* sin persistencia, pero el panel sigue */
    }
  }

  function render() {
    const today = state.plan ? state.plan.date : null;

    // Nada de UI si no hay plan o si cerraste el panel por hoy.
    if (!state.plan || (state.ui.dismissedDate && state.ui.dismissedDate === today)) {
      removePanel();
      return;
    }

    // Estamos en un grupo, pero su direccion no cuadra con ninguno de los 18.
    // En vez de no mostrar nada, preguntamos cual es.
    if (!state.group) {
      let caja = panelRoot();
      if (!caja) {
        caja = el('aside', 'rgpc-panel');
        caja.id = PANEL_ID;
        caja.setAttribute('role', 'complementary');
        caja.setAttribute('aria-label', 'Asistente de grupos Rent & Go');
        caja.setAttribute('dir', 'ltr');
        document.documentElement.appendChild(caja);
      }
      caja.textContent = '';
      caja.classList.remove('rgpc-collapsed');
      const head = el('header', 'rgpc-head');
      head.appendChild(el('span', 'rgpc-code', '?'));
      head.appendChild(el('span', 'rgpc-name', 'Grupo sin identificar'));
      const cerrar = button('rgpc-icon', '\u00d7', async () => {
        state.ui.dismissedDate = today;
        await saveUi();
        removePanel();
      });
      cerrar.title = 'Ocultar por hoy';
      head.appendChild(cerrar);
      caja.appendChild(head);
      caja.appendChild(buildUnknown());
      return;
    }

    let root = panelRoot();
    if (!root) {
      root = el('aside', 'rgpc-panel');
      root.id = PANEL_ID;
      root.setAttribute('role', 'complementary');
      root.setAttribute('aria-label', 'Asistente de grupos Rent & Go');
      root.setAttribute('dir', 'ltr');
      document.documentElement.appendChild(root);
    }
    root.textContent = '';
    root.classList.toggle('rgpc-collapsed', Boolean(state.ui.collapsed));

    root.appendChild(buildHead());
    if (!state.ui.collapsed) root.appendChild(buildBody());
  }

  function buildHead() {
    const head = el('header', 'rgpc-head');
    head.appendChild(el('span', 'rgpc-code', state.group.code));
    head.appendChild(el('span', 'rgpc-name', state.group.name));

    const toggle = button('rgpc-icon', state.ui.collapsed ? '+' : '−', async () => {
      state.ui.collapsed = !state.ui.collapsed;
      await saveUi();
      render();
    });
    toggle.title = state.ui.collapsed ? 'Abrir el panel' : 'Contraer el panel';
    toggle.setAttribute('aria-expanded', state.ui.collapsed ? 'false' : 'true');
    head.appendChild(toggle);

    const close = button('rgpc-icon', '×', async () => {
      state.ui.dismissedDate = state.plan.date;
      await saveUi();
      removePanel();
    });
    close.title = 'Cerrar por hoy (vuelve manana)';
    head.appendChild(close);
    return head;
  }

  /**
   * La linea de la campana: que hora tiene ESTE grupo y si es el turno de ahora.
   * Informativa, nunca bloqueante: los botones de abajo funcionan igual. El dueno
   * decide cuando publica; el panel solo evita que se le olvide el orden.
   */
  function buildSlotLine(body) {
    const s = state.slot;
    const next = state.nextSlot;
    if (!s) return;

    if (s.isNext) {
      const line = el('p', 'rgpc-note rgpc-note-action',
        'Slot ' + s.slot + ' de la campana, ' + s.slotTime + '. ' +
        (s.isPast ? 'Su hora ya paso: es el que toca, y vas tarde.' : 'Es el que toca ahora.'));
      line.setAttribute('role', 'status');
      body.appendChild(line);
      return;
    }

    if (s.status === 'posted' || s.status === 'skipped') return; // buildDone/buildNothing ya lo dicen

    // Se adelanto (o se retraso) respecto al orden de la campana. Se dice y punto.
    const bits = ['Este grupo era el slot de las ' + s.slotTime + '.'];
    if (next) {
      bits.push(
        next.slotHour < s.slotHour
          ? 'El que toca es el de las ' + next.slotTime + ' (' + next.groupCode + ' — ' + next.groupName + '): te adelantaste.'
          : 'El que toca ahora es el de las ' + next.slotTime + ' (' + next.groupCode + ' — ' + next.groupName + ').'
      );
    } else if (s.isPast) {
      bits.push('Su hora ya paso.');
    }
    bits.push('Puedes publicarlo igual: esto es un recordatorio, no un candado.');
    body.appendChild(el('p', 'rgpc-warn', bits.join(' ')));
  }

  function buildBody() {
    const body = el('div', 'rgpc-body');

    if (state.stale) {
      body.appendChild(el('p', 'rgpc-warn', 'Plan sin actualizar: no pude hablar con el sitio. Puede estar viejo.'));
    }

    const a = state.assignment;
    if (a && !a.alreadyPosted) buildSlotLine(body);

    if (a && !a.alreadyPosted) buildWork(body, a);
    else if (a && a.alreadyPosted) buildDone(body, a);
    else if (state.group.cooldown) buildCooldown(body);
    else buildNothing(body);

    if (state.note) {
      const note = el('p', 'rgpc-note rgpc-note-' + state.note.kind, state.note.text);
      note.setAttribute('role', 'status');
      note.setAttribute('aria-live', 'polite');
      body.appendChild(note);
    }
    return body;
  }

  /* ---------------- estado 1: hay trabajo ---------------- */

  function buildWork(body, a) {
    const meta = el('div', 'rgpc-meta');
    meta.appendChild(el('strong', 'rgpc-prop', a.propertyShortName || a.propertyName));
    meta.appendChild(el('span', 'rgpc-price', a.priceDisplay));
    meta.appendChild(el('span', 'rgpc-lang', LANG_NAME[a.lang] || a.lang));
    body.appendChild(meta);

    const pre = el('pre', 'rgpc-pre', a.postText);
    pre.setAttribute('aria-label', 'Vista previa del post');
    body.appendChild(pre);

    const row1 = el('div', 'rgpc-row');
    row1.appendChild(button('rgpc-primary', 'Llenar el post', () => onFill(a)));
    row1.appendChild(button('rgpc-ghost', 'Copiar el texto', () => onCopy(a.postText, 'Texto del post copiado.')));
    body.appendChild(row1);

    if (a.imageUrl) {
      const row2 = el('div', 'rgpc-row');
      row2.appendChild(button('rgpc-ghost', 'Bajar la foto', (ev) => onDownload(a, ev)));
      if (state.lastDownloadId !== null) {
        row2.appendChild(
          button('rgpc-link', 'Ver en la carpeta', () => send('RGPC_SHOW_DOWNLOAD', { id: state.lastDownloadId }))
        );
      }
      body.appendChild(row2);
      body.appendChild(
        el('p', 'rgpc-hint', 'La foto no se adjunta sola: bajala y arrastrala al compositor (o dale a Foto/video y buscala).')
      );
    }

    const row3 = el('div', 'rgpc-row');
    row3.appendChild(
      button('rgpc-gold', 'Copiar comentario', () =>
        onCopy(a.commentText, 'Comentario copiado. Va en el PRIMER comentario, no en el post.')
      )
    );
    body.appendChild(row3);
    body.appendChild(el('p', 'rgpc-ref', 'Ref ' + a.ref));

    const row4 = el('div', 'rgpc-row rgpc-row-end');
    row4.appendChild(button('rgpc-done', 'Ya lo publique', () => onMark(a, false)));
    row4.appendChild(button('rgpc-link', 'Saltar hoy', () => onMark(a, true)));
    body.appendChild(row4);
  }

  /* ---------------- estado 2: ya publicaste hoy ---------------- */

  function buildDone(body, a) {
    const s = state.slot;
    body.appendChild(
      el('p', 'rgpc-ok', 'Ya publicaste aqui hoy: ' + (a.propertyShortName || a.propertyName) +
        (s ? ' (slot de las ' + s.slotTime + ').' : '.'))
    );
    if (state.nextSlot) {
      body.appendChild(
        el('p', 'rgpc-hint', 'El siguiente de la campana es a las ' + state.nextSlot.slotTime +
          ': ' + state.nextSlot.groupCode + ' — ' + state.nextSlot.groupName + '.')
      );
    }
    body.appendChild(
      el(
        'p',
        'rgpc-hint',
        'Si todavia no pusiste el comentario, espera unos minutos desde que publicaste antes de pegarlo. ' +
          'Un comentario con link de wa.me puesto al instante Facebook lo esconde (visto en produccion).'
      )
    );
    const row = el('div', 'rgpc-row');
    row.appendChild(
      button('rgpc-gold', 'Copiar comentario', () => onCopy(a.commentText, 'Comentario copiado.'))
    );
    body.appendChild(row);
    body.appendChild(el('p', 'rgpc-ref', 'Ref ' + a.ref));
    body.appendChild(el('p', 'rgpc-hint', 'Este grupo vuelve a estar libre en 7 dias.'));
  }

  /* ---------------- estado 3: en cooldown ---------------- */

  function buildCooldown(body) {
    const g = state.group;
    const what = g.lastPropertyName ? g.lastPropertyName : 'un listado';
    body.appendChild(
      el(
        'p',
        'rgpc-warn',
        'Este grupo recibio ' + what + ' el ' + humanDate(g.lastPostedDate) + '. Hoy NO toca publicar aqui.'
      )
    );
    body.appendChild(
      el(
        'p',
        'rgpc-hint',
        'Se libera el ' +
          humanDate(g.freeOn) +
          ' (faltan ' +
          g.daysUntilFree +
          (g.daysUntilFree === 1 ? ' dia' : ' dias') +
          '). Mientras tanto: comenta y aporta, que eso no gasta la semana.'
      )
    );
    todayList(body);
  }

  /* ---------------- estado 4: libre pero sin asignacion ---------------- */

  function buildNothing(body) {
    const s = state.slot;
    body.appendChild(el('p', 'rgpc-warn', 'Hoy no le toca a este grupo.'));
    if (state.group.skippedToday) {
      body.appendChild(el('p', 'rgpc-hint',
        (s ? 'Era el slot de las ' + s.slotTime + ' y lo saltaste. ' : 'Lo saltaste hoy. ') +
        'Manana vuelve a la cola: saltar no gasta su semana.'));
    } else if (state.plan.reason) {
      body.appendChild(el('p', 'rgpc-hint', state.plan.reason));
    }
    todayList(body);
  }

  /**
   * Los grupos que si tocan hoy, con enlace para abrirlos. En modo campana va con
   * la hora de cada slot y marcado el que toca ahora, que es lo que hace que el
   * dueno pueda saltar de un grupo al siguiente sin abrir el panel del sitio.
   */
  function todayList(body) {
    const slots = Array.isArray(state.plan.slots) ? state.plan.slots : null;
    const rows = slots
      ? slots
          .filter((s) => s.status === 'pending' || s.status === 'missed')
          .map((s) => ({
            time: s.slotTime,
            code: s.groupCode,
            name: s.groupName,
            url: s.groupUrl,
            tail: s.isNext ? (s.isPast ? 'TOCA YA' : 'TOCA AHORA') : null,
          }))
      : (state.plan.assignments || [])
          .filter((a) => !a.alreadyPosted)
          .map((a) => ({
            time: null,
            code: a.groupCode,
            name: a.groupName,
            url: a.groupUrl,
            tail: a.propertyShortName || a.propertyName,
          }));

    if (!rows.length) return;
    const camp = state.plan.campaign || null;
    body.appendChild(el('p', 'rgpc-hint', slots && camp
      ? 'Hoy toca ' + (camp.propertyShortName || camp.propertyName || 'la campana') + ' en:'
      : 'Hoy toca:'));

    const ul = el('ul', 'rgpc-list');
    for (const r of rows) {
      const li = el('li', null);
      const link = el('a', 'rgpc-a', (r.time ? r.time + ' · ' : '') + r.code + ' · ' + r.name);
      if (typeof r.url === 'string' && r.url.startsWith('https://www.facebook.com/groups/')) {
        link.href = r.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
      }
      li.appendChild(link);
      if (r.tail) li.appendChild(el('span', 'rgpc-dim', ' — ' + r.tail));
      ul.appendChild(li);
    }
    body.appendChild(ul);
  }

  /* ================================================================== *
   * Acciones
   * ================================================================== */

  async function onFill(a) {
    if (state.busy) return;
    state.busy = true;
    setNote('Buscando el compositor...', 'info');
    try {
      const res = await fillComposer(a.postText);
      if (res.ok) {
        setNote('Listo. REVISA EL TEXTO Y DALE A PUBLICAR TU MISMO. La extension no lo hace por ti.', 'action');
        return;
      }
      if (res.code === 'busy') {
        setNote('El compositor ya tiene texto tuyo. Borralo y dale a Llenar otra vez.', 'warn');
        return;
      }
      if (res.code === 'no-composer') {
        const copied = await copyText(a.postText);
        setNote(
          copied
            ? 'No encontre el compositor (Facebook cambio el diseno). Te copie el texto: abrelo y pega con Ctrl+V.'
            : 'No encontre el compositor y tampoco pude copiar. Usa "Copiar el texto" y pega a mano.',
          'warn'
        );
        return;
      }
      const copied = await copyText(a.postText);
      setNote(
        copied
          ? 'No pude escribir dentro del compositor. Te copie el texto: haz clic dentro y pega con Ctrl+V.'
          : 'No pude escribir ni copiar. Usa "Copiar el texto" y pega a mano.',
        'warn'
      );
    } finally {
      state.busy = false;
    }
  }

  async function onCopy(text, okMessage) {
    const ok = await copyText(text);
    setNote(ok ? okMessage : 'No pude copiar. Selecciona el texto de la vista previa y copialo a mano.', ok ? 'ok' : 'warn');
  }

  async function onDownload(a) {
    setNote('Bajando la foto...', 'info');
    const res = await send('RGPC_DOWNLOAD_IMAGE', { url: a.imageUrl, filename: a.imageFilename });
    if (res && res.ok) {
      state.lastDownloadId = res.id;
      setNote('Foto en tu carpeta de Descargas (rentandgo/). Arrastrala al compositor.', 'ok');
      return;
    }
    setNote((res && res.error) || 'No pude bajar la foto.', 'warn');
  }

  /**
   * Registra el post en el historial del sitio. Lo aprieta el dueno DESPUES de
   * haber publicado con su propia mano: aqui no se publica nada, solo se anota
   * para que arranque el cooldown de 7 dias y el ref sirva de atribucion.
   */
  async function onMark(a, skipped) {
    if (state.busy) return;
    state.busy = true;
    setNote(skipped ? 'Saltando...' : 'Registrando...', 'info');
    try {
      const res = await send('RGPC_MARK', {
        groupCode: a.groupCode,
        propertySlug: a.propertySlug,
        ref: a.ref,
        // Que quede grabada la foto de este slot, no la que el servidor
        // recalcularia: en campana los 5 slots comparten propiedad.
        imagePath: a.imagePath || '',
        imageUrl: a.imageUrl || '',
        skipped: Boolean(skipped),
      });
      if (!res || !res.ok) {
        setNote((res && res.error) || 'No pude registrarlo. Revisa el token en el popup.', 'warn');
        return;
      }
      if (res.plan) applyPlan({ ok: true, plan: res.plan, stale: false });
      setNote(
        skipped
          ? 'Saltado. El grupo no gasta su semana.'
          : 'Registrado. Ahora espera unos minutos antes de pegar el comentario con el link de WhatsApp: ' +
              'Facebook esconde los comentarios con wa.me puestos al instante.',
        'ok'
      );
    } finally {
      state.busy = false;
    }
  }

  /* ================================================================== *
   * Arranque y navegacion (Facebook es una SPA: la URL cambia sin recargar)
   * ================================================================== */

  function applyPlan(res) {
    if (!res || !res.ok || !res.plan) {
      state.plan = null;
      state.group = null;
      state.assignment = null;
      state.slot = null;
      state.nextSlot = null;
      return;
    }
    state.plan = res.plan;
    state.stale = Boolean(res.stale);
    state.group = findGroup(res.plan, state.groupKey);

    // Sin coincidencia el panel no aparece, y hasta ahora no decia por que.
    // Facebook a veces sirve el ID numerico donde la config guarda el nombre
    // (G04, G06 y G07 usan nombre), asi que la clave real puede no ser la
    // esperada. Dejarlo en consola convierte una falla muda en una pista.
    if (!state.group && res && res.plan) {
      console.info(
        '[Rent & Go] Este grupo no esta en tu lista de 18. Clave detectada: "%s". ' +
        'Si SI deberia estar, pasa esa clave para agregarla a group-assist-config.json.',
        state.groupKey
      );
    }
    state.assignment = state.group ? findAssignment(res.plan, state.group.code) : null;
    // isNext/isPast los re-sella background.js con el reloj de ahora al servir el
    // plan, cacheado o no, asi que aqui no hace falta ningun temporizador.
    state.slot = state.group ? findSlot(res.plan, state.group.code) : null;
    state.nextSlot = findNextSlot(res.plan);
  }

  async function saveAlias(key, code) {
    state.aliases = { ...state.aliases, [key]: code };
    try {
      await chrome.storage.local.set({ [ALIAS_KEY]: state.aliases });
    } catch (e) {
      /* si no se puede guardar, al menos vale para esta pestana */
    }
  }

  /**
   * El panel que sale cuando la URL no cuadra con ninguno de los 18. Antes esto
   * era silencio total: el usuario abria el grupo, no pasaba nada, y la pista
   * estaba en la consola. Una lista y un boton lo resuelven de una vez.
   */
  function buildUnknown() {
    const box = el('div', 'rgpc-body');
    box.appendChild(el('p', 'rgpc-note',
      'No reconozco este grupo por su direccion. Si es uno de tu lista, elegilo una vez y lo recuerdo.'));

    const select = el('select', 'rgpc-select');
    const vacia = el('option', null, 'Elegi el grupo...');
    vacia.value = '';
    select.appendChild(vacia);
    for (const g of state.plan.groups) {
      const opt = el('option', null, g.code + ' - ' + g.name);
      opt.value = g.code;
      select.appendChild(opt);
    }
    box.appendChild(select);

    const guardar = button('rgpc-primary', 'Recordar este grupo', async () => {
      if (!select.value) return;
      await saveAlias(state.groupKey, select.value);
      state.group = findGroup(state.plan, state.groupKey);
      state.assignment = state.group ? findAssignment(state.plan, state.group.code) : null;
      state.slot = state.group ? findSlot(state.plan, state.group.code) : null;
      render();
    });
    box.appendChild(guardar);

    const clave = el('p', 'rgpc-note', 'Clave detectada: ' + state.groupKey);
    box.appendChild(clave);
    return box;
  }

  async function refresh(force) {
    state.groupKey = groupKeyFromUrl(location.href);
    if (!state.groupKey) {
      state.group = null;
      removePanel();
      return;
    }
    const res = await send('RGPC_GET_PLAN', { force: Boolean(force) });
    applyPlan(res);
    render();
  }

  async function init() {
    try {
      const stored = await chrome.storage.local.get([UI_KEY, ALIAS_KEY]);
      if (stored && stored[UI_KEY] && typeof stored[UI_KEY] === 'object') {
        state.ui.collapsed = Boolean(stored[UI_KEY].collapsed);
        state.ui.dismissedDate = stored[UI_KEY].dismissedDate || null;
      }
      if (stored && stored[ALIAS_KEY] && typeof stored[ALIAS_KEY] === 'object') {
        state.aliases = stored[ALIAS_KEY];
      }
    } catch (e) {
      /* valores por defecto */
    }

    await refresh(false);

    // La URL cambia sin recargar; un compare de strings cada segundo es mas
    // barato y mas fiable que parchear history.pushState desde otro mundo.
    let lastHref = location.href;
    setInterval(() => {
      if (location.href !== lastHref) {
        lastHref = location.href;
        state.note = null;
        state.lastDownloadId = null;
        refresh(false);
        return;
      }
      // React a veces se lleva por delante nodos que no son suyos.
      const root = panelRoot();
      if (state.group && !root) render();
      else if (root && !document.documentElement.contains(root)) render();
    }, 1000);

    // Si pegas el token (o cambias la URL base) con la pestana abierta, el
    // panel aparece solo.
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== 'local') return;
      if (changes.token || changes.baseUrl) refresh(true);
      else if (changes.planCache) refresh(false);
    });
  }

  init();
})();
