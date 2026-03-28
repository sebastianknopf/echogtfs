/* ==========================================================================
   MAIN APP - Haupt-Anwendungslogik und Navigation
========================================================================== */

// Global app state for cross-module access
window.appState = {
  currentUser: null,
  isAuthenticated: false
};

const app = (() => {
  let _currentUser = null;

  // -- Authentication -----------------------------------------------------
  async function handleLogin(e) {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);
    const credentials = {
      username: formData.get('username'),
      password: formData.get('password'),
    };

    ui.setLoginBusy(true);
    ui.setLoginError(null);

    try {
      const response = await api.login(credentials);
      localStorage.setItem('auth-token', response.access_token);
      
      // Get user data after successful login
      const user = await api.getMe();
      localStorage.setItem('current-user', JSON.stringify(user));
      
      await init(); // Re-initialize with user context
    } catch (err) {
      ui.setLoginError(err.message);
    } finally {
      ui.setLoginBusy(false);
    }
  }

  function handleLogout() {
    localStorage.removeItem('auth-token');
    localStorage.removeItem('current-user');
    window.location.reload();
  }

  // -- Navigation ---------------------------------------------------------
  function handleNavClick(e) {
    const navItem = e.target.closest('.nav-item[data-panel]');
    if (!navItem) return;

    e.preventDefault();
    const panel = navItem.dataset.panel;
    ui.setPanel(panel);

    // Load panel-specific data
    switch (panel) {
      case 'accounts':
        if (typeof accounts !== 'undefined') {
          console.log('Loading accounts...');
          accounts.load();
        }
        break;
      case 'sources':
        if (typeof sources !== 'undefined') {
          console.log('Loading sources...');
          sources.load();
        }
        break;
      case 'alerts':
        if (typeof alerts !== 'undefined') {
          console.log('Loading alerts...');
          alerts.load();
        }
        break;
      case 'settings':
        if (typeof settings !== 'undefined') {
          console.log('Loading settings...');
          settings.load();
        }
        break;
    }
  }

  // -- Add Handlers -------------------------------------------------------
  function handleAddAccount() {
    if (typeof accounts !== 'undefined') accounts.openCreateModal();
  }

  function handleAddSource() {
    if (typeof sources !== 'undefined') sources.openCreateModal();
  }

  function handleAddAlert() {
    if (typeof alerts !== 'undefined') alerts.openCreateModal();
  }

  // -- Content Click Handlers (delegation to modules) -------------------
  function handleAccountsContentClick(e) {
    if (typeof accounts !== 'undefined') accounts.handleContentClick(e);
  }

  function handleSourcesContentClick(e) {
    if (typeof sources !== 'undefined') sources.handleContentClick(e);
  }

  function handleAlertsContentClick(e) {
    if (typeof alerts !== 'undefined') alerts.handleContentClick(e);
  }

  // -- Initialization ----------------------------------------------------
  async function init() {
    // Check for existing auth
    const token = localStorage.getItem('auth-token');
    const userData = localStorage.getItem('current-user');
    
    if (!token || !userData) {
      ui.showView('login');
      ui.setLoading(false);
      return;
    }

    try {
      // Verify token and get fresh user data
      _currentUser = await api.getMe();
      localStorage.setItem('current-user', JSON.stringify(_currentUser));
      window.appState.currentUser = _currentUser;
      window.appState.isAuthenticated = true;

      // Render authenticated UI
      ui.renderUser(_currentUser);
      ui.showView('app');
      ui.setPanel('alerts'); // Default panel

      // Load settings and apply theme
      try {
        const appSettings = await api.getSettings();
        theme.apply(appSettings);
      } catch (err) {
        console.warn('Could not load settings:', err.message);
      }

      // Initialize modules
      console.log('Initializing modules...');
      if (typeof accounts !== 'undefined') accounts.init();
      if (typeof sources !== 'undefined') await sources.init(); // sources.init is async
      if (typeof alerts !== 'undefined') alerts.init();
      if (typeof settings !== 'undefined') settings.init();
      console.log('Modules initialized.');

      // Load default panel data
      console.log('Loading default panel (alerts)...');
      if (typeof alerts !== 'undefined') {
        await alerts.load();
      } else {
        // Fallback if alerts module is not available
        ui.el('alerts-content').innerHTML = '<div class="panel__placeholder">Aktuell sind noch keine Meldungen verfügbar.</div>';
      }
      console.log('Default panel loaded.');

    } catch (err) {
      // Token expired or invalid
      localStorage.removeItem('auth-token');
      localStorage.removeItem('current-user');
      ui.showView('login');
    }
    
    ui.setLoading(false);
  }

  // -- Public API --------------------------------------------------------
  return {
    init, handleLogin, handleLogout, handleNavClick,
    handleAddAccount, handleAccountsContentClick,
    handleAddSource, handleSourcesContentClick,
    handleAddAlert, handleAlertsContentClick,
  };
})();

/* ==========================================================================
   BOOTSTRAP - Event Listeners und App-Start
========================================================================== */
document.addEventListener('DOMContentLoaded', () => {
  initRipples();

  // Login
  document.getElementById('login-form')?.addEventListener('submit', app.handleLogin);
  ['username', 'password'].forEach(name => {
    document.getElementById(name)?.addEventListener('input', () => ui.setLoginError(null));
  });

  // Logout
  document.getElementById('logout-btn')?.addEventListener('click', app.handleLogout);
  document.getElementById('logout-card-btn')?.addEventListener('click', app.handleLogout);

  // Sidebar navigation
  document.querySelector('.sidebar')?.addEventListener('click', app.handleNavClick);

  // Panel-specific handlers
  document.getElementById('add-account-btn')?.addEventListener('click', () => {
    console.log('Add account clicked');
    app.handleAddAccount();
  });
  document.getElementById('accounts-content')?.addEventListener('click', app.handleAccountsContentClick);

  // Account modal
  document.getElementById('modal-cancel-btn')?.addEventListener('click', () => ui.closeAccountModal());
  document.getElementById('account-modal')?.querySelector('.modal__backdrop')
    ?.addEventListener('click', () => ui.closeAccountModal());

  document.getElementById('add-source-btn')?.addEventListener('click', () => {
    console.log('Add source clicked');
    app.handleAddSource();
  });
  document.getElementById('sources-content')?.addEventListener('click', app.handleSourcesContentClick);

  document.getElementById('add-alert-btn')?.addEventListener('click', () => {
    console.log('Add alert clicked');
    app.handleAddAlert();
  });
  document.getElementById('alerts-content')?.addEventListener('click', app.handleAlertsContentClick);

  // View alert modal
  document.getElementById('view-alert-close-btn')?.addEventListener('click', () => ui.closeViewAlertModal());
  document.getElementById('view-alert-modal')?.querySelector('.modal__backdrop')
    ?.addEventListener('click', () => ui.closeViewAlertModal());
  
  // Alert modal (create/edit)
  document.getElementById('alert-modal-cancel-btn')?.addEventListener('click', () => ui.closeAlertModal());
  document.getElementById('alert-modal')?.querySelector('.modal__backdrop')
    ?.addEventListener('click', () => ui.closeAlertModal());
  
  // Alert modal tabs
  document.querySelectorAll('#alert-modal .modal__tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const targetTab = tab.dataset.tab;
      
      // Update tab buttons
      document.querySelectorAll('#alert-modal .modal__tab').forEach(t => {
        const isActive = t.dataset.tab === targetTab;
        t.classList.toggle('modal__tab--active', isActive);
        t.setAttribute('aria-selected', isActive ? 'true' : 'false');
      });
      
      // Update tab panels
      document.querySelectorAll('#alert-modal .modal__tab-panel').forEach(panel => {
        panel.hidden = panel.dataset.tab !== targetTab;
      });
    });
  });
  
  // Alert modal add buttons
  document.getElementById('alert-add-translation-btn')?.addEventListener('click', () => {
    ui.addTranslationItem();
  });
  
  document.getElementById('alert-add-period-btn')?.addEventListener('click', () => {
    ui.addPeriodItem();
  });
  
  document.getElementById('alert-add-entity-btn')?.addEventListener('click', () => {
    ui.addEntityItem();
  });

  // Initialize app
  console.log('Starting application initialization...');
  app.init();
});