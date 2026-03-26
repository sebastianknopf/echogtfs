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
      'Cannot deactivate yourself': 'Der eigene Account kann nicht deaktiviert werden.',
      'Cannot delete yourself': 'Der eigene Account kann nicht gelöscht werden.',
      'Alert not found': 'Meldung nicht gefunden.',
      'Authentication required': 'Authentifizierung erforderlich.',
      'Invalid credentials': 'Ungültige Anmeldedaten.',
      'Not found': 'Nicht gefunden.',
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
      ui.toast('Sitzung abgelaufen. Bitte erneut anmelden.', 'error');
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

    saveGtfsConfig({ feed_url, cron }) {
      return request('/gtfs/feed-url', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feed_url, cron }),
      });
    },

    triggerGtfsImport() {
      return request('/gtfs/import', { method: 'POST' });
    },

    // Alerts
    getAlerts() {
      return request('/alerts/', {}, true);
    },

    getAlert(id) {
      return request(`/alerts/${id}`, {}, true);
    },

    createAlert(data) {
      return request('/alerts/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },

    updateAlert(id, data) {
      return request(`/alerts/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },

    deleteAlert(id) {
      return request(`/alerts/${id}`, { method: 'DELETE' });
    },

    // GTFS data for autocomplete
    getAgencies() {
      return request('/gtfs/agencies');
    },

    getRoutes(q = '') {
      return request(`/gtfs/routes?q=${encodeURIComponent(q)}&limit=100`);
    },

    getStops(q = '') {
      return request(`/gtfs/stops?q=${encodeURIComponent(q)}&limit=100`);
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

  // -- Toast (Snackbar) ----------------------------------------------------
  let _toastTimer = null;
  function toast(message, type = 'default') {
    const node = el('snackbar');
    node.textContent = message;
    node.className = 'toast is-visible';
    if (type !== 'default') node.classList.add(`is-${type}`);
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => {
      node.classList.remove('is-visible');
    }, type === 'error' ? 5000 : 3000);
  }

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
    const userAvatar = el('user-avatar');
    if (userAvatar) userAvatar.textContent = user.username.charAt(0).toUpperCase();
    
    const topbarUsername = el('topbar-username');
    if (topbarUsername) topbarUsername.textContent = user.username;

    // Profile card
    const userName = el('user-name');
    if (userName) userName.textContent = user.username;
    
    const userEmail = el('user-email');
    if (userEmail) userEmail.textContent = user.email;

    // Status chips
    const chipsEl = el('user-chips');
    if (chipsEl) {
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
    }

    // Detail cells
    const detailUsername = el('detail-username');
    if (detailUsername) detailUsername.textContent = user.username;
    
    const detailEmail = el('detail-email');
    if (detailEmail) detailEmail.textContent = user.email;
    
    const detailCreated = el('detail-created');
    if (detailCreated) {
      detailCreated.textContent = new Date(user.created_at).toLocaleDateString('de-DE', {
        year: 'numeric', month: 'long', day: 'numeric',
      });
    }
    
    const detailRole = el('detail-role');
    if (detailRole) detailRole.textContent = user.is_superuser ? 'Administrator' : 'Standard';

    // Show/hide admin-only sidebar items
    document.querySelectorAll('.nav-item[data-admin-only]').forEach(item => {
      item.hidden = !user.is_superuser;
    });
  }

  function clearUser() {
    ['user-avatar', 'topbar-username', 'user-name', 'user-email',
     'user-chips', 'detail-username', 'detail-email', 'detail-created', 'detail-role']
      .forEach(id => { 
        const elem = el(id);
        if (elem) elem.textContent = ''; 
      });
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
          ? '<span class="badge badge--system">Administrator</span>'
          : '<span class="badge badge--system">Standard</span>'}</td>
        <td>${user.is_active
          ? '<span class="badge badge--system">Aktiv</span>'
          : '<span class="badge badge--system">Inaktiv</span>'}</td>
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
  function openConfirmModal(message, title = 'Bestätigung erforderlich') {
    return new Promise(resolve => {
      el('confirm-title').textContent = title;
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

  // -- Alert cards ------------------------------------------------------------
  async function renderAlertsList(alerts) {
    const container = el('alerts-content');
    if (!alerts.length) {
      container.innerHTML = '<div class="panel__placeholder">Aktuell sind noch keine Meldungen verfügbar.</div>';
      return;
    }
    
    container.innerHTML = '<ul class="alert-list"></ul>';
    const list = container.querySelector('.alert-list');
    
    for (const alert of alerts) {
      const item = document.createElement('li');
      item.className = 'alert-list-item' + (alert.is_active ? '' : ' alert-list-item--inactive');
      
      // Get first translation (prefer German)
      const firstTrans = alert.translations.find(t => t.language === 'de') || alert.translations[0] || {};
      const title = firstTrans.header_text || 'Keine Überschrift';
      
      // Get start date from first active period and end date from last period
      let startDate = '';
      let endDate = '';
      if (alert.active_periods.length > 0) {
        if (alert.active_periods[0].start_time) {
          const d = new Date(alert.active_periods[0].start_time * 1000);
          startDate = d.toLocaleDateString('de-DE', { 
            day: '2-digit', 
            month: 'short', 
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
          });
        }
        
        const lastPeriod = alert.active_periods[alert.active_periods.length - 1];
        if (lastPeriod.end_time) {
          const d = new Date(lastPeriod.end_time * 1000);
          endDate = d.toLocaleDateString('de-DE', { 
            day: '2-digit', 
            month: 'short', 
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
          });
        }
      }
      
      // Determine source badge (intern/extern)
      const isInternal = alert.source === 'echogtfs';
      const sourceBadge = `<span class="badge badge--system">${isInternal ? 'Intern' : 'Extern'}</span>`;
      
      // Build entity badges with name resolution
      let entityBadges = '';
      let hasResolutionErrors = false;
      if (alert.informed_entities && alert.informed_entities.length > 0) {
        const enrichedEntities = await Promise.all(
          alert.informed_entities.map(entity => _enrichEntityWithNames(entity))
        );
        
        // Check if any entity has resolution errors
        hasResolutionErrors = enrichedEntities.some(e => e.hasResolutionError);
        
        entityBadges = enrichedEntities.map(entity => {
          const labels = [];
          if (entity.agency_name) labels.push(entity.agency_name);
          if (entity.route_name) labels.push(entity.route_name);
          if (entity.stop_name) labels.push(entity.stop_name);
          if (entity.trip_id) labels.push(`Fahrt ${entity.trip_id}`);
          
          return labels.map(label => 
            `<span class="badge badge--entity">${_esc(label)}</span>`
          ).join('');
        }).join('');
      }
      
      item.innerHTML = `
        <div class="alert-list-item__content">
          <div class="alert-list-item__header">
            <h3 class="alert-list-item__title">${_esc(title)}</h3>
            <div class="alert-list-item__badges">
              ${sourceBadge}
              ${!alert.is_active ? '<span class="badge badge--system">Inaktiv</span>' : ''}
            </div>
          </div>
          
          ${startDate ? `<div class="alert-list-item__time">
            <svg class="alert-list-item__icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.2 3.2.8-1.3-4.5-2.7V7z"/>
            </svg>
            <span>${startDate}${endDate ? ` – ${endDate}` : ''}</span>
          </div>` : ''}
          
          ${entityBadges ? `<div class="alert-list-item__entities">${entityBadges}</div>` : ''}
        </div>
        
        <div class="alert-list-item__actions">
          ${hasResolutionErrors ? `<span class="resolution-warning" title="Einige Bezüge konnten nicht aufgelöst werden">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>
          </span>` : ''}
          <button class="icon-btn" data-action="view" data-id="${alert.id}" title="Anzeigen" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
          </button>
          <button class="icon-btn" data-action="edit" data-id="${alert.id}" title="Bearbeiten" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
          </button>
          <button class="icon-btn icon-btn--danger" data-action="delete" data-id="${alert.id}" title="Löschen" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          </button>
        </div>
      `;
      
      list.appendChild(item);
    }
    
    initRipples(container);
  }

  // -- Alert modal ------------------------------------------------------------
  let _periodCounter = 0;
  let _translationCounter = 0;
  let _entityCounter = 0;

  function _addTranslationItem(lang = 'de', headerText = '', descText = '', url = '') {
    const transId = _translationCounter++;
    const container = el('alert-translations-container');
    
    const transDiv = document.createElement('div');
    transDiv.className = 'alert-translation-item';
    transDiv.dataset.transId = transId;
    
    transDiv.innerHTML = `
      <div class="alert-period-item__header">
        <span class="alert-period-item__title">Übersetzung ${container.children.length + 1}</span>
        <button type="button" class="icon-btn icon-btn--danger" data-action="remove-translation" data-trans-id="${transId}" title="Entfernen" data-ripple>
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </div>
      <div class="alert-period-item__fields">
        <div class="md-field" style="max-width: 200px;">
          <select class="md-field__input translation-lang">
            <option value="de" ${lang === 'de' ? 'selected' : ''}>Deutsch</option>
            <option value="en" ${lang === 'en' ? 'selected' : ''}>English</option>
            <option value="fr" ${lang === 'fr' ? 'selected' : ''}>Français</option>
            <option value="it" ${lang === 'it' ? 'selected' : ''}>Italiano</option>
            <option value="es" ${lang === 'es' ? 'selected' : ''}>Español</option>
          </select>
          <label class="md-field__label">Sprache</label>
        </div>
        <div class="md-field">
          <input class="md-field__input translation-header" type="text" placeholder=" " maxlength="512" value="${_esc(headerText)}" />
          <label class="md-field__label">Titel</label>
        </div>
      </div>
      <div class="md-field">
        <textarea class="md-field__input translation-desc" placeholder=" " rows="3">${_esc(descText)}</textarea>
        <label class="md-field__label">Beschreibung (optional)</label>
      </div>
      <div class="md-field">
        <input class="md-field__input translation-url" type="url" placeholder=" " maxlength="1024" value="${_esc(url)}" />
        <label class="md-field__label">URL (optional)</label>
      </div>
    `;
    
    container.appendChild(transDiv);
    initRipples(transDiv);
    
    // Attach remove handler
    transDiv.querySelector('[data-action="remove-translation"]').addEventListener('click', () => {
      transDiv.remove();
      _updateTranslationTitles();
    });
  }

  function _updateTranslationTitles() {
    const items = document.querySelectorAll('.alert-translation-item');
    items.forEach((item, idx) => {
      item.querySelector('.alert-period-item__title').textContent = `Übersetzung ${idx + 1}`;
    });
  }

  function _clearTranslations() {
    el('alert-translations-container').innerHTML = '';
    _translationCounter = 0;
  }

  // Helper: Convert Unix timestamp to local datetime-local string
  function _timestampToLocalDatetime(timestamp) {
    const date = new Date(timestamp * 1000);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  }

  function _addPeriodItem(startTime = null, endTime = null) {
    const periodId = _periodCounter++;
    const container = el('alert-periods-container');
    
    const periodDiv = document.createElement('div');
    periodDiv.className = 'alert-period-item';
    periodDiv.dataset.periodId = periodId;
    
    const startVal = startTime ? _timestampToLocalDatetime(startTime) : '';
    const endVal = endTime ? _timestampToLocalDatetime(endTime) : '';
    
    periodDiv.innerHTML = `
      <div class="alert-period-item__header">
        <span class="alert-period-item__title">Zeitraum ${container.children.length + 1}</span>
        <button type="button" class="icon-btn icon-btn--danger" data-action="remove-period" data-period-id="${periodId}" title="Entfernen" data-ripple>
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </div>
      <div class="alert-period-item__fields">
        <div class="md-field">
          <input class="md-field__input period-start" type="datetime-local" placeholder=" " value="${startVal}" />
          <label class="md-field__label">Von (optional)</label>
        </div>
        <div class="md-field">
          <input class="md-field__input period-end" type="datetime-local" placeholder=" " value="${endVal}" />
          <label class="md-field__label">Bis (optional)</label>
        </div>
      </div>
    `;
    
    container.appendChild(periodDiv);
    initRipples(periodDiv);
    
    // Attach remove handler
    periodDiv.querySelector('[data-action="remove-period"]').addEventListener('click', () => {
      periodDiv.remove();
      _updatePeriodTitles();
    });
  }

  function _updatePeriodTitles() {
    const items = document.querySelectorAll('.alert-period-item');
    items.forEach((item, idx) => {
      item.querySelector('.alert-period-item__title').textContent = `Zeitraum ${idx + 1}`;
    });
  }

  function _clearPeriods() {
    el('alert-periods-container').innerHTML = '';
    _periodCounter = 0;
  }

  function _addEntityItem(entity = {}) {
    const entityId = _entityCounter++;
    const container = el('alert-entities-container');
    
    const entityDiv = document.createElement('div');
    entityDiv.className = 'alert-entity-item';
    entityDiv.dataset.entityId = entityId;
    
    function _esc(str) {
      return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    
    // Pre-fetch display names if we have IDs
    let agencyName = '';
    let routeName = '';
    let stopName = '';
    let hasResolutionError = false;
    
    if (entity.agency_id) {
      agencyName = entity.agency_name || entity.agency_id;
      if (!entity.agency_name) hasResolutionError = true;
    }
    if (entity.route_id) {
      routeName = entity.route_name || entity.route_id;
      if (!entity.route_name) hasResolutionError = true;
    }
    if (entity.stop_id) {
      stopName = entity.stop_name || entity.stop_id;
      if (!entity.stop_name) hasResolutionError = true;
    }
    
    entityDiv.innerHTML = `
      <div class="alert-period-item__header">
        <span class="alert-period-item__title">Bezug ${container.children.length + 1}</span>
        <div class="alert-period-item__header-actions">
          ${hasResolutionError ? `<span class="resolution-warning resolution-warning--inline" title="Bezug konnte nicht aufgelöst werden">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>
          </span>` : ''}
          <button type="button" class="icon-btn icon-btn--danger" data-action="remove-entity" data-entity-id="${entityId}" title="Entfernen" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>
      </div>
      <div class="alert-period-item__fields">
        <div class="md-field">
          <input class="md-field__input entity-agency-name autocomplete-input" type="text" placeholder=" " value="${_esc(agencyName)}" data-autocomplete-type="agency" />
          <input type="hidden" class="entity-agency-id" value="${_esc(entity.agency_id)}" />
          <label class="md-field__label">Unternehmen (optional)</label>
        </div>
        <div class="md-field">
          <input class="md-field__input entity-route-name autocomplete-input" type="text" placeholder=" " value="${_esc(routeName)}" data-autocomplete-type="route" />
          <input type="hidden" class="entity-route-id" value="${_esc(entity.route_id)}" />
          <label class="md-field__label">Linie (optional)</label>
        </div>
      </div>
      <div class="alert-period-item__fields">
        <div class="md-field">
          <select class="md-field__input entity-route-type">
            <option value="" ${entity.route_type === null || entity.route_type === undefined ? 'selected' : ''}></option>
            <option value="0" ${entity.route_type === 0 ? 'selected' : ''}>Straßenbahn</option>
            <option value="1" ${entity.route_type === 1 ? 'selected' : ''}>U-Bahn</option>
            <option value="2" ${entity.route_type === 2 ? 'selected' : ''}>Zug</option>
            <option value="3" ${entity.route_type === 3 ? 'selected' : ''}>Bus</option>
            <option value="4" ${entity.route_type === 4 ? 'selected' : ''}>Fähre</option>
            <option value="5" ${entity.route_type === 5 ? 'selected' : ''}>Seilbahn</option>
            <option value="6" ${entity.route_type === 6 ? 'selected' : ''}>Gondel</option>
            <option value="7" ${entity.route_type === 7 ? 'selected' : ''}>Standseilbahn</option>
          </select>
          <label class="md-field__label">Linientyp (optional)</label>
        </div>
        <div class="md-field">
          <select class="md-field__input entity-direction-id">
            <option value="" ${entity.direction_id === null || entity.direction_id === undefined ? 'selected' : ''}></option>
            <option value="0" ${entity.direction_id === 0 ? 'selected' : ''}>Hinfahrt</option>
            <option value="1" ${entity.direction_id === 1 ? 'selected' : ''}>Rückfahrt</option>
          </select>
          <label class="md-field__label">Richtung (optional)</label>
        </div>
      </div>
      <div class="alert-period-item__fields">
        <div class="md-field">
          <input class="md-field__input entity-stop-name autocomplete-input" type="text" placeholder=" " value="${_esc(stopName)}" data-autocomplete-type="stop" />
          <input type="hidden" class="entity-stop-id" value="${_esc(entity.stop_id)}" />
          <label class="md-field__label">Haltestelle (optional)</label>
        </div>
      </div>
    `;
    
    container.appendChild(entityDiv);
    initRipples(entityDiv);
    
    // Attach remove handler
    entityDiv.querySelector('[data-action="remove-entity"]').addEventListener('click', () => {
      entityDiv.remove();
      _updateEntityTitles();
    });
    
    // Setup autocomplete for all autocomplete-input fields
    entityDiv.querySelectorAll('.autocomplete-input').forEach(input => {
      _setupAutocomplete(input);
    });
  }

  function _updateEntityTitles() {
    const items = document.querySelectorAll('.alert-entity-item');
    items.forEach((item, idx) => {
      item.querySelector('.alert-period-item__title').textContent = `Bezug ${idx + 1}`;
    });
  }

  function _clearEntities() {
    el('alert-entities-container').innerHTML = '';
    _entityCounter = 0;
  }

  // Autocomplete functionality
  let _autocompleteCache = { agencies: null, routes: null, stops: null };
  let _autocompleteDebounceTimers = {};
  
  async function _fetchAutocompleteData(type, query = '') {
    try {
      if (type === 'agency') {
        if (!_autocompleteCache.agencies) {
          _autocompleteCache.agencies = await api.getAgencies();
        }
        return _autocompleteCache.agencies;
      } else if (type === 'route') {
        // Always fetch fresh data for routes with query
        const data = await api.getRoutes(query);
        return data || [];
      } else if (type === 'stop') {
        // Always fetch fresh data for stops with query
        const data = await api.getStops(query);
        return data || [];
      }
    } catch (error) {
      console.error(`Failed to fetch ${type} autocomplete data:`, error);
      return [];
    }
    return [];
  }
  
  function _setupAutocomplete(input) {
    const type = input.dataset.autocompleteType;
    if (!type) return;
    
    const hiddenInput = input.parentElement.querySelector(`input[type="hidden"].entity-${type}-id`);
    if (!hiddenInput) {
      console.error('Hidden input not found for', type, input);
      return;
    }
    
    let autocompleteList = null;
    let selectedIndex = -1;
    let currentItems = [];
    
    function closeAutocomplete() {
      if (autocompleteList) {
        autocompleteList.remove();
        autocompleteList = null;
        selectedIndex = -1;
        currentItems = [];
      }
    }
    
    async function showAutocomplete() {
      closeAutocomplete();
      
      const query = input.value.trim();
      
      // Fetch items
      const items = await _fetchAutocompleteData(type, query);
      
      if (!items || items.length === 0) {
        closeAutocomplete();
        return;
      }
      
      // Filter and limit items
      let filteredItems = items;
      if (query) {
        const lowerQuery = query.toLowerCase();
        filteredItems = items.filter(item => {
          if (type === 'agency') {
            return item.gtfs_id.toLowerCase().includes(lowerQuery) || 
                   item.name.toLowerCase().includes(lowerQuery);
          } else if (type === 'route') {
            return item.gtfs_id.toLowerCase().includes(lowerQuery) ||
                   item.short_name.toLowerCase().includes(lowerQuery) ||
                   item.long_name.toLowerCase().includes(lowerQuery);
          } else if (type === 'stop') {
            return item.gtfs_id.toLowerCase().includes(lowerQuery) ||
                   item.name.toLowerCase().includes(lowerQuery);
          }
          return false;
        });
      }
      
      currentItems = filteredItems.slice(0, 15);
      
      if (currentItems.length === 0) {
        closeAutocomplete();
        return;
      }
      
      // Create autocomplete dropdown
      autocompleteList = document.createElement('div');
      autocompleteList.className = 'autocomplete-list';
      
      currentItems.forEach((item, idx) => {
        const div = document.createElement('div');
        div.className = 'autocomplete-item';
        div.dataset.index = idx;
        
        let displayText = '';
        let displayName = '';
        
        if (type === 'agency') {
          displayText = `<div class="autocomplete-item__id">${item.gtfs_id}</div><div class="autocomplete-item__name">${item.name}</div>`;
          displayName = item.name;
          div.dataset.id = item.gtfs_id;
          div.dataset.name = item.name;
        } else if (type === 'route') {
          displayText = `<div class="autocomplete-item__id">${item.gtfs_id}</div><div class="autocomplete-item__name">${item.short_name} - ${item.long_name}</div>`;
          displayName = `${item.short_name} ${item.long_name}`;
          div.dataset.id = item.gtfs_id;
          div.dataset.name = displayName;
        } else if (type === 'stop') {
          displayText = `<div class="autocomplete-item__id">${item.gtfs_id}</div><div class="autocomplete-item__name">${item.name}</div>`;
          displayName = item.name;
          div.dataset.id = item.gtfs_id;
          div.dataset.name = item.name;
        }
        
        div.innerHTML = displayText;
        
        div.addEventListener('click', () => {
          input.value = div.dataset.name;
          hiddenInput.value = div.dataset.id;
          closeAutocomplete();
        });
        
        autocompleteList.appendChild(div);
      });
      
      input.parentElement.style.position = 'relative';
      input.parentElement.appendChild(autocompleteList);
    }
    
    // Clear hidden input when user types
    input.addEventListener('input', () => {
      // Don't clear hidden input immediately - allow manual entry
      
      // Clear existing timer
      if (_autocompleteDebounceTimers[type]) {
        clearTimeout(_autocompleteDebounceTimers[type]);
      }
      
      const query = input.value.trim();
      if (query.length >= 1) {
        // Debounce for 300ms
        _autocompleteDebounceTimers[type] = setTimeout(() => {
          showAutocomplete();
        }, 300);
      } else {
        closeAutocomplete();
        hiddenInput.value = ''; // Clear only when input is empty
      }
    });
    
    input.addEventListener('focus', () => {
      const query = input.value.trim();
      if (query.length >= 1) {
        showAutocomplete();
      }
    });
    
    input.addEventListener('keydown', (e) => {
      if (!autocompleteList) return;
      const items = autocompleteList.querySelectorAll('.autocomplete-item');
      
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
        items.forEach((item, idx) => {
          item.classList.toggle('autocomplete-item--selected', idx === selectedIndex);
        });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedIndex = Math.max(selectedIndex - 1, 0);
        items.forEach((item, idx) => {
          item.classList.toggle('autocomplete-item--selected', idx === selectedIndex);
        });
      } else if (e.key === 'Enter' && selectedIndex >= 0) {
        e.preventDefault();
        items[selectedIndex].click();
      } else if (e.key === 'Escape') {
        closeAutocomplete();
      }
    });
    
    document.addEventListener('click', (e) => {
      if (!input.contains(e.target) && (!autocompleteList || !autocompleteList.contains(e.target))) {
        closeAutocomplete();
      }
    });
  }

  // Helper function to load human-readable names for entity IDs
  async function _enrichEntityWithNames(entity) {
    const enriched = { ...entity };
    let hasResolutionError = false;
    
    try {
      // Load agency name if agency_id is set
      if (entity.agency_id && !entity.agency_name) {
        const agencies = await _fetchAutocompleteData('agency');
        const agency = agencies?.find(a => a.gtfs_id === entity.agency_id);
        if (agency) {
          enriched.agency_name = agency.name;
        } else {
          hasResolutionError = true;
        }
      }
      
      // Load route name if route_id is set
      if (entity.route_id && !entity.route_name) {
        const routes = await api.getRoutes(entity.route_id);
        const route = routes?.find(r => r.gtfs_id === entity.route_id);
        if (route) {
          enriched.route_name = `${route.short_name} ${route.long_name}`;
        } else {
          hasResolutionError = true;
        }
      }
      
      // Load stop name if stop_id is set
      if (entity.stop_id && !entity.stop_name) {
        const stops = await api.getStops(entity.stop_id);
        const stop = stops?.find(s => s.gtfs_id === entity.stop_id);
        if (stop) {
          enriched.stop_name = stop.name;
        } else {
          hasResolutionError = true;
        }
      }
    } catch (error) {
      console.error('Failed to enrich entity with names:', error);
      hasResolutionError = true;
    }
    
    enriched.hasResolutionError = hasResolutionError;
    return enriched;
  }

  async function openAlertModal({ title, alert = null } = {}) {
    el('alert-modal-title').textContent = title;
    el('alert-cause').value = 'UNKNOWN_CAUSE';
    el('alert-effect').value = 'UNKNOWN_EFFECT';
    el('alert-severity').value = 'UNKNOWN_SEVERITY';
    el('alert-is-active').checked = true;
    el('alert-modal-error').textContent = '';
    el('alert-modal-error').classList.remove('is-visible');
    _clearTranslations();
    _clearPeriods();
    _clearEntities();
    
    // Fill form if editing
    if (alert) {
      el('alert-cause').value = alert.cause;
      el('alert-effect').value = alert.effect;
      el('alert-severity').value = alert.severity_level || 'UNKNOWN_SEVERITY';
      el('alert-is-active').checked = alert.is_active;
      
      // Load existing translations
      if (alert.translations && alert.translations.length > 0) {
        alert.translations.forEach(trans => {
          _addTranslationItem(trans.language, trans.header_text, trans.description_text || '', trans.url || '');
        });
      } else {
        // Default: one German translation
        _addTranslationItem('de', '', '', '');
      }
      
      // Load existing periods
      if (alert.active_periods && alert.active_periods.length > 0) {
        alert.active_periods.forEach(period => {
          _addPeriodItem(period.start_time, period.end_time);
        });
      }
      
      // Load existing informed entities
      if (alert.informed_entities && alert.informed_entities.length > 0) {
        for (const entity of alert.informed_entities) {
          const enriched = await _enrichEntityWithNames(entity);
          _addEntityItem(enriched);
        }
      }
    } else {
      // New alert: start with one German translation
      _addTranslationItem('de', '', '', '');
    }
    
    // Reset to first tab (Grunddaten)
    document.querySelectorAll('.modal__tab').forEach((tab, idx) => {
      if (idx === 0) {
        tab.classList.add('modal__tab--active');
        tab.setAttribute('aria-selected', 'true');
      } else {
        tab.classList.remove('modal__tab--active');
        tab.setAttribute('aria-selected', 'false');
      }
    });
    document.querySelectorAll('.modal__tab-panel').forEach((panel, idx) => {
      panel.hidden = idx !== 0;
    });
    
    el('alert-modal').hidden = false;
    // Focus first field (cause)
    setTimeout(() => {
      el('alert-cause').focus();
    }, 50);
  }

  function closeAlertModal() {
    el('alert-modal').hidden = true;
  }

  function setAlertModalBusy(busy) {
    el('alert-modal-submit-btn').disabled = busy;
    el('alert-modal-submit-spinner').hidden = !busy;
    el('alert-modal-submit-label').textContent = busy ? 'Wird gespeichert ...' : 'Speichern';
  }

  function setAlertModalError(msg) {
    const e = el('alert-modal-error');
    e.textContent = msg ?? '';
    e.classList.toggle('is-visible', !!msg);
  }

  // -- View Alert Modal (read-only) ------------------------------------------
  
  async function openViewAlertModal(alert) {
    const content = el('view-alert-content');
    
    // Set modal title to alert title (prefer German translation)
    const firstTrans = alert.translations.find(t => t.language === 'de') || alert.translations[0] || {};
    const title = firstTrans.header_text || 'Meldung anzeigen';
    el('view-alert-title').textContent = title;
    
    // Helper maps
    const causeMap = {
      'TECHNICAL_PROBLEM': 'Technisches Problem', 'STRIKE': 'Streik', 'ACCIDENT': 'Unfall',
      'WEATHER': 'Wetter', 'MAINTENANCE': 'Wartung', 'CONSTRUCTION': 'Bauarbeiten',
      'POLICE_ACTIVITY': 'Polizeieinsatz', 'MEDICAL_EMERGENCY': 'Medizinischer Notfall',
      'DEMONSTRATION': 'Demonstration', 'HOLIDAY': 'Feiertag', 'OTHER_CAUSE': 'Sonstige Ursache',
      'UNKNOWN_CAUSE': 'Unbekannte Ursache'
    };
    const effectMap = {
      'NO_SERVICE': 'Kein Service', 'REDUCED_SERVICE': 'Eingeschränkter Service',
      'SIGNIFICANT_DELAYS': 'Erhebliche Verspätungen', 'DETOUR': 'Umleitung',
      'ADDITIONAL_SERVICE': 'Zusätzlicher Service', 'MODIFIED_SERVICE': 'Geänderter Service',
      'STOP_MOVED': 'Haltestelle verlegt', 'NO_EFFECT': 'Keine Auswirkung',
      'ACCESSIBILITY_ISSUE': 'Barrierefreiheitsproblem', 'OTHER_EFFECT': 'Sonstige Auswirkung',
      'UNKNOWN_EFFECT': 'Unbekannte Auswirkung'
    };
    const severityMap = {
      'INFO': 'Info', 'WARNING': 'Warnung', 'SEVERE': 'Schwerwiegend', 'UNKNOWN_SEVERITY': 'Unbekannt'
    };
    
    // Translations
    let translationsHtml = '';
    if (alert.translations && alert.translations.length > 0) {
      translationsHtml = alert.translations.map(t => `
        <div class="view-item">
          <div class="view-item__label">${_esc(t.language.toUpperCase())}</div>
          <div class="view-item__content">
            <strong>${_esc(t.header_text || '—')}</strong>
            ${t.description_text ? `<p style="margin-top: 4px;">${_esc(t.description_text)}</p>` : ''}
            ${t.url ? `<p style="margin-top: 4px;"><a href="${_esc(t.url)}" target="_blank" rel="noopener">${_esc(t.url)}</a></p>` : ''}
          </div>
        </div>
      `).join('');
    }
    
    // Active Periods
    let periodsHtml = '';
    if (alert.active_periods && alert.active_periods.length > 0) {
      periodsHtml = alert.active_periods.map(p => {
        const start = p.start_time ? new Date(p.start_time * 1000).toLocaleDateString('de-DE', { 
          day: '2-digit', 
          month: 'short', 
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        }) : '—';
        const end = p.end_time ? new Date(p.end_time * 1000).toLocaleDateString('de-DE', { 
          day: '2-digit', 
          month: 'short', 
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        }) : '—';
        return `<div class="view-item view-item--entity"><div class="view-item__content">${start} – ${end}</div></div>`;
      }).join('');
    } else {
      periodsHtml = '<div class="view-item view-item--entity"><div class="view-item__content"><em>Dauerhaft gültig</em></div></div>';
    }
    
    // Informed Entities
    let entitiesHtml = '';
    if (alert.informed_entities && alert.informed_entities.length > 0) {
      const enrichedEntities = await Promise.all(
        alert.informed_entities.map(entity => _enrichEntityWithNames(entity))
      );
      entitiesHtml = enrichedEntities.map(e => {
        const parts = [];
        
        // Show names if available, otherwise show IDs
        if (e.agency_id) {
          parts.push(`Unternehmen: ${e.agency_name || e.agency_id}`);
        }
        if (e.route_id) {
          parts.push(`Linie: ${e.route_name || e.route_id}`);
        }
        if (e.route_type !== null && e.route_type !== undefined) {
          const routeTypes = ['Straßenbahn', 'U-Bahn', 'Zug', 'Bus', 'Fähre', 'Seilbahn', 'Gondel', 'Standseilbahn'];
          parts.push(`Linientyp: ${routeTypes[e.route_type] || e.route_type}`);
        }
        if (e.direction_id !== null && e.direction_id !== undefined) {
          parts.push(`Richtung: ${e.direction_id === 0 ? 'Hinfahrt' : 'Rückfahrt'}`);
        }
        if (e.stop_id) {
          parts.push(`Haltestelle: ${e.stop_name || e.stop_id}`);
        }
        if (e.trip_id) {
          parts.push(`Fahrt: ${e.trip_id}`);
        }
        
        const warningIcon = e.hasResolutionError 
          ? '<span class="view-item__warning" title="Bezug konnte nicht aufgelöst werden"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg></span>'
          : '';
        
        return `<div class="view-item view-item--entity"><div class="view-item__content">${parts.join(' • ')}</div>${warningIcon}</div>`;
      }).join('');
    } else {
      entitiesHtml = '<div class="view-item view-item--entity"><div class="view-item__content"><em>Alle Verbindungen betroffen</em></div></div>';
    }
    
    content.innerHTML = `
      <div class="view-section">
        <h3 class="view-section__title">Grunddaten</h3>
        <div class="view-item">
          <div class="view-item__label">Ursache</div>
          <div class="view-item__content">${causeMap[alert.cause] || alert.cause}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label">Auswirkung</div>
          <div class="view-item__content">${effectMap[alert.effect] || alert.effect}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label">Schweregrad</div>
          <div class="view-item__content">${severityMap[alert.severity_level] || alert.severity_level}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label">Status</div>
          <div class="view-item__content">${alert.is_active ? '✓ Aktiv' : '✗ Inaktiv'}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label">Quelle</div>
          <div class="view-item__content">${alert.source === 'echogtfs' ? 'Intern (echogtfs)' : _esc(alert.source)}</div>
        </div>
      </div>
      
      <div class="view-section">
        <h3 class="view-section__title">Gültigkeitszeiträume</h3>
        ${periodsHtml}
      </div>
      
      <div class="view-section">
        <h3 class="view-section__title">Bezüge</h3>
        ${entitiesHtml}
      </div>
      
      <div class="view-section">
        <h3 class="view-section__title">Übersetzungen</h3>
        ${translationsHtml}
      </div>
    `;
    
    el('view-alert-modal').hidden = false;
  }
  
  function closeViewAlertModal() {
    el('view-alert-modal').hidden = true;
  }

  return {
    showView, setLoading, toast,
    setLoginError, setLoginBusy,
    renderUser, clearUser,
    setPanel, renderAccountsList,
    openAccountModal, closeAccountModal, setModalBusy, setModalError,
    openConfirmModal,
    renderAlertsList, openAlertModal, closeAlertModal, setAlertModalBusy, setAlertModalError,
    openViewAlertModal, closeViewAlertModal,
    addPeriodItem: _addPeriodItem,
    addTranslationItem: _addTranslationItem,
    addEntityItem: _addEntityItem,
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
    _el('settings-gtfs-rt-path').value          = _current.gtfs_rt_path ?? 'realtime/service-alerts.pbf';
    _el('settings-gtfs-rt-username').value      = _current.gtfs_rt_username ?? '';
    _el('settings-gtfs-rt-password').value      = _current.gtfs_rt_password ?? '';
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
    const gtfsRtPath = _el('settings-gtfs-rt-path').value.trim();
    const gtfsRtUsername = _el('settings-gtfs-rt-username').value.trim();
    const gtfsRtPassword = _el('settings-gtfs-rt-password').value;
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
    if (!gtfsRtPath) {
      errEl.textContent = 'Bitte einen GTFS-RT Endpunkt-Pfad eingeben.';
      errEl.classList.add('is-visible');
      return;
    }

    const btn = _el('settings-save-btn');
    btn.disabled = true;
    _el('settings-save-spinner').hidden = false;
    _el('settings-save-label').textContent = 'Wird gespeichert ...';

    try {
      const saved = await api.saveSettings({
        app_title: appTitle,
        color_primary: p,
        color_secondary: s,
        gtfs_rt_path: gtfsRtPath,
        gtfs_rt_username: gtfsRtUsername,
        gtfs_rt_password: gtfsRtPassword,
      });
      _current = { ...saved };
      theme.apply(saved);
      ui.toast('Einstellungen gespeichert.', 'success');
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
    _el('settings-gtfs-import-label').textContent = busy ? 'Wird importiert …' : 'Importieren';
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
      _el('settings-gtfs-cron').value = s.cron ?? '';
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
    let cron  = _el('settings-gtfs-cron').value.trim();
    if (!cron) cron = null;
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
      await api.saveGtfsConfig({ feed_url: url, cron });
      ui.toast('Feed-URL und Cron gespeichert.', 'success');
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
    // Save URL and cron first so the backend is up-to-date
    const url  = _el('settings-gtfs-url').value.trim();
    let cron = _el('settings-gtfs-cron').value.trim();
    if (!cron) cron = null;
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      errEl.textContent = 'Bitte zuerst eine gültige Feed-URL eingeben.';
      errEl.classList.add('is-visible');
      return;
    }
    _setBusy(true);
    _showStatus('Import läuft …', 'running');
    try {
      await api.saveGtfsConfig({ feed_url: url, cron });
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

    // Restore session from sessionStorage
    if (state.isAuthenticated) {
      try {
        const user = await api.getMe();
        state.setAuth(state.token, user);
        ui.renderUser(user);
        ui.showView('app');
        ui.setPanel('alerts');
        _loadAlerts(); // Load alerts on startup
      } catch (err) {
        if (err.message !== 'SESSION_EXPIRED') {
          // Unexpected error: clear and show login with a message
          state.clearAuth();
          ui.showView('login');
          ui.toast('Sitzung konnte nicht wiederhergestellt werden.', 'error');
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
      _loadAlerts();
      form.reset();
      // No login toast
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
    // No logout toast
  }

  // -- Navigation ------------------------------------------------------------
  function handleNavClick(e) {
    const btn = e.target.closest('.nav-item[data-panel]');
    if (!btn) return;
    const panel = btn.dataset.panel;
    ui.setPanel(panel);
    if (panel === 'alerts') _loadAlerts();
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
    if (!user) { ui.toast('Account nicht gefunden.', 'error'); return; }
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
      ui.toast(userId ? 'Account aktualisiert.' : 'Account erstellt.', 'success');
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
      `Account „${user.username}" wirklich löschen? Diese Aktion ist unwiderruflich.`,
      'Account löschen'
    );
    if (!confirmed) return;
    try {
      await api.deleteUser(userId);
      await _loadAccounts();
      ui.toast(`Account „${user.username}“ wurde gelöscht.`);
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  // -- Alerts ----------------------------------------------------------------
  let _alerts = [];
  
  async function _loadAlerts() {
    document.getElementById('alerts-content').innerHTML =
      '<div class="panel__loading">Wird geladen ...</div>';
    try {
      _alerts = await api.getAlerts();
      ui.renderAlertsList(_alerts);
    } catch {
      document.getElementById('alerts-content').innerHTML =
        '<div class="panel__placeholder">Fehler beim Laden der Meldungen.</div>';
    }
  }

  function handleAlertsContentClick(e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const id = btn.dataset.id; // UUID as string
    if (btn.dataset.action === 'view')   _viewAlert(id);
    if (btn.dataset.action === 'edit')   _openEditAlert(id);
    if (btn.dataset.action === 'delete') _confirmDeleteAlert(id);
  }

  async function handleAddAlert() {
    await ui.openAlertModal({ title: 'Neue Meldung' });
    document.getElementById('alert-form').onsubmit = e => _saveAlert(e, null);
  }

  async function _viewAlert(alertId) {
    const alert = _alerts.find(a => a.id === alertId);
    if (!alert) { ui.toast('Meldung nicht gefunden.', 'error'); return; }
    await ui.openViewAlertModal(alert);
  }

  async function _openEditAlert(alertId) {
    const alert = _alerts.find(a => a.id === alertId);
    if (!alert) { ui.toast('Meldung nicht gefunden.', 'error'); return; }
    await ui.openAlertModal({ title: 'Meldung bearbeiten', alert });
    document.getElementById('alert-form').onsubmit = e => _saveAlert(e, alertId);
  }

  async function _saveAlert(e, alertId) {
    e.preventDefault();
    const form = e.currentTarget;
    
    // Collect all translations from the UI
    const translationItems = document.querySelectorAll('.alert-translation-item');
    const translations = [];
    
    translationItems.forEach(item => {
      const langInput = item.querySelector('.translation-lang');
      const headerInput = item.querySelector('.translation-header');
      const descInput = item.querySelector('.translation-desc');
      const urlInput = item.querySelector('.translation-url');
      
      const lang = langInput.value;
      const header = headerInput.value.trim();
      const desc = descInput.value.trim();
      const url = urlInput.value.trim();
      
      if (header) {
        translations.push({
          language: lang,
          header_text: header,
          description_text: desc || null,
          url: url || null
        });
      }
    });

    const cause = document.getElementById('alert-cause').value;
    const effect = document.getElementById('alert-effect').value;
    const severityLevel = document.getElementById('alert-severity').value;
    const isActive = document.getElementById('alert-is-active').checked;

    ui.setAlertModalError(null);
    if (translations.length === 0) {
      ui.setAlertModalError('Bitte mindestens eine Übersetzung mit Titel eingeben.');
      return;
    }

    // Collect all periods from the UI
    const periodItems = document.querySelectorAll('.alert-period-item');
    const activePeriods = [];
    
    periodItems.forEach(item => {
      const startInput = item.querySelector('.period-start');
      const endInput = item.querySelector('.period-end');
      const startStr = startInput.value;
      const endStr = endInput.value;
      
      // Only add period if at least start time is provided
      if (startStr) {
        const startTime = Math.floor(new Date(startStr).getTime() / 1000);
        const endTime = endStr ? Math.floor(new Date(endStr).getTime() / 1000) : null;
        activePeriods.push({ start_time: startTime, end_time: endTime });
      }
    });

    // Collect all informed entities from the UI
    const entityItems = document.querySelectorAll('.alert-entity-item');
    const informedEntities = [];
    
    entityItems.forEach(item => {
      // For each field: Use hidden input if filled, otherwise use visible input value
      const agencyIdHidden = item.querySelector('.entity-agency-id').value.trim();
      const agencyIdVisible = item.querySelector('.entity-agency-name').value.trim();
      const agencyId = agencyIdHidden || agencyIdVisible;
      
      const routeIdHidden = item.querySelector('.entity-route-id').value.trim();
      const routeIdVisible = item.querySelector('.entity-route-name').value.trim();
      const routeId = routeIdHidden || routeIdVisible;
      
      const stopIdHidden = item.querySelector('.entity-stop-id').value.trim();
      const stopIdVisible = item.querySelector('.entity-stop-name').value.trim();
      const stopId = stopIdHidden || stopIdVisible;
      
      const routeType = item.querySelector('.entity-route-type').value;
      const directionId = item.querySelector('.entity-direction-id').value;
      
      // Only add entity if at least one field is filled
      if (agencyId || routeId || routeType || stopId || directionId) {
        informedEntities.push({
          agency_id: agencyId || null,
          route_id: routeId || null,
          route_type: routeType ? parseInt(routeType, 10) : null,
          stop_id: stopId || null,
          trip_id: null, // Not yet implemented in UI
          direction_id: directionId ? parseInt(directionId, 10) : null,
        });
      }
    });

    const payload = {
      cause,
      effect,
      severity_level: severityLevel,
      is_active: isActive,
      translations: translations,
      active_periods: activePeriods,
      informed_entities: informedEntities,
    };

    ui.setAlertModalBusy(true);
    try {
      if (!alertId) {
        await api.createAlert(payload);
      } else {
        await api.updateAlert(alertId, payload);
      }
      ui.closeAlertModal();
      await _loadAlerts();
      ui.toast(alertId ? 'Meldung aktualisiert.' : 'Meldung erstellt.', 'success');
    } catch (err) {
      ui.setAlertModalError(err.message);
    } finally {
      ui.setAlertModalBusy(false);
    }
  }

  async function _confirmDeleteAlert(alertId) {
    const alert = _alerts.find(a => a.id === alertId);
    if (!alert) return;
    const deTrans = alert.translations.find(t => t.language === 'de') || {};
    const header = deTrans.header_text || 'Unbenannte Meldung';
    const confirmed = await ui.openConfirmModal(
      `Meldung „${header}" wirklich löschen? Diese Aktion ist unwiderruflich.`,
      'Meldung löschen'
    );
    if (!confirmed) return;
    try {
      await api.deleteAlert(alertId);
      await _loadAlerts();
      ui.toast(`Meldung „${header}" wurde gelöscht.`);
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  return {
    init, handleLogin, handleLogout, handleNavClick,
    handleAddAccount, handleAccountsContentClick,
    handleAddAlert, handleAlertsContentClick,
  };
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

  document.getElementById('logout-btn')?.addEventListener('click', app.handleLogout);
  document.getElementById('logout-card-btn')?.addEventListener('click', app.handleLogout);

  // Sidebar navigation
  document.querySelector('.sidebar').addEventListener('click', app.handleNavClick);

  // Accounts panel

  document.getElementById('add-account-btn')?.addEventListener('click', app.handleAddAccount);
  document.getElementById('accounts-content')?.addEventListener('click', app.handleAccountsContentClick);

  // Account modal

  document.getElementById('modal-cancel-btn')?.addEventListener('click', () => ui.closeAccountModal());
  document.getElementById('account-modal')?.querySelector('.modal__backdrop')
    ?.addEventListener('click', () => ui.closeAccountModal());

  // Alerts panel

  document.getElementById('add-alert-btn')?.addEventListener('click', app.handleAddAlert);
  document.getElementById('alerts-content')?.addEventListener('click', app.handleAlertsContentClick);

  // Alert modal

  document.getElementById('alert-modal-cancel-btn')?.addEventListener('click', () => ui.closeAlertModal());
  document.getElementById('alert-modal')?.querySelector('.modal__backdrop')
    ?.addEventListener('click', () => ui.closeAlertModal());
  document.getElementById('alert-add-period-btn')?.addEventListener('click', () => ui.addPeriodItem());
  document.getElementById('alert-add-translation-btn')?.addEventListener('click', () => ui.addTranslationItem());
  document.getElementById('alert-add-entity-btn')?.addEventListener('click', () => ui.addEntityItem());

  // View alert modal
  
  document.getElementById('view-alert-close-btn')?.addEventListener('click', () => ui.closeViewAlertModal());
  document.getElementById('view-alert-modal')?.querySelector('.modal__backdrop')
    ?.addEventListener('click', () => ui.closeViewAlertModal());

  // Alert modal tabs
  document.querySelectorAll('.modal__tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      const targetTab = e.currentTarget.getAttribute('data-tab');
      
      // Update tab buttons
      document.querySelectorAll('.modal__tab').forEach(t => {
        t.classList.remove('modal__tab--active');
        t.setAttribute('aria-selected', 'false');
      });
      e.currentTarget.classList.add('modal__tab--active');
      e.currentTarget.setAttribute('aria-selected', 'true');
      
      // Update tab panels
      document.querySelectorAll('.modal__tab-panel').forEach(panel => {
        panel.hidden = panel.getAttribute('data-tab') !== targetTab;
      });
    });
  });

  // Confirm modal backdrop

  document.getElementById('confirm-modal')?.querySelector('.modal__backdrop')
    ?.addEventListener('click', () => document.getElementById('confirm-cancel-btn')?.click());

  // Escape closes open modals
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (!document.getElementById('confirm-modal').hidden) {
      document.getElementById('confirm-cancel-btn').click();
    } else if (!document.getElementById('view-alert-modal').hidden) {
      ui.closeViewAlertModal();
    } else if (!document.getElementById('account-modal').hidden) {
      ui.closeAccountModal();
    } else if (!document.getElementById('alert-modal').hidden) {
      ui.closeAlertModal();
    }
  });

  // Settings panel
  settingsPanel.init();
  gtfsPanel.init();
  document.getElementById('settings-form').addEventListener('submit', settingsPanel.handleSave);
  document.getElementById('settings-reset-btn').addEventListener('click', settingsPanel.handleReset);

  app.init();
});

