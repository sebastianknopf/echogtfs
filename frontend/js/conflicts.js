/* ==========================================================================
   CONFLICTS MODULE - Conflict review
========================================================================== */

const conflicts = (() => {
  const POLL_INTERVAL_MS = 60_000;
  const SOURCE_STORAGE_KEY = 'echogtfs_conflicts_source';
  const FILTERS_STORAGE_KEY = 'echogtfs_conflicts_filters';
  const WARNING_ICON_PATH = 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z';

  let _dataSources = [];
  let _selectedSourceId = null;
  let _selectedConflictTypes = {};
  let _loadSequence = 0;
  let _conflictLoadSequence = 0;
  let _pollTimer = null;
  let _conflicts = [];
  let _isLoadingConflicts = false;

  function _isPanelActive() {
    const panel = document.querySelector('.panel[data-panel="conflicts"]');
    return Boolean(panel?.classList.contains('is-active'));
  }

  function _startPolling() {
    if (_pollTimer) return;
    _pollTimer = window.setInterval(() => {
      if (!_isPanelActive()) return;
      if (_selectedSourceId) _loadConflicts(_selectedSourceId);
    }, POLL_INTERVAL_MS);
  }

  function _isPoweruser() {
    const role = window.appState?.currentUser?.role;
    return role === 'POWERUSER' || role === 'ADMIN';
  }

  function _getFilteredConflicts() {
    return _conflicts.filter(conflict =>
      String(conflict.datasource.id) === _selectedSourceId &&
      _selectedConflictTypes[String(conflict.code)] === true
    ).sort((left, right) => new Date(right.timestamp) - new Date(left.timestamp));
  }

  function _renderError(messageKey) {
    const container = document.getElementById('conflicts-content');
    if (!container) return;
    container.innerHTML = `<div class="panel__placeholder" data-i18n="${messageKey}">${window.i18n(messageKey)}</div>`;
    window.i18n.initializeTranslations();
  }

  function _setControlsEnabled(enabled) {
    const sourceFilter = document.getElementById('conflicts-source-filter');
    const exportButton = document.getElementById('conflicts-export-btn');
    const filterButton = document.getElementById('conflicts-filter-btn');
    if (sourceFilter) sourceFilter.disabled = !enabled;
    if (exportButton) exportButton.disabled = !enabled;
    if (filterButton) filterButton.disabled = !enabled;
  }

  function _setSourcePlaceholder(messageKey) {
    const sourceFilter = document.getElementById('conflicts-source-filter');
    if (sourceFilter) {
      sourceFilter.innerHTML = `<option value="">${window.i18n(messageKey)}</option>`;
    }
  }

  function _getStoredSourceId() {
    try {
      return localStorage.getItem(SOURCE_STORAGE_KEY);
    } catch (error) {
      return null;
    }
  }

  function _saveSourceId(sourceId) {
    _selectedSourceId = String(sourceId);
    try {
      localStorage.setItem(SOURCE_STORAGE_KEY, _selectedSourceId);
    } catch (error) {
    }
  }

  function _getStoredConflictTypes() {
    try {
      const saved = localStorage.getItem(FILTERS_STORAGE_KEY);
      if (!saved) return {};
      const filters = JSON.parse(saved);
      return filters && typeof filters === 'object' && !Array.isArray(filters) ? filters : {};
    } catch (error) {
      return {};
    }
  }

  function _saveConflictTypes() {
    try {
      localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(_selectedConflictTypes));
    } catch (error) {
    }
  }

  function _populateFilterOptions(options) {
    const sourceFilter = document.getElementById('conflicts-source-filter');
    const typeOptions = document.getElementById('conflicts-type-options');
    if (!sourceFilter || !typeOptions) return;

    _dataSources = options.data_sources;
    sourceFilter.innerHTML = _dataSources.map(source =>
      `<option value="${ui.esc(source.id)}">${ui.esc(source.name)}</option>`
    ).join('');
    const storedSourceId = _getStoredSourceId();
    const selectedSourceId = _dataSources.some(source => String(source.id) === storedSourceId)
      ? storedSourceId
      : String(_dataSources[0].id);
    sourceFilter.value = selectedSourceId;
    _saveSourceId(selectedSourceId);

    const storedTypes = _getStoredConflictTypes();
    _selectedConflictTypes = {};
    typeOptions.innerHTML = options.conflict_types.map(conflictType => {
      const code = String(conflictType.code);
      const checked = typeof storedTypes[code] === 'boolean' ? storedTypes[code] : true;
      _selectedConflictTypes[code] = checked;
      return `
        <label class="filter-checkbox">
          <input type="checkbox" value="${ui.esc(code)}"${checked ? ' checked' : ''}>
          <span>${ui.esc(conflictType.name)}</span>
        </label>
      `;
    }).join('');
    _saveConflictTypes();
    _setControlsEnabled(true);
  }

  function _handleSourceChange(event) {
    const sourceId = String(event.target.value);
    if (!_dataSources.some(source => String(source.id) === sourceId)) return;
    _saveSourceId(sourceId);
    _loadConflicts(sourceId);
  }

  function _handleFilterChange() {
    _selectedConflictTypes = {};
    document.querySelectorAll('#conflicts-filter-popout input[type="checkbox"]').forEach(checkbox => {
      _selectedConflictTypes[checkbox.value] = checkbox.checked;
    });
    _saveConflictTypes();
    _render();
  }

  function _getLevel(conflict) {
    return conflict.code >= 2000 ? 'warning' : 'error';
  }

  function _formatValue(value) {
    if (value === null || value === undefined) return '';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }

  function _formatTimestamp(value) {
    const date = new Date(value);
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${day}.${month}.${year}, ${hours}:${minutes}:${seconds}`;
  }

  function _renderProperties(conflict) {
    return Object.entries(conflict.properties)
      .filter(([key]) => key !== 'datasource_id')
      .map(([key, value]) => `
        <div class="conflict-list-item__property">
          ${ui.esc(key)}: ${ui.esc(_formatValue(value))}
        </div>
      `).join('');
  }

  function _render() {
    const container = document.getElementById('conflicts-content');
    if (!container) return;

    if (_dataSources.length === 0) {
      _renderError('conflicts.error.no_sources');
      return;
    }
    if (_isLoadingConflicts) {
      container.innerHTML = `<div class="panel__loading" data-i18n="conflicts.loading">${window.i18n('conflicts.loading')}</div>`;
      window.i18n.initializeTranslations();
      return;
    }

    const filteredConflicts = _getFilteredConflicts();
    if (filteredConflicts.length === 0) {
      _renderError('conflicts.error.no_conflicts');
      const exportButton = document.getElementById('conflicts-export-btn');
      if (exportButton) exportButton.disabled = true;
      return;
    }

    const exportButton = document.getElementById('conflicts-export-btn');
    if (exportButton) exportButton.disabled = false;

    container.innerHTML = `
      <ul class="alert-list conflicts-list">
        ${filteredConflicts.map(conflict => {
          const level = _getLevel(conflict);
          const levelKey = `conflicts.level.${level}`;
          const type = conflict.message;
          return `
            <li class="alert-list-item">
              <div class="alert-list-item__content">
                <div class="alert-list-item__header">
                  <div class="conflict-list-item__heading">
                    <span class="view-item__warning${level === 'warning' ? ' view-item__warning--no-realtime-data' : ''}" data-i18n-title="${levelKey}" data-i18n-aria-label="${levelKey}" title="${window.i18n(levelKey)}" aria-label="${window.i18n(levelKey)}">
                      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${WARNING_ICON_PATH}"/></svg>
                    </span>
                    <h3 class="alert-list-item__title">${ui.esc(type)}</h3>
                  </div>
                </div>
                <div class="conflict-list-item__meta">
                  <div class="alert-list-item__time">
                    <svg class="alert-list-item__icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                      <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.2 3.2.8-1.3-4.5-2.7V7z"/>
                    </svg>
                    <span><span class="conflict-list-item__field-label" data-i18n="conflicts.field.timestamp">${window.i18n('conflicts.field.timestamp')}</span>: ${ui.esc(_formatTimestamp(conflict.timestamp))}</span>
                  </div>
                  <div class="conflict-list-item__field">
                    <span class="conflict-list-item__field-label" data-i18n="conflicts.field.code">${window.i18n('conflicts.field.code')}</span>
                    <span>${ui.esc(_formatValue(conflict.code))}</span>
                  </div>
                </div>
                <dl class="conflict-list-item__properties">
                  ${_renderProperties(conflict)}
                </dl>
              </div>
            </li>
          `;
        }).join('')}
      </ul>
    `;
    window.i18n.initializeTranslations();
  }

  async function _exportCsv() {
    if (!_isPoweruser() || _dataSources.length === 0) return;

    const sourceId = _selectedSourceId;
    if (!sourceId) return;

    const selectedConflictTypes = Object.entries(_selectedConflictTypes)
      .filter(([, selected]) => selected)
      .map(([code]) => code);

    try {
      const result = await api.exportConflictsCsv(sourceId, selectedConflictTypes);
      if (!result) return;

      const url = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = result.filename;
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  function _setFilterPopoutVisible(visible) {
    const popout = document.getElementById('conflicts-filter-popout');
    const button = document.getElementById('conflicts-filter-btn');
    if (!popout || !button) return;

    popout.hidden = !visible;
    button.setAttribute('aria-expanded', String(visible));
  }

  function _toggleFilterPopout() {
    const popout = document.getElementById('conflicts-filter-popout');
    if (popout) _setFilterPopoutVisible(popout.hidden);
  }

  function _handleOutsideClick(event) {
    if (event.target.closest('#conflicts-filter-container')) return;
    const popout = document.getElementById('conflicts-filter-popout');
    if (popout && !popout.hidden) _setFilterPopoutVisible(false);
  }

  function init() {
    if (!_isPoweruser()) return;

    document.getElementById('conflicts-source-filter')?.addEventListener('change', _handleSourceChange);
    document.getElementById('conflicts-filter-btn')?.addEventListener('click', _toggleFilterPopout);
    document.getElementById('conflicts-filter-popout')?.addEventListener('change', _handleFilterChange);
    document.getElementById('conflicts-export-btn')?.addEventListener('click', _exportCsv);
    document.addEventListener('click', _handleOutsideClick);
    _startPolling();
  }

  async function load() {
    const container = document.getElementById('conflicts-content');
    const loadSequence = ++_loadSequence;
    ++_conflictLoadSequence;
    _isLoadingConflicts = false;
    if (!_isPoweruser()) {
      _conflicts = [];
      if (container) container.replaceChildren();
      return;
    }

    _setControlsEnabled(false);
    if (container) {
      container.innerHTML = `<div class="panel__loading" data-i18n="conflicts.loading">${window.i18n('conflicts.loading')}</div>`;
      window.i18n.initializeTranslations();
    }

    try {
      const options = await api.getConflictFilterOptions();
      if (loadSequence !== _loadSequence) return;
      if (!Array.isArray(options?.data_sources) || !Array.isArray(options?.conflict_types)) {
        throw new Error('Invalid conflict filter options response.');
      }
      if (options.data_sources.length === 0) {
        _dataSources = [];
        _setSourcePlaceholder('conflicts.error.no_sources');
        _setControlsEnabled(false);
        _renderError('conflicts.error.no_sources');
        return;
      }

      _populateFilterOptions(options);
      await _loadConflicts(_selectedSourceId);
    } catch (error) {
      if (loadSequence !== _loadSequence) return;
      _dataSources = [];
      _conflicts = [];
      _setSourcePlaceholder('conflicts.source.unavailable');
      _setControlsEnabled(false);
      _renderError('conflicts.error.load_options');
      console.error('Failed to load conflict filter options:', error);
    }
  }

  async function _loadConflicts(sourceId) {
    if (!_isPoweruser() || !sourceId) return;

    _selectedSourceId = String(sourceId);
    const requestSequence = ++_conflictLoadSequence;
    _conflicts = [];
    _isLoadingConflicts = true;
    _render();

    try {
      const response = await api.getMonitoringConflicts(_selectedSourceId);
      if (requestSequence !== _conflictLoadSequence) return;
      if (!Array.isArray(response?.conflicts)) {
        throw new Error('Invalid monitoring conflicts response.');
      }

      _conflicts = response.conflicts;
      _isLoadingConflicts = false;
      _render();
    } catch (error) {
      if (requestSequence !== _conflictLoadSequence) return;
      _conflicts = [];
      _isLoadingConflicts = false;
      _renderError('conflicts.error.load_conflicts');
      const exportButton = document.getElementById('conflicts-export-btn');
      if (exportButton) exportButton.disabled = true;
      console.error(`Failed to load conflicts for data source ${sourceId}:`, error);
    }
  }

  return { init, load };
})();
