/* ==========================================================================
   TRIPS MODULE - Mock trips list in alerts style
========================================================================== */

const trips = (() => {
  const PAGE_SIZE = 20;
  const SORT_STORAGE_KEY = 'echogtfs_trips_sort';
  const FILTERS_STORAGE_KEY = 'echogtfs_trips_filters';

  let _eventsBound = false;
  let _allTrips = [];
  let _filteredTrips = [];
  let _filterText = '';
  let _sortOrder = 'asc';
  let _currentPage = 1;
  let _totalPages = 1;
  let _total = 0;
  let _filterTimeout = null;
  let _filters = {
    active: true,
    inactive: true,
  };

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

  function _createMockTrips() {
    const serviceDate = '2026-07-22';
    const trips = [
      { id: 'trip-001', line: 'S3', startTime: '05:42', startStopName: 'Winterthur', startStopId: '8506000', endTime: '06:15', endStopName: 'Zürich HB', endStopId: '8503000', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: true, scheduleRelationship: 'SCHEDULED' },
      { id: 'trip-002', line: 'IC5', startTime: '06:05', startStopName: 'Biel/Bienne', startStopId: '8504300', endTime: '07:12', endStopName: 'Zürich HB', endStopId: '8503000', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-003', line: 'T2', startTime: '06:18', startStopName: 'Schlieren Zentrum', startStopId: '8591210', endTime: '06:49', endStopName: 'Flughafen Zürich', endStopId: '8503010', sourceName: 'echogtfs', isInternal: true, isActive: false, isMatched: true },
      { id: 'trip-004', line: 'RE48', startTime: '06:30', startStopName: 'Baden', startStopId: '8502113', endTime: '06:55', endStopName: 'Zürich HB', endStopId: '8503000', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: false, scheduleRelationship: 'CANCELED' },
      { id: 'trip-005', line: '31', startTime: '06:33', startStopName: 'Klusplatz', startStopId: '8590191', endTime: '06:57', endStopName: 'Zürich, Kaserne', endStopId: '8591123', sourceName: 'VBZ', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-006', line: 'S11', startTime: '06:41', startStopName: 'Aarau', startStopId: '8502112', endTime: '07:34', endStopName: 'Winterthur', endStopId: '8506000', sourceName: 'SBB Import', isInternal: false, isActive: false, isMatched: false, scheduleRelationship: 'DELETED' },
      { id: 'trip-007', line: '10', startTime: '06:45', startStopName: 'Bahnhofplatz/HB', startStopId: '8591042', endTime: '07:02', endStopName: 'Flughafen Zürich', endStopId: '8503010', sourceName: 'VBG', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-008', line: 'IR35', startTime: '06:52', startStopName: 'Bern', startStopId: '8507000', endTime: '07:50', endStopName: 'Zürich HB', endStopId: '8503000', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-009', line: 'N18', startTime: '07:05', startStopName: 'Hardbrücke', startStopId: '8503050', endTime: '07:34', endStopName: 'Flughafen Zürich', endStopId: '8503010', sourceName: 'echogtfs', isInternal: true, isActive: true, isMatched: false, scheduleRelationship: 'CANCELED' },
      { id: 'trip-010', line: 'S9', startTime: '07:12', startStopName: 'Uster', startStopId: '8503125', endTime: '07:36', endStopName: 'Zürich HB', endStopId: '8503000', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-011', line: '7', startTime: '07:17', startStopName: 'Stettbach', startStopId: '8503064', endTime: '07:39', endStopName: 'Wollishofen', endStopId: '8590898', sourceName: 'VBZ', isInternal: false, isActive: false, isMatched: true },
      { id: 'trip-012', line: 'RE70', startTime: '07:20', startStopName: 'Basel SBB', startStopId: '8500010', endTime: '08:12', endStopName: 'Zürich HB', endStopId: '8503000', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-013', line: '14', startTime: '07:22', startStopName: 'Triemli', startStopId: '8590905', endTime: '07:55', endStopName: 'Seebach', endStopId: '8591188', sourceName: 'VBZ', isInternal: false, isActive: true, isMatched: false, scheduleRelationship: 'DELETED' },
      { id: 'trip-014', line: 'S24', startTime: '07:28', startStopName: 'Zug', startStopId: '8502204', endTime: '08:05', endStopName: 'Zürich HB', endStopId: '8503000', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-015', line: '33', startTime: '07:30', startStopName: 'Bhf Tiefenbrunnen', startStopId: '8591162', endTime: '07:52', endStopName: 'Albisriederplatz', endStopId: '8591008', sourceName: 'ZVV Feed', isInternal: false, isActive: false, isMatched: true },
      { id: 'trip-016', line: 'S6', startTime: '07:34', startStopName: 'Baden', startStopId: '8502113', endTime: '07:58', endStopName: 'Zürich HB', endStopId: '8503000', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-017', line: '4', startTime: '07:42', startStopName: 'Altstetten', startStopId: '8503015', endTime: '08:08', endStopName: 'Bahnhof Tiefenbrunnen', endStopId: '8591162', sourceName: 'VBZ', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-018', line: 'IC1', startTime: '07:50', startStopName: 'St. Gallen', startStopId: '8506302', endTime: '09:06', endStopName: 'Genève', endStopId: '8501008', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: false, scheduleRelationship: 'CANCELED' },
      { id: 'trip-019', line: '31', startTime: '07:58', startStopName: 'Hegibachplatz', startStopId: '8591093', endTime: '08:19', endStopName: 'Kienastenwies', endStopId: '8591138', sourceName: 'echogtfs', isInternal: true, isActive: true, isMatched: true },
      { id: 'trip-020', line: 'S7', startTime: '08:03', startStopName: 'Meilen', startStopId: '8503131', endTime: '08:31', endStopName: 'Zürich Stadelhofen', endStopId: '8503056', sourceName: 'SBB Import', isInternal: false, isActive: false, isMatched: true },
      { id: 'trip-021', line: '13', startTime: '08:06', startStopName: 'Frankental', startStopId: '8591075', endTime: '08:38', endStopName: 'Albisgütli', endStopId: '8591002', sourceName: 'VBZ', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-022', line: 'RE37', startTime: '08:12', startStopName: 'Rapperswil', startStopId: '8503228', endTime: '08:47', endStopName: 'Zürich HB', endStopId: '8503000', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: true },
      { id: 'trip-023', line: 'N3', startTime: '08:15', startStopName: 'Central', startStopId: '8591051', endTime: '08:44', endStopName: 'Werdhölzli', endStopId: '8591192', sourceName: 'ZVV Feed', isInternal: false, isActive: true, isMatched: false, scheduleRelationship: 'DELETED' },
      { id: 'trip-024', line: 'S15', startTime: '08:18', startStopName: 'Rapperswil', startStopId: '8503228', endTime: '09:04', endStopName: 'Niederweningen', endStopId: '8503137', sourceName: 'SBB Import', isInternal: false, isActive: true, isMatched: true },
    ];

    return trips.map((trip) => {
      const startDate = _createLocalDate(serviceDate, trip.startTime);
      let endDate = _createLocalDate(serviceDate, trip.endTime);

      if (endDate < startDate) {
        endDate = new Date(endDate.getTime() + 24 * 60 * 60 * 1000);
      }

      return {
        ...trip,
        startDate,
        endDate,
      };
    });
  }

  function _createLocalDate(datePart, timePart) {
    const [year, month, day] = datePart.split('-').map(Number);
    const [hours, minutes] = timePart.split(':').map(Number);
    return new Date(year, month - 1, day, hours, minutes, 0, 0);
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
    _renderTripsList();
  }

  function _handleSearchChange(e) {
    _filterText = e.target.value.trim().toLowerCase();

    if (_filterTimeout) {
      clearTimeout(_filterTimeout);
    }

    _filterTimeout = setTimeout(() => {
      _currentPage = 1;
      _setPageInURL(1);
      _renderTripsList();
    }, 300);
  }

  function _toggleSortOrder() {
    _sortOrder = _sortOrder === 'asc' ? 'desc' : 'asc';
    _saveSortOrderToStorage();
    _currentPage = 1;
    _setPageInURL(1);
    _updateSortButton();
    _renderTripsList();
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


  function _getGtfsTripId(trip) {
    if (trip.gtfsTripId) return trip.gtfsTripId;
    const numericId = parseInt(String(trip.id).replace(/\D/g, ''), 10) || 0;
    const suffix = String(555 + numericId).padStart(3, '0');
    return `bod-47-2883-T0.Special#${suffix}`;
  }

  function _getSourceBadgeLabel(trip) {
    if (trip.isInternal) return window.i18n('alerts.badge.internal');
    return trip.sourceName || window.i18n('alerts.badge.external');
  }

  function _matchesStatus(trip) {
    if (_filters.active && _filters.inactive) return true;
    if (!_filters.active && !_filters.inactive) return false;
    if (_filters.active) return trip.isActive;
    return !trip.isActive;
  }

  function _matchesSearch(trip) {
    if (!_filterText) return true;
    const gtfsTripId = _getGtfsTripId(trip);
    return [
      trip.line,
      gtfsTripId,
      trip.startStopName,
      trip.startStopId,
      trip.endStopName,
      trip.endStopId,
    ].some(value => _matchesFilter(value, _filterText));
  }

  function _applyFilters() {
    _filteredTrips = _allTrips
      .filter(trip => _matchesStatus(trip) && _matchesSearch(trip))
      .sort((a, b) => {
        const aStart = a.startDate?.getTime?.() ?? 0;
        const bStart = b.startDate?.getTime?.() ?? 0;
        return _sortOrder === 'asc' ? aStart - bStart : bStart - aStart;
      });
    _total = _filteredTrips.length;
    _totalPages = Math.max(1, Math.ceil(_total / PAGE_SIZE));
    if (_currentPage > _totalPages) {
      _currentPage = _totalPages;
    }
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
    _renderTripsList();
  }

  function _renderTripsList() {
    const container = document.getElementById('trips-content');
    if (!container) return;

    _applyFilters();

    if (!_filteredTrips.length) {
      const message = _filterText || (!_filters.active && !_filters.inactive)
        ? `<div class="panel__placeholder">${window.i18n('trips.empty.filter')}</div>`
        : `<div class="panel__placeholder">${window.i18n('trips.empty')}</div>`;
      container.innerHTML = message;
      return;
    }

    const startIndex = (_currentPage - 1) * PAGE_SIZE;
    const pageItems = _filteredTrips.slice(startIndex, startIndex + PAGE_SIZE);

    container.innerHTML = '<ul class="alert-list"></ul>';
    const list = container.querySelector('.alert-list');

    pageItems.forEach(trip => {
      const item = document.createElement('li');
      item.className = 'alert-list-item' + (trip.isActive ? '' : ' alert-list-item--inactive');

      const sourceBadge = `<span class="badge badge--system">${ui.esc(_getSourceBadgeLabel(trip))}</span>`;
      const gtfsTripId = _getGtfsTripId(trip);
      const startDateLabel = _formatLocalDateTime(trip.startDate);
      const endDateLabel = _formatLocalDateTime(trip.endDate);
      const scheduleRelationship = trip.scheduleRelationship || 'SCHEDULED';
      const titleClassSuffix = scheduleRelationship === 'CANCELED'
        ? ' alert-list-item__title--canceled'
        : (scheduleRelationship === 'DELETED' ? ' alert-list-item__title--deleted' : '');

      item.innerHTML = `
        <div class="alert-list-item__content">
          <div class="alert-list-item__header">
            <h3 class="alert-list-item__title${titleClassSuffix}">${window.i18n('trips.field.line')} ${ui.esc(trip.line)} <span class="alert-list-item__subtitle">(${ui.esc(gtfsTripId)})</span></h3>
            <div class="alert-list-item__badges">
              ${sourceBadge}
              ${!trip.isActive ? `<span class="badge badge--system badge--inactive">${window.i18n('alerts.badge.inactive')}</span>` : ''}
            </div>
          </div>

          <div class="alert-list-item__time">
            <svg class="alert-list-item__icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.2 3.2.8-1.3-4.5-2.7V7z"/>
            </svg>
            <span>${window.i18n('trips.field.start')} ${ui.esc(startDateLabel)} - ${ui.esc(trip.startStopName)} (${ui.esc(trip.startStopId)}) • ${window.i18n('trips.field.end')} ${ui.esc(endDateLabel)} - ${ui.esc(trip.endStopName)} (${ui.esc(trip.endStopId)})</span>
          </div>
        </div>

        <div class="alert-list-item__actions">
          ${!trip.isMatched ? `<span class="resolution-warning" title="${window.i18n('trips.resolution.warning')}"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg></span>` : ''}
          <button class="icon-btn" data-action="view" data-id="${trip.id}" title="${window.i18n('common.view')}" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
          </button>
          <button class="icon-btn ${trip.isActive ? 'icon-btn--success' : 'icon-btn--warning'}" data-action="toggle" data-id="${trip.id}" title="${trip.isActive ? window.i18n('common.deactivate') : window.i18n('common.activate')}" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.59-5.41L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z"/></svg>
          </button>
        </div>
      `;

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
    const trip = _allTrips.find(t => t.id === tripId);
    if (!trip) return;

    if (btn.dataset.action === 'view') {
      ui.toast(window.i18n('trips.mock.view', { line: trip.line }), 'success');
      return;
    }

    if (btn.dataset.action === 'toggle') {
      trip.isActive = !trip.isActive;
      _renderTripsList();
      ui.toast(
        trip.isActive
          ? window.i18n('trips.status.activated', { line: trip.line })
          : window.i18n('trips.status.deactivated', { line: trip.line }),
        'success'
      );
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

    window.addEventListener('popstate', () => {
      _currentPage = _getPageFromURL();
      _renderTripsList();
    });

    _eventsBound = true;
  }

  function init() {
    _allTrips = _createMockTrips();
    _loadSortOrderFromStorage();
    _loadFiltersFromStorage();
    _updateSortButton();
    _bindEvents();
  }

  function load() {
    if (!_allTrips.length) {
      _allTrips = _createMockTrips();
    }
    _currentPage = _getPageFromURL();
    _bindEvents();
    _renderTripsList();
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
