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
      'Invalid credentials': window.i18n('error.invalid_credentials'),
      'User not found': window.i18n('error.user_not_found'),
      'User already exists': window.i18n('error.user_exists'),
      'Missing required fields': window.i18n('error.required_fields'),
      'Invalid email format': window.i18n('error.invalid_email'),
      'Password too short': window.i18n('error.password_short'),
      'Access denied': window.i18n('error.access_denied'),
      'Data source not found': window.i18n('error.source_not_found'),
      'Invalid cron expression': window.i18n('error.invalid_cron'),
      'Alert not found': window.i18n('error.alert_not_found'),
      'Cannot delete external alert': window.i18n('error.cannot_delete_external'),
      'Invalid active period': window.i18n('error.invalid_period'),
      'Missing translation': window.i18n('error.missing_translation'),
      'Invalid informed entity': window.i18n('error.invalid_entity'),
    };
    
    if (status === 422) return window.i18n('error.invalid_input');
    if (status === 409) return window.i18n('error.conflict');
    if (status === 500) return window.i18n('error.server_500');
    if (status === 503) return window.i18n('error.server_503');
    if (status >= 400 && status < 500) return translations[msg] || window.i18n('error.request_failed');
    if (status >= 500) return window.i18n('error.server_error');
    return translations[msg] || msg || window.i18n('error.unknown');
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
        throw new Error(window.i18n('error.network'));
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
    getAlerts(page = 1, limit = 20, sort = 'newest', search = '', filters = {}) {
      const params = new URLSearchParams({ page, limit, sort });
      if (search) {
        params.set('search', search);
      }
      // Add filter parameters if not all are selected
      if (filters.active !== undefined && filters.inactive !== undefined) {
        if (filters.active && !filters.inactive) {
          params.set('is_active', 'true');
        } else if (!filters.active && filters.inactive) {
          params.set('is_active', 'false');
        }
        // If both are true or both false, don't add the parameter (show all)
      }
      if (filters.internal !== undefined && filters.external !== undefined) {
        if (filters.internal && !filters.external) {
          params.set('has_data_source', 'false');
        } else if (!filters.internal && filters.external) {
          params.set('has_data_source', 'true');
        }
        // If both are true or both false, don't add the parameter (show all)
      }
      return request(`/alerts/?${params}`);
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

    toggleSourceActive(id) {
      return request(`/sources/${id}/toggle-active`, { method: 'POST' });
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
    el('login-btn-label').textContent = busy ? window.i18n('login.button.busy') : window.i18n('login.button');
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
        c.textContent = window.i18n('account.chip.active');
        chipsEl.appendChild(c);
      }
      if (user.is_superuser) {
        const c = document.createElement('span');
        c.className = 'md-chip md-chip--secondary';
        c.textContent = window.i18n('account.chip.admin');
        chipsEl.appendChild(c);
      }
      if (user.is_technical_contact) {
        const c = document.createElement('span');
        c.className = 'md-chip md-chip--secondary';
        c.textContent = window.i18n('account.chip.poweruser');
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
    if (detailRole) detailRole.textContent = user.is_superuser ? window.i18n('account.chip.admin') : (user.is_technical_contact ? window.i18n('account.chip.poweruser') : window.i18n('account.chip.standard'));

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
  function openConfirmModal(message, title = null) {
    return new Promise(resolve => {
      el('confirm-title').textContent = title || window.i18n('confirm.title');
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
  // Add translation item
  function _addTranslationItem(lang = 'de', headerText = '', descText = '', url = '') {
    const transId = _translationCounter++;
    const container = el('alert-translations-container');
    
    // Normalize to BCP47 base language code (remove region)
    const normalizedLang = lang.split('-')[0];
    
    const transDiv = document.createElement('div');
    transDiv.className = 'alert-translation-item';
    transDiv.dataset.transId = transId;
    
    transDiv.innerHTML = `
      <div class="alert-period-item__header">
        <span class="alert-period-item__title">${window.i18n('alert.translation.title', {number: container.children.length + 1})}</span>
        <button type="button" class="icon-btn icon-btn--danger" data-action="remove-translation" data-trans-id="${transId}" data-i18n-title="common.remove.title" title="Entfernen" data-ripple>
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </div>
      <div class="alert-period-item__fields">
        <div class="md-field" style="max-width: 200px;">
          <select class="md-field__input translation-lang">
            <option value="de" ${normalizedLang === 'de' ? 'selected' : ''}>${window.i18n('alert.translation.language.de')}</option>
            <option value="en" ${normalizedLang === 'en' ? 'selected' : ''}>${window.i18n('alert.translation.language.en')}</option>
            <option value="fr" ${normalizedLang === 'fr' ? 'selected' : ''}>${window.i18n('alert.translation.language.fr')}</option>
            <option value="it" ${normalizedLang === 'it' ? 'selected' : ''}>${window.i18n('alert.translation.language.it')}</option>
            <option value="es" ${normalizedLang === 'es' ? 'selected' : ''}>${window.i18n('alert.translation.language.es')}</option>
          </select>
          <label class="md-field__label" data-i18n="alert.translation.language">${window.i18n('alert.translation.language')}</label>
        </div>
        <div class="md-field">
          <input class="md-field__input translation-header" type="text" placeholder=" " maxlength="512" value="${esc(headerText)}" />
          <label class="md-field__label" data-i18n="alert.translation.header">${window.i18n('alert.translation.header')}</label>
        </div>
      </div>
      <div class="md-field">
        <textarea class="md-field__input translation-desc" placeholder=" " rows="3">${esc(descText)}</textarea>
        <label class="md-field__label" data-i18n="alert.translation.desc">${window.i18n('alert.translation.desc')}</label>
      </div>
      <div class="md-field">
        <input class="md-field__input translation-url" type="url" placeholder=" " maxlength="1024" value="${esc(url)}" />
        <label class="md-field__label" data-i18n="alert.translation.url">${window.i18n('alert.translation.url')}</label>
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
      item.querySelector('.alert-period-item__title').textContent = window.i18n('alert.translation.title', {number: idx + 1});
    });
  }
  
  function _clearTranslations() {
    el('alert-translations-container').innerHTML = '';
    _translationCounter = 0;
  }
  
  // Add period item
  function _addPeriodItem(startTime = null, endTime = null, periodType = 'impact_period') {
    const periodId = _periodCounter++;
    const container = el('alert-periods-container');
    
    const periodDiv = document.createElement('div');
    periodDiv.className = 'alert-period-item';
    periodDiv.dataset.periodId = periodId;
    
    const startVal = startTime ? _timestampToLocalDatetime(startTime) : '';
    const endVal = endTime ? _timestampToLocalDatetime(endTime) : '';
    
    periodDiv.innerHTML = `
      <div class="alert-period-item__header">
        <span class="alert-period-item__title">${window.i18n('alert.period.title', {number: container.children.length + 1})}</span>
        <button type="button" class="icon-btn icon-btn--danger" data-action="remove-period" data-period-id="${periodId}" data-i18n-title="common.remove.title" title="Entfernen" data-ripple>
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </div>
      <div class="alert-period-item__fields">
        <div class="md-field">
          <select class="md-field__input period-type">
            <option value="impact_period" ${periodType === 'impact_period' ? 'selected' : ''}>${window.i18n('alert.period.type.impact')}</option>
            <option value="communication_period" ${periodType === 'communication_period' ? 'selected' : ''}>${window.i18n('alert.period.type.communication')}</option>
          </select>
          <label class="md-field__label" data-i18n="alert.period.type">${window.i18n('alert.period.type')}</label>
        </div>
        <div class="md-field">
          <input class="md-field__input period-start" type="datetime-local" placeholder=" " value="${startVal}" />
          <label class="md-field__label" data-i18n="alert.period.start.label">${window.i18n('alert.period.start.label')}</label>
        </div>
        <div class="md-field">
          <input class="md-field__input period-end" type="datetime-local" placeholder=" " value="${endVal}" />
          <label class="md-field__label" data-i18n="alert.period.end.label">${window.i18n('alert.period.end.label')}</label>
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
      item.querySelector('.alert-period-item__title').textContent = window.i18n('alert.period.title', {number: idx + 1});
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
    
    // Use is_valid flag from API if available
    const isInvalid = entity.is_valid === false;
    
    if (entity.agency_id) {
      agencyName = entity.agency_name || entity.agency_id;
    }
    if (entity.route_id) {
      routeName = entity.route_name || entity.route_id;
    }
    if (entity.stop_id) {
      stopName = entity.stop_name || entity.stop_id;
    }
    
    entityDiv.innerHTML = `
      <div class="alert-period-item__header">
        <span class="alert-period-item__title">${window.i18n('alert.entity.title', {number: container.children.length + 1})}</span>
        <div class="alert-period-item__header-actions">
          ${isInvalid ? `<span class="resolution-warning resolution-warning--inline" data-i18n-title="alert.entity.invalid.tooltip" title="${window.i18n('alert.entity.invalid.tooltip')}">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>
          </span>` : ''}
          <button type="button" class="icon-btn icon-btn--danger" data-action="remove-entity" data-entity-id="${entityId}" data-i18n-title="common.remove.title" title="${window.i18n('common.remove.title')}" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>
      </div>
      <div class="alert-period-item__fields">
        <div class="md-field">
          <input class="md-field__input entity-agency-name autocomplete-input" type="text" placeholder=" " value="${esc(agencyName)}" data-autocomplete-type="agency" />
          <input type="hidden" class="entity-agency-id" value="${esc(entity.agency_id || '')}" />
          <label class="md-field__label" data-i18n="alert.entity.agency.label">${window.i18n('alert.entity.agency.label')}</label>
        </div>
        <div class="md-field">
          <input class="md-field__input entity-route-name autocomplete-input" type="text" placeholder=" " value="${esc(routeName)}" data-autocomplete-type="route" />
          <input type="hidden" class="entity-route-id" value="${esc(entity.route_id || '')}" />
          <label class="md-field__label" data-i18n="alert.entity.route.label">${window.i18n('alert.entity.route.label')}</label>
        </div>
      </div>
      <div class="alert-period-item__fields">
        <div class="md-field">
          <select class="md-field__input entity-route-type">
            <option value="" ${entity.route_type === null || entity.route_type === undefined ? 'selected' : ''}></option>
            <option value="0" ${entity.route_type === 0 ? 'selected' : ''}>${window.i18n('alert.entity.route_type.tram')}</option>
            <option value="1" ${entity.route_type === 1 ? 'selected' : ''}>${window.i18n('alert.entity.route_type.subway')}</option>
            <option value="2" ${entity.route_type === 2 ? 'selected' : ''}>${window.i18n('alert.entity.route_type.rail')}</option>
            <option value="3" ${entity.route_type === 3 ? 'selected' : ''}>${window.i18n('alert.entity.route_type.bus')}</option>
            <option value="4" ${entity.route_type === 4 ? 'selected' : ''}>${window.i18n('alert.entity.route_type.ferry')}</option>
            <option value="5" ${entity.route_type === 5 ? 'selected' : ''}>${window.i18n('alert.entity.route_type.cable_tram')}</option>
            <option value="6" ${entity.route_type === 6 ? 'selected' : ''}>${window.i18n('alert.entity.route_type.aerial_lift')}</option>
            <option value="7" ${entity.route_type === 7 ? 'selected' : ''}>${window.i18n('alert.entity.route_type.funicular')}</option>
          </select>
          <label class="md-field__label" data-i18n="alert.entity.route_type.label">${window.i18n('alert.entity.route_type.label')}</label>
        </div>
        <div class="md-field">
          <select class="md-field__input entity-direction-id">
            <option value="" ${entity.direction_id === null || entity.direction_id === undefined ? 'selected' : ''}></option>
            <option value="0" ${entity.direction_id === 0 ? 'selected' : ''}>${window.i18n('alert.entity.direction.outbound')}</option>
            <option value="1" ${entity.direction_id === 1 ? 'selected' : ''}>${window.i18n('alert.entity.direction.inbound')}</option>
          </select>
          <label class="md-field__label" data-i18n="alert.entity.direction.label">${window.i18n('alert.entity.direction.label')}</label>
        </div>
      </div>
      <div class="md-field">
        <input class="md-field__input entity-stop-name autocomplete-input" type="text" placeholder=" " value="${esc(stopName)}" data-autocomplete-type="stop" />
        <input type="hidden" class="entity-stop-id" value="${esc(entity.stop_id || '')}" />
        <label class="md-field__label" data-i18n="alert.entity.stop.label">${window.i18n('alert.entity.stop.label')}</label>
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
      item.querySelector('.alert-period-item__title').textContent = window.i18n('alert.entity.title', {number: idx + 1});
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
          _addPeriodItem(period.start_time, period.end_time, period.period_type || 'impact_period');
        });
      }
      
      // Populate existing informed entities (already enriched with names from API)
      if (alert.informed_entities && alert.informed_entities.length > 0) {
        for (const entity of alert.informed_entities) {
          _addEntityItem(entity);
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
        container.innerHTML = `<div class="panel__placeholder">${window.i18n('accounts.empty')}</div>`;
        return;
      }
      const table = document.createElement('table');
      table.className = 'user-table';
      table.innerHTML = `
        <thead><tr>
          <th data-i18n="accounts.table.username">${window.i18n('accounts.table.username')}</th>
          <th data-i18n="accounts.table.email">${window.i18n('accounts.table.email')}</th>
          <th data-i18n="accounts.table.role">${window.i18n('accounts.table.role')}</th>
          <th data-i18n="accounts.table.status">${window.i18n('accounts.table.status')}</th>
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
            ? `<span class="badge badge--system" data-i18n="accounts.role.admin">${window.i18n('accounts.role.admin')}</span>`
            : (user.is_technical_contact
              ? `<span class="badge badge--system" data-i18n="accounts.role.poweruser">${window.i18n('accounts.role.poweruser')}</span>`
              : `<span class="badge badge--system" data-i18n="accounts.role.standard">${window.i18n('accounts.role.standard')}</span>`)}</td>
          <td>${user.is_active
            ? `<span class="badge badge--system" data-i18n="accounts.status.active">${window.i18n('accounts.status.active')}</span>`
            : `<span class="badge badge--system" data-i18n="accounts.status.inactive">${window.i18n('accounts.status.inactive')}</span>`}</td>
          <td><div class="user-table__actions">
            <button class="icon-btn" data-action="edit" data-id="${user.id}"
              data-i18n-title="accounts.edit.tooltip" title="${window.i18n('accounts.edit.tooltip')}" data-i18n-aria-label="accounts.edit.aria" aria-label="${window.i18n('accounts.edit.aria', {name: user.username})}" data-ripple>
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
            </button>
            <button class="icon-btn icon-btn--danger" data-action="delete" data-id="${user.id}"
              data-i18n-title="accounts.delete.tooltip" title="${window.i18n('accounts.delete.tooltip')}" data-i18n-aria-label="accounts.delete.aria" aria-label="${window.i18n('accounts.delete.aria', {name: user.username})}" data-ripple>
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
      el('modal-password-hint').textContent = editMode ? window.i18n('account.password.hint.edit') : window.i18n('account.password.hint.create');
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
      el('modal-submit-label').textContent = busy ? window.i18n('loading.saving') : window.i18n('common.save');
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
    const firstTrans = alert.translations.find(t => t.language.startsWith('de')) || alert.translations[0] || {};
    const title = firstTrans.header_text || 'Meldung anzeigen';
    el('view-alert-title').textContent = title;
    
    // Helper: Get localized cause/effect/severity
    const getCauseText = (cause) => {
      const key = `alert.cause.${cause.toLowerCase().replace(/_/g, '.')}`;
      return window.i18n(key);
    };
    const getEffectText = (effect) => {
      const key = `alert.effect.${effect.toLowerCase().replace(/_/g, '.')}`;
      return window.i18n(key);
    };
    const getSeverityText = (severity) => {
      const key = `alert.severity.${severity.toLowerCase().replace(/_/g, '.')}`;
      return window.i18n(key);
    };
    const getRouteTypeText = (routeType) => {
      const types = [
        window.i18n('alert.entity.route_type.tram'),
        window.i18n('alert.entity.route_type.subway'),
        window.i18n('alert.entity.route_type.rail'),
        window.i18n('alert.entity.route_type.bus'),
        window.i18n('alert.entity.route_type.ferry'),
        window.i18n('alert.entity.route_type.cable_tram'),
        window.i18n('alert.entity.route_type.aerial_lift'),
        window.i18n('alert.entity.route_type.funicular')
      ];
      return types[routeType] || routeType;
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
    
    // Active Periods - group by period type
    let periodsHtml = '';
    if (alert.active_periods && alert.active_periods.length > 0) {
      // Group periods by type
      const periodsByType = {
        impact_period: [],
        communication_period: []
      };
      
      alert.active_periods.forEach(period => {
        const type = period.period_type || 'impact_period';
        if (periodsByType[type]) {
          periodsByType[type].push(period);
        }
      });
      
      const periodSections = [];
      
      // Impact periods (Gültigkeitszeitraum)
      if (periodsByType.impact_period.length > 0) {
        const impactPeriodsHtml = periodsByType.impact_period.map(p => {
          const start = p.start_time ? new Date(p.start_time * 1000).toLocaleDateString('de-DE', { 
            day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
          }) : '—';
          const end = p.end_time ? new Date(p.end_time * 1000).toLocaleDateString('de-DE', { 
            day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
          }) : '—';
          return `<div class="view-item view-item--entity"><div class="view-item__content">${start} – ${end}</div></div>`;
        }).join('');
        
        periodSections.push(`
          <div class="view-item">
            <div class="view-item__label">${window.i18n('alert.period.type.impact')}</div>
            <div class="view-item__content">
              ${impactPeriodsHtml}
            </div>
          </div>
        `);
      }
      
      // Communication periods (Veröffentlichungszeitraum)
      if (periodsByType.communication_period.length > 0) {
        const commPeriodsHtml = periodsByType.communication_period.map(p => {
          const start = p.start_time ? new Date(p.start_time * 1000).toLocaleDateString('de-DE', { 
            day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
          }) : '—';
          const end = p.end_time ? new Date(p.end_time * 1000).toLocaleDateString('de-DE', { 
            day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
          }) : '—';
          return `<div class="view-item view-item--entity"><div class="view-item__content">${start} – ${end}</div></div>`;
        }).join('');
        
        periodSections.push(`
          <div class="view-item">
            <div class="view-item__label">${window.i18n('alert.period.type.communication')}</div>
            <div class="view-item__content">
              ${commPeriodsHtml}
            </div>
          </div>
        `);
      }
      
      periodsHtml = periodSections.join('');
    } else {
      periodsHtml = `<div class="view-item view-item--entity"><div class="view-item__content"><em>${window.i18n('alert.period.always_valid')}</em></div></div>`;
    }
    
    // Informed Entities
    let entitiesHtml = '';
    if (alert.informed_entities && alert.informed_entities.length > 0) {
      entitiesHtml = alert.informed_entities.map(e => {
        const parts = [];
        if (e.agency_id) parts.push(`${window.i18n('alert.entity.label.agency')}: ${e.agency_name || e.agency_id}`);
        if (e.route_id) parts.push(`${window.i18n('alert.entity.label.route')}: ${e.route_name || e.route_id}`);
        if (e.route_type !== null && e.route_type !== undefined) {
          parts.push(`${window.i18n('alert.entity.label.route_type')}: ${getRouteTypeText(e.route_type)}`);
        }
        if (e.direction_id !== null && e.direction_id !== undefined) {
          parts.push(`${window.i18n('alert.entity.direction')}: ${e.direction_id === 0 ? window.i18n('alert.entity.direction.outbound') : window.i18n('alert.entity.direction.inbound')}`);
        }
        if (e.stop_id) parts.push(`${window.i18n('alert.entity.stop')}: ${e.stop_name || e.stop_id}`);
        if (e.trip_id) parts.push(`${window.i18n('alert.entity.label.trip')}: ${e.trip_id}`);
        
        const warning = e.is_valid === false
          ? `<span class="view-item__warning" title="${window.i18n('alert.entity.invalid.tooltip')}"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg></span>`
          : '';
        
        return `<div class="view-item view-item--entity"><div class="view-item__content">${parts.join(' • ')}</div>${warning}</div>`;
      }).join('');
    } else {
      entitiesHtml = `<div class="view-item view-item--entity"><div class="view-item__content"><em>${window.i18n('alert.entity.all_routes')}</em></div></div>`;
    }
    
    content.innerHTML = `
      <div class="view-section">
        <h3 class="view-section__title" data-i18n="alert.tabs.basics">${window.i18n('alert.tabs.basics')}</h3>
        <div class="view-item">
          <div class="view-item__label" data-i18n="alert.cause">${window.i18n('alert.cause')}</div>
          <div class="view-item__content">${getCauseText(alert.cause)}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label" data-i18n="alert.effect">${window.i18n('alert.effect')}</div>
          <div class="view-item__content">${getEffectText(alert.effect)}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label" data-i18n="alert.severity">${window.i18n('alert.severity')}</div>
          <div class="view-item__content">${getSeverityText(alert.severity_level)}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label" data-i18n="alert.view.status">${window.i18n('alert.view.status')}</div>
          <div class="view-item__content">${alert.is_active ? window.i18n('alert.active.yes') : window.i18n('alert.active.no')}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label" data-i18n="alert.view.source">${window.i18n('alert.view.source')}</div>
          <div class="view-item__content">${alert.source === 'echogtfs' ? window.i18n('alert.view.source.internal') : esc(alert.source)}</div>
        </div>
      </div>
      <div class="view-section">
        <h3 class="view-section__title" data-i18n="alert.tabs.validity">${window.i18n('alert.tabs.validity')}</h3>
        ${periodsHtml}
      </div>
      <div class="view-section">
        <h3 class="view-section__title" data-i18n="alert.tabs.references">${window.i18n('alert.tabs.references')}</h3>
        ${entitiesHtml}
      </div>
      <div class="view-section">
        <h3 class="view-section__title" data-i18n="alert.translation.translations">${window.i18n('alert.translation.translations')}</h3>
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