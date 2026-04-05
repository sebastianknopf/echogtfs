/* ==========================================================================
   LOCALIZATION - i18n functionality for multi-language support
   Requires: languages.js (must be loaded first)
========================================================================== */

const i18n = (() => {
  // Current language (default: German)
  let _currentLanguage = 'de';
  
  // LocalStorage key for user language preference
  const STORAGE_KEY = 'echogtfs_language';

  /**
   * Get translated string for a given key in the current language.
   * Returns the key itself if no translation is found.
   * 
   * @param {string} key - Translation key (e.g., 'login.title')
   * @param {Object} params - Optional parameters for string interpolation
   * @returns {string} Translated string or key if not found
   */
  function translate(key, params = {}) {
    // Access global translations from languages.js
    const translations = window.translations || {};
    const languageStrings = translations[_currentLanguage];
    
    if (!languageStrings) {
      console.warn(`Language '${_currentLanguage}' not found, falling back to key`);
      return key;
    }
    
    let text = languageStrings[key];
    
    if (!text) {
      console.warn(`Translation key '${key}' not found for language '${_currentLanguage}'`);
      return key;
    }
    
    // Simple parameter interpolation: {paramName} in strings
    if (params && typeof params === 'object') {
      Object.keys(params).forEach(paramKey => {
        const placeholder = `{${paramKey}}`;
        text = text.replace(new RegExp(placeholder, 'g'), params[paramKey]);
      });
    }
    
    return text;
  }

  /**
   * Set the current language.
   * 
   * @param {string} language - Language code ('de' or 'en')
   * @param {boolean} saveToStorage - Whether to save preference to localStorage (default: false)
   */
  function setLanguage(language, saveToStorage = false) {
    const translations = window.translations || {};
    
    if (!translations[language]) {
      console.warn(`Language '${language}' not supported, keeping current language '${_currentLanguage}'`);
      return;
    }
    
    _currentLanguage = language;
    
    // Save to localStorage if requested
    if (saveToStorage) {
      try {
        localStorage.setItem(STORAGE_KEY, language);
      } catch (error) {
        console.warn('Failed to save language preference to localStorage:', error);
      }
    }
    
    // Re-translate all elements with data-i18n attribute
    initializeTranslations();
  }
  
  /**
   * Get user's language preference from localStorage.
   * 
   * @returns {string|null} Language code or null if not set
   */
  function getUserLanguagePreference() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (error) {
      console.warn('Failed to read language preference from localStorage:', error);
      return null;
    }
  }
  
  /**
   * Clear user's language preference from localStorage.
   */
  function clearUserLanguagePreference() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (error) {
      console.warn('Failed to clear language preference from localStorage:', error);
    }
  }

  /**
   * Get the current language code.
   * 
   * @returns {string} Current language code (e.g., 'de', 'en')
   */
  function getCurrentLanguage() {
    return _currentLanguage;
  }

  /**
   * Load language setting from localStorage (user preference) or backend API.
   * Priority: localStorage > backend setting > default (de)
   * This is called early in the app initialization, before login.
   * The /app endpoint is public and doesn't require authentication.
   */
  async function loadLanguageFromSettings() {
    // First check localStorage for user preference
    const userPreference = getUserLanguagePreference();
    if (userPreference) {
      console.log('Using language from localStorage:', userPreference);
      setLanguage(userPreference);
      return;
    }
    
    // If no user preference, try to load from backend
    try {
      const response = await fetch('/api/settings/app');
      
      if (response.ok) {
        const settings = await response.json();
        
        if (settings.app_language) {
          console.log('Using language from backend settings:', settings.app_language);
          setLanguage(settings.app_language);
        } else {
          // No language set in backend, initialize with default
          initializeTranslations();
        }
      } else {
        // Failed to fetch settings, initialize with default
        initializeTranslations();
      }
    } catch (error) {
      console.warn('Failed to load language from settings, using default:', error);
      // Keep default language (de) on error, but still initialize
      initializeTranslations();
    }
  }

  /**
   * Initialize/update all HTML elements with data-i18n attribute.
   * Translates their text content based on the current language.
   * 
   * Supports:
   * - data-i18n="key" - translates textContent
   * - data-i18n-placeholder="key" - translates placeholder attribute
   * - data-i18n-title="key" - translates title attribute
   * - data-i18n-aria-label="key" - translates aria-label attribute
   */
  function initializeTranslations() {
    // Translate textContent
    document.querySelectorAll('[data-i18n]').forEach(element => {
      const key = element.getAttribute('data-i18n');
      if (key) {
        element.textContent = translate(key);
      }
    });
    
    // Translate placeholder attributes
    document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
      const key = element.getAttribute('data-i18n-placeholder');
      if (key) {
        element.placeholder = translate(key);
      }
    });
    
    // Translate title attributes
    document.querySelectorAll('[data-i18n-title]').forEach(element => {
      const key = element.getAttribute('data-i18n-title');
      if (key) {
        element.title = translate(key);
      }
    });
    
    // Translate aria-label attributes
    document.querySelectorAll('[data-i18n-aria-label]').forEach(element => {
      const key = element.getAttribute('data-i18n-aria-label');
      if (key) {
        element.setAttribute('aria-label', translate(key));
      }
    });
  }

  /**
   * Add a new translation key at runtime (for dynamic content).
   * 
   * @param {string} language - Language code ('de' or 'en')
   * @param {string} key - Translation key
   * @param {string} value - Translated string
   */
  function addTranslation(language, key, value) {
    const translations = window.translations || {};
    
    if (!translations[language]) {
      console.warn(`Language '${language}' not supported`);
      return;
    }
    
    translations[language][key] = value;
  }

  // Public API
  return {
    // Main translation function (also exposed as global function below)
    t: translate,
    
    // Language management
    setLanguage,
    getCurrentLanguage,
    loadLanguageFromSettings,
    getUserLanguagePreference,
    clearUserLanguagePreference,
    
    // Initialization
    initializeTranslations,
    
    // Dynamic translations
    addTranslation,
  };
})();

// Expose i18n as global function with all methods attached
// This allows both window.i18n('key') and window.i18n.setLanguage()
window.i18n = Object.assign(
  (...args) => i18n.t(...args),  // Make it callable as a function
  i18n  // Attach all methods as properties
);
