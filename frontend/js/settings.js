/* ==========================================================================
   SETTINGS MODULE
========================================================================== */
console.log('[SETTINGS] Script loading - before module creation');
const settings = (() => {
  console.log('[SETTINGS] Inside IIFE - module creation starting');
  let _pollInterval = null;

  function init() {
    console.log('[SETTINGS] init() called');
    
    // Sync color pickers with hex inputs
    console.log('[SETTINGS] Syncing color inputs...');
    _syncColorInputs('primary');
    _syncColorInputs('secondary');
    
    // Form submit handler for AppSettings
    const form = ui.el('settings-form');
    console.log('[SETTINGS] Settings form element:', form);
    if (form) {
      form.addEventListener('submit', (e) => {
        console.log('[SETTINGS] Form submit event triggered');
        e.preventDefault();
        _saveSettings();
      });
      console.log('[SETTINGS] Form submit handler registered');
    } else {
      console.error('[SETTINGS] Settings form not found!');
    }
    
    // Reset button handler
    const resetBtn = ui.el('settings-reset-btn');
    console.log('[SETTINGS] Reset button element:', resetBtn);
    if (resetBtn) {
      resetBtn.addEventListener('click', (e) => {
        console.log('[SETTINGS] Reset button clicked');
        e.preventDefault();
        _resetSettings();
      });
      console.log('[SETTINGS] Reset button handler registered');
    }
    
    // GTFS section handlers
    const gtfsSaveBtn = ui.el('settings-gtfs-save-btn');
    console.log('[SETTINGS] GTFS save button element:', gtfsSaveBtn);
    if (gtfsSaveBtn) {
      gtfsSaveBtn.addEventListener('click', () => {
        console.log('[SETTINGS] GTFS save button clicked');
        _saveGtfsFeed();
      });
      console.log('[SETTINGS] GTFS save button handler registered');
    }
    
    const gtfsImportBtn = ui.el('settings-gtfs-import-btn');
    console.log('[SETTINGS] GTFS import button element:', gtfsImportBtn);
    if (gtfsImportBtn) {
      gtfsImportBtn.addEventListener('click', () => {
        console.log('[SETTINGS] GTFS import button clicked');
        _triggerImport();
      });
      console.log('[SETTINGS] GTFS import button handler registered');
    }
    
    console.log('[SETTINGS] init() completed');
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
    console.log('[SETTINGS] load() called');
    try {
      console.log('[SETTINGS] Fetching app settings and GTFS status...');
      
      // Load app settings and GTFS status in parallel
      const [appSettings, gtfsStatus] = await Promise.all([
        api.getSettings(),
        api.getGtfsStatus()
      ]);
      
      console.log('[SETTINGS] App settings loaded:', appSettings);
      console.log('[SETTINGS] GTFS status loaded:', gtfsStatus);
      
      // Populate app settings form
      console.log('[SETTINGS] Populating settings form...');
      _populateSettings(appSettings);
      
      // Populate GTFS feed form
      console.log('[SETTINGS] Populating GTFS feed form...');
      _populateGtfsFeed(gtfsStatus);
      
      // Display GTFS status
      console.log('[SETTINGS] Rendering GTFS status...');
      _renderGtfsStatus(gtfsStatus);
      
      // Apply theme
      console.log('[SETTINGS] Applying theme...');
      theme.apply(appSettings);
      
      console.log('[SETTINGS] load() completed successfully');
      
    } catch (err) {
      console.error('[SETTINGS] Error loading settings:', err);
      ui.toast(err.message, 'error');
    }
  }

  function _populateSettings(settings) {
    console.log('[SETTINGS] _populateSettings() called with:', settings);
    
    const titleInput = ui.el('settings-app-title');
    console.log('[SETTINGS] Title input element:', titleInput);
    if (titleInput) {
      titleInput.value = settings.app_title || '';
      console.log('[SETTINGS] Set title to:', titleInput.value);
    }
    
    const primaryColor = settings.color_primary || '#008c99';
    const primaryInput = ui.el('settings-color-primary');
    const primaryHex = ui.el('settings-color-primary-hex');
    console.log('[SETTINGS] Primary color elements:', primaryInput, primaryHex);
    if (primaryInput) {
      primaryInput.value = primaryColor;
      console.log('[SETTINGS] Set primary color to:', primaryColor);
    }
    if (primaryHex) {
      primaryHex.value = primaryColor;
    }
    
    const secondaryColor = settings.color_secondary || '#99cc04';
    const secondaryInput = ui.el('settings-color-secondary');
    const secondaryHex = ui.el('settings-color-secondary-hex');
    console.log('[SETTINGS] Secondary color elements:', secondaryInput, secondaryHex);
    if (secondaryInput) {
      secondaryInput.value = secondaryColor;
      console.log('[SETTINGS] Set secondary color to:', secondaryColor);
    }
    if (secondaryHex) {
      secondaryHex.value = secondaryColor;
    }
    
    const rtPath = ui.el('settings-gtfs-rt-path');
    console.log('[SETTINGS] GTFS-RT path element:', rtPath);
    if (rtPath) {
      rtPath.value = settings.gtfs_rt_path || '';
      console.log('[SETTINGS] Set GTFS-RT path to:', rtPath.value);
    }
    
    const rtUsername = ui.el('settings-gtfs-rt-username');
    console.log('[SETTINGS] GTFS-RT username element:', rtUsername);
    if (rtUsername) {
      rtUsername.value = settings.gtfs_rt_username || '';
      console.log('[SETTINGS] Set GTFS-RT username to:', rtUsername.value);
    }
    
    console.log('[SETTINGS] _populateSettings() completed');
    // Password field stays empty (don't populate for security)
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
      _showStatus('Import läuft …', 'running');
    } else if (status.status === 'success') {
      _showStatus(
        (time ? `Letzter Import: ${time} — ` : '') + (status.message ?? ''),
        'success',
      );
    } else if (status.status === 'error') {
      _showStatus(
        (time ? `Fehler (${time}): ` : 'Fehler: ') + (status.message ?? ''),
        'error',
      );
    } else {
      _showStatus(time ? `Letzter Import: ${time}` : 'Noch kein Import durchgeführt.');
    }
    
    // Continue polling if import is running
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
      label.textContent = 'Wird gespeichert...';
      
      const data = {
        app_title: ui.el('settings-app-title')?.value || '',
        color_primary: ui.el('settings-color-primary')?.value || '#008c99',
        color_secondary: ui.el('settings-color-secondary')?.value || '#99cc04',
        gtfs_rt_path: ui.el('settings-gtfs-rt-path')?.value || '',
        gtfs_rt_username: ui.el('settings-gtfs-rt-username')?.value || '',
        gtfs_rt_password: ui.el('settings-gtfs-rt-password')?.value || '',
      };
      
      console.log('Saving settings:', data);
      const result = await api.updateSettings(data);
      
      // Apply theme immediately
      theme.apply(result);
      
      ui.toast('Einstellungen gespeichert.');
      
      // Clear password field after save
      const pwInput = ui.el('settings-gtfs-rt-password');
      if (pwInput) pwInput.value = '';
      
    } catch (err) {
      console.error('Error saving settings:', err);
      if (errorEl) {
        errorEl.textContent = err.message;
        errorEl.style.display = 'block';
      }
      ui.toast(err.message, 'error');
    } finally {
      saveBtn.disabled = false;
      spinner.hidden = true;
      label.textContent = 'Speichern';
    }
  }

  async function _resetSettings() {
    const confirmed = await ui.openConfirmModal(
      'Möchten Sie wirklich alle Einstellungen auf die Standardwerte zurücksetzen?',
      'Einstellungen zurücksetzen'
    );

    if (!confirmed) return;

    try {
      const defaults = {
        app_title: 'echogtfs',
        color_primary: '#008c99',
        color_secondary: '#99cc04',
        gtfs_rt_path: 'realtime/service-alerts.pbf',
        gtfs_rt_username: '',
        gtfs_rt_password: ''
      };
      
      const result = await api.updateSettings(defaults);
      
      // Repopulate form
      _populateSettings(result);
      
      // Apply theme
      theme.apply(result);
      
      ui.toast('Einstellungen zurückgesetzt.');
    } catch (err) {
      console.error('Error resetting settings:', err);
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
      
      console.log('Saving GTFS feed config:', data);
      await api.updateGtfsFeedUrl(data);
      
      ui.toast('Feed-URL und Cron gespeichert.', 'success');
      
    } catch (err) {
      console.error('Error saving GTFS feed:', err);
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
    
    // Save URL and cron first so the backend is up-to-date
    const url = ui.el('settings-gtfs-url')?.value.trim();
    let cron = ui.el('settings-gtfs-cron')?.value.trim();
    if (!cron) cron = null;
    
    if (!url || (!url.startsWith('http://') && !url.startsWith('https://'))) {
      if (errorEl) {
        errorEl.textContent = 'Bitte zuerst eine gültige Feed-URL eingeben.';
        errorEl.style.display = 'block';
      }
      return;
    }
    
    try {
      importBtn.disabled = true;
      spinner.hidden = false;
      label.textContent = 'Wird importiert …';
      
      _showStatus('Import läuft …', 'running');
      
      console.log('Saving GTFS config before import...');
      await api.updateGtfsFeedUrl({ feed_url: url, cron });
      
      console.log('Triggering GTFS import...');
      await api.triggerGtfsImport();
      
      // Start polling for status updates
      _startPolling();
      
    } catch (err) {
      console.error('Error triggering import:', err);
      importBtn.disabled = false;
      spinner.hidden = true;
      label.textContent = 'Importieren';
      _showStatus('');
      if (errorEl) {
        errorEl.textContent = err.message;
        errorEl.style.display = 'block';
      }
    }
  }

  function _startPolling() {
    // Clear existing interval
    if (_pollInterval) {
      clearInterval(_pollInterval);
    }
    
    let pollCount = 0;
    const maxPolls = 100; // 5 minutes at 3s intervals
    
    _pollInterval = setInterval(async () => {
      try {
        pollCount++;
        
        const status = await api.getGtfsStatus();
        console.log(`Status poll ${pollCount}:`, status);
        
        // Render updated status
        _renderGtfsStatus(status);
        
        // Stop polling if finished or error
        if (status.status === 'success' || status.status === 'error' || pollCount >= maxPolls) {
          clearInterval(_pollInterval);
          _pollInterval = null;
          
          // Re-enable import button
          const importBtn = ui.el('settings-gtfs-import-btn');
          const spinner = ui.el('settings-gtfs-import-spinner');
          const label = ui.el('settings-gtfs-import-label');
          
          if (importBtn) importBtn.disabled = false;
          if (spinner) spinner.hidden = true;
          if (label) label.textContent = 'Importieren';
          
          if (status.status === 'success') {
            ui.toast('GTFS-Import erfolgreich abgeschlossen.');
          } else if (status.status === 'error') {
            ui.toast('GTFS-Import fehlgeschlagen. Siehe Status-Details.', 'error');
          }
        }
        
      } catch (err) {
        console.error('Error polling status:', err);
        clearInterval(_pollInterval);
        _pollInterval = null;
      }
    }, 3000);
  }

  console.log('[SETTINGS] Module creation complete - returning public API');
  return { init, load };
})();
console.log('[SETTINGS] Module assigned to window.settings:', typeof settings, settings);
