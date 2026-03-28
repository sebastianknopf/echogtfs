/* ==========================================================================
   SOURCES MODULE - Datenquellen-Management
========================================================================== */

const sources = (() => {
  let _sources = [];
  let _adapterTypes = [];
  let _editingSourceId = null;

  // -- Source Mapping Management ------------------------------------------
  let _allMappings = [];
  let _currentDisplayedEntityType = 'agency'; // Track which entity type is currently displayed
  
  const _entityTypeNames = {
    'agency': 'Unternehmen',
    'route': 'Linien', 
    'stop': 'Haltestellen'
  };
  
  // Helper to check if user has poweruser or admin rights
  function _isPoweruser() {
    const user = window.appState?.currentUser;
    return user && (user.is_technical_contact || user.is_superuser);
  }
  
  function _initializeMappings(mappings) {
    _allMappings = mappings || [];
    console.log('Initialized mappings:', _allMappings);
    console.log('Mappings details:', _allMappings.map(m => `${m.entity_type}: ${m.key} -> ${m.value}`).join(', '));
  }
  
  function _saveCurrentMappings() {
    // Use the currently DISPLAYED entity type, not the one from the select
    // (because when this is called on change, the select has the NEW value but UI shows OLD rows)
    const entityTypeToSave = _currentDisplayedEntityType;
    if (!entityTypeToSave) return;
    
    console.log(`Saving current mappings for displayed entity type: ${entityTypeToSave}`)
    
    // Get existing mappings for this entity type (to preserve IDs)
    const existingMappings = _allMappings.filter(m => m.entity_type === entityTypeToSave);
    
    // Remove existing mappings for this entity type
    _allMappings = _allMappings.filter(m => m.entity_type !== entityTypeToSave);
    
    // Add current UI mappings for this entity type (only from mappings-container)
    const container = ui.el('mappings-container');
    if (!container) return;
    
    const rows = container.querySelectorAll('.mapping-row');
    console.log(`Found ${rows.length} mapping rows in UI for entity type: ${entityTypeToSave}`);
    
    rows.forEach((row, index) => {
      const key = row.querySelector('[name="mapping-key"]')?.value?.trim();
      const value = row.querySelector('[name="mapping-value"]')?.value?.trim();
      if (key && value) {
        // Try to find existing mapping with same key to preserve ID
        const existingMapping = existingMappings.find(m => m.key === key);
        const mapping = {
          entity_type: entityTypeToSave,
          key,
          value
        };
        // Preserve ID if this mapping existed before
        if (existingMapping && existingMapping.id) {
          mapping.id = existingMapping.id;
        }
        _allMappings.push(mapping);
      }
    });
    
    console.log('All mappings after save:', _allMappings);
  }
  
  function _renderMappingsForEntityType(entityType) {
    console.log(`Rendering mappings for entity type: ${entityType}`);
    console.log('All mappings:', _allMappings);
    const filteredMappings = _allMappings.filter(m => m.entity_type === entityType);
    console.log('Filtered mappings:', filteredMappings);
    console.log('Filtered mappings details:', filteredMappings.map(m => `${m.key} -> ${m.value}`).join(', '));
    const container = ui.el('mappings-container');
    
    if (!filteredMappings.length) {
      const entityTypeName = _entityTypeNames[entityType] || 'diesen Typ';
      console.log(`No mappings for ${entityType}, showing placeholder`);
      container.innerHTML = `<p class="panel__placeholder">Keine Mappings für ${entityTypeName} vorhanden.</p>`;
      // Update the currently displayed entity type after rendering
      _currentDisplayedEntityType = entityType;
      return;
    }
    
    console.log(`Creating table with ${filteredMappings.length} rows`);
    const table = document.createElement('table');
    table.className = 'mapping-table';
    table.innerHTML = `
      <thead><tr>
        <th>Schlüssel</th>
        <th>Wert (Entity ID)</th>
        <th></th>
      </tr></thead>
      <tbody></tbody>`;
    
    const tbody = table.querySelector('tbody');
    filteredMappings.forEach(mapping => {
      console.log(`Creating row for mapping: ${mapping.key} -> ${mapping.value}`);
      const row = _createMappingRow(mapping);
      tbody.appendChild(row);
    });
    
    console.log('Clearing container and adding new table');
    container.innerHTML = '';
    container.appendChild(table);
    console.log('Table appended, rows in tbody:', tbody.children.length);
    
    // Re-initialize ripples for new buttons
    initRipples(container);
    
    // Update the currently displayed entity type after rendering
    _currentDisplayedEntityType = entityType;
    console.log('Rendering complete for entity type:', entityType);
  }
  
  function _createMappingRow(mapping = {}) {
    console.log('Creating mapping row with data:', mapping);
    const tr = document.createElement('tr');
    tr.className = 'mapping-row';
    
    const currentEntityType = mapping.entity_type || ui.el('mapping-entity-type-select')?.value || 'agency';
    tr.dataset.entityType = currentEntityType;
    
    const keyValue = ui.esc(mapping.key || '');
    const valueValue = ui.esc(mapping.value || '');
    console.log(`Row values: key="${keyValue}", value="${valueValue}"`);
    
    tr.innerHTML = `
      <td><input type="text" name="mapping-key" class="md-field__input" value="${keyValue}" placeholder="z.B. externer Key" /></td>
      <td><input type="text" name="mapping-value" class="md-field__input" value="${valueValue}" placeholder="z.B. route_123" /></td>
      <td><button type="button" class="icon-btn icon-btn--danger" data-action="remove-mapping" title="Entfernen" data-ripple>
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
        </svg>
      </button></td>`;
    
    return tr;
  }
  
  function _addMappingRow() {
    const entityType = ui.el('mapping-entity-type-select')?.value || 'agency';
    const container = ui.el('mappings-container');
    
    // Create table if it doesn't exist
    let table = container.querySelector('.mapping-table');
    if (!table) {
      table = document.createElement('table');
      table.className = 'mapping-table';
      table.innerHTML = `
        <thead><tr>
          <th>Schlüssel</th>
          <th>Wert (Entity ID)</th>
          <th></th>
        </tr></thead>
        <tbody></tbody>`;
      container.innerHTML = '';
      container.appendChild(table);
    }
    
    const tbody = table.querySelector('tbody');
    const row = _createMappingRow({ entity_type: entityType });
    tbody.appendChild(row);
    
    // Initialize ripples for new button
    initRipples(row);
  }
  
  function _removeMappingRow(event) {
    const btn = event.target.closest('[data-action="remove-mapping"]');
    if (!btn) return;
    
    const row = btn.closest('.mapping-row');
    const tbody = row.parentElement;
    row.remove();
    
    // Show placeholder if no rows left
    if (tbody.children.length === 0) {
      const entityType = ui.el('mapping-entity-type-select')?.value || 'agency';
      const entityTypeName = _entityTypeNames[entityType] || 'diesen Typ';
      ui.el('mappings-container').innerHTML = 
        `<p class="panel__placeholder">Keine Mappings für ${entityTypeName} vorhanden.</p>`;
    }
  }
  
  function _getAllMappings() {
    _saveCurrentMappings(); // Save current state first
    return [..._allMappings]; // Return copy
  }

  // -- Internal State Management -------------------------------------------
  async function _loadSources() {
    console.log('Loading sources via API...');
    try {
      _sources = await api.getSources();
      console.log('Sources loaded:', _sources.length);
      _renderSourcesList();
    } catch (err) {
      console.error('Error loading sources:', err);
      ui.toast(err.message, 'error');
      // Show error in UI
      const container = ui.el('sources-content');
      container.innerHTML = `<div class="panel__placeholder">Fehler beim Laden: ${err.message}</div>`;
    }
  }
  
  function _renderSourcesList() {
    const container = ui.el('sources-content');
    if (!_sources.length) {
      container.innerHTML = '<div class="panel__placeholder">Keine Datenquellen vorhanden.</div>';
      return;
    }
    
    const table = document.createElement('table');
    table.className = 'user-table';
    table.innerHTML = `
      <thead><tr>
        <th>Name</th>
        <th>Typ</th>
        <th>Cron</th>
        <th>Letzte Ausführung</th>
        <th></th>
      </tr></thead>
      <tbody></tbody>`;
    
    const tbody = table.querySelector('tbody');
    _sources.forEach(source => {
      const tr = document.createElement('tr');
      const cronText = source.cron || '—';
      const lastRunText = source.last_run_at 
        ? new Date(source.last_run_at).toLocaleString('de-DE', { 
            dateStyle: 'short', 
            timeStyle: 'short' 
          })
        : '—';
      tr.innerHTML = `
        <td>${ui.esc(source.name)}</td>
        <td>${ui.esc(source.type)}</td>
        <td><code>${ui.esc(cronText)}</code></td>
        <td>${ui.esc(lastRunText)}</td>
        <td><div class="user-table__actions">
          <button class="icon-btn" data-action="run" data-id="${source.id}"
            title="Jetzt ausführen" aria-label="Datenquelle ${ui.esc(source.name)} jetzt ausführen" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
          </button>
          <button class="icon-btn" data-action="edit" data-id="${source.id}"
            title="Bearbeiten" aria-label="Datenquelle ${ui.esc(source.name)} bearbeiten" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
          </button>
          <button class="icon-btn icon-btn--danger" data-action="delete" data-id="${source.id}"
            title="Löschen" aria-label="Datenquelle ${ui.esc(source.name)} löschen" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          </button>
        </div></td>`;
      tbody.appendChild(tr);
    });
    
    container.innerHTML = '';
    container.appendChild(table);
    if (window.initRipples) initRipples(container);
  }

  async function _loadAdapterTypes() {
    // Check if user has permission to load adapter types
    if (!_isPoweruser()) {
      console.log('Skipping adapter types load: user does not have poweruser rights');
      _adapterTypes = [];
      return;
    }
    
    console.log('Loading adapter types via API...');
    try {
      const response = await api.getAdapterTypes();
      _adapterTypes = response.adapter_types || [];
      console.log('Adapter types loaded:', _adapterTypes.length, _adapterTypes);
    } catch (err) {
      console.error('Error loading adapter types:', err);
      ui.toast(err.message, 'error');
      _adapterTypes = [];
    }
  }

  // -- Source Modal Management ---------------------------------------------
  function _openSourceModal({ title, name = '', type = '', config = {}, cron = '', mappings = [] } = {}) {
    ui.el('source-modal-title').textContent = title;
    ui.el('source-name').value = name;
    ui.el('source-name').readOnly = false;
    
    // Populate adapter type dropdown
    const typeSelect = ui.el('source-type');
    typeSelect.innerHTML = '<option value="">Typ auswählen...</option>';
    if (_adapterTypes && Array.isArray(_adapterTypes) && _adapterTypes.length > 0) {
      _adapterTypes.forEach(adapter => {
        const option = document.createElement('option');
        option.value = adapter.type;
        option.textContent = adapter.type;
        typeSelect.appendChild(option);
      });
    } else {
      console.warn('No adapter types available. _adapterTypes:', _adapterTypes);
    }
    typeSelect.value = type;
    
    // Ensure config is an object
    const configObj = (typeof config === 'object' && config !== null) ? config : {};
    _renderConfigFields(type, configObj);
    
    ui.el('source-cron').value = cron || '';
    
    // Initialize mappings
    _initializeMappings(mappings);
    const entityTypeSelect = ui.el('mapping-entity-type-select');
    if (entityTypeSelect) {
      // Default to 'agency' as first entity type
      const defaultEntityType = 'agency';
      entityTypeSelect.value = defaultEntityType;
      _currentDisplayedEntityType = defaultEntityType; // Initialize tracking variable
      _renderMappingsForEntityType(defaultEntityType);
    }
    
    // Reset to first tab (Konfiguration) - scope to source-modal only
    const modal = ui.el('source-modal');
    modal.querySelectorAll('.modal__tab').forEach((tab, idx) => {
      const isFirst = idx === 0;
      tab.classList.toggle('modal__tab--active', isFirst);
      tab.setAttribute('aria-selected', isFirst ? 'true' : 'false');
    });
    modal.querySelectorAll('.modal__tab-panel').forEach((panel, idx) => {
      panel.hidden = idx !== 0;
    });
    
    ui.el('source-modal-error').textContent = '';
    ui.el('source-modal-error').classList.remove('is-visible');
    modal.hidden = false;
    ui.el('source-name').focus();
  }
  
  function _closeSourceModal() {
    ui.el('source-modal').hidden = true;
  }
  
  function _setSourceModalBusy(busy) {
    ui.el('source-modal-submit-btn').disabled = busy;
    ui.el('source-modal-submit-spinner').hidden = !busy;
    ui.el('source-modal-submit-label').textContent = busy ? 'Wird gespeichert ...' : 'Speichern';
  }
  
  function _setSourceModalError(msg) {
    const e = ui.el('source-modal-error');
    e.textContent = msg ?? '';
    e.classList.toggle('is-visible', !!msg);
  }
  
  async function _openCreateSource() {
    // Ensure adapter types are loaded before opening modal
    if (!_adapterTypes || _adapterTypes.length === 0) {
      await _loadAdapterTypes();
    }
    
    _editingSourceId = null;
    _openSourceModal({
      title: 'Neue Datenquelle',
      name: '',
      type: '',
      config: {},
      cron: '',
      mappings: []
    });
    
    // Setup form submit handler for create mode
    document.getElementById('source-form').onsubmit = e => _saveSource(e);
  }

  async function _openEditSource(sourceId) {
    try {
      // Ensure adapter types are loaded before opening modal
      if (!_adapterTypes || _adapterTypes.length === 0) {
        await _loadAdapterTypes();
      }
      
      _editingSourceId = sourceId;
      const source = await api.getSource(sourceId);
      
      // Backend returns config as JSON string, parse it
      let configObj = {};
      try {
        configObj = JSON.parse(source.config || '{}');
      } catch (err) {
        console.error('Failed to parse source config:', err);
        configObj = {};
      }
      
      _openSourceModal({
        title: 'Datenquelle bearbeiten',
        name: source.name,
        type: source.type,
        config: configObj,
        cron: source.cron || '',
        mappings: source.mappings || []
      });
      
      // Setup form submit handler for edit mode
      document.getElementById('source-form').onsubmit = e => _saveSource(e);
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  async function _saveSource(e) {
    e.preventDefault();
    
    const name = ui.el('source-name').value.trim();
    const type = ui.el('source-type').value;
    const cron = ui.el('source-cron').value.trim();

    if (!name || !type) {
      _setSourceModalError('Name und Typ sind erforderlich.');
      return;
    }

    // Parse config from form fields
    let config = {};
    document.querySelectorAll('#source-config-fields input, #source-config-fields textarea').forEach(input => {
      const fieldName = input.name.replace('config-', '');
      const value = input.value.trim();
      if (value) {
        config[fieldName] = value;
      }
    });

    // Collect mappings from internal mapping manager
    const mappings = _getAllMappings();

    _setSourceModalBusy(true);
    try {
      // Backend expects config as JSON string, not object
      const data = { 
        name, 
        type, 
        config: JSON.stringify(config), 
        cron: cron || null, 
        mappings 
      };
      if (!_editingSourceId) {
        await api.createSource(data);
      } else {
        await api.updateSource(_editingSourceId, data);
      }
      _closeSourceModal();
      await _loadSources();
      ui.toast(_editingSourceId ? 'Datenquelle aktualisiert.' : 'Datenquelle erstellt.');
    } catch (err) {
      _setSourceModalError(err.message);
    } finally {
      _setSourceModalBusy(false);
    }
  }

  async function _deleteSource(sourceId) {
    const source = _sources.find(s => s.id === sourceId);
    if (!source) return;

    const confirmed = await ui.openConfirmModal(
      `Möchten Sie die Datenquelle "${source.name}" wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.`,
      'Datenquelle löschen'
    );

    if (!confirmed) return;

    try {
      await api.deleteSource(sourceId);
      await _loadSources();
      ui.toast('Datenquelle gelöscht.');
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  async function _runSource(sourceId) {
    const source = _sources.find(s => s.id === sourceId);
    if (!source) return;

    try {
      await api.runSourceImport(sourceId);
      ui.toast(`Import von "${source.name}" wurde gestartet.`);
      // Reload to show updated last_run_at
      setTimeout(() => _loadSources(), 2000);
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  // -- Config Fields Rendering --------------------------------------------
  function _renderConfigFields(adapterType, configValues = {}) {
    const container = ui.el('source-config-fields');
    container.innerHTML = '';
    
    if (!adapterType) {
      return;
    }
    
    const adapter = _adapterTypes?.find(a => a.type === adapterType);
    if (!adapter || !adapter.config_schema) {
      return;
    }
    
    adapter.config_schema.forEach(field => {
      const fieldDiv = document.createElement('div');
      fieldDiv.className = 'md-field';
      
      const inputType = field.type === 'password' ? 'password' : 
                        field.type === 'url' ? 'url' : 'text';
      
      const value = configValues[field.name] || '';
      
      if (field.type === 'textarea') {
        fieldDiv.innerHTML = `
          <textarea class="md-field__input" name="config-${field.name}" 
                    placeholder=" "${field.required ? ' required' : ''}>${ui.esc(value)}</textarea>
          <label class="md-field__label" for="config-${field.name}">${ui.esc(field.label)}</label>
          ${field.help_text ? `<div class="md-field__helper">${ui.esc(field.help_text)}</div>` : ''}
        `;
      } else {
        fieldDiv.innerHTML = `
          <input class="md-field__input" type="${inputType}" name="config-${field.name}" 
                 value="${ui.esc(value)}" placeholder=" "${field.required ? ' required' : ''} />
          <label class="md-field__label" for="config-${field.name}">${ui.esc(field.label)}</label>
          ${field.help_text ? `<div class="md-field__helper">${ui.esc(field.help_text)}</div>` : ''}
        `;
      }
      
      container.appendChild(fieldDiv);
    });
  }

  // -- Event Handlers -----------------------------------------------------
  async function init() {
    console.log('Sources module initializing...');
    
    // Load initial data
    await _loadAdapterTypes();
    
    // Register form-specific event listeners
    // Modal handlers (submit is handled per-modal-open, not here)
    ui.el('source-modal-cancel-btn')?.addEventListener('click', _closeSourceModal);
    ui.el('source-modal')?.querySelector('.modal__backdrop')
      ?.addEventListener('click', _closeSourceModal);

    // Adapter type change handler
    ui.el('source-type')?.addEventListener('change', (e) => {
      const selectedType = e.target.value;
      _renderConfigFields(selectedType, {});
    });

    // Mapping entity type change handler
    ui.el('mapping-entity-type-select')?.addEventListener('change', (e) => {
      console.log('Entity type changed to:', e.target.value);
      _saveCurrentMappings(); // Save current mappings before switching
      _renderMappingsForEntityType(e.target.value);
    });

    // Add mapping button handler
    ui.el('add-mapping-btn')?.addEventListener('click', _addMappingRow);

    // Remove mapping button handler (delegated)
    document.addEventListener('click', (e) => {
      if (e.target.matches('[data-action="remove-mapping"]') || e.target.closest('[data-action="remove-mapping"]')) {
        _removeMappingRow(e);
      }
    });
    
    // Source modal tabs
    document.querySelectorAll('#source-modal .modal__tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const targetTab = tab.dataset.tab;
        
        // Update tab buttons
        document.querySelectorAll('#source-modal .modal__tab').forEach(t => {
          const isActive = t.dataset.tab === targetTab;
          t.classList.toggle('modal__tab--active', isActive);
          t.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        
        // Update tab panels
        document.querySelectorAll('#source-modal .modal__tab-panel').forEach(panel => {
          panel.hidden = panel.dataset.tab !== targetTab;
        });
      });
    });
    
    console.log('Sources module initialization complete.');
  }

  async function load() {
    await _loadSources();
  }

  function handleContentClick(e) {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;

    const action = btn.dataset.action;
    const sourceId = parseInt(btn.dataset.id);

    switch (action) {
      case 'run':
        _runSource(sourceId);
        break;
      case 'edit':
        _openEditSource(sourceId);
        break;
      case 'delete':
        _deleteSource(sourceId);
        break;
    }
  }

  // -- Public API --------------------------------------------------------
  return { 
    init, 
    load, 
    handleContentClick,
    openCreateModal: _openCreateSource
  };
})();