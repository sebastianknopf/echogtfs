/* ==========================================================================
   DASHBOARD - Basic dashboard view
========================================================================== */

const dashboard = (() => {
  const POLL_INTERVAL_MS = 60_000;

  const STATS = [
    {
      key: 'service_alerts',
      titleKey: 'nav.alerts',
      icon: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 22a2 2 0 0 0 2-2h-4a2 2 0 0 0 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4a1.5 1.5 0 0 0-3 0v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>',
    },
    {
      key: 'trip_updates',
      titleKey: 'nav.trips',
      icon: '<svg viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true"><path d="M760-360v-80H200v80h560Zm0-160v-80H200v80h560Zm0-160v-80H200v80h560ZM200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h560q33 0 56.5 23.5T840-760v560q0 33-23.5 56.5T760-120H200Zm560-80v-80H200v80h560Z"/></svg>',
    },
    {
      key: 'vehicle_positions',
      titleKey: 'nav.vehicles',
      icon: '<svg viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true"><path d="M240-120q-17 0-28.5-11.5T200-160v-82q-18-20-29-44.5T160-340v-380q0-83 77-121.5T480-880q172 0 246 37t74 123v380q0 29-11 53.5T760-242v82q0 17-11.5 28.5T720-120h-40q-17 0-28.5-11.5T640-160v-40H320v40q0 17-11.5 28.5T280-120h-40Zm242-640h224-448 224Zm158 280H240h480-80Zm-400-80h480v-120H240v120Zm142.5 222.5Q400-355 400-380t-17.5-42.5Q365-440 340-440t-42.5 17.5Q280-405 280-380t17.5 42.5Q315-320 340-320t42.5-17.5Zm280 0Q680-355 680-380t-17.5-42.5Q645-440 620-440t-42.5 17.5Q560-405 560-380t17.5 42.5Q595-320 620-320t42.5-17.5ZM258-760h448q-15-17-64.5-28.5T482-800q-107 0-156.5 12.5T258-760Zm62 480h320q33 0 56.5-23.5T720-360v-120H240v120q0 33 23.5 56.5T320-280Z"/></svg>',
    },
  ];

  const ENDPOINTS = [
    {
      key: 'service_alerts',
      labelKey: 'dashboard.endpoints.service_alerts',
    },
    {
      key: 'trip_updates',
      labelKey: 'dashboard.endpoints.trip_updates',
    },
    {
      key: 'vehicle_positions',
      labelKey: 'dashboard.endpoints.vehicle_positions',
    },
  ];

  let _dashboardData = {
    counts: {
      service_alerts: { active: 0, inactive: 0 },
      trip_updates: { active: 0, monitored: 0, inactive: 0 },
      vehicle_positions: { active: 0, inactive: 0 },
    },
    endpoints: {
      service_alerts: { path: 'realtime/service-alerts.pbf', url: `${window.location.origin}/api/realtime/service-alerts.pbf` },
      trip_updates: { path: 'realtime/trip-updates.pbf', url: `${window.location.origin}/api/realtime/trip-updates.pbf` },
      vehicle_positions: { path: 'realtime/vehicle-positions.pbf', url: `${window.location.origin}/api/realtime/vehicle-positions.pbf` },
    },
  };
  let _pollTimer = null;

  function _isPanelActive() {
    const panel = document.querySelector('.panel[data-panel="dashboard"]');
    return Boolean(panel?.classList.contains('is-active'));
  }

  function _startPolling() {
    if (_pollTimer) return;
    _pollTimer = window.setInterval(() => {
      if (_isPanelActive()) {
        _loadDashboardData(false);
      }
    }, POLL_INTERVAL_MS);
  }

  function _getContent() {
    return document.getElementById('dashboard-content');
  }

  function _buildJsonUrl(url) {
    return url.includes('?') ? `${url}&json` : `${url}?json`;
  }

  function _getEndpointUrl(key, format) {
    const endpoint = _dashboardData.endpoints[key];
    if (!endpoint || !endpoint.url) {
      return window.location.origin;
    }

    return format === 'json' ? _buildJsonUrl(endpoint.url) : endpoint.url;
  }

  function _setDashboardData(payload) {
    if (!payload || typeof payload !== 'object') {
      return;
    }

    if (payload.counts && typeof payload.counts === 'object') {
      _dashboardData.counts = {
        ..._dashboardData.counts,
        ...payload.counts,
      };
    }

    if (payload.endpoints && typeof payload.endpoints === 'object') {
      _dashboardData.endpoints = {
        ..._dashboardData.endpoints,
        ...payload.endpoints,
      };
    }
  }

  function _renderStats() {
    return STATS.map(item => `
      <article class="dashboard-stat" data-stat="${item.key}">
        <div class="dashboard-stat__header">
          <span class="dashboard-stat__icon">${item.icon}</span>
          <h3 class="dashboard-stat__headline">
            <span class="dashboard-stat__headline-number">${_dashboardData.counts[item.key]?.active ?? 0}</span>
            <span class="dashboard-stat__headline-label" data-i18n="${item.titleKey}">${window.i18n(item.titleKey)}</span>
          </h3>
        </div>
        <div class="dashboard-stat__value-wrap">
          ${item.key === 'trip_updates'
            ? `<div class="dashboard-stat__subvalues">
                <div class="dashboard-stat__subvalue">${window.i18n('dashboard.metric.monitored', { count: _dashboardData.counts[item.key]?.monitored ?? 0 })}</div>
                <div class="dashboard-stat__subvalue">${window.i18n('dashboard.metric.inactive', { count: _dashboardData.counts[item.key]?.inactive ?? 0 })}</div>
              </div>`
            : `<div class="dashboard-stat__subvalue">${window.i18n('dashboard.metric.inactive', { count: _dashboardData.counts[item.key]?.inactive ?? 0 })}</div>`}
        </div>
      </article>
    `).join('');
  }

  function _renderEndpoints() {
    return ENDPOINTS.map((item, index) => {
      const protobufUrl = _getEndpointUrl(item.key, 'protobuf');
      return `
        <div class="dashboard-endpoint-row">
          <div class="dashboard-endpoint-row__label" data-i18n="${item.labelKey}">${window.i18n(item.labelKey)}</div>
          <div class="dashboard-endpoint-row__url-line">
            <a class="dashboard-endpoint-row__link" href="${protobufUrl}" target="_blank" rel="noopener noreferrer">${protobufUrl}</a>
            <div class="dashboard-endpoint-row__actions">
              <button
                type="button"
                class="dashboard-copy-btn"
                data-ripple
                data-copy-index="${index}"
                data-copy-key="${item.key}"
                data-copy-format="protobuf"
                data-i18n-title="dashboard.copy.protobuf"
                data-i18n-aria-label="dashboard.copy.protobuf"
                title="${window.i18n('dashboard.copy.protobuf')}"
                aria-label="${window.i18n('dashboard.copy.protobuf')}"
              >
                <svg viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true"><path d="M360-240q-33 0-56.5-23.5T280-320v-440q0-33 23.5-56.5T360-840h360q33 0 56.5 23.5T800-760v440q0 33-23.5 56.5T720-240H360Zm0-80h360v-440H360v440ZM200-120q-33 0-56.5-23.5T120-200v-480h80v480h400v80H200Zm160-200v-440 440Z"/></svg>
                <span data-i18n="dashboard.copy.protobuf.short">${window.i18n('dashboard.copy.protobuf.short')}</span>
              </button>
              <button
                type="button"
                class="dashboard-copy-btn"
                data-ripple
                data-copy-index="${index}"
                data-copy-key="${item.key}"
                data-copy-format="json"
                data-i18n-title="dashboard.copy.json"
                data-i18n-aria-label="dashboard.copy.json"
                title="${window.i18n('dashboard.copy.json')}"
                aria-label="${window.i18n('dashboard.copy.json')}"
              >
                <svg viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true"><path d="M360-240q-33 0-56.5-23.5T280-320v-440q0-33 23.5-56.5T360-840h360q33 0 56.5 23.5T800-760v440q0 33-23.5 56.5T720-240H360Zm0-80h360v-440H360v440ZM200-120q-33 0-56.5-23.5T120-200v-480h80v480h400v80H200Zm160-200v-440 440Z"/></svg>
                <span data-i18n="dashboard.copy.json.short">${window.i18n('dashboard.copy.json.short')}</span>
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  async function _copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const helper = document.createElement('textarea');
    helper.value = text;
    helper.setAttribute('readonly', '');
    helper.style.position = 'absolute';
    helper.style.left = '-9999px';
    document.body.appendChild(helper);
    helper.select();
    document.execCommand('copy');
    document.body.removeChild(helper);
  }

  async function _handleContentClick(e) {
    const copyButton = e.target.closest('.dashboard-copy-btn');
    if (!copyButton) return;

    const endpointKey = copyButton.dataset.copyKey || '';
    const format = copyButton.dataset.copyFormat;
    if (!endpointKey) return;

    try {
      await _copyText(_getEndpointUrl(endpointKey, format));
      ui.toast(window.i18n('dashboard.copy.success'), 'success');
    } catch (error) {
      ui.toast(window.i18n('dashboard.copy.error'), 'error');
    }
  }

  async function _loadDashboardData(render = true) {
    try {
      const payload = await api.getDashboard();
      _setDashboardData(payload);
      if (render) {
        _render();
      }
    } catch (error) {
      if (render) {
        const container = _getContent();
        if (container) {
          container.innerHTML = `<div class="panel__placeholder">${window.i18n('error.request_failed')}</div>`;
        }
      }
    }
  }

  function _render() {
    const container = _getContent();
    if (!container) return;

    container.innerHTML = `
      <div class="dashboard-grid">
        <section class="dashboard-section">
          <div class="dashboard-section__header">
            <h3 class="dashboard-section__title" data-i18n="dashboard.section.stats">${window.i18n('dashboard.section.stats')}</h3>
          </div>
          <div class="dashboard-stat-grid">
            ${_renderStats()}
          </div>
        </section>

        <section class="dashboard-section dashboard-section--full">
          <div class="dashboard-section__header">
            <h3 class="dashboard-section__title" data-i18n="dashboard.section.endpoints">${window.i18n('dashboard.section.endpoints')}</h3>
          </div>
          <div class="dashboard-endpoints-list">
            ${_renderEndpoints()}
          </div>
        </section>
      </div>
    `;

    window.i18n.initializeTranslations();
    if (window.initRipples) initRipples(container);
  }

  function init() {
    _getContent()?.addEventListener('click', _handleContentClick);
    _startPolling();
  }

  async function load() {
    await _loadDashboardData(true);
  }

  return {
    init,
    load,
  };
})();
