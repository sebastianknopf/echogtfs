/* ==========================================================================
   ALERTS MODULE - Alerts management
========================================================================== */

const alerts = (() => {
  let _alerts = [];
  let _sources = [];
  let _filterText = '';
  let _sortOrder = 'newest';
  let _currentPage = 1;
  let _totalPages = 1;
  let _total = 0;
  let _filterTimeout = null; // For debouncing filter input
  
  // Cache for GTFS entity data to avoid redundant API calls
  let _agenciesCache = null;
  let _routesCache = {}; // Keyed by route_id
  let _stopsCache = {}; // Keyed by stop_id

  // Helper to check if user has poweruser or admin rights
  function _isPoweruser() {
    const user = window.appState?.currentUser;
    return user && (user.is_technical_contact || user.is_superuser);
  }

  // Helper function to get agencies (cached)
  async function _getCachedAgencies() {
    if (_agenciesCache === null) {
      _agenciesCache = await api.getAgencies();
    }
    return _agenciesCache;
  }

  // Helper function to get routes (cached)
  async function _getCachedRoutes(routeId) {
    if (!_routesCache[routeId]) {
      _routesCache[routeId] = await api.getRoutes(routeId);
    }
    return _routesCache[routeId];
  }

  // Helper function to get stops (cached)
  async function _getCachedStops(stopId) {
    if (!_stopsCache[stopId]) {
      _stopsCache[stopId] = await api.getStops(stopId);
    }
    return _stopsCache[stopId];
  }

  // Clear all caches
  function _clearCache() {
    _agenciesCache = null;
    _routesCache = {};
    _stopsCache = {};
  }

  // Enrich entity with names from GTFS data
  async function _enrichEntityWithNames(entity) {
    const enriched = { ...entity, hasResolutionError: false };
    
    try {
      if (entity.agency_id) {
        const agencies = await _getCachedAgencies();
        const agency = agencies.find(a => a.gtfs_id === entity.agency_id);
        if (agency) {
          enriched.agency_name = agency.name;
        } else {
          enriched.hasResolutionError = true;
        }
      }
      
      if (entity.route_id) {
        const routes = await _getCachedRoutes(entity.route_id);
        const route = routes.find(r => r.gtfs_id === entity.route_id);
        if (route) {
          // Combine short_name and long_name for full route display
          const parts = [];
          if (route.short_name) parts.push(route.short_name);
          if (route.long_name) parts.push(route.long_name);
          enriched.route_name = parts.length > 0 ? parts.join(' – ') : 'Unbekannte Linie';
        } else {
          enriched.hasResolutionError = true;
        }
      }
      
      if (entity.stop_id) {
        const stops = await _getCachedStops(entity.stop_id);
        const stop = stops.find(s => s.gtfs_id === entity.stop_id);
        if (stop) {
          enriched.stop_name = stop.name;
        } else {
          enriched.hasResolutionError = true;
        }
      }
    } catch (err) {
      enriched.hasResolutionError = true;
    }
    
    return enriched;
  }

  // Get page from URL parameter
  function _getPageFromURL() {
    const params = new URLSearchParams(window.location.search);
    const page = parseInt(params.get('page'), 10);
    return (page && page > 0) ? page : 1;
  }
  
  // Set page in URL parameter
  function _setPageInURL(page) {
    const params = new URLSearchParams(window.location.search);
    if (page === 1) {
      params.delete('page');
    } else {
      params.set('page', page);
    }
    const newURL = params.toString() ? `?${params}` : window.location.pathname;
    window.history.pushState({}, '', newURL);
  }

  async function _loadAlerts() {
    const container = ui.el('alerts-content');
    container.innerHTML = '<div class="panel__loading">Wird geladen ...</div>';
    
    // Clear cache when reloading alerts to get fresh data
    _clearCache();
    
    // Get page from URL
    _currentPage = _getPageFromURL();
    
    try {
      // Load alerts and sources (if user has poweruser rights)
      const requests = [api.getAlerts(_currentPage, 20, _sortOrder, _filterText)];
      
      if (_isPoweruser()) {
        requests.push(api.getSources().catch(() => []));
      } else {
        requests.push(Promise.resolve([]));
      }
      
      const [alertsResponse, sources] = await Promise.all(requests);
      
      _alerts = alertsResponse.items;
      _currentPage = alertsResponse.page;
      _totalPages = alertsResponse.total_pages;
      _total = alertsResponse.total;
      _sources = sources;
      
      await _renderAlertsList();
    } catch (err) {
      container.innerHTML = '<div class="panel__placeholder">Fehler beim Laden der Meldungen.</div>';
    }
  }

  // Match filter with wildcards
  function _matchesFilter(text, filter) {
    if (!filter) return true;
    if (!text) return false;
    
    // Add wildcards if not present
    let searchPattern = filter;
    if (!searchPattern.startsWith('*')) {
      searchPattern = '*' + searchPattern;
    }
    if (!searchPattern.endsWith('*')) {
      searchPattern = searchPattern + '*';
    }
    
    // Convert wildcard pattern to regex and escape special chars
    const escapedFilter = searchPattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
    const pattern = '^' + escapedFilter.replace(/\*/g, '.*') + '$';
    const regex = new RegExp(pattern, 'i');
    
    return regex.test(text);
  }

  // Get start time from alert for sorting
  function _getAlertStartTime(alert) {
    if (alert.active_periods && alert.active_periods.length > 0 && alert.active_periods[0].start_time) {
      return alert.active_periods[0].start_time;
    }
    return Infinity;
  }

  // Sort alerts based on current sort order
  function _sortAlerts(alerts) {
    // Sorting is now done on the backend, no need to sort here
    return alerts;
  }

  async function _renderAlertsList() {
    const container = ui.el('alerts-content');
    if (!_alerts.length) {
      const message = _filterText 
        ? '<div class="panel__placeholder">Keine Meldungen entsprechen dem Filter.</div>'
        : '<div class="panel__placeholder">Aktuell sind noch keine Meldungen verfügbar.</div>';
      container.innerHTML = message;
      return;
    }
    
    // No local filtering needed - backend handles it
    const displayAlerts = _alerts;
    
    container.innerHTML = '<ul class="alert-list"></ul>';
    const list = container.querySelector('.alert-list');
    
    // Create skeleton placeholders for all alerts
    const skeletonItems = [];
    for (let i = 0; i < displayAlerts.length; i++) {
      const skeleton = document.createElement('li');
      skeleton.className = 'alert-list-item alert-list-item--loading';
      skeleton.innerHTML = `
        <div class="alert-skeleton">
          <div class="alert-skeleton__spinner"></div>
          <div class="alert-skeleton__content">
            <div class="alert-skeleton__line alert-skeleton__line--title"></div>
            <div class="alert-skeleton__line alert-skeleton__line--subtitle"></div>
          </div>
        </div>
      `;
      list.appendChild(skeleton);
      skeletonItems.push(skeleton);
    }
    
    // Render alerts one by one, replacing skeletons
    for (let i = 0; i < displayAlerts.length; i++) {
      const alert = displayAlerts[i];
      const item = document.createElement('li');
      item.className = 'alert-list-item' + (alert.is_active ? '' : ' alert-list-item--inactive');
      
      // Get first translation (prefer German)
      const firstTrans = alert.translations.find(t => t.language.startsWith('de')) || alert.translations[0] || {};
      const title = firstTrans.header_text || 'Keine Überschrift';
      
      // Get start date from first active period and end date from last period
      let startDate = '';
      let endDate = '';
      if (alert.active_periods && alert.active_periods.length > 0) {
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
      
      // Build source badge
      const isInternal = alert.source === 'echogtfs' || !alert.data_source_id;
      let sourceName = 'Intern';
      if (!isInternal && alert.data_source_id) {
        const source = _sources.find(s => s.id === alert.data_source_id);
        sourceName = source ? source.name : 'Extern';
      }
      const sourceBadge = `<span class="badge badge--system">${ui.esc(sourceName)}</span>`;
      
      // Build entity badges with name resolution (limit to first 10 in list view)
      let entityBadges = '';
      let hasResolutionErrors = false;
      if (alert.informed_entities && alert.informed_entities.length > 0) {
        const maxEntitiesInList = 10;
        const entitiesToResolve = alert.informed_entities.slice(0, maxEntitiesInList);
        const hasMoreEntities = alert.informed_entities.length > maxEntitiesInList;
        
        const enrichedEntities = await Promise.all(
          entitiesToResolve.map(entity => _enrichEntityWithNames(entity))
        );
        
        hasResolutionErrors = enrichedEntities.some(e => e.hasResolutionError);
        
        entityBadges = enrichedEntities.map(entity => {
          const labels = [];
          if (entity.agency_name) labels.push(entity.agency_name);
          if (entity.route_name) labels.push(entity.route_name);
          if (entity.stop_name) labels.push(entity.stop_name);
          
          return labels.map(label => 
            `<span class="badge badge--entity">${ui.esc(label)}</span>`
          ).join('');
        }).join('');
        
        // Add "..." badge if there are more entities
        if (hasMoreEntities) {
          entityBadges += '<span class="badge badge--entity">...</span>';
        }
      }
      
      item.innerHTML = `
        <div class="alert-list-item__content">
          <div class="alert-list-item__header">
            <h3 class="alert-list-item__title">${ui.esc(title)}</h3>
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
          ${isInternal ? `<button class="icon-btn" data-action="edit" data-id="${alert.id}" title="Bearbeiten" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
          </button>` : ''}
          ${isInternal ? `<button class="icon-btn icon-btn--danger" data-action="delete" data-id="${alert.id}" title="Löschen" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          </button>` : ''}
          <button class="icon-btn ${alert.is_active ? 'icon-btn--success' : 'icon-btn--warning'}" data-action="toggle" data-id="${alert.id}" title="${alert.is_active ? 'Deaktivieren' : 'Aktivieren'}" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.59-5.41L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z"/></svg>
          </button>
        </div>
      `;
      
      // Replace skeleton with actual content
      list.replaceChild(item, skeletonItems[i]);
    }
    
    if (window.initRipples) initRipples(container);
    
    // Render pagination controls
    _renderPagination(container);
  }
  
  function _renderPagination(container) {
    // Only show pagination if there are multiple pages
    if (_totalPages <= 1) return;
    
    const paginationHTML = `
      <div class="pagination">
        <div class="pagination__info">
          Seite ${_currentPage} von ${_totalPages} (${_total} Meldungen)
        </div>
        <div class="pagination__controls">
          <button class="pagination__btn" data-page="1" ${_currentPage === 1 ? 'disabled' : ''}>
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.41 16.59L13.82 12l4.59-4.59L17 6l-6 6 6 6 1.41-1.41zM6 6h2v12H6V6z"/>
            </svg>
          </button>
          <button class="pagination__btn" data-page="${_currentPage - 1}" ${_currentPage === 1 ? 'disabled' : ''}>
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12l4.58-4.59z"/>
            </svg>
          </button>
          <span class="pagination__pages">${_currentPage} / ${_totalPages}</span>
          <button class="pagination__btn" data-page="${_currentPage + 1}" ${_currentPage === _totalPages ? 'disabled' : ''}>
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6-6-6z"/>
            </svg>
          </button>
          <button class="pagination__btn" data-page="${_totalPages}" ${_currentPage === _totalPages ? 'disabled' : ''}>
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M5.59 7.41L10.18 12l-4.59 4.59L7 18l6-6-6-6-1.41 1.41zM16 6h2v12h-2V6z"/>
            </svg>
          </button>
        </div>
      </div>
    `;
    
    container.insertAdjacentHTML('beforeend', paginationHTML);
    
    // Add click handlers for pagination buttons
    container.querySelectorAll('.pagination__btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const page = parseInt(btn.dataset.page, 10);
        if (page && page !== _currentPage) {
          _goToPage(page);
        }
      });
    });
  }
  
  async function _goToPage(page) {
    _currentPage = page;
    _setPageInURL(page);
    await _loadAlerts();
  }

 
  async function _confirmDelete(alertId) {
    const alert = _alerts.find(a => a.id === alertId);
    if (!alert) return;
    
    const deTrans = alert.translations.find(t => t.language.startsWith('de')) || {};
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

  async function _viewAlert(alertId) {
    const alert = _alerts.find(a => a.id === alertId);
    if (!alert) {
      ui.toast('Meldung nicht gefunden.', 'error');
      return;
    }
    
    // Enrich entities before showing
    const enrichedAlert = { ...alert };
    if (alert.informed_entities && alert.informed_entities.length > 0) {
      enrichedAlert.informed_entities = await Promise.all(
        alert.informed_entities.map(entity => _enrichEntityWithNames(entity))
      );
    }
    
    await ui.openViewAlertModal(enrichedAlert);
  }

  async function _openEditAlert(alertId) {
    const alert = _alerts.find(a => a.id === alertId);
    if (!alert) {
      ui.toast('Meldung nicht gefunden.', 'error');
      return;
    }
    
    await ui.openAlertModal({
      title: 'Meldung bearbeiten',
      alert: alert
    });
    
    // Setup form submit handler with alert ID for update
    document.getElementById('alert-form').onsubmit = e => _saveAlert(e, alertId);
  }

  async function _toggleAlert(alertId) {
    try {
      const result = await api.toggleAlertActive(alertId);
      
      // Update alert in local array
      const alert = _alerts.find(a => a.id === alertId);
      if (alert) {
        // Use result.is_active if available, otherwise toggle manually
        alert.is_active = result?.is_active !== undefined ? result.is_active : !alert.is_active;
      }
      
      // Update DOM without full reload
      const alertItems = document.querySelectorAll('.alert-list-item');
      alertItems.forEach(item => {
        const toggleBtn = item.querySelector(`[data-action="toggle"][data-id="${alertId}"]`);
        if (toggleBtn) {
          const isActive = alert.is_active;
          
          // Update list item class
          item.classList.toggle('alert-list-item--inactive', !isActive);
          
          // Update toggle button
          toggleBtn.classList.toggle('icon-btn--success', isActive);
          toggleBtn.classList.toggle('icon-btn--warning', !isActive);
          toggleBtn.title = isActive ? 'Deaktivieren' : 'Aktivieren';
          
          // Update/remove inactive badge
          const header = item.querySelector('.alert-list-item__header');
          const badgesContainer = header?.querySelector('.alert-list-item__badges');
          if (badgesContainer) {
            let inactiveBadge = Array.from(badgesContainer.children).find(
              badge => badge.textContent === 'Inaktiv'
            );
            
            if (!isActive && !inactiveBadge) {
              // Add inactive badge
              const badge = document.createElement('span');
              badge.className = 'badge badge--system';
              badge.textContent = 'Inaktiv';
              badgesContainer.appendChild(badge);
            } else if (isActive && inactiveBadge) {
              // Remove inactive badge
              inactiveBadge.remove();
            }
          }
        }
      });
      
      ui.toast('Meldungsstatus geändert.', 'success');
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  async function _openCreateAlert() {
    await ui.openAlertModal({
      title: 'Neue Meldung erstellen',
      alert: null
    });
    
    // Setup form submit handler for create mode
    document.getElementById('alert-form').onsubmit = e => _saveAlert(e, null);
  }
  
  async function _saveAlert(e, alertId) {
    e.preventDefault();
    
    // Collect all translations from the UI
    const translationItems = document.querySelectorAll('.alert-translation-item');
    const translations = [];
    
    translationItems.forEach(item => {
      const lang = item.querySelector('.translation-lang').value;
      const header = item.querySelector('.translation-header').value.trim();
      const desc = item.querySelector('.translation-desc').value.trim();
      const url = item.querySelector('.translation-url').value.trim();
      
      if (header) {
        translations.push({
          language: lang,
          header_text: header,
          description_text: desc || null,
          url: url || null
        });
      }
    });

    const cause = ui.el('alert-cause').value;
    const effect = ui.el('alert-effect').value;
    const severityLevel = ui.el('alert-severity').value;
    const isActive = ui.el('alert-is-active').checked;

    ui.setAlertModalError('');
    if (translations.length === 0) {
      ui.setAlertModalError('Bitte mindestens eine Übersetzung mit Titel eingeben.');
      return;
    }

    // Collect all periods from the UI
    const periodItems = document.querySelectorAll('.alert-period-item');
    const activePeriods = [];
    
    periodItems.forEach(item => {
      const startVal = item.querySelector('.period-start').value;
      const endVal = item.querySelector('.period-end').value;
      
      // Only add period if at least start time is provided
      if (startVal) {
        const startTime = Math.floor(new Date(startVal).getTime() / 1000);
        const endTime = endVal ? Math.floor(new Date(endVal).getTime() / 1000) : null;
        activePeriods.push({ start_time: startTime, end_time: endTime });
      }
    });

    // Collect all informed entities from the UI
    const entityItems = document.querySelectorAll('.alert-entity-item');
    const informedEntities = [];
    
    entityItems.forEach(item => {
      // For each field: Use hidden input if filled
      const agencyIdHidden = item.querySelector('.entity-agency-id').value.trim();
      const routeIdHidden = item.querySelector('.entity-route-id').value.trim();
      const stopIdHidden = item.querySelector('.entity-stop-id').value.trim();
      
      const routeType = item.querySelector('.entity-route-type').value;
      const directionId = item.querySelector('.entity-direction-id').value;
      
      // Only add entity if at least one field is filled
      if (agencyIdHidden || routeIdHidden || routeType || stopIdHidden || directionId) {
        const entity = {};
        if (agencyIdHidden) entity.agency_id = agencyIdHidden;
        if (routeIdHidden) entity.route_id = routeIdHidden;
        if (routeType !== '') entity.route_type = parseInt(routeType, 10);
        if (directionId !== '') entity.direction_id = parseInt(directionId, 10);
        if (stopIdHidden) entity.stop_id = stopIdHidden;
        informedEntities.push(entity);
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

  function _handleFilterChange(e) {
    _filterText = e.target.value.trim();
    
    // Clear existing timeout
    if (_filterTimeout) {
      clearTimeout(_filterTimeout);
    }
    
    // Debounce: wait 300ms after user stops typing
    _filterTimeout = setTimeout(() => {
      // Reset to first page when filtering
      _currentPage = 1;
      _setPageInURL(1);
      // Reload alerts with filter from backend
      _loadAlerts();
    }, 300);
  }

  function _toggleSortOrder() {
    _sortOrder = _sortOrder === 'newest' ? 'oldest' : 'newest';
    
    // Save to localStorage
    try {
      localStorage.setItem('echogtfs_alerts_sort', _sortOrder);
    } catch (err) {
    }
    
    // Update button label
    _updateSortButton();
    
    // Sort order is now handled by backend, reload alerts
    _currentPage = 1; // Reset to first page when changing sort
    _setPageInURL(1);
    _loadAlerts();
  }

  function _updateSortButton() {
    const label = ui.el('sort-alerts-label');
    if (label) {
      label.textContent = _sortOrder === 'newest' ? 'neueste zuerst' : 'älteste zuerst';
    }
  }

  function _loadSortOrderFromStorage() {
    try {
      const saved = localStorage.getItem('echogtfs_alerts_sort');
      if (saved === 'oldest' || saved === 'newest') {
        _sortOrder = saved;
      }
    } catch (err) {
    }
    _updateSortButton();
  }

  function init() {
    // Load sort order from storage
    _loadSortOrderFromStorage();
    
    // Setup event listeners
    const filterInput = ui.el('alert-filter');
    if (filterInput) {
      filterInput.addEventListener('input', _handleFilterChange);
    }
    

    const sortBtn = ui.el('sort-alerts-btn');
    if (sortBtn) {
      sortBtn.addEventListener('click', _toggleSortOrder);
    }
    
    // Handle browser back/forward navigation
    window.addEventListener('popstate', () => {
      _loadAlerts();
    });
  }

  async function load() {
    await _loadAlerts();
  }

  function handleContentClick(e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const id = btn.dataset.id; // UUID as string
    if (btn.dataset.action === 'view') _viewAlert(id);
    if (btn.dataset.action === 'edit') _openEditAlert(id);
    if (btn.dataset.action === 'delete') _confirmDelete(id);
    if (btn.dataset.action === 'toggle') _toggleAlert(id);
  }

  function openCreateModal() {
    _openCreateAlert();
  }

  return { init, load, handleContentClick, openCreateModal };
})();