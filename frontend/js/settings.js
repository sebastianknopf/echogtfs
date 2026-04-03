/* ==========================================================================
   SETTINGS MODULE
========================================================================== */
const settings = (() => {
  let _pollInterval = null;

  function init() {
    // Sync color pickers with hex inputs
    _syncColorInputs('primary');
    _syncColorInputs('secondary');
    
    // Form submit handler for app settings
    const form = ui.el('settings-form');
    if (form) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        _saveSettings();
      });
    }
    
    // Reset button handler
    const resetBtn = ui.el('settings-reset-btn');
    if (resetBtn) {
      resetBtn.addEventListener('click', (e) => {
        e.preventDefault();
        _resetSettings();
      });
    }
    
    // GTFS section event handlers
    const gtfsSaveBtn = ui.el('settings-gtfs-save-btn');
    if (gtfsSaveBtn) {
      gtfsSaveBtn.addEventListener('click', () => {
        _saveGtfsFeed();
      });
    }
    
    const gtfsImportBtn = ui.el('settings-gtfs-import-btn');
    if (gtfsImportBtn) {
      gtfsImportBtn.addEventListener('click', () => {
        _triggerImport();
      });
    }
  }

  function _syncColorInputs(type) {
    const colorInput = ui.el(`settings-color-${type}`);
    const hexInput = ui.el(`settings-color-${type}-hex`);
    
    if (colorInput && hexInput) {
      colorInput.addEventListener('input', () => {
        hexInput.value = colorInput.value;
      });
      hexInput.addEventListener('input', () => {
        if (/^#[0-9A-Fa-f]{6}$/.test(hexInput.value)) {
          colorInput.value = hexInput.value;
        }
      });
    }
  }

  async function load() {
    try {
      
      // Load app settings and GTFS status concurrently
      const [appSettings, gtfsStatus] = await Promise.all([
        api.getSettings(),
        api.getGtfsStatus()
      ]);
      
      // Populate settings form
      _populateSettings(appSettings);
      
      // Populate GTFS feed form
      _populateGtfsFeed(gtfsStatus);
      
      // Display GTFS status
      _renderGtfsStatus(gtfsStatus);
      
      // Apply theme
      theme.apply(appSettings);
      
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  function _populateSettings(settings) {
    const titleInput = ui.el('settings-app-title');
    if (titleInput) {
      titleInput.value = settings.app_title || '';
    }
    
    const languageInput = ui.el('settings-app-language');
    if (languageInput) {
      languageInput.value = settings.app_language || 'de';
    }
    
    const primaryColor = settings.color_primary || '#008c99';
    const primaryInput = ui.el('settings-color-primary');
    const primaryHex = ui.el('settings-color-primary-hex');
    if (primaryInput) {
      primaryInput.value = primaryColor;
    }
    if (primaryHex) {
      primaryHex.value = primaryColor;
    }
    
    const secondaryColor = settings.color_secondary || '#99cc04';
    const secondaryInput = ui.el('settings-color-secondary');
    const secondaryHex = ui.el('settings-color-secondary-hex');
    if (secondaryInput) {
      secondaryInput.value = secondaryColor;
    }
    if (secondaryHex) {
      secondaryHex.value = secondaryColor;
    }
    
    const rtPath = ui.el('settings-gtfs-rt-path');
    if (rtPath) {
      rtPath.value = settings.gtfs_rt_path || '';
    }
    
    const rtUsername = ui.el('settings-gtfs-rt-username');
    if (rtUsername) {
      rtUsername.value = settings.gtfs_rt_username || '';
    }
    
    // Password field stays empty for security
  }

  function _populateGtfsFeed(status) {
    const urlInput = ui.el('settings-gtfs-url');
    if (urlInput) urlInput.value = status.feed_url || '';
    
    const cronInput = ui.el('settings-gtfs-cron');
    if (cronInput) cronInput.value = status.cron || '';
  }

  function _showStatus(text, type = '') {
    const box = ui.el('settings-gtfs-status');
    if (!box) return;
    box.className = 'gtfs-status' + (type ? ` gtfs-status--${type}` : '');
    box.innerHTML = type === 'running'
      ? `<span class="gtfs-status__spinner" aria-hidden="true"></span><span>${text}</span>`
      : text;
  }

  function _renderGtfsStatus(status) {
    if (!status) {
      _showStatus('');
      return;
    }
    
    const time = status.imported_at
      ? new Date(status.imported_at).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
      : null;

    if (status.status === 'running') {
      _showStatus(window.i18n('settings.gtfs_import_running'), 'running');
    } else if (status.status === 'success') {
      _showStatus(
        (time ? window.i18n('settings.gtfs_import_last', { time }) + ' — ' : '') + (status.message ?? ''),
        'success',
      );
    } else if (status.status === 'error') {
      _showStatus(
        (time ? window.i18n('settings.gtfs_import_error_time', { time, message: status.message ?? '' }) : window.i18n('settings.gtfs_import_error_short', { message: status.message ?? '' })),
        'error',
      );
    } else {
      _showStatus(time ? window.i18n('settings.gtfs_import_last_short', { time }) : window.i18n('settings.gtfs_import_none'));
    }
    
    // Continue polling during import
    if (status.status === 'running') {
      _startPolling();
    }
  }

  async function _saveSettings() {
    const saveBtn = ui.el('settings-save-btn');
    const spinner = ui.el('settings-save-spinner');
    const label = ui.el('settings-save-label');
    const errorEl = ui.el('settings-error');
    
    if (errorEl) errorEl.style.display = 'none';
    
    try {
      saveBtn.disabled = true;
      spinner.hidden = false;
      label.textContent = window.i18n('loading.saving');
      
      const data = {
        app_title: ui.el('settings-app-title')?.value || '',
        app_language: ui.el('settings-app-language')?.value || 'de',
        color_primary: ui.el('settings-color-primary')?.value || '#008c99',
        color_secondary: ui.el('settings-color-secondary')?.value || '#99cc04',
        gtfs_rt_path: ui.el('settings-gtfs-rt-path')?.value || '',
        gtfs_rt_username: ui.el('settings-gtfs-rt-username')?.value || '',
        gtfs_rt_password: ui.el('settings-gtfs-rt-password')?.value || '',
      };
      
      const result = await api.updateSettings(data);
      
      // Apply theme immediately
      theme.apply(result);
      
      // Apply language immediately
      if (result.app_language) {
        window.i18n.setLanguage(result.app_language);
      }
      
      ui.toast(window.i18n('settings.saved'));
      
      // Clear password field after successful save
      const pwInput = ui.el('settings-gtfs-rt-password');
      if (pwInput) pwInput.value = '';
      
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message;
        errorEl.style.display = 'block';
      }
      ui.toast(err.message, 'error');
    } finally {
      saveBtn.disabled = false;
      spinner.hidden = true;
      label.textContent = window.i18n('common.save');
    }
  }

  async function _resetSettings() {
    const confirmed = await ui.openConfirmModal(
      window.i18n('settings.reset.confirm'),
      window.i18n('settings.reset.title')
    );

    if (!confirmed) return;

    try {
      const defaults = {
        app_title: 'echogtfs',
        app_language: 'de',
        color_primary: '#008c99',
        color_secondary: '#99cc04',
        gtfs_rt_path: 'realtime/service-alerts.pbf',
        gtfs_rt_username: '',
        gtfs_rt_password: ''
      };
      
      const result = await api.updateSettings(defaults);
      
      // Re-populate form with defaults
      _populateSettings(result);
      
      // Apply theme
      theme.apply(result);
      
      ui.toast(window.i18n('settings.reset.done'));
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  async function _saveGtfsFeed() {
    const saveBtn = ui.el('settings-gtfs-save-btn');
    const errorEl = ui.el('settings-gtfs-error');
    
    if (errorEl) errorEl.style.display = 'none';
    
    try {
      saveBtn.disabled = true;
      
      let cron = ui.el('settings-gtfs-cron')?.value.trim() || '';
      if (!cron) cron = null;
      
      const data = {
        feed_url: ui.el('settings-gtfs-url')?.value || '',
        cron: cron,
      };
      
      await api.updateGtfsFeedUrl(data);
      
      ui.toast(window.i18n('settings.gtfs_url_saved'), 'success');
      
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message;
        errorEl.style.display = 'block';
      }
      ui.toast(err.message, 'error');
    } finally {
      saveBtn.disabled = false;
    }
  }

  async function _triggerImport() {
    const importBtn = ui.el('settings-gtfs-import-btn');
    const spinner = ui.el('settings-gtfs-import-spinner');
    const label = ui.el('settings-gtfs-import-label');
    const errorEl = ui.el('settings-gtfs-error');
    
    if (errorEl) errorEl.style.display = 'none';
    
    // Save URL and cron before triggering import
    const url = ui.el('settings-gtfs-url')?.value.trim();
    let cron = ui.el('settings-gtfs-cron')?.value.trim();
    if (!cron) cron = null;
    
    if (!url || (!url.startsWith('http://') && !url.startsWith('https://'))) {
      if (errorEl) {
        errorEl.textContent = window.i18n('settings.gtfs_import_url_required');
        errorEl.style.display = 'block';
      }
      return;
    }
    
    try {
      importBtn.disabled = true;
      spinner.hidden = false;
      label.textContent = window.i18n('loading.importing');
      
      _showStatus(window.i18n('settings.gtfs_import_running'), 'running');
      
      await api.updateGtfsFeedUrl({ feed_url: url, cron });
      await api.triggerGtfsImport();
      
      // Start polling for status updates
      _startPolling();
      
    } catch (err) {
      importBtn.disabled = false;
      spinner.hidden = true;
      label.textContent = window.i18n('common.import');
      _showStatus('');
      if (errorEl) {
        errorEl.textContent = err.message;
        errorEl.style.display = 'block';
      }
    }
  }

  function _startPolling() {
    // Clear existing timer
    if (_pollInterval) {
      clearInterval(_pollInterval);
    }
    
    let pollCount = 0;
    const maxPolls = 100; // 5 minutes at 3s interval
    
    _pollInterval = setInterval(async () => {
      try {
        pollCount++;
        
        const status = await api.getGtfsStatus();
        
        // Render status update
        _renderGtfsStatus(status);
        
        // Stop polling when complete or error
        if (status.status === 'success' || status.status === 'error' || pollCount >= maxPolls) {
          clearInterval(_pollInterval);
          _pollInterval = null;
          
          // Re-enable import button
          const importBtn = ui.el('settings-gtfs-import-btn');
          const spinner = ui.el('settings-gtfs-import-spinner');
          const label = ui.el('settings-gtfs-import-label');
          
          if (importBtn) importBtn.disabled = false;
          if (spinner) spinner.hidden = true;
          if (label) label.textContent = window.i18n('common.import');
          
          if (status.status === 'success') {
            ui.toast(window.i18n('settings.gtfs_import_success'));
          } else if (status.status === 'error') {
            ui.toast(window.i18n('settings.gtfs_import_error'), 'error');
          }
        }
        
      } catch (err) {
        clearInterval(_pollInterval);
        _pollInterval = null;
      }
    }, 3000);
  }

  return { init, load };
})();
