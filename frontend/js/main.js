/* ==========================================================================
   MAIN APP - Main application logic and navigation
========================================================================== */

// Global app state for cross-module access
window.appState = {
  currentUser: null,
  isAuthenticated: false
};

const app = (() => {
  let _currentUser = null;

  // Authentication
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
      
      // Fetch user data after successful login
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

  // Navigation
  function handleNavClick(e) {
    const navItem = e.target.closest('.nav-item[data-panel]');
    if (!navItem) return;

    e.preventDefault();
    const panel = navItem.dataset.panel;
    ui.setPanel(panel);

    // Load panel data
    switch (panel) {
      case 'accounts':
        if (typeof accounts !== 'undefined') {
          accounts.load();
        }
        break;
      case 'sources':
        if (typeof sources !== 'undefined') {
          sources.load();
        }
        break;
      case 'alerts':
        if (typeof alerts !== 'undefined') {
          alerts.load();
        }
        break;
      case 'settings':
        if (typeof settings !== 'undefined') {
          settings.load();
        }
        break;
    }
  }

  // Add handlers
  function handleAddAccount() {
    if (typeof accounts !== 'undefined') accounts.openCreateModal();
  }

  function handleAddSource() {
    if (typeof sources !== 'undefined') sources.openCreateModal();
  }

  function handleAddAlert() {
    if (typeof alerts !== 'undefined') alerts.openCreateModal();
  }

  // Content click handlers (delegate to modules)
  function handleAccountsContentClick(e) {
    if (typeof accounts !== 'undefined') accounts.handleContentClick(e);
  }

  function handleSourcesContentClick(e) {
    if (typeof sources !== 'undefined') sources.handleContentClick(e);
  }

  function handleAlertsContentClick(e) {
    if (typeof alerts !== 'undefined') alerts.handleContentClick(e);
  }

  // Initialization
  async function init() {
    // Check for existing authentication
    const token = localStorage.getItem('auth-token');
    const userData = localStorage.getItem('current-user');
    
    if (!token || !userData) {
      ui.showView('login');
      ui.setLoading(false);
      return;
    }

    try {
      // Verify token and get current user data
      _currentUser = await api.getMe();
      localStorage.setItem('current-user', JSON.stringify(_currentUser));
      window.appState.currentUser = _currentUser;
      window.appState.isAuthenticated = true;

      // Render authenticated UI
      ui.renderUser(_currentUser);
      ui.showView('app');
      ui.setPanel('alerts'); // Default panel
      
      // Update language selector to show active language
      if (typeof languageSelector !== 'undefined') {
        languageSelector.init();
      }

      // Load settings
      try {
        const appSettings = await api.getSettings();
        theme.apply(appSettings);
        
        // Apply language setting only if user hasn't set a preference in browser
        if (appSettings.app_language && !window.i18n.getUserLanguagePreference()) {
          window.i18n.setLanguage(appSettings.app_language);
        }
      } catch (err) {
      }

      // Initialize modules
      if (typeof accounts !== 'undefined') accounts.init();
      if (typeof sources !== 'undefined') await sources.init(); // sources.init is async
      if (typeof alerts !== 'undefined') alerts.init();
      if (typeof settings !== 'undefined') settings.init();

      // Load default panel
      if (typeof alerts !== 'undefined') {
        await alerts.load();
      } else {
        // Fallback if module not available
        ui.el('alerts-content').innerHTML = `<div class="panel__placeholder">${window.i18n('alerts.empty')}</div>`;
      }

    } catch (err) {
      // Token invalid or expired
      localStorage.removeItem('auth-token');
      localStorage.removeItem('current-user');
      ui.showView('login');
    }
    
    ui.setLoading(false);
  }

  // Public API
  return {
    init, handleLogin, handleLogout, handleNavClick,
    handleAddAccount, handleAccountsContentClick,
    handleAddSource, handleSourcesContentClick,
    handleAddAlert, handleAlertsContentClick,
  };
})();

/* ==========================================================================
   LANGUAGE SELECTOR - Language switching functionality
========================================================================== */
const languageSelector = (() => {
  let _isOpen = false;
  
  function toggleMenu() {
    const menu = document.getElementById('language-menu');
    const button = document.getElementById('language-btn');
    
    if (!menu || !button) return;
    
    _isOpen = !_isOpen;
    
    if (_isOpen) {
      menu.classList.add('is-open');
      button.setAttribute('aria-expanded', 'true');
      updateActiveLanguage();
      
      // Focus first option when opening
      const firstOption = menu.querySelector('.language-selector__option');
      if (firstOption) {
        setTimeout(() => firstOption.focus(), 0);
      }
    } else {
      menu.classList.remove('is-open');
      button.setAttribute('aria-expanded', 'false');
    }
  }
  
  function closeMenu() {
    const menu = document.getElementById('language-menu');
    const button = document.getElementById('language-btn');
    
    if (!menu || !button) return;
    
    _isOpen = false;
    menu.classList.remove('is-open');
    button.setAttribute('aria-expanded', 'false');
  }
  
  function updateActiveLanguage() {
    const currentLang = window.i18n.getCurrentLanguage();
    const options = document.querySelectorAll('.language-selector__option');
    
    options.forEach(option => {
      const lang = option.getAttribute('data-lang');
      if (lang === currentLang) {
        option.classList.add('is-active');
      } else {
        option.classList.remove('is-active');
      }
    });
  }
  
  function selectLanguage(lang) {
    // Set language with saveToStorage = true to persist in localStorage
    window.i18n.setLanguage(lang, true);
    updateActiveLanguage();
    closeMenu();
  }
  
  function init() {
    // Set initial active state
    updateActiveLanguage();
  }
  
  return {
    init,
    toggleMenu,
    closeMenu,
    selectLanguage,
  };
})();

/* ==========================================================================
   PROFILE SELECTOR - User profile dropdown functionality
========================================================================== */
const profileSelector = (() => {
  let _isOpen = false;
  
  function toggleMenu() {
    const menu = document.getElementById('profile-menu');
    const button = document.getElementById('profile-btn');
    
    if (!menu || !button) return;
    
    _isOpen = !_isOpen;
    
    if (_isOpen) {
      menu.classList.add('is-open');
      button.setAttribute('aria-expanded', 'true');
      
      // Focus first option when opening
      const firstOption = menu.querySelector('.profile-selector__option');
      if (firstOption) {
        setTimeout(() => firstOption.focus(), 0);
      }
    } else {
      menu.classList.remove('is-open');
      button.setAttribute('aria-expanded', 'false');
    }
  }
  
  function closeMenu() {
    const menu = document.getElementById('profile-menu');
    const button = document.getElementById('profile-btn');
    
    if (!menu || !button) return;
    
    _isOpen = false;
    menu.classList.remove('is-open');
    button.setAttribute('aria-expanded', 'false');
  }
  
  return {
    toggleMenu,
    closeMenu,
  };
})();

/* ==========================================================================
   PASSWORD MODAL - Change password functionality
========================================================================== */
const passwordModal = (() => {
  let _modal = null;
  let _form = null;
  
  function open() {
    _modal = document.getElementById('password-modal');
    _form = document.getElementById('password-form');
    
    if (!_modal || !_form) return;
    
    // Reset form
    _form.reset();
    setError(null);
    
    // Show modal
    _modal.removeAttribute('hidden');
    
    // Focus first field
    const firstInput = document.getElementById('password-current');
    if (firstInput) {
      setTimeout(() => firstInput.focus(), 100);
    }
    
    // Close profile menu
    profileSelector.closeMenu();
  }
  
  function close() {
    if (!_modal) return;
    _modal.setAttribute('hidden', '');
    _form?.reset();
    setError(null);
  }
  
  function setError(message) {
    const errorEl = document.getElementById('password-error');
    if (!errorEl) return;
    
    if (message) {
      errorEl.textContent = message;
      errorEl.style.display = 'block';
    } else {
      errorEl.textContent = '';
      errorEl.style.display = 'none';
    }
  }
  
  function setBusy(busy) {
    const submitBtn = document.getElementById('password-submit-btn');
    const spinner = document.getElementById('password-submit-spinner');
    const label = document.getElementById('password-submit-label');
    
    if (!submitBtn) return;
    
    submitBtn.disabled = busy;
    if (spinner) spinner.hidden = !busy;
    if (label) label.textContent = busy ? window.i18n('loading.saving') : window.i18n('common.save');
  }
  
  async function handleSubmit(e) {
    e.preventDefault();
    
    const formData = new FormData(_form);
    const currentPassword = formData.get('current_password');
    const newPassword = formData.get('new_password');
    const repeatPassword = formData.get('new_password_repeat');
    
    // Client-side validation
    if (!currentPassword) {
      setError(window.i18n('password.error.current_required'));
      return;
    }
    
    if (!newPassword) {
      setError(window.i18n('password.error.new_required'));
      return;
    }
    
    if (!repeatPassword) {
      setError(window.i18n('password.error.repeat_required'));
      return;
    }
    
    if (newPassword !== repeatPassword) {
      setError(window.i18n('password.error.mismatch'));
      return;
    }
    
    // Make API request
    setBusy(true);
    setError(null);
    
    try {
      const response = await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      
      // Success
      ui.toast(window.i18n('password.success'), 'success');
      close();
    } catch (err) {
      // Check if it's an incorrect password error
      if (err.message && err.message.includes('incorrect')) {
        setError(window.i18n('password.error.current_incorrect'));
      } else {
        setError(err.message);
      }
    } finally {
      setBusy(false);
    }
  }
  
  return {
    open,
    close,
    handleSubmit,
  };
})();

/* ==========================================================================
   BOOTSTRAP - Event listeners and app startup
========================================================================== */

/**
 * Load public app settings (theme and language) from backend.
 * This is called before login to apply theme and language to the login page.
 */
async function loadPublicAppSettings() {
  try {
    const response = await fetch('/api/settings/app');
    
    if (response.ok) {
      const settings = await response.json();
      
      // Apply theme
      if (settings.color_primary && settings.color_secondary) {
        theme.apply({
          color_primary: settings.color_primary,
          color_secondary: settings.color_secondary,
          app_title: settings.app_title
        });
      }
      
      // Display version
      if (settings.app_version) {
        const versionLogin = document.getElementById('version-info-login');
        const versionApp = document.getElementById('version-info-app');
        console.log('Setting version to:', settings.app_version);
        if (versionLogin) versionLogin.textContent = `v${settings.app_version}`;
        if (versionApp) versionApp.textContent = `v${settings.app_version}`;
      } else {
        console.warn('No app_version in settings:', settings);
      }
      
      // Apply language: localStorage preference > backend setting
      const userPreference = window.i18n.getUserLanguagePreference();
      if (userPreference) {
        console.log('Using language from localStorage:', userPreference);
        window.i18n.setLanguage(userPreference);
      } else if (settings.app_language) {
        console.log('Using language from backend settings:', settings.app_language);
        window.i18n.setLanguage(settings.app_language);
      } else {
        // No language set, initialize with default
        window.i18n.initializeTranslations();
      }
    } else {
      // Failed to fetch settings, initialize with default
      window.i18n.initializeTranslations();
    }
  } catch (error) {
    console.warn('Failed to load public app settings, using defaults:', error);
    // Initialize with defaults on error
    window.i18n.initializeTranslations();
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  // Load theme and language from backend settings first (before any UI is shown)
  await loadPublicAppSettings();
  
  // Initialize button ripple effects
  initRipples();
  
  // Initialize language selector
  languageSelector.init();

  // Login
  document.getElementById('login-form')?.addEventListener('submit', app.handleLogin);
  ['username', 'password'].forEach(name => {
    document.getElementById(name)?.addEventListener('input', () => ui.setLoginError(null));
  });

  // Logout
  document.getElementById('logout-btn')?.addEventListener('click', app.handleLogout);
  document.getElementById('logout-card-btn')?.addEventListener('click', app.handleLogout);
  
  // Language selector
  document.getElementById('language-btn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    profileSelector.closeMenu(); // Close profile menu when opening language menu
    languageSelector.toggleMenu();
  });
  
  // Language options
  document.querySelectorAll('.language-selector__option').forEach(option => {
    option.addEventListener('click', (e) => {
      e.stopPropagation();
      const lang = option.getAttribute('data-lang');
      if (lang) {
        languageSelector.selectLanguage(lang);
      }
    });
    
    // Keyboard navigation
    option.addEventListener('keydown', (e) => {
      const options = Array.from(document.querySelectorAll('.language-selector__option'));
      const currentIndex = options.indexOf(option);
      
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          const nextIndex = (currentIndex + 1) % options.length;
          options[nextIndex].focus();
          break;
        case 'ArrowUp':
          e.preventDefault();
          const prevIndex = (currentIndex - 1 + options.length) % options.length;
          options[prevIndex].focus();
          break;
        case 'Enter':
        case ' ':
          e.preventDefault();
          const lang = option.getAttribute('data-lang');
          if (lang) {
            languageSelector.selectLanguage(lang);
          }
          break;
      }
    });
  });
  
  // Close language menu when clicking outside
  document.addEventListener('click', (e) => {
    const languageMenu = document.getElementById('language-menu');
    const languageBtn = document.getElementById('language-btn');
    
    if (languageMenu && languageBtn &&
        !languageMenu.contains(e.target) && 
        !languageBtn.contains(e.target)) {
      languageSelector.closeMenu();
    }
  });
  
  // Close language menu on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      languageSelector.closeMenu();
      profileSelector.closeMenu();
      passwordModal.close();
    }
  });
  
  // Profile selector
  document.getElementById('profile-btn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    languageSelector.closeMenu(); // Close language menu when opening profile menu
    profileSelector.toggleMenu();
  });
  
  document.getElementById('change-password-btn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    passwordModal.open();
  });
  
  // Close profile menu when clicking outside
  document.addEventListener('click', (e) => {
    const profileMenu = document.getElementById('profile-menu');
    const profileBtn = document.getElementById('profile-btn');
    
    if (profileMenu && profileBtn &&
        !profileMenu.contains(e.target) && 
        !profileBtn.contains(e.target)) {
      profileSelector.closeMenu();
    }
  });
  
  // Password modal
  document.getElementById('password-form')?.addEventListener('submit', passwordModal.handleSubmit);
  document.getElementById('password-cancel-btn')?.addEventListener('click', () => passwordModal.close());
  document.getElementById('password-modal')?.querySelector('.modal__backdrop')
    ?.addEventListener('click', () => passwordModal.close());

  // Sidebar navigation
  document.querySelector('.sidebar')?.addEventListener('click', app.handleNavClick);

  // Panel-specific handlers
  document.getElementById('add-account-btn')?.addEventListener('click', () => {
    app.handleAddAccount();
  });
  document.getElementById('accounts-content')?.addEventListener('click', app.handleAccountsContentClick);

  // Account modal
  document.getElementById('modal-cancel-btn')?.addEventListener('click', () => ui.closeAccountModal());
  document.getElementById('account-modal')?.querySelector('.modal__backdrop')
    ?.addEventListener('click', () => ui.closeAccountModal());

  document.getElementById('add-source-btn')?.addEventListener('click', () => {
    app.handleAddSource();
  });
  document.getElementById('sources-content')?.addEventListener('click', app.handleSourcesContentClick);

  document.getElementById('add-alert-btn')?.addEventListener('click', () => {
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

  // Initialize application
  app.init();
});