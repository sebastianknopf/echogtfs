/* ==========================================================================
   CORE - Base functionality for all modules
   API, UI helpers, theme, shared utilities
========================================================================== */

/* ==========================================================================
   API CLIENT
========================================================================== */
const api = (() => {
  const BASE_URL = '/api';
  
  function translateError(msg, status) {
    const translations = {
      'Invalid credentials': 'Ungültige Anmeldedaten.',
      'User not found': 'Benutzer nicht gefunden.',
      'User already exists': 'Benutzer existiert bereits.',
      'Missing required fields': 'Erforderliche Felder fehlen.',
      'Invalid email format': 'Ungültiges E-Mail-Format.',
      'Password too short': 'Passwort zu kurz.',
      'Access denied': 'Zugriff verweigert.',
      'Data source not found': 'Datenquelle nicht gefunden.',
      'Invalid cron expression': 'Ungültiger Cron-Ausdruck.',
      'Alert not found': 'Meldung nicht gefunden.',
      'Cannot delete external alert': 'Externe Meldungen können nicht gelöscht werden.',
      'Invalid active period': 'Ungültiger Aktivierungszeitraum.',
      'Missing translation': 'Übersetzung fehlt.',
      'Invalid informed entity': 'Ungültiger Bezug.',
    };
    
    if (status === 422) return 'Die Eingabedaten sind ungültig. Bitte überprüfen Sie Ihre Eingaben.';
    if (status === 409) return 'Konflikt: Die angeforderte Änderung ist nicht möglich.';
    if (status === 500) return 'Interner Serverfehler. Bitte versuchen Sie es später erneut.';
    if (status === 503) return 'Der Server ist vorübergehend nicht verfügbar.';
    if (status >= 400 && status < 500) return translations[msg] || 'Anfrage fehlgeschlagen.';
    if (status >= 500) return 'Serverfehler. Bitte wenden Sie sich an den Administrator.';
    return translations[msg] || msg || 'Ein unbekannter Fehler ist aufgetreten.';
  }

  async function request(path, options = {}, skipAuthRedirect = false) {
    const url = path.startsWith('http') ? path : `${BASE_URL}${path}`;
    const token = localStorage.getItem('auth-token');

    const config = {
      ...options,
      headers: {
        ...options.headers,
        ...(token && { 'Authorization': `Bearer ${token}` }),
      },
    };

    try {
      const response = await fetch(url, config);
      
      // Handle 204 No Content
      if (response.status === 204) {
        return null;
      }
      
      const contentType = response.headers.get('content-type');
      const isJson = contentType?.includes('application/json');
      const data = isJson ? await response.json() : await response.text();

      if (!response.ok) {
        if (response.status === 401 && !skipAuthRedirect) {
          localStorage.removeItem('auth-token');
          localStorage.removeItem('current-user');
          window.location.reload();
          return;
        }
        throw new Error(translateError(isJson ? data.detail : data, response.status));
      }

      return data;
    } catch (error) {
      if (error.name === 'TypeError' && error.message.includes('fetch')) {
        throw new Error('Der Server ist nicht erreichbar. Bitte überprüfen Sie Ihre Internetverbindung.');
      }
      throw error;
    }
  }

  return {
    // Auth
    login(credentials) {
      const formData = new FormData();
      formData.append('username', credentials.username);
      formData.append('password', credentials.password);
      
      return request('/auth/token', {
        method: 'POST',
        body: formData,
      }, true);
    },

    getMe() {
      return request('/users/me');
    },

    // Users
    getUsers() {
      return request('/users/');
    },

    getUser(id) {
      return request(`/users/${id}`);
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

    // Alerts
    getAlerts() {
      return request('/alerts/');
    },

    getAlert(id) {
      return request(`/alerts/${id}`);
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

    toggleAlertActive(id) {
      return request(`/alerts/${id}/toggle-active`, { method: 'POST' });
    },

    // Data sources
    getSources() {
      return request('/sources/');
    },

    getAdapterTypes() {
      return request('/sources/adapter-types');
    },

    getSource(id) {
      return request(`/sources/${id}`);
    },

    createSource(data) {
      return request('/sources/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },

    updateSource(id, data) {
      return request(`/sources/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },

    deleteSource(id) {
      return request(`/sources/${id}`, { method: 'DELETE' });
    },

    runSourceImport(id) {
      return request(`/sources/${id}/run`, { method: 'POST' });
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

    // Settings
    getSettings() {
      return request('/settings/');
    },

    updateSettings(data) {
      return request('/settings/', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },

    resetSettings() {
      // Backend doesn't have reset endpoint, so we'll use defaults
      return this.updateSettings({
        app_title: 'echogtfs',
        color_primary: '#008c99',
        color_secondary: '#99cc04',
        gtfs_rt_path: 'realtime/service-alerts.pbf',
        gtfs_rt_username: '',
        gtfs_rt_password: ''
      });
    },

    // GTFS Static Import
    getGtfsStatus() {
      return request('/gtfs/status');
    },

    updateGtfsFeedUrl(data) {
      return request('/gtfs/feed-url', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },

    triggerGtfsImport() {
      return request('/gtfs/import', {
        method: 'POST',
      });
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
    el('login-btn-label').textContent = busy ? 'Anmelden …' : 'Anmelden';
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
        c.textContent = 'Admin';
        chipsEl.appendChild(c);
      }
      if (user.is_technical_contact) {
        const c = document.createElement('span');
        c.className = 'md-chip md-chip--secondary';
        c.textContent = 'Poweruser';
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
    if (detailRole) detailRole.textContent = user.is_superuser ? 'Admin' : (user.is_technical_contact ? 'Poweruser' : 'Standard');

    // Show/hide poweruser-only sidebar items (for powerusers and admins)
    document.querySelectorAll('.nav-item[data-poweruser-only]').forEach(item => {
      item.hidden = !(user.is_technical_contact || user.is_superuser);
    });
    
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
    // Restore all poweruser-only and admin-only elements so the next login re-evaluates them
    document.querySelectorAll('[data-poweruser-only]').forEach(item => { item.hidden = false; });
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

  // XSS-safe string escaping
  function esc(str) {
    return String(str).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  }

  // Confirm dialog (returns Promise<boolean>)
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

  // Alert Modal State & Helpers
  // Counter for dynamic IDs - must be defined before functions!
  let _periodCounter = 0;
  let _translationCounter = 0;
  let _entityCounter = 0;
  
  let _autocompleteCache = { agencies: null, routes: null, stops: null };
  let _autocompleteDebounceTimers = {};
  
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
  
  // Fetch autocomplete data
  async function _fetchAutocompleteData(type, query = '') {
    try {
      if (type === 'agency') {
        if (!_autocompleteCache.agencies) {
          _autocompleteCache.agencies = await api.getAgencies();
        }
        return _autocompleteCache.agencies;
      } else if (type === 'route') {
        const data = await api.getRoutes(query);
        return data || [];
      } else if (type === 'stop') {
        const data = await api.getStops(query);
        return data || [];
      }
    } catch (error) {
      return [];
    }
    return [];
  }
  
  // Setup autocomplete for input field
  function _setupAutocomplete(input) {
    const type = input.dataset.autocompleteType;
    if (!type) return;
    
    const hiddenInput = input.parentElement.querySelector(`input[type="hidden"].entity-${type}-id`);
    if (!hiddenInput) {
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
    
    input.addEventListener('input', () => {
      if (_autocompleteDebounceTimers[type]) {
        clearTimeout(_autocompleteDebounceTimers[type]);
      }
      
      const query = input.value.trim();
      if (query.length >= 1) {
        _autocompleteDebounceTimers[type] = setTimeout(() => {
          showAutocomplete();
        }, 300);
      } else {
        closeAutocomplete();
        hiddenInput.value = '';
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
  
  // Enrich entity with names from GTFS data
  async function _enrichEntityWithNames(entity) {
    const enriched = { ...entity };
    let hasResolutionError = false;
    
    try {
      if (entity.agency_id && !entity.agency_name) {
        const agencies = await _fetchAutocompleteData('agency');
        const agency = agencies?.find(a => a.gtfs_id === entity.agency_id);
        if (agency) {
          enriched.agency_name = agency.name;
        } else {
          hasResolutionError = true;
        }
      }
      
      if (entity.route_id && !entity.route_name) {
        const routes = await api.getRoutes(entity.route_id);
        const route = routes?.find(r => r.gtfs_id === entity.route_id);
        if (route) {
          enriched.route_name = `${route.short_name} ${route.long_name}`;
        } else {
          hasResolutionError = true;
        }
      }
      
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
      hasResolutionError = true;
    }
    
    enriched.hasResolutionError = hasResolutionError;
    return enriched;
  }
  
  // Add translation item
  function _addTranslationItem(lang = 'de-DE', headerText = '', descText = '', url = '') {
    const transId = _translationCounter++;
    const container = el('alert-translations-container');
    
    // Normalize language code for backwards compatibility
    const normalizedLang = lang.includes('-') ? lang : 
      (lang === 'de' ? 'de-DE' : 
       lang === 'en' ? 'en-US' : 
       lang === 'fr' ? 'fr-FR' : 
       lang === 'it' ? 'it-IT' : 
       lang === 'es' ? 'es-ES' : lang);
    
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
            <option value="de-DE" ${normalizedLang === 'de-DE' ? 'selected' : ''}>Deutsch (DE)</option>
            <option value="en-US" ${normalizedLang === 'en-US' ? 'selected' : ''}>English (US)</option>
            <option value="en-GB" ${normalizedLang === 'en-GB' ? 'selected' : ''}>English (GB)</option>
            <option value="fr-FR" ${normalizedLang === 'fr-FR' ? 'selected' : ''}>Français (FR)</option>
            <option value="it-IT" ${normalizedLang === 'it-IT' ? 'selected' : ''}>Italiano (IT)</option>
            <option value="es-ES" ${normalizedLang === 'es-ES' ? 'selected' : ''}>Español (ES)</option>
          </select>
          <label class="md-field__label">Sprache</label>
        </div>
        <div class="md-field">
          <input class="md-field__input translation-header" type="text" placeholder=" " maxlength="512" value="${esc(headerText)}" />
          <label class="md-field__label">Titel</label>
        </div>
      </div>
      <div class="md-field">
        <textarea class="md-field__input translation-desc" placeholder=" " rows="3">${esc(descText)}</textarea>
        <label class="md-field__label">Beschreibung (optional)</label>
      </div>
      <div class="md-field">
        <input class="md-field__input translation-url" type="url" placeholder=" " maxlength="1024" value="${esc(url)}" />
        <label class="md-field__label">URL (optional)</label>
      </div>
    `;
    
    container.appendChild(transDiv);
    if (window.initRipples) initRipples(transDiv);
    
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
  
  // Add period item
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
    if (window.initRipples) initRipples(periodDiv);
    
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
  
  // Add entity item
  function _addEntityItem(entity = {}) {
    const entityId = _entityCounter++;
    const container = el('alert-entities-container');
    
    const entityDiv = document.createElement('div');
    entityDiv.className = 'alert-entity-item';
    entityDiv.dataset.entityId = entityId;
    
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
          <input class="md-field__input entity-agency-name autocomplete-input" type="text" placeholder=" " value="${esc(agencyName)}" data-autocomplete-type="agency" />
          <input type="hidden" class="entity-agency-id" value="${esc(entity.agency_id || '')}" />
          <label class="md-field__label">Unternehmen (optional)</label>
        </div>
        <div class="md-field">
          <input class="md-field__input entity-route-name autocomplete-input" type="text" placeholder=" " value="${esc(routeName)}" data-autocomplete-type="route" />
          <input type="hidden" class="entity-route-id" value="${esc(entity.route_id || '')}" />
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
      <div class="md-field">
        <input class="md-field__input entity-stop-name autocomplete-input" type="text" placeholder=" " value="${esc(stopName)}" data-autocomplete-type="stop" />
        <input type="hidden" class="entity-stop-id" value="${esc(entity.stop_id || '')}" />
        <label class="md-field__label">Haltestelle (optional)</label>
      </div>
    `;
    
    container.appendChild(entityDiv);
    if (window.initRipples) initRipples(entityDiv);
    
    entityDiv.querySelector('[data-action="remove-entity"]').addEventListener('click', () => {
      entityDiv.remove();
      _updateEntityTitles();
    });
    
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
  
  // Main openAlertModal function
  async function _openAlertModal({ title, alert = null } = {}) {
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
    
    // Populate form if editing
    if (alert) {
      el('alert-cause').value = alert.cause;
      el('alert-effect').value = alert.effect;
      el('alert-severity').value = alert.severity_level || 'UNKNOWN_SEVERITY';
      el('alert-is-active').checked = alert.is_active;
      
      // Populate existing translations
      if (alert.translations && alert.translations.length > 0) {
        alert.translations.forEach(trans => {
          _addTranslationItem(trans.language, trans.header_text, trans.description_text || '', trans.url || '');
        });
      } else {
        _addTranslationItem('de', '', '', '');
      }
      
      // Populate existing periods
      if (alert.active_periods && alert.active_periods.length > 0) {
        alert.active_periods.forEach(period => {
          _addPeriodItem(period.start_time, period.end_time);
        });
      }
      
      // Populate existing informed entities
      if (alert.informed_entities && alert.informed_entities.length > 0) {
        for (const entity of alert.informed_entities) {
          const enriched = await _enrichEntityWithNames(entity);
          _addEntityItem(enriched);
        }
      }
    } else {
      // New alert: initialize with one German translation
      _addTranslationItem('de', '', '', '');
    }
    
    // Reset to first tab (Grunddaten) - scope to alert-modal only
    const modal = el('alert-modal');
    modal.querySelectorAll('.modal__tab').forEach((tab, idx) => {
      const isFirst = idx === 0;
      tab.classList.toggle('modal__tab--active', isFirst);
      tab.setAttribute('aria-selected', isFirst ? 'true' : 'false');
    });
    modal.querySelectorAll('.modal__tab-panel').forEach((panel, idx) => {
      panel.hidden = idx !== 0;
    });
    
    modal.hidden = false;
    setTimeout(() => {
      el('alert-cause').focus();
    }, 50);
  }
  
  function _closeAlertModal() {
    el('alert-modal').hidden = true;
  }
  
  function _setAlertModalBusy(busy) {
    el('alert-modal-submit-btn').disabled = busy;
    el('alert-modal-submit-spinner').hidden = !busy;
    el('alert-modal-submit-label').textContent = busy ? 'Wird gespeichert ...' : 'Speichern';
  }
  
  function _setAlertModalError(msg) {
    const e = el('alert-modal-error');
    e.textContent = msg ?? '';
    e.classList.toggle('is-visible', !!msg);
  }

  // ==========================================================================
  // UI MODULE EXPORTS
  // ==========================================================================
  return {
    // Export element helper for modules
    el,
    // Views
    showView, setLoading,
    // Toast 
    toast,
    // Login
    setLoginError, setLoginBusy,
    // User
    renderUser, clearUser,
    // Panel navigation
    setPanel,
    // Utilities
    esc, openConfirmModal,
    // Account rendering
    renderAccountsList: function(users) {
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
          <td>${esc(user.username)}</td>
          <td>${esc(user.email)}</td>
          <td>${user.is_superuser
            ? '<span class="badge badge--system">Admin</span>'
            : (user.is_technical_contact
              ? '<span class="badge badge--system">Poweruser</span>'
              : '<span class="badge badge--system">Standard</span>')}</td>
          <td>${user.is_active
            ? '<span class="badge badge--system">Aktiv</span>'
            : '<span class="badge badge--system">Inaktiv</span>'}</td>
          <td><div class="user-table__actions">
            <button class="icon-btn" data-action="edit" data-id="${user.id}"
              title="Bearbeiten" aria-label="Account ${esc(user.username)} bearbeiten" data-ripple>
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
            </button>
            <button class="icon-btn icon-btn--danger" data-action="delete" data-id="${user.id}"
              title="Löschen" aria-label="Account ${esc(user.username)} löschen" data-ripple>
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
            </button>
          </div></td>`;
        tbody.appendChild(tr);
      });
      container.innerHTML = '';
      container.appendChild(table);
      if (window.initRipples) initRipples(container);
    },
    openAccountModal: function(options = {}) {
      const {
        title = 'Account',
        username = '',
        email = '',
        isActive = true,
        isSuperuser = false,
        isTechnicalContact = false,
        editMode = false
      } = options;
      
      el('modal-title').textContent = title;
      el('modal-username').value = username;
      el('modal-username').readOnly = editMode;
      el('modal-email').value = email;
      el('modal-password').value = '';
      el('modal-is-active').checked = isActive;
      el('modal-is-superuser').checked = isSuperuser;
      el('modal-is-technical-contact').checked = isTechnicalContact;
      el('modal-password-hint').textContent = editMode ? 'Leer lassen, um das Passwort nicht zu ändern.' : '';
      el('modal-error').textContent = '';
      el('modal-error').classList.remove('is-visible');
      el('account-modal').hidden = false;
      (editMode ? el('modal-email') : el('modal-username')).focus();
    },
    closeAccountModal: function() {
      el('account-modal').hidden = true;
    },
    setModalBusy: function(busy) {
      el('modal-submit-btn').disabled = busy;
      el('modal-submit-spinner').hidden = !busy;
      el('modal-submit-label').textContent = busy ? 'Wird gespeichert ...' : 'Speichern';
    },
    setModalError: function(msg) {
      const e = el('modal-error');
      e.textContent = msg ?? '';
      e.classList.toggle('is-visible', !!msg);
    },
    openAlertModal: function(...args) {
      return _openAlertModal(...args);
    },
    closeAlertModal: function() {
      return _closeAlertModal();
    },
    setAlertModalBusy: function(...args) {
      return _setAlertModalBusy(...args);
    },
    setAlertModalError: function(...args) {
      return _setAlertModalError(...args);
    },
    addTranslationItem: function(...args) {
      return _addTranslationItem(...args);
    },
    addPeriodItem: function(...args) {
      return _addPeriodItem(...args);
    },
    addEntityItem: function(...args) {
      return _addEntityItem(...args);
    },
    openViewAlertModal: function(alert) {
      return _renderViewAlertModal(alert);
    },
    closeViewAlertModal: function() {
      el('view-alert-modal').hidden = true;
    },
  };

  // Helper function for view alert modal (too large to inline)
  function _renderViewAlertModal(alert) {
    const content = el('view-alert-content');
    
    // Set modal title
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
    let translationsHtml = alert.translations && alert.translations.length > 0
      ? alert.translations.map(t => `
          <div class="view-item">
            <div class="view-item__label">${esc(t.language.toUpperCase())}</div>
            <div class="view-item__content">
              <strong>${esc(t.header_text || '—')}</strong>
              ${t.description_text ? `<p style="margin-top: 4px;">${esc(t.description_text)}</p>` : ''}
              ${t.url ? `<p style="margin-top: 4px;"><a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.url)}</a></p>` : ''}
            </div>
          </div>
        `).join('')
      : '';
    
    // Active Periods
    let periodsHtml = '';
    if (alert.active_periods && alert.active_periods.length > 0) {
      periodsHtml = alert.active_periods.map(p => {
        const start = p.start_time ? new Date(p.start_time * 1000).toLocaleDateString('de-DE', { 
          day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
        }) : '—';
        const end = p.end_time ? new Date(p.end_time * 1000).toLocaleDateString('de-DE', { 
          day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
        }) : '—';
        return `<div class="view-item view-item--entity"><div class="view-item__content">${start} – ${end}</div></div>`;
      }).join('');
    } else {
      periodsHtml = '<div class="view-item view-item--entity"><div class="view-item__content"><em>Dauerhaft gültig</em></div></div>';
    }
    
    // Informed Entities
    let entitiesHtml = '';
    if (alert.informed_entities && alert.informed_entities.length > 0) {
      entitiesHtml = alert.informed_entities.map(e => {
        const parts = [];
        if (e.agency_id) parts.push(`Unternehmen: ${e.agency_name || e.agency_id}`);
        if (e.route_id) parts.push(`Linie: ${e.route_name || e.route_id}`);
        if (e.route_type !== null && e.route_type !== undefined) {
          const types = ['Straßenbahn', 'U-Bahn', 'Zug', 'Bus', 'Fähre', 'Seilbahn', 'Gondel', 'Standseilbahn'];
          parts.push(`Linientyp: ${types[e.route_type] || e.route_type}`);
        }
        if (e.direction_id !== null && e.direction_id !== undefined) {
          parts.push(`Richtung: ${e.direction_id === 0 ? 'Hinfahrt' : 'Rückfahrt'}`);
        }
        if (e.stop_id) parts.push(`Haltestelle: ${e.stop_name || e.stop_id}`);
        if (e.trip_id) parts.push(`Fahrt: ${e.trip_id}`);
        
        const warning = e.hasResolutionError 
          ? '<span class="view-item__warning" title="Bezug konnte nicht aufgelöst werden"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg></span>'
          : '';
        
        return `<div class="view-item view-item--entity"><div class="view-item__content">${parts.join(' • ')}</div>${warning}</div>`;
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
          <div class="view-item__content">${alert.source === 'echogtfs' ? 'Intern (echogtfs)' : esc(alert.source)}</div>
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

})();

/* ==========================================================================
   Ripple Effects - Material Design
========================================================================== */
function initRipples(container = document.body) {
  container.querySelectorAll('[data-ripple]:not([data-ripple-initialized])').forEach(element => {
    element.setAttribute('data-ripple-initialized', 'true');
    element.style.position = 'relative';
    element.style.overflow = 'hidden';
    element.addEventListener('click', event => {
      const ripple = document.createElement('div');
      const rect = element.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      const x = event.clientX - rect.left - size / 2;
      const y = event.clientY - rect.top - size / 2;
      ripple.style.cssText = `
        position: absolute; border-radius: 50%; background: rgba(255,255,255,0.3);
        width: ${size}px; height: ${size}px; left: ${x}px; top: ${y}px;
        transform: scale(0); animation: ripple 0.6s ease-out;
        pointer-events: none;
      `;
      element.appendChild(ripple);
      setTimeout(() => ripple.remove(), 600);
    });
  });
}

/* ==========================================================================
   GLOBAL APP STATE & INITIALIZATION
========================================================================== */
window.appState = {
  currentUser: null,
  isAuthenticated: false,
};

// CSS Animation for ripples
if (!document.querySelector('#ripple-styles')) {
  const style = document.createElement('style');
  style.id = 'ripple-styles';
  style.textContent = `@keyframes ripple { to { transform: scale(2); opacity: 0; } }`;
  document.head.appendChild(style);
}