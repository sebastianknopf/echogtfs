'use strict';

/* ==========================================================================
   STATE
   Single source of truth. Token is kept in sessionStorage so the user
   stays logged in across same-tab page reloads, but not across new tabs
   or browser sessions (more secure than localStorage).
   No direct DOM access here.
========================================================================== */
const state = (() => {
  const TOKEN_KEY = 'echogtfs:token';

  let _token = sessionStorage.getItem(TOKEN_KEY) ?? null;
  let _user  = null;

  return {
    get token()           { return _token; },
    get user()            { return _user;  },
    get isAuthenticated() { return _token !== null; },

    setAuth(token, user) {
      _token = token;
      _user  = user;
      sessionStorage.setItem(TOKEN_KEY, token);
    },

    clearAuth() {
      _token = null;
      _user  = null;
      sessionStorage.removeItem(TOKEN_KEY);
    },
  };
})();


/* ==========================================================================
   API
   All network calls centralised here. The Authorization header is attached
   automatically when a token is present.
   A 401 on a protected call (existing token) auto-clears state.
========================================================================== */
const api = (() => {
  const BASE = '/api';

  function translateError(msg, status) {
    const map = {
      'Incorrect username or password': 'Benutzername oder Passwort ist falsch.',
      'User not found': 'Benutzer nicht gefunden.',
      'Inactive user': 'Dieser Benutzer ist deaktiviert.',
      'Not enough permissions': 'Keine ausreichenden Berechtigungen.',
      'Could not validate credentials': 'Anmeldedaten konnten nicht verifiziert werden.',
      'Username or email already taken': 'Benutzername oder E-Mail bereits vergeben.',
      'Cannot remove your own admin privileges': 'Eigene Administrator-Rechte können nicht entzogen werden.',
      'Cannot delete yourself': 'Der eigene Account kann nicht gelöscht werden.',
    };
    if (map[msg]) return map[msg];
    if (status === 401) return 'Benutzername oder Passwort ist falsch.';
    if (status === 403) return 'Keine ausreichenden Berechtigungen.';
    if (status === 404) return 'Ressource nicht gefunden.';
    if (status === 429) return 'Zu viele Versuche. Bitte warten Sie einen Moment.';
    if (status >= 500) return 'Serverfehler. Bitte versuchen Sie es später erneut.';
    return msg;
  }

  /** Generic fetch wrapper. Set skipAuthRedirect=true for the login call. */
  async function request(path, options = {}, skipAuthRedirect = false) {
    const headers = { ...options.headers };
    if (state.token) {
      headers['Authorization'] = `Bearer ${state.token}`;
    }

    let res;
    try {
      res = await fetch(BASE + path, { ...options, headers });
    } catch {
      throw new Error('Netzwerkfehler – Server nicht erreichbar.');
    }

    if (res.status === 204) return null;

    const data = await res.json().catch(() => null);

    if (res.status === 401 && !skipAuthRedirect) {
      // Token expired or invalid while already authenticated → force logout
      state.clearAuth();
      ui.showView('login');
      ui.snackbar('Sitzung abgelaufen. Bitte erneut anmelden.', 'error');
      throw new Error('SESSION_EXPIRED');
    }

    if (!res.ok) {
      const detail = data?.detail;
      const raw = Array.isArray(detail)
        ? detail.map(e => e.msg ?? String(e)).join(', ')
        : (detail ?? `HTTP ${res.status}`);
      throw new Error(translateError(raw, res.status));
    }

    return data;
  }

  return {
    health() {
      return request('/health');
    },

    /** OAuth2 password flow – never auto-redirects on 401 (wrong credentials). */
    login(username, password) {
      return request(
        '/auth/token',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ username, password }),
        },
        true   // ← skipAuthRedirect: wrong password must not trigger logout flow
      );
    },

    getMe() {
      return request('/users/me');
    },

    getUsers() {
      return request('/users/');
    },

    createUser(data) {
      return request('/users/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },

    updateUser(id, data) {
      return request(`/users/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },

    deleteUser(id) {
      return request(`/users/${id}`, { method: 'DELETE' });
    },

    getSettings() {
      return request('/settings/', {}, true);
    },

    saveSettings(data) {
      return request('/settings/', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },

    getGtfsStatus() {
      return request('/gtfs/status');
    },

    saveGtfsFeedUrl(feed_url) {
      return request('/gtfs/feed-url', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feed_url }),
      });
    },

    triggerGtfsImport() {
      return request('/gtfs/import', { method: 'POST' });
    },
  };
})();


/* ==========================================================================
   THEME
   Derives and applies a full MD3 colour token set from primary + secondary.
========================================================================== */
const theme = (() => {
  function _parseHex(hex) {
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
    return { r: parseInt(hex.slice(0,2),16), g: parseInt(hex.slice(2,4),16), b: parseInt(hex.slice(4,6),16) };
  }
  function _toHex({r,g,b}) {
    return '#' + [r,g,b].map(v => Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0')).join('');
  }
  function _darken({r,g,b}, a)  { return { r:r*(1-a), g:g*(1-a), b:b*(1-a) }; }
  function _lighten({r,g,b}, a) { return { r:r+(255-r)*a, g:g+(255-g)*a, b:b+(255-b)*a }; }
  function _lum({r,g,b}) {
    const s = [r,g,b].map(c => { c/=255; return c<=0.03928?c/12.92:Math.pow((c+0.055)/1.055,2.4); });
    return 0.2126*s[0] + 0.7152*s[1] + 0.0722*s[2];
  }
  // Switch to white text earlier by increasing threshold
  function _onColor(col) { return _lum(col) > 0.35 ? '#1a1a1a' : '#ffffff'; }

  function apply({ color_primary, color_secondary, app_title }) {
    const p  = _parseHex(color_primary);
    const pD = _darken(p, 0.15);
    const pL = _lighten(p, 0.35);
    const pC = _lighten(p, 0.72);
    const s  = _parseHex(color_secondary);
    const sD = _darken(s, 0.15);
    const sC = _lighten(s, 0.55);
    const root = document.documentElement;
    root.style.setProperty('--md-primary',                    _toHex(p));
    root.style.setProperty('--md-primary-dark',               _toHex(pD));
    root.style.setProperty('--md-primary-light',              _toHex(pL));
    root.style.setProperty('--md-on-primary',                 _onColor(p));
    root.style.setProperty('--md-primary-hover-bg',           `rgba(${Math.round(p.r)},${Math.round(p.g)},${Math.round(p.b)},.08)`);
    root.style.setProperty('--md-primary-container',          _toHex(pC));
    root.style.setProperty('--md-primary-container-border',   `rgba(${Math.round(p.r)},${Math.round(p.g)},${Math.round(p.b)},.3)`);
    root.style.setProperty('--md-secondary',                  _toHex(s));
    root.style.setProperty('--md-secondary-dark',             _toHex(sD));
    root.style.setProperty('--md-on-secondary',               _onColor(s));
    root.style.setProperty('--md-secondary-container',        _toHex(sC));
    root.style.setProperty('--md-on-secondary-container',     _onColor(sC));
    root.style.setProperty('--md-secondary-container-border', `rgba(${Math.round(s.r)},${Math.round(s.g)},${Math.round(s.b)},.4)`);

    if (typeof app_title === 'string' && app_title.trim()) {
      const t = app_title.trim();
      document.title = t;
      const loginTitle  = document.getElementById('app-title-login');
      const topbarTitle = document.getElementById('app-title-topbar');
      if (loginTitle)  loginTitle.textContent  = t;
      if (topbarTitle) topbarTitle.textContent = t;
    }
  }

  return { apply };
})();


/* ==========================================================================
   UI
   Pure DOM manipulation – no business logic, no API calls.
   Uses an element cache to avoid repeated getElementById lookups.
========================================================================== */
const ui = (() => {
  const _cache = {};
  const el = id => (_cache[id] ??= document.getElementById(id));

  // -- Views ---------------------------------------------------------------
  function showView(name) {
    document.querySelectorAll('.view').forEach(v => {
      v.classList.toggle('is-active', v.dataset.view === name);
    });
  }

  // -- Loading screen ------------------------------------------------------
  function setLoading(visible) {
    el('loading-screen').classList.toggle('is-hidden', !visible);
  }

  // -- Snackbar ------------------------------------------------------------
  let _snackTimer = null;
  function snackbar(message, type = 'default') {
    const node = el('snackbar');
    node.textContent = message;
    node.className = 'snackbar is-visible';
    if (type !== 'default') node.classList.add(`is-${type}`);
    clearTimeout(_snackTimer);
    _snackTimer = setTimeout(() => {
      node.classList.remove('is-visible');
    }, type === 'error' ? 5000 : 3000);
  }

  // -- API status badge ----------------------------------------------------
  function setApiStatus(_ok) { /* badge removed */ }

  // -- Login form state ----------------------------------------------------
  function setLoginError(message) {
    const errEl = el('login-error');
    if (message) {
      errEl.textContent = message;
      errEl.classList.add('is-visible');
      el('field-username').classList.add('is-error');
      el('field-password').classList.add('is-error');
    } else {
      errEl.classList.remove('is-visible');
      el('field-username').classList.remove('is-error');
      el('field-password').classList.remove('is-error');
    }
  }

  function setLoginBusy(busy) {
    const btn = el('login-btn');
    btn.disabled = busy;
    el('login-btn-spinner').hidden = !busy;
    el('login-btn-label').textContent = busy ? 'Anmelden \u2026' : 'Anmelden';
  }

  // -- Render authenticated user -------------------------------------------
  function renderUser(user) {
    // Avatar initial
    el('user-avatar').textContent     = user.username.charAt(0).toUpperCase();
    el('topbar-username').textContent = user.username;

    // Profile card
    el('user-name').textContent  = user.username;
    el('user-email').textContent = user.email;

    // Status chips
    const chipsEl = el('user-chips');
    chipsEl.innerHTML = '';
    if (user.is_active) {
      const c = document.createElement('span');
      c.className = 'md-chip md-chip--primary';
      c.textContent = 'Aktiv';
      chipsEl.appendChild(c);
    }
    if (user.is_superuser) {
      const c = document.createElement('span');
      c.className = 'md-chip md-chip--secondary';
      c.textContent = 'Administrator';
      chipsEl.appendChild(c);
    }

    // Detail cells
    el('detail-username').textContent = user.username;
    el('detail-email').textContent    = user.email;
    el('detail-created').textContent  = new Date(user.created_at).toLocaleDateString('de-DE', {
      year: 'numeric', month: 'long', day: 'numeric',
    });
    el('detail-role').textContent = user.is_superuser ? 'Administrator' : 'Standard';

    // Show/hide admin-only sidebar items
    document.querySelectorAll('.nav-item[data-admin-only]').forEach(item => {
      item.hidden = !user.is_superuser;
    });
  }

  function clearUser() {
    ['user-avatar', 'topbar-username', 'user-name', 'user-email',
     'user-chips', 'detail-username', 'detail-email', 'detail-created', 'detail-role']
      .forEach(id => { el(id).textContent = ''; });
    // Restore all admin-only elements so the next login re-evaluates them
    document.querySelectorAll('[data-admin-only]').forEach(item => { item.hidden = false; });
  }

  // -- Panel navigation ------------------------------------------------------
  function setPanel(name) {
    document.querySelectorAll('.panel').forEach(p => {
      p.classList.toggle('is-active', p.dataset.panel === name);
    });
    document.querySelectorAll('.nav-item[data-panel]').forEach(btn => {
      const active = btn.dataset.panel === name;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-current', active ? 'page' : 'false');
    });
  }

  // -- XSS-safe string escaping -----------------------------------------------
  function _esc(str) {
    return String(str).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  }

  // -- Accounts list ----------------------------------------------------------
  function renderAccountsList(users) {
    const container = el('accounts-content');
    if (!users.length) {
      container.innerHTML = '<div class="panel__placeholder">Keine Accounts vorhanden.</div>';
      return;
    }
    const table = document.createElement('table');
    table.className = 'user-table';
    table.innerHTML = `
      <thead><tr>
        <th>Benutzername</th>
        <th>E-Mail</th>
        <th>Rolle</th>
        <th>Status</th>
        <th></th>
      </tr></thead>
      <tbody></tbody>`;
    const tbody = table.querySelector('tbody');
    users.forEach(user => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${_esc(user.username)}</td>
        <td>${_esc(user.email)}</td>
        <td>${user.is_superuser
          ? '<span class="md-chip md-chip--secondary">Administrator</span>'
          : '<span class="md-chip">Standard</span>'}</td>
        <td>${user.is_active
          ? '<span class="md-chip md-chip--primary">Aktiv</span>'
          : '<span class="md-chip">Inaktiv</span>'}</td>
        <td><div class="user-table__actions">
          <button class="icon-btn" data-action="edit" data-id="${user.id}"
            title="Bearbeiten" aria-label="Account ${_esc(user.username)} bearbeiten" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
          </button>
          <button class="icon-btn icon-btn--danger" data-action="delete" data-id="${user.id}"
            title="Löschen" aria-label="Account ${_esc(user.username)} löschen" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          </button>
        </div></td>`;
      tbody.appendChild(tr);
    });
    container.innerHTML = '';
    container.appendChild(table);
    initRipples(container);
  }

  // -- Account modal ----------------------------------------------------------
  function openAccountModal({ title, username = '', email = '', isActive = true, isSuperuser = false, editMode = false } = {}) {
    el('modal-title').textContent         = title;
    el('modal-username').value            = username;
    el('modal-username').readOnly         = editMode;
    el('modal-email').value               = email;
    el('modal-password').value            = '';
    el('modal-is-active').checked         = isActive;
    el('modal-is-superuser').checked      = isSuperuser;
    el('modal-password-hint').textContent = editMode ? 'Leer lassen, um das Passwort nicht zu ändern.' : '';
    el('modal-error').textContent         = '';
    el('modal-error').classList.remove('is-visible');
    el('account-modal').hidden = false;
    (editMode ? el('modal-email') : el('modal-username')).focus();
  }

  function closeAccountModal() { el('account-modal').hidden = true; }

  function setModalBusy(busy) {
    el('modal-submit-btn').disabled        = busy;
    el('modal-submit-spinner').hidden      = !busy;
    el('modal-submit-label').textContent   = busy ? 'Wird gespeichert ...' : 'Speichern';
  }

  function setModalError(msg) {
    const e = el('modal-error');
    e.textContent = msg ?? '';
    e.classList.toggle('is-visible', !!msg);
  }

  // -- Confirm dialog (returns Promise<boolean>) ------------------------------
  function openConfirmModal(message) {
    return new Promise(resolve => {
      el('confirm-message').textContent = message;
      el('confirm-modal').hidden = false;
      const ok     = el('confirm-ok-btn');
      const cancel = el('confirm-cancel-btn');
      const done = result => {
        el('confirm-modal').hidden = true;
        ok.removeEventListener('click', onOk);
        cancel.removeEventListener('click', onCancel);
        resolve(result);
      };
      const onOk     = () => done(true);
      const onCancel = () => done(false);
      ok.addEventListener('click', onOk,     { once: true });
      cancel.addEventListener('click', onCancel, { once: true });
      ok.focus();
    });
  }

  return {
    showView, setLoading, snackbar, setApiStatus,
    setLoginError, setLoginBusy,
    renderUser, clearUser,
    setPanel, renderAccountsList,
    openAccountModal, closeAccountModal, setModalBusy, setModalError,
    openConfirmModal,
  };
})();


/* ==========================================================================
   SETTINGS PANEL
   Color pickers with live preview and save/reset.
========================================================================== */
const settingsPanel = (() => {
  const DEFAULTS = { color_primary: '#008c99', color_secondary: '#99cc04' };
  let _current = { ...DEFAULTS };

  function _el(id) { return document.getElementById(id); }

  function _syncSwatchFromHex(prefix) {
    const hex = _el(`settings-color-${prefix}-hex`).value.trim();
    if (/^#[0-9a-fA-F]{6}$/.test(hex)) {
      _el(`settings-color-${prefix}`).value = hex;
    }
  }

  function _syncHexFromSwatch(prefix) {
    _el(`settings-color-${prefix}-hex`).value = _el(`settings-color-${prefix}`).value;
  }

  function load(savedSettings) {
    _current = { ...savedSettings };
    _el('settings-app-title').value             = _current.app_title ?? '';
    _el('settings-color-primary').value         = _current.color_primary;
    _el('settings-color-primary-hex').value     = _current.color_primary;
    _el('settings-color-secondary').value       = _current.color_secondary;
    _el('settings-color-secondary-hex').value   = _current.color_secondary;
  }

  function init() {
    // Swatch <-> hex sync
    ['primary', 'secondary'].forEach(key => {
      _el(`settings-color-${key}`).addEventListener('input', () => {
        _syncHexFromSwatch(key);
      });
      _el(`settings-color-${key}-hex`).addEventListener('input', () => {
        _syncSwatchFromHex(key);
      });
    });
  }

  async function handleSave(e) {
    e.preventDefault();
    const appTitle = _el('settings-app-title').value.trim();
    const p = _el('settings-color-primary').value;
    const s = _el('settings-color-secondary').value;
    const errEl = _el('settings-error');
    errEl.classList.remove('is-visible');

    if (!appTitle) {
      errEl.textContent = 'Bitte einen App-Titel eingeben.';
      errEl.classList.add('is-visible');
      return;
    }
    if (!/^#[0-9a-fA-F]{6}$/.test(p) || !/^#[0-9a-fA-F]{6}$/.test(s)) {
      errEl.textContent = 'Bitte gültige Hex-Farben eingeben (z. B. #008c99).';
      errEl.classList.add('is-visible');
      return;
    }

    const btn = _el('settings-save-btn');
    btn.disabled = true;
    _el('settings-save-spinner').hidden = false;
    _el('settings-save-label').textContent = 'Wird gespeichert ...';

    try {
      const saved = await api.saveSettings({ app_title: appTitle, color_primary: p, color_secondary: s });
      _current = { ...saved };
      theme.apply(saved);
      ui.snackbar('Einstellungen gespeichert.', 'success');
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.add('is-visible');
    } finally {
      btn.disabled = false;
      _el('settings-save-spinner').hidden = true;
      _el('settings-save-label').textContent = 'Speichern';
    }
  }

  function handleReset() {
    load(_current);        // revert form to last saved state
  }

  /** Called when the Settings tab is re-opened – reverts unsaved edits. */
  function refresh() { load(_current); }

  return { init, load, refresh, handleSave, handleReset };
})();


/* ==========================================================================
   GTFS PANEL
   Handles the GTFS-Feed section in the settings panel: persisting the feed
   URL and triggering/polling the background import.
========================================================================== */
const gtfsPanel = (() => {
  const POLL_INTERVAL_MS = 2_000;
  const POLL_MAX         = 150;   // 5 minutes max

  let _pollTimer  = null;
  let _pollCount  = 0;

  function _el(id) { return document.getElementById(id); }

  // -- Status box -----------------------------------------------------------
  function _showStatus(text, type = '') {
    const box = _el('settings-gtfs-status');
    box.className = 'gtfs-status' + (type ? ` gtfs-status--${type}` : '');
    box.innerHTML = type === 'running'
      ? `<span class="gtfs-status__spinner" aria-hidden="true"></span><span>${text}</span>`
      : text;
  }

  function _renderStatus(s) {
    if (!s) { _showStatus(''); return; }
    const time = s.imported_at
      ? new Date(s.imported_at).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
      : null;

    if (s.status === 'running') {
      _showStatus('Import läuft …', 'running');
    } else if (s.status === 'success') {
      _showStatus(
        (time ? `Letzter Import: ${time} — ` : '') + (s.message ?? ''),
        'success',
      );
    } else if (s.status === 'error') {
      _showStatus(
        (time ? `Fehler (${time}): ` : 'Fehler: ') + (s.message ?? ''),
        'error',
      );
    } else {
      _showStatus(time ? `Letzter Import: ${time}` : 'Noch kein Import durchgeführt.');
    }
  }

  // -- Polling --------------------------------------------------------------
  function _stopPoll() {
    clearTimeout(_pollTimer);
    _pollTimer = null;
    _pollCount = 0;
  }

  function _setBusy(busy) {
    _el('settings-gtfs-import-btn').disabled    = busy;
    _el('settings-gtfs-import-spinner').hidden  = !busy;
    _el('settings-gtfs-import-label').textContent = busy ? 'Wird importiert …' : 'Import starten';
  }

  async function _poll() {
    _pollCount++;
    if (_pollCount > POLL_MAX) {
      _stopPoll();
      _setBusy(false);
      _showStatus('Import-Timeout — bitte Seite neu laden.', 'error');
      return;
    }
    try {
      const s = await api.getGtfsStatus();
      _renderStatus(s);
      if (s.status !== 'running') {
        _stopPoll();
        _setBusy(false);
      } else {
        _pollTimer = setTimeout(_poll, POLL_INTERVAL_MS);
      }
    } catch {
      _stopPoll();
      _setBusy(false);
    }
  }

  // -- Public API -----------------------------------------------------------
  async function load() {
    _el('settings-gtfs-error').classList.remove('is-visible');
    try {
      const s = await api.getGtfsStatus();
      _el('settings-gtfs-url').value = s.feed_url ?? '';
      _renderStatus(s);
      if (s.status === 'running') {
        _setBusy(true);
        _stopPoll();
        _pollTimer = setTimeout(_poll, POLL_INTERVAL_MS);
      }
    } catch { /* non-admin users won't reach this section */ }
  }

  async function handleSaveUrl() {
    const url   = _el('settings-gtfs-url').value.trim();
    const errEl = _el('settings-gtfs-error');
    errEl.classList.remove('is-visible');
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      errEl.textContent = 'Bitte eine gültige URL (http:// oder https://) eingeben.';
      errEl.classList.add('is-visible');
      return;
    }
    const btn = _el('settings-gtfs-save-btn');
    btn.disabled = true;
    try {
      await api.saveGtfsFeedUrl(url);
      ui.snackbar('Feed-URL gespeichert.', 'success');
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.add('is-visible');
    } finally {
      btn.disabled = false;
    }
  }

  async function handleImport() {
    const errEl = _el('settings-gtfs-error');
    errEl.classList.remove('is-visible');
    // Save URL first so the backend is up-to-date
    const url = _el('settings-gtfs-url').value.trim();
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      errEl.textContent = 'Bitte zuerst eine gültige Feed-URL eingeben.';
      errEl.classList.add('is-visible');
      return;
    }
    _setBusy(true);
    _showStatus('Import läuft …', 'running');
    try {
      await api.saveGtfsFeedUrl(url);
      await api.triggerGtfsImport();
      _stopPoll();
      _pollTimer = setTimeout(_poll, POLL_INTERVAL_MS);
    } catch (err) {
      _setBusy(false);
      _showStatus('');
      errEl.textContent = err.message;
      errEl.classList.add('is-visible');
    }
  }

  function init() {
    _el('settings-gtfs-save-btn').addEventListener('click', handleSaveUrl);
    _el('settings-gtfs-import-btn').addEventListener('click', handleImport);
  }

  return { init, load };
})();


/* ==========================================================================
   RIPPLE
   Attaches the Material Design ripple effect to every element marked
   with [data-ripple]. Safe to call multiple times (idempotent).
========================================================================== */
function initRipples(root = document) {
  root.querySelectorAll('[data-ripple]:not([data-ripple-init])').forEach(target => {
    target.dataset.rippleInit = '1';
    target.addEventListener('pointerdown', e => {
      const rect   = target.getBoundingClientRect();
      const size   = Math.max(rect.width, rect.height) * 2.4;
      const x      = e.clientX - rect.left - size / 2;
      const y      = e.clientY - rect.top  - size / 2;
      const ripple = document.createElement('span');
      ripple.className  = 'ripple';
      ripple.style.cssText = `width:${size}px;height:${size}px;left:${x}px;top:${y}px`;
      target.appendChild(ripple);
      ripple.addEventListener('animationend', () => ripple.remove(), { once: true });
    });
  });
}


/* ==========================================================================
   APP
   Orchestrates state ↔ api ↔ ui. Contains all business logic.
   No direct DOM access – everything goes through the ui module.
========================================================================== */
const app = (() => {

  let _accounts = [];

  async function init() {
    ui.setLoading(true);

    // Load and apply theme colours on every page load (public endpoint)
    try {
      const saved = await api.getSettings();
      theme.apply(saved);
      settingsPanel.load(saved);
    } catch { /* use CSS defaults if unavailable */ }

    // Health probe (non-blocking for UX – failure only updates badge)
    api.health()
      .then(() => ui.setApiStatus(true))
      .catch(() => ui.setApiStatus(false));

    // Restore session from sessionStorage
    if (state.isAuthenticated) {
      try {
        const user = await api.getMe();
        state.setAuth(state.token, user);
        ui.renderUser(user);
        ui.showView('app');
        ui.setPanel('alerts');
      } catch (err) {
        if (err.message !== 'SESSION_EXPIRED') {
          // Unexpected error: clear and show login with a message
          state.clearAuth();
          ui.showView('login');
          ui.snackbar('Sitzung konnte nicht wiederhergestellt werden.', 'error');
        }
        // SESSION_EXPIRED already handled by api layer
      }
    } else {
      ui.showView('login');
    }

    ui.setLoading(false);
  }

  async function handleLogin(e) {
    e.preventDefault();
    const form     = e.currentTarget;
    const username = form.elements['username'].value.trim();
    const password = form.elements['password'].value;

    if (!username || !password) {
      ui.setLoginError('Bitte Benutzername und Passwort eingeben.');
      return;
    }

    ui.setLoginError(null);
    ui.setLoginBusy(true);

    try {
      // 1. Obtain token
      const tokenData = await api.login(username, password);

      // 2. Store token so getMe() can attach the Authorization header
      state.setAuth(tokenData.access_token, null);

      // 3. Fetch full user profile
      const user = await api.getMe();
      state.setAuth(tokenData.access_token, user);

      // 4. Update UI
      ui.renderUser(user);
      ui.showView('app');
      ui.setPanel('alerts');
      form.reset();
      ui.snackbar(`Willkommen, ${user.username}!`, 'success');
    } catch (err) {
      // Undo partial token set if getMe() failed after login
      if (!state.user) state.clearAuth();

      if (err.message !== 'SESSION_EXPIRED') {
        ui.setLoginError(err.message);
      }
    } finally {
      ui.setLoginBusy(false);
    }
  }

  function handleLogout() {
    const username = state.user?.username ?? '';
    state.clearAuth();
    ui.clearUser();
    ui.showView('login');
    if (username) ui.snackbar(`${username} wurde abgemeldet.`);
  }

  // -- Navigation ------------------------------------------------------------
  function handleNavClick(e) {
    const btn = e.target.closest('.nav-item[data-panel]');
    if (!btn) return;
    const panel = btn.dataset.panel;
    ui.setPanel(panel);
    if (panel === 'accounts') _loadAccounts();
    if (panel === 'settings') { settingsPanel.refresh(); gtfsPanel.load(); }
  }

  // -- Accounts: load --------------------------------------------------------
  async function _loadAccounts() {
    document.getElementById('accounts-content').innerHTML =
      '<div class="panel__loading">Wird geladen ...</div>';
    try {
      _accounts = await api.getUsers();
      ui.renderAccountsList(_accounts);
    } catch {
      document.getElementById('accounts-content').innerHTML =
        '<div class="panel__placeholder">Fehler beim Laden der Accounts.</div>';
    }
  }

  // -- Accounts: event delegation on table ----------------------------------
  function handleAccountsContentClick(e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const id = parseInt(btn.dataset.id, 10);
    if (btn.dataset.action === 'edit')   _openEditModal(id);
    if (btn.dataset.action === 'delete') _confirmDelete(id);
  }

  // -- Accounts: add ---------------------------------------------------------
  function handleAddAccount() {
    ui.openAccountModal({ title: 'Neuer Account', editMode: false });
    document.getElementById('account-form').onsubmit = e => _saveAccount(e, null);
  }

  // -- Accounts: edit --------------------------------------------------------
  function _openEditModal(userId) {
    const user = _accounts.find(u => u.id === userId);
    if (!user) { ui.snackbar('Account nicht gefunden.', 'error'); return; }
    ui.openAccountModal({
      title:       'Account bearbeiten',
      username:    user.username,
      email:       user.email,
      isActive:    user.is_active,
      isSuperuser: user.is_superuser,
      editMode:    true,
    });
    document.getElementById('account-form').onsubmit = e => _saveAccount(e, userId);
  }

  // -- Accounts: save (create or update) ------------------------------------
  async function _saveAccount(e, userId) {
    e.preventDefault();
    const form      = e.currentTarget;
    const username  = form.elements['username'].value.trim();
    const email     = form.elements['email'].value.trim();
    const password  = form.elements['password'].value;
    const isActive  = form.elements['is_active'].checked;
    const isSuperuser = form.elements['is_superuser'].checked;

    ui.setModalError(null);
    if (!email)               { ui.setModalError('Bitte E-Mail eingeben.'); return; }
    if (!userId && !username) { ui.setModalError('Bitte Benutzername eingeben.'); return; }
    if (!userId && !password) { ui.setModalError('Bitte Passwort eingeben.'); return; }

    ui.setModalBusy(true);
    try {
      if (!userId) {
        // Create: use register endpoint, then patch flags if non-default
        const created = await api.createUser({ username, email, password });
        if (!isActive || isSuperuser) {
          await api.updateUser(created.id, { is_active: isActive, is_superuser: isSuperuser });
        }
      } else {
        const patch = { email, is_active: isActive, is_superuser: isSuperuser };
        if (password) patch.password = password;
        await api.updateUser(userId, patch);
      }
      ui.closeAccountModal();
      await _loadAccounts();
      ui.snackbar(userId ? 'Account aktualisiert.' : 'Account erstellt.', 'success');
    } catch (err) {
      ui.setModalError(err.message);
    } finally {
      ui.setModalBusy(false);
    }
  }

  // -- Accounts: delete ------------------------------------------------------
  async function _confirmDelete(userId) {
    const user = _accounts.find(u => u.id === userId);
    if (!user) return;
    const confirmed = await ui.openConfirmModal(
      `Account „${user.username}“ wirklich löschen? Diese Aktion ist unwiderruflich.`
    );
    if (!confirmed) return;
    try {
      await api.deleteUser(userId);
      await _loadAccounts();
      ui.snackbar(`Account „${user.username}“ wurde gelöscht.`);
    } catch (err) {
      ui.snackbar(err.message, 'error');
    }
  }

  return { init, handleLogin, handleLogout, handleNavClick, handleAddAccount, handleAccountsContentClick };
})();


/* ==========================================================================
   BOOTSTRAP
========================================================================== */
document.addEventListener('DOMContentLoaded', () => {
  initRipples();

  // Login
  document.getElementById('login-form').addEventListener('submit', app.handleLogin);
  ['username', 'password'].forEach(name => {
    document.getElementById(name)?.addEventListener('input', () => ui.setLoginError(null));
  });

  // Logout
  document.getElementById('logout-btn').addEventListener('click', app.handleLogout);
  document.getElementById('logout-card-btn').addEventListener('click', app.handleLogout);

  // Sidebar navigation
  document.querySelector('.sidebar').addEventListener('click', app.handleNavClick);

  // Accounts panel
  document.getElementById('add-account-btn').addEventListener('click', app.handleAddAccount);
  document.getElementById('accounts-content').addEventListener('click', app.handleAccountsContentClick);

  // Account modal
  document.getElementById('modal-cancel-btn').addEventListener('click', () => ui.closeAccountModal());
  document.getElementById('account-modal').querySelector('.modal__backdrop')
    .addEventListener('click', () => ui.closeAccountModal());

  // Confirm modal backdrop
  document.getElementById('confirm-modal').querySelector('.modal__backdrop')
    .addEventListener('click', () => document.getElementById('confirm-cancel-btn').click());

  // Escape closes open modals
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (!document.getElementById('confirm-modal').hidden) {
      document.getElementById('confirm-cancel-btn').click();
    } else if (!document.getElementById('account-modal').hidden) {
      ui.closeAccountModal();
    }
  });

  // Settings panel
  settingsPanel.init();
  gtfsPanel.init();
  document.getElementById('settings-form').addEventListener('submit', settingsPanel.handleSave);
  document.getElementById('settings-reset-btn').addEventListener('click', settingsPanel.handleReset);

  app.init();
});

