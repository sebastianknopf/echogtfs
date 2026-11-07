/* ==========================================================================
   CONFLICTS MODULE - Mock conflict review
========================================================================== */

const conflicts = (() => {
  const WARNING_ICON_PATH = 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z';

  const MOCK_RESPONSE = {
    conflicts: [
    {
      id: 'b6dd0f6e-2d18-4f4c-9f35-0dcf78d6a021',
      timestamp: '2026-11-06T09:15:00Z',
      code: 1001,
      message: 'ERROR_DATASOURCE_FAILURE',
      datasource: { id: 12, name: 'City Transit GTFS' },
      properties: { datasource_id: 12, last_status: 503, last_failure: '2026-11-06T09:15:00Z' },
    },
    {
      id: '5b97522a-4cb0-4b2a-9c0c-9af0d29cdb1a',
      timestamp: '2026-11-05T14:30:00Z',
      code: 1003,
      message: 'ERROR_NO_STOP_FOUND',
      datasource: { id: 12, name: 'City Transit GTFS' },
      properties: { datasource_id: 12, last_failure: '2026-11-05T14:30:00Z', stop_id: '804' },
    },
    {
      id: '61895838-6ce1-49b6-9b41-4f22bcd6bb19',
      timestamp: '2026-11-04T08:00:00Z',
      code: 2003,
      message: 'WARNING_WRONG_QUAY',
      datasource: { id: 18, name: 'Regional Transit GTFS' },
      properties: {
        datasource_id: 18,
        last_failure: '2026-11-04T08:00:00Z',
        trip_id: 'R3-2026-11-04',
        stop_id: '2201',
        stop_sequence: 4,
        original_stop_id: '2200',
      },
    },
    {
      id: 'db2207f9-1f91-44e1-a17c-7447e59c6ead',
      timestamp: '2026-11-03T11:45:00Z',
      code: 2002,
      message: 'WARNING_IMPLIED_CANCELED_STOP',
      datasource: { id: 18, name: 'Regional Transit GTFS' },
      properties: {
        datasource_id: 18,
        last_failure: '2026-11-03T11:45:00Z',
        trip_id: 'R3-2026-11-03',
        stop_id: '2202',
        stop_sequence: 7,
      },
    },
    {
      id: '6cc5cc8d-4c7f-4f21-a6b8-ad027b109dc0',
      timestamp: '2026-11-02T16:20:00Z',
      code: 2004,
      message: 'WARNING_ROUTE_NO_GLOBAL_ID',
      datasource: { id: 12, name: 'City Transit GTFS' },
      properties: { datasource_id: 12, last_failure: '2026-11-02T16:20:00Z', route_id: '12' },
    },
    ],
  };

  function _isPoweruser() {
    const role = window.appState?.currentUser?.role;
    return role === 'POWERUSER' || role === 'ADMIN';
  }

  function _getFilteredConflicts() {
    const sourceId = document.getElementById('conflicts-source-filter')?.value || 'all';
    const selectedCodes = Array.from(
      document.querySelectorAll('#conflicts-filter-popout input[type="checkbox"]:checked')
    ).map(checkbox => checkbox.value);
    return MOCK_RESPONSE.conflicts.filter(conflict =>
      (sourceId === 'all' || String(conflict.datasource.id) === sourceId) &&
      selectedCodes.includes(String(conflict.code))
    );
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
    return new Date(value).toLocaleString();
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

    const filteredConflicts = _getFilteredConflicts();
    if (filteredConflicts.length === 0) {
      container.innerHTML = `<div class="panel__placeholder" data-i18n="conflicts.empty">${window.i18n('conflicts.empty')}</div>`;
      window.i18n.initializeTranslations();
      return;
    }

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

  function _csvCell(value) {
    return `"${String(value).replace(/"/g, '""')}"`;
  }

  function _exportCsv() {
    if (!_isPoweruser()) return;

    const headers = [
      'conflicts.csv.id',
      'conflicts.field.timestamp',
      'conflicts.field.code',
      'conflicts.csv.type',
      'conflicts.csv.level',
      'conflicts.csv.properties',
    ].map(key => window.i18n(key));
    const rows = _getFilteredConflicts().map(conflict => [
      conflict.id,
      conflict.timestamp,
      conflict.code,
      conflict.message,
      window.i18n(`conflicts.level.${_getLevel(conflict)}`),
      JSON.stringify(Object.fromEntries(
        Object.entries(conflict.properties).filter(([key]) => key !== 'datasource_id')
      )),
    ]);
    const csv = [headers, ...rows].map(row => row.map(_csvCell).join(',')).join('\r\n');
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'conflicts.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
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

    document.getElementById('conflicts-source-filter')?.addEventListener('change', _render);
    document.getElementById('conflicts-filter-btn')?.addEventListener('click', _toggleFilterPopout);
    document.querySelectorAll('#conflicts-filter-popout input[type="checkbox"]')
      .forEach(checkbox => checkbox.addEventListener('change', _render));
    document.getElementById('conflicts-export-btn')?.addEventListener('click', _exportCsv);
    document.addEventListener('click', _handleOutsideClick);
  }

  function load() {
    const container = document.getElementById('conflicts-content');
    if (!_isPoweruser()) {
      if (container) container.replaceChildren();
      return;
    }

    _render();
  }

  return { init, load };
})();
