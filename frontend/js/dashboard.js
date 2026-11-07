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

  let _dashboardData = {
    counts: {
      service_alerts: { active: 0, inactive: 0 },
      trip_updates: { active: 0, monitored: 0, inactive: 0 },
      vehicle_positions: { active: 0, inactive: 0 },
    },
    siriHealth: false,
  };
  let _pollTimer = null;
  let _siriServiceAvailable = false;

  function _isPanelActive() {
    const panel = document.querySelector('.panel[data-panel="dashboard"]');
    return Boolean(panel?.classList.contains('is-active'));
  }

  function _startPolling() {
    if (_pollTimer) return;
    _pollTimer = window.setInterval(() => {
      if (_isPanelActive()) {
        _loadDashboardData(true);
      }
    }, POLL_INTERVAL_MS);
  }

  function _getContent() {
    return document.getElementById('dashboard-content');
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

  function _renderServiceStatus() {
    if (!_siriServiceAvailable) {
      return `
        <section class="dashboard-section dashboard-section--full">
          <div class="dashboard-section__header">
            <h3 class="dashboard-section__title" data-i18n="dashboard.section.services">${window.i18n('dashboard.section.services')}</h3>
          </div>
          <p class="dashboard-services-empty" data-i18n="dashboard.services.none">${window.i18n('dashboard.services.none')}</p>
        </section>
      `;
    }

    const statusKey = _dashboardData.siriHealth
      ? 'dashboard.service_status.ok'
      : 'dashboard.service_status.disrupted';
    const statusClass = _dashboardData.siriHealth ? 'is-ok' : 'is-disrupted';

    return `
      <section class="dashboard-section dashboard-section--full">
        <div class="dashboard-section__header">
          <h3 class="dashboard-section__title" data-i18n="dashboard.section.services">${window.i18n('dashboard.section.services')}</h3>
        </div>
        <div class="dashboard-stat-grid">
          <article class="dashboard-stat dashboard-service-status ${statusClass}">
            <div class="dashboard-stat__header">
              <span class="dashboard-stat__icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/>
                  <path d="M12 17h.01M9.5 9a2.5 2.5 0 1 1 4.32 1.73c-.9.9-1.82 1.34-1.82 2.77" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2" transform="translate(0 1)"/>
                </svg>
              </span>
              <h3 class="dashboard-stat__headline">
                <span class="dashboard-stat__headline-label dashboard-service-status__title" data-i18n="dashboard.card.siri">${window.i18n('dashboard.card.siri')}</span>
              </h3>
            </div>
            <div class="dashboard-stat__value-wrap">
              <div class="dashboard-service-status__value" data-i18n="${statusKey}">${window.i18n(statusKey)}</div>
            </div>
          </article>
        </div>
      </section>
    `;
  }

  async function _loadCapabilities() {
    try {
      const capabilities = await api.getCapabilities();
      _siriServiceAvailable = Array.isArray(capabilities) && capabilities.includes('siricomservice');
    } catch (e) {
      _siriServiceAvailable = false;
    }
  }

  async function _loadDashboardData(render = true) {
    const [dashboardResult, siriHealthResult] = await Promise.allSettled([
      api.getDashboard(),
      _siriServiceAvailable ? api.getSiriHealth() : Promise.reject(new Error('siricomservice unavailable')),
    ]);

    _dashboardData.siriHealth = siriHealthResult.status === 'fulfilled' && siriHealthResult.value === true;

    if (dashboardResult.status === 'fulfilled') {
      _setDashboardData(dashboardResult.value);
      if (render) {
        _render();
      }
      return;
    }

    if (render) {
      const container = _getContent();
      if (container) {
        container.innerHTML = `<div class="panel__placeholder">${window.i18n('error.request_failed')}</div>`;
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

        ${_renderServiceStatus()}
      </div>
    `;

    window.i18n.initializeTranslations();
    if (window.initRipples) initRipples(container);
  }

  function init() {
    _startPolling();
  }

  async function load() {
    await _loadCapabilities();
    await _loadDashboardData(true);
  }

  return {
    init,
    load,
  };
})();
