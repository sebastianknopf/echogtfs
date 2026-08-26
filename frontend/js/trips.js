/* ==========================================================================
  TRIPS MODULE - Realtime trips list
========================================================================== */

const trips = (() => {
  const PAGE_SIZE = 20;
  const SORT_STORAGE_KEY = 'echogtfs_trips_sort';
  const FILTERS_STORAGE_KEY = 'echogtfs_trips_filters';
  const POLL_INTERVAL_MS = 30_000;
  const WARNING_ICON_PATH = 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z';

  let _eventsBound = false;
  let _pollTimer = null;
  let _items = [];
  let _filterText = '';
  let _sortOrder = 'asc';
  let _currentPage = 1;
  let _totalPages = 1;
  let _total = 0;
  let _filterTimeout = null;
  let _loadRequestId = 0;
  let _filters = {
    active: true,
    inactive: true,
  };

  function _isPanelActive() {
    const panel = document.querySelector('.panel[data-panel="trips"]');
    return Boolean(panel?.classList.contains('is-active'));
  }

  function _startPolling() {
    if (_pollTimer) return;
    _pollTimer = window.setInterval(() => {
      if (_isPanelActive()) {
        _loadTrips();
      }
    }, POLL_INTERVAL_MS);
  }

  function _parseServiceDateTime(startDate, startTime) {
    if (!startDate || !startTime) return null;

    const normalizedDate = String(startDate).trim();
    const normalizedTime = String(startTime).trim();
    const dateMatch = normalizedDate.match(/^(\d{4})-?(\d{2})-?(\d{2})$/);
    if (!dateMatch) return null;

    const timeParts = normalizedTime.split(':').map((value) => Number(value));
    if (timeParts.length < 2 || timeParts.some((value) => !Number.isFinite(value))) {
      return null;
    }

    const year = Number(dateMatch[1]);
    const month = Number(dateMatch[2]);
    const day = Number(dateMatch[3]);
    const hours = timeParts[0];
    const minutes = timeParts[1];
    const seconds = Number.isFinite(timeParts[2]) ? timeParts[2] : 0;

    const date = new Date(year, month - 1, day, 0, 0, 0, 0);
    date.setHours(hours, minutes, seconds, 0);
    return date;
  }

  function _formatLocalDateTime(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';

    const currentLang = typeof window.i18n?.getCurrentLanguage === 'function'
      ? window.i18n.getCurrentLanguage()
      : 'de';
    const locale = currentLang === 'de' ? 'de-DE' : 'en-GB';

    return date.toLocaleString(locale, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function _formatLocalTime(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '-';

    const currentLang = typeof window.i18n?.getCurrentLanguage === 'function'
      ? window.i18n.getCurrentLanguage()
      : 'de';
    const locale = currentLang === 'de' ? 'de-DE' : 'en-GB';

    return date.toLocaleTimeString(locale, {
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function _formatLocalDate(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '-';

    const currentLang = typeof window.i18n?.getCurrentLanguage === 'function'
      ? window.i18n.getCurrentLanguage()
      : 'de';
    const locale = currentLang === 'de' ? 'de-DE' : 'en-GB';

    return date.toLocaleDateString(locale, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  }

  function _coerceDate(value) {
    if (!value) return null;
    const date = value instanceof Date ? value : new Date(value);
    return (date instanceof Date && !Number.isNaN(date.getTime())) ? date : null;
  }

  function _parseOperationDay(startDate) {
    if (!startDate) return null;

    const normalizedDate = String(startDate).trim();
    const dateMatch = normalizedDate.match(/^(\d{4})-?(\d{2})-?(\d{2})$/);
    if (!dateMatch) return null;

    const year = Number(dateMatch[1]);
    const month = Number(dateMatch[2]);
    const day = Number(dateMatch[3]);
    const date = new Date(year, month - 1, day, 0, 0, 0, 0);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function _startOfDay(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  }

  function _formatTimeExtended(date, operationDayDate) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '-';

    if (operationDayDate instanceof Date && !Number.isNaN(operationDayDate.getTime())) {
      const dayDiff = Math.round((_startOfDay(date) - _startOfDay(operationDayDate)) / 86_400_000);
      if (dayDiff === 1) {
        const hours = String(date.getHours() + 24).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
      }
    }

    return _formatLocalTime(date);
  }

  function _resolveScheduledStopName(stopId, stopEvents, fallback) {
    if (!stopId) return fallback;

    const matchingStopEvent = stopEvents.find((stopEvent) => String(stopEvent?.stop_id || '') === String(stopId));
    return matchingStopEvent?.stop_name || matchingStopEvent?.stop_id || stopId || fallback;
  }

  function _getScheduleRelationshipText(value) {
    const normalized = String(value || '').trim().toUpperCase();
    const keyByRelationship = {
      SCHEDULED: 'trips.schedule.scheduled',
      ADDED: 'trips.schedule.added',
      UNSCHEDULED: 'trips.schedule.unscheduled',
      CANCELED: 'trips.schedule.canceled',
      DELETED: 'trips.schedule.deleted',
      DUPLICATED: 'trips.schedule.duplicated',
      REPLACEMENT: 'trips.schedule.replacement',
      SKIPPED: 'trips.schedule.skipped',
      NO_DATA: 'trips.schedule.no_data',
    };

    const key = keyByRelationship[normalized];
    return key ? window.i18n(key) : (normalized || '-');
  }

  function _getTripStatusClass(value) {
    const normalized = String(value || '').trim().toUpperCase();
    if (normalized === 'CANCELED' || normalized === 'DELETED') {
      return 'status-text--negative';
    }
    if (normalized === 'ADDED' || normalized === 'UNSCHEDULED' || normalized === 'DUPLICATED' || normalized === 'REPLACEMENT') {
      return 'status-text--positive';
    }
    return '';
  }

  function _getStopEventStatusClass(value) {
    const normalized = String(value || '').trim().toUpperCase();
    if (normalized === 'SKIPPED') {
      return 'status-text--negative';
    }
    if (normalized === 'ADDED') {
      return 'status-text--positive';
    }
    return '';
  }

  function _normalizeTrip(item) {
    const stopEvents = Array.isArray(item.stop_events) ? [...item.stop_events] : [];
    stopEvents.sort((a, b) => {
      const aSeq = Number(a.stop_sequence);
      const bSeq = Number(b.stop_sequence);
      if (Number.isFinite(aSeq) && Number.isFinite(bSeq)) {
        return aSeq - bSeq;
      }
      return String(a.stop_sequence ?? '').localeCompare(String(b.stop_sequence ?? ''));
    });

    const firstStopEvent = stopEvents[0] || null;
    const lastStopEvent = stopEvents.length ? stopEvents[stopEvents.length - 1] : null;

    const scheduledStartTime = _coerceDate(item.scheduled_start_time);
    const scheduledEndTime = _coerceDate(item.scheduled_end_time);
    const startDate = scheduledStartTime || _parseServiceDateTime(item.start_date, item.start_time);
    const endDate = scheduledEndTime || startDate;
    const operationDayDate = _parseOperationDay(item.start_date);
    const hasInvalidStopEvent = stopEvents.some((stopEvent) => stopEvent?.is_valid === false);
    const isTripValid = item.is_trip_valid !== false;
    const isRouteValid = item.is_route_valid !== false;
    const isValid = Boolean(item.is_valid) && !hasInvalidStopEvent;
    const hasOnlyNoDataStopEvents = stopEvents.length > 0 && stopEvents.every(
      (stopEvent) => String(stopEvent?.schedule_relationship || '').trim().toUpperCase() === 'NO_DATA',
    );

    const scheduledStartStopId = item.scheduled_start_stop_id != null && item.scheduled_start_stop_id !== ''
      ? String(item.scheduled_start_stop_id)
      : null;
    const scheduledEndStopId = item.scheduled_end_stop_id != null && item.scheduled_end_stop_id !== ''
      ? String(item.scheduled_end_stop_id)
      : null;
    const scheduledStartStopName = item.scheduled_start_stop_name != null && item.scheduled_start_stop_name !== ''
      ? String(item.scheduled_start_stop_name)
      : (scheduledStartStopId || null);
    const scheduledEndStopName = item.scheduled_end_stop_name != null && item.scheduled_end_stop_name !== ''
      ? String(item.scheduled_end_stop_name)
      : (scheduledEndStopId || null);

    const normalizedStopEvents = stopEvents.map((stopEvent) => {
      const arrivalDate = stopEvent?.arrival_time ? new Date(stopEvent.arrival_time) : null;
      const departureDate = stopEvent?.departure_time ? new Date(stopEvent.departure_time) : null;

      const statusCode = String(stopEvent?.schedule_relationship || '');
      const statusLabel = statusCode === 'ADDED'
        ? window.i18n('trips.stop_event.added')
        : (statusCode === 'SKIPPED' ? window.i18n('trips.stop_event.skipped') : _getScheduleRelationshipText(stopEvent?.schedule_relationship));

      return {
        stopDisplayName: stopEvent?.stop_name || stopEvent?.stop_id || '-',
        arrivalTimeLabel: _formatTimeExtended(arrivalDate, operationDayDate),
        departureTimeLabel: _formatTimeExtended(departureDate, operationDayDate),
        statusCode,
        statusLabel,
        isValid: stopEvent?.is_valid !== false,
      };
    });

    const startStopName = scheduledStartStopName || scheduledStartStopId || firstStopEvent?.stop_name || firstStopEvent?.stop_id || '-';
    const endStopName = scheduledEndStopName || scheduledEndStopId || lastStopEvent?.stop_name || lastStopEvent?.stop_id || '-';

    const hasScheduledDisplayData = Boolean(
      scheduledStartStopId && scheduledEndStopId && scheduledStartTime && scheduledEndTime
    );

    return {
      id: item.id,
      line: item.route_name || item.route_id || '-',
      vehicleDisplayText: item.vehicle_display_text || '-',
      tripId: item.trip_id || '-',
      originalTripId: item.original_trip_id || '-',
      assignmentType: item.assignment_type || '-',
      startDate,
      endDate,
      operationDayDate,
      startStopName,
      startStopId: scheduledStartStopId || firstStopEvent?.stop_id || '-',
      endStopName,
      endStopId: scheduledEndStopId || lastStopEvent?.stop_id || '-',
      scheduledStartTime,
      scheduledEndTime,
      scheduledStartStopId,
      scheduledEndStopId,
      scheduledStartStopName,
      scheduledEndStopName,
      hasScheduledDisplayData,
      sourceName: item.data_source_name || item.source || window.i18n('alerts.badge.external'),
      isInternal: !item.data_source_id,
      isActive: Boolean(item.is_active),
      isValid,
      isTripValid,
      isRouteValid,
      hasOnlyNoDataStopEvents,
      isMatched: stopEvents.length > 0,
      scheduleRelationship: item.schedule_relationship || 'SCHEDULED',
      scheduleRelationshipLabel: _getScheduleRelationshipText(item.schedule_relationship || 'SCHEDULED'),
      scheduleRelationshipClass: _getTripStatusClass(item.schedule_relationship || 'SCHEDULED'),
      stopEvents: normalizedStopEvents,
    };
  }

  function _renderTripDetailsModal(trip) {
    const titleElement = document.getElementById('view-trip-title');
    const contentElement = document.getElementById('view-trip-content');
    const modalElement = document.getElementById('view-trip-modal');
    if (!titleElement || !contentElement || !modalElement) return;

    const headerWarning = trip.hasOnlyNoDataStopEvents
      ? ` <span class="view-item__warning view-item__warning--no-realtime-data" title="${ui.esc(window.i18n('trips.realtime_data.warning'))}"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${WARNING_ICON_PATH}"/></svg></span>`
      : '';
    const modalTitle = window.i18n('trips.modal.view');
    const lineLabel = window.i18n('trips.field.line');
    const vehicleLabel = window.i18n('trips.view.vehicle');
    titleElement.innerHTML = `${ui.esc(modalTitle)}: ${ui.esc(lineLabel)} ${ui.esc(trip.line)} / ${ui.esc(trip.tripId)}${headerWarning}`;

    const startTimeLabel = _formatTimeExtended(trip.startDate, trip.operationDayDate);
    const endTimeLabel = _formatTimeExtended(trip.endDate, trip.operationDayDate);
    const scheduledDateLabel = trip.operationDayDate ? _formatLocalDate(trip.operationDayDate) : null;
    const scheduledOverview = scheduledDateLabel
      ? `
        <div class="view-item">
          <div class="view-item__label">${ui.esc(window.i18n('trips.view.operation_day'))}</div>
          <div class="view-item__content">${ui.esc(scheduledDateLabel)}</div>
        </div>
      `
      : '';

    const stopEventsHtml = trip.stopEvents.length
      ? trip.stopEvents.map((stopEvent) => {
        const warning = stopEvent.isValid
          ? ''
          : `<span class="view-item__warning" title="${ui.esc(window.i18n('trips.stop_reference.warning'))}"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${WARNING_ICON_PATH}"/></svg></span>`;

        return `
          <div class="view-item view-item--entity">
            <div class="view-item__content">
              <strong>${ui.esc(stopEvent.stopDisplayName)}</strong><br>
              ${ui.esc(window.i18n('trips.view.arrival'))}: ${ui.esc(stopEvent.arrivalTimeLabel)} •
              ${ui.esc(window.i18n('trips.view.departure'))}: ${ui.esc(stopEvent.departureTimeLabel)} •
              ${ui.esc(window.i18n('trips.view.status'))}: <span class="${_getStopEventStatusClass(stopEvent.statusCode)}">${ui.esc(stopEvent.statusLabel)}</span>
            </div>
            ${warning}
          </div>
        `;
      }).join('')
      : `<div class="view-item view-item--entity"><div class="view-item__content"><em>${ui.esc(window.i18n('trips.view.empty_stop_events'))}</em></div></div>`;

    const tripIdWarning = trip.isTripValid
      ? ''
      : `<span class="view-item__warning" title="${ui.esc(window.i18n('trips.resolution.warning'))}"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${WARNING_ICON_PATH}"/></svg></span>`;
    const routeWarning = trip.isRouteValid
      ? ''
      : `<span class="view-item__warning" title="${ui.esc(window.i18n('trips.resolution.warning'))}"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${WARNING_ICON_PATH}"/></svg></span>`;

    contentElement.innerHTML = `
      <div class="view-section">
        <h3 class="view-section__title">${ui.esc(window.i18n('trips.view.section.trip'))}</h3>
        <div class="view-item">
          <div class="view-item__label">${ui.esc(window.i18n('trips.view.trip_id'))}</div>
          <div class="view-item__content">${ui.esc(trip.tripId)}</div>
          ${tripIdWarning}
        </div>
        <div class="view-item">
          <div class="view-item__label">${ui.esc(window.i18n('trips.view.original_trip_id'))}</div>
          <div class="view-item__content">${ui.esc(trip.originalTripId)}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label">${ui.esc(window.i18n('trips.view.route'))}</div>
          <div class="view-item__content">${ui.esc(trip.line)}</div>
          ${routeWarning}
        </div>
        <div class="view-item">
          <div class="view-item__label">${ui.esc(vehicleLabel)}</div>
          <div class="view-item__content">${ui.esc(trip.vehicleDisplayText || '-')}</div>
        </div>
        ${scheduledOverview}
        <div class="view-item">
          <div class="view-item__label">${ui.esc(window.i18n('trips.field.start'))}</div>
          <div class="view-item__content">${ui.esc(startTimeLabel)} - ${ui.esc(trip.startStopName)}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label">${ui.esc(window.i18n('trips.field.end'))}</div>
          <div class="view-item__content">${ui.esc(endTimeLabel)} - ${ui.esc(trip.endStopName)}</div>
        </div>
        <div class="view-item">
          <div class="view-item__label">${ui.esc(window.i18n('trips.view.status'))}</div>
          <div class="view-item__content"><span class="${trip.scheduleRelationshipClass}">${ui.esc(trip.scheduleRelationshipLabel)}</span></div>
        </div>
        <div class="view-item">
          <div class="view-item__label">${ui.esc(window.i18n('trips.view.assignment_type'))}</div>
          <div class="view-item__content">${ui.esc(trip.assignmentType)}</div>
        </div>
      </div>

      <div class="view-section">
        <h3 class="view-section__title">${ui.esc(window.i18n('trips.view.section.stop_events'))}</h3>
        ${stopEventsHtml}
      </div>
    `;

    modalElement.hidden = false;
  }

  function _openTripDetails(trip) {
    _renderTripDetailsModal(trip);
  }

  function _closeTripDetailsModal() {
    const modalElement = document.getElementById('view-trip-modal');
    if (modalElement) {
      modalElement.hidden = true;
    }
  }

  async function _loadTrips() {
    const container = document.getElementById('trips-content');
    if (!container) return;

    const requestId = ++_loadRequestId;
    const requestedPage = _getPageFromURL();
    _currentPage = requestedPage;

    try {
      const response = await api.getTrips(requestedPage, PAGE_SIZE, _sortOrder, _filterText, _filters);
      if (requestId !== _loadRequestId) return;

      _items = (response.items || []).map(_normalizeTrip);
      _currentPage = response.page || requestedPage;
      _totalPages = response.total_pages || 1;
      _total = response.total || 0;

      if (_currentPage > _totalPages && _totalPages > 0) {
        _currentPage = 1;
        _setPageInURL(1);
        _loadTrips();
        return;
      }

      _renderTripsList();
    } catch (err) {
      container.innerHTML = `<div class="panel__placeholder">${window.i18n('trips.error.load')}</div>`;
    }
  }

  function _getPageFromURL() {
    const params = new URLSearchParams(window.location.search);
    const page = parseInt(params.get('page'), 10);
    return (page && page > 0) ? page : 1;
  }

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

  function _handleOutsideClick(e) {
    const popout = document.getElementById('filter-trips-popout');
    const container = e.target.closest('.filter-dropdown-container');

    if (!container && popout && !popout.hidden) {
      popout.hidden = true;
      document.removeEventListener('click', _handleOutsideClick);
    }
  }

  function _toggleFilterPopout() {
    const popout = document.getElementById('filter-trips-popout');
    if (!popout) return;

    if (popout.hidden) {
      popout.hidden = false;
      setTimeout(() => {
        document.addEventListener('click', _handleOutsideClick);
      }, 0);
    } else {
      popout.hidden = true;
      document.removeEventListener('click', _handleOutsideClick);
    }
  }

  function _updateFilterCheckboxes() {
    const activeCheckbox = document.getElementById('filter-trips-active');
    const inactiveCheckbox = document.getElementById('filter-trips-inactive');

    if (activeCheckbox) activeCheckbox.checked = _filters.active;
    if (inactiveCheckbox) inactiveCheckbox.checked = _filters.inactive;
  }

  function _loadSortOrderFromStorage() {
    try {
      const saved = localStorage.getItem(SORT_STORAGE_KEY);
      if (saved === 'asc' || saved === 'desc') {
        _sortOrder = saved;
      }
    } catch (err) {
    }
  }

  function _saveSortOrderToStorage() {
    try {
      localStorage.setItem(SORT_STORAGE_KEY, _sortOrder);
    } catch (err) {
    }
  }

  function _loadFiltersFromStorage() {
    try {
      const saved = localStorage.getItem(FILTERS_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        _filters = { ..._filters, ...parsed };
      }
    } catch (err) {
    }
    _updateFilterCheckboxes();
  }

  function _saveFiltersToStorage() {
    try {
      localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(_filters));
    } catch (err) {
    }
  }

  function _handleFilterChange() {
    const activeCheckbox = document.getElementById('filter-trips-active');
    const inactiveCheckbox = document.getElementById('filter-trips-inactive');

    _filters.active = activeCheckbox ? activeCheckbox.checked : true;
    _filters.inactive = inactiveCheckbox ? inactiveCheckbox.checked : true;
    _saveFiltersToStorage();
    _currentPage = 1;
    _setPageInURL(1);
    _loadTrips();
  }

  function _handleSearchChange(e) {
    _filterText = e.target.value.trim().toLowerCase();

    if (_filterTimeout) {
      clearTimeout(_filterTimeout);
    }

    _filterTimeout = setTimeout(() => {
      _currentPage = 1;
      _setPageInURL(1);
      _loadTrips();
    }, 300);
  }

  function _toggleSortOrder() {
    _sortOrder = _sortOrder === 'asc' ? 'desc' : 'asc';
    _saveSortOrderToStorage();
    _currentPage = 1;
    _setPageInURL(1);
    _updateSortButton();
    _loadTrips();
  }

  function _updateSortButton() {
    const label = document.getElementById('sort-trips-label');
    if (!label) return;

    label.textContent = _sortOrder === 'asc'
      ? window.i18n('trips.sort.asc')
      : window.i18n('trips.sort.desc');
  }
  function _matchesFilter(text, filter) {
    if (!filter) return true;
    if (!text) return false;

    let searchPattern = filter;
    if (!searchPattern.startsWith('*')) {
      searchPattern = '*' + searchPattern;
    }
    if (!searchPattern.endsWith('*')) {
      searchPattern = searchPattern + '*';
    }

    const escapedFilter = searchPattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
    const pattern = '^' + escapedFilter.replace(/\*/g, '.*') + '$';
    const regex = new RegExp(pattern, 'i');

    return regex.test(text);
  }
  function _getSourceBadgeLabel(trip) {
    if (trip.isInternal) return window.i18n('alerts.badge.internal');
    return trip.sourceName || window.i18n('alerts.badge.external');
  }

  function _renderPagination(container) {
    if (_totalPages <= 1) return;

    const paginationHTML = `
      <div class="pagination">
        <div class="pagination__info">
          ${window.i18n('trips.pagination.info', { current: _currentPage, total: _totalPages, count: _total })}
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

    container.querySelectorAll('.pagination__btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const page = parseInt(btn.dataset.page, 10);
        if (page && page !== _currentPage) {
          _goToPage(page);
        }
      });
    });
  }

  function _goToPage(page) {
    _currentPage = page;
    _setPageInURL(page);
    _loadTrips();
  }

  function _createTripListItem(trip) {
    const item = document.createElement('li');
    item.className = 'alert-list-item' + (trip.isActive ? '' : ' alert-list-item--inactive');

    const sourceBadge = `<span class="badge badge--system">${ui.esc(_getSourceBadgeLabel(trip))}</span>`;
    const gtfsTripId = trip.tripId;
    const scheduleRelationship = trip.scheduleRelationship || 'SCHEDULED';
    const titleClassSuffix = scheduleRelationship === 'CANCELED'
      ? ' alert-list-item__title--canceled'
      : (scheduleRelationship === 'DELETED' ? ' alert-list-item__title--deleted' : '');

    const operationDayLabel = trip.operationDayDate ? _formatLocalDate(trip.operationDayDate) : null;
    const startTimeLabel = trip.startDate ? _formatTimeExtended(trip.startDate, trip.operationDayDate) : null;
    const endTimeLabel = trip.endDate ? _formatTimeExtended(trip.endDate, trip.operationDayDate) : null;
    const startStopLabel = trip.startStopName && trip.startStopName !== '-' ? trip.startStopName : null;
    const endStopLabel = trip.endStopName && trip.endStopName !== '-' ? trip.endStopName : null;

    const operationDaySegment = operationDayLabel
      ? `${window.i18n('trips.view.operation_day')} ${ui.esc(operationDayLabel)}`
      : null;
    const startSegment = startTimeLabel && startStopLabel
      ? `${window.i18n('trips.field.start')} ${ui.esc(startTimeLabel)} ${ui.esc(startStopLabel)}`
      : null;
    const endSegment = endTimeLabel && endStopLabel
      ? `${window.i18n('trips.field.end')} ${ui.esc(endTimeLabel)} ${ui.esc(endStopLabel)}`
      : null;

    const summaryParts = [];
    if (operationDaySegment) summaryParts.push(operationDaySegment);
    if (startSegment || endSegment) {
      const startEndSummary = [startSegment, endSegment].filter(Boolean).join(' - ');
      if (startEndSummary) summaryParts.push(startEndSummary);
    }

    const summaryHtml = summaryParts.length
      ? `<div class="alert-list-item__time">
          <svg class="alert-list-item__icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.2 3.2.8-1.3-4.5-2.7V7z"/>
          </svg>
          <span>${summaryParts.join(' • ')}</span>
        </div>`
      : '';

    item.innerHTML = `
      <div class="alert-list-item__content">
        <div class="alert-list-item__header">
          <h3 class="alert-list-item__title${titleClassSuffix}">${window.i18n('trips.field.line')} ${ui.esc(trip.line)} <span class="alert-list-item__subtitle">(${ui.esc(gtfsTripId)})</span></h3>
          <div class="alert-list-item__badges">
            ${sourceBadge}
            ${!trip.isActive ? `<span class="badge badge--system badge--inactive">${window.i18n('alerts.badge.inactive')}</span>` : ''}
          </div>
        </div>

        ${summaryHtml}
      </div>

      <div class="alert-list-item__actions">
        ${!trip.isValid ? `<span class="resolution-warning" title="${window.i18n('trips.resolution.warning')}"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg></span>` : (trip.hasOnlyNoDataStopEvents ? `<span class="resolution-warning resolution-warning--no-realtime-data" title="${window.i18n('trips.realtime_data.warning')}"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg></span>` : '')}
        <button class="icon-btn" data-action="view" data-id="${trip.id}" title="${window.i18n('common.view')}" data-ripple>
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
        </button>
        <button class="icon-btn ${trip.isActive ? 'icon-btn--success' : 'icon-btn--warning'}" data-action="toggle" data-id="${trip.id}" title="${trip.isActive ? window.i18n('common.deactivate') : window.i18n('common.activate')}" data-ripple>
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.59-5.41L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z"/></svg>
        </button>
      </div>
    `;

    return item;
  }

  function _replaceTripListItem(trip) {
    const container = document.getElementById('trips-content');
    if (!container) return;

    const toggleBtn = container.querySelector(`[data-action="toggle"][data-id="${trip.id}"]`);
    const oldItem = toggleBtn?.closest('.alert-list-item');
    if (!oldItem || !oldItem.parentNode) {
      _renderTripsList();
      return;
    }

    const newItem = _createTripListItem(trip);
    oldItem.parentNode.replaceChild(newItem, oldItem);
    if (window.initRipples) {
      initRipples(newItem);
    }
  }

  function _renderTripsList() {
    const container = document.getElementById('trips-content');
    if (!container) return;

    if (!_items.length) {
      const message = _filterText || (!_filters.active && !_filters.inactive)
        ? `<div class="panel__placeholder">${window.i18n('trips.empty.filter')}</div>`
        : `<div class="panel__placeholder">${window.i18n('trips.empty')}</div>`;
      container.innerHTML = message;
      return;
    }

    container.innerHTML = '<ul class="alert-list"></ul>';
    const list = container.querySelector('.alert-list');

    _items.forEach(trip => {
      const item = _createTripListItem(trip);
      list.appendChild(item);
    });

    if (window.initRipples) {
      initRipples(container);
    }

    _renderPagination(container);
  }

  function _handleContentClick(e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;

    const tripId = btn.dataset.id;
    const trip = _items.find(t => t.id === tripId);
    if (!trip) return;

    if (btn.dataset.action === 'view') {
      _openTripDetails(trip);
      return;
    }

    if (btn.dataset.action === 'toggle') {
      const previousIsActive = trip.isActive;
      api.toggleTripActive(trip.id)
        .then((result) => {
          const updatedTrip = result ? _normalizeTrip(result) : {
            ...trip,
            isActive: !trip.isActive,
          };
          const itemIndex = _items.findIndex((item) => item.id === trip.id);
          if (itemIndex !== -1) {
            _items[itemIndex] = updatedTrip;
          }
          _replaceTripListItem(updatedTrip);

          ui.toast(
            previousIsActive
              ? window.i18n('trips.status.deactivated', { line: trip.line })
              : window.i18n('trips.status.activated', { line: trip.line }),
            'success'
          );
        })
        .catch((err) => {
          ui.toast(err.message, 'error');
        });
    }
  }

  function _bindEvents() {
    if (_eventsBound) return;

    const sortBtn = document.getElementById('sort-trips-btn');
    if (sortBtn) {
      sortBtn.addEventListener('click', _toggleSortOrder);
    }

    const filterBtn = document.getElementById('filter-trips-btn');
    if (filterBtn) {
      filterBtn.addEventListener('click', _toggleFilterPopout);
    }

    const filterInput = document.getElementById('trip-filter');
    if (filterInput) {
      filterInput.addEventListener('input', _handleSearchChange);
    }

    const activeCheckbox = document.getElementById('filter-trips-active');
    const inactiveCheckbox = document.getElementById('filter-trips-inactive');
    if (activeCheckbox) {
      activeCheckbox.addEventListener('change', _handleFilterChange);
    }
    if (inactiveCheckbox) {
      inactiveCheckbox.addEventListener('change', _handleFilterChange);
    }

    const content = document.getElementById('trips-content');
    if (content) {
      content.addEventListener('click', _handleContentClick);
    }

    const viewModalCloseBtn = document.getElementById('view-trip-close-btn');
    if (viewModalCloseBtn) {
      viewModalCloseBtn.addEventListener('click', _closeTripDetailsModal);
    }

    const viewModalBackdrop = document.querySelector('#view-trip-modal .modal__backdrop');
    if (viewModalBackdrop) {
      viewModalBackdrop.addEventListener('click', _closeTripDetailsModal);
    }

    window.addEventListener('popstate', () => {
      _currentPage = _getPageFromURL();
      _loadTrips();
    });

    _eventsBound = true;
  }

  function init() {
    _loadSortOrderFromStorage();
    _loadFiltersFromStorage();
    _updateSortButton();
    _bindEvents();
    _startPolling();
  }

  function load() {
    _currentPage = _getPageFromURL();
    _bindEvents();
    _loadTrips();
  }

  function handleContentClick(e) {
    _handleContentClick(e);
  }

  return {
    init,
    load,
    handleContentClick,
  };
})();
