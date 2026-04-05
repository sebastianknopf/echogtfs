/* ==========================================================================
   SOURCES MODULE - Data sources management
========================================================================== */

const sources = (() => {
  let _sources = [];
  let _adapterTypes = [];
  let _editingSourceId = null;

  // Source mapping management
  let _allMappings = [];
  let _currentDisplayedEntityType = 'agency';
  
  const _entityTypeNames = {
    'agency': window.i18n('source.mapping.type.agency'),
    'route': window.i18n('source.mapping.type.route'), 
    'stop': window.i18n('source.mapping.type.stop')
  };
  
  // Source enrichment management
  let _allEnrichments = [];
  let _currentDisplayedEnrichmentType = 'cause';
  
  const _enrichmentTypeNames = {
    'cause': window.i18n('source.enrichment.type.cause'),
    'effect': window.i18n('source.enrichment.type.effect'),
    'severity': window.i18n('source.enrichment.type.severity')
  };
  
  const _enrichmentValues = {
    'cause': [
      'UNKNOWN_CAUSE', 'OTHER_CAUSE', 'TECHNICAL_PROBLEM', 'STRIKE',
      'DEMONSTRATION', 'ACCIDENT', 'HOLIDAY', 'WEATHER',
      'MAINTENANCE', 'CONSTRUCTION', 'POLICE_ACTIVITY', 'MEDICAL_EMERGENCY'
    ],
    'effect': [
      'NO_SERVICE', 'REDUCED_SERVICE', 'SIGNIFICANT_DELAYS', 'DETOUR',
      'ADDITIONAL_SERVICE', 'MODIFIED_SERVICE', 'OTHER_EFFECT', 'UNKNOWN_EFFECT',
      'STOP_MOVED', 'NO_EFFECT', 'ACCESSIBILITY_ISSUE'
    ],
    'severity': [
      'UNKNOWN_SEVERITY', 'INFO', 'WARNING', 'SEVERE'
    ]
  };
  
  const _sourceFieldNames = {
    'header': window.i18n('source.enrichment.source_field.header'),
    'description': window.i18n('source.enrichment.source_field.description'),
    'header_description': window.i18n('source.enrichment.source_field.header_description')
  };
  
  // Helper function to get translated label for enrichment value
  function _getEnrichmentValueLabel(enrichmentType, value) {
    if (!value) return '';
    
    // Convert value to lowercase and replace underscores with dots for i18n key
    const valueLower = value.toLowerCase().replace(/_/g, '.');
    const i18nKey = `alert.${enrichmentType}.${valueLower}`;
    return window.i18n(i18nKey);
  }
  
  // Helper to check poweruser/admin rights
  function _isPoweruser() {
    const user = window.appState?.currentUser;
    return user && (user.is_technical_contact || user.is_superuser);
  }
  
  function _initializeMappings(mappings) {
    _allMappings = mappings || [];
  }
  
  function _saveCurrentMappings() {
    // Use currently displayed entity type
    const entityTypeToSave = _currentDisplayedEntityType;
    if (!entityTypeToSave) return;
    
    // Get existing mappings for this entity type (to preserve IDs)
    const existingMappings = _allMappings.filter(m => m.entity_type === entityTypeToSave);
    
    // Remove existing mappings for this type
    _allMappings = _allMappings.filter(m => m.entity_type !== entityTypeToSave);
    
    // Add current UI mappings for this type
    const container = ui.el('mappings-container');
    if (!container) return;
    
    const rows = container.querySelectorAll('.mapping-row');
    
    rows.forEach((row, index) => {
      const key = row.querySelector('[name="mapping-key"]')?.value?.trim();
      const value = row.querySelector('[name="mapping-value"]')?.value?.trim();
      if (key && value) {
        // Try to preserve ID if mapping already existed
        const existingMapping = existingMappings.find(m => m.key === key);
        const mapping = {
          entity_type: entityTypeToSave,
          key,
          value
        };
        // Preserve ID if it existed
        if (existingMapping && existingMapping.id) {
          mapping.id = existingMapping.id;
        }
        _allMappings.push(mapping);
      }
    });
  }
  
  function _renderMappingsForEntityType(entityType) {
    const filteredMappings = _allMappings.filter(m => m.entity_type === entityType);
    const container = ui.el('mappings-container');
    
    if (!filteredMappings.length) {
      const entityTypeName = _entityTypeNames[entityType] || window.i18n('source.mapping.type.agency');
      container.innerHTML = `<p class="panel__placeholder">${window.i18n('source.mapping.empty', { type: entityTypeName })}</p>`;
      // Update tracking
      _currentDisplayedEntityType = entityType;
      return;
    }
    
    const table = document.createElement('table');
    table.className = 'mapping-table';
    table.innerHTML = `
      <thead><tr>
        <th>${window.i18n('source.mapping.key')}</th>
        <th>${window.i18n('source.mapping.value')}</th>
        <th></th>
      </tr></thead>
      <tbody></tbody>`;
    
    const tbody = table.querySelector('tbody');
    filteredMappings.forEach(mapping => {
      const row = _createMappingRow(mapping);
      tbody.appendChild(row);
    });
    
    container.innerHTML = '';
    container.appendChild(table);
    
    // Re-initialize ripples for new buttons
    initRipples(container);
    
    // Update tracking
    _currentDisplayedEntityType = entityType;
  }
  
  function _createMappingRow(mapping = {}) {
    const tr = document.createElement('tr');
    tr.className = 'mapping-row';
    
    const currentEntityType = mapping.entity_type || ui.el('mapping-entity-type-select')?.value || 'agency';
    tr.dataset.entityType = currentEntityType;
    
    const keyValue = ui.esc(mapping.key || '');
    const valueValue = ui.esc(mapping.value || '');
    
    tr.innerHTML = `
      <td><input type="text" name="mapping-key" class="md-field__input" value="${keyValue}" placeholder="${window.i18n('source.mapping.key.placeholder')}" /></td>
      <td><input type="text" name="mapping-value" class="md-field__input" value="${valueValue}" placeholder="${window.i18n('source.mapping.value.placeholder')}" /></td>
      <td><button type="button" class="icon-btn icon-btn--danger" data-action="remove-mapping" title="${window.i18n('common.remove')}" data-ripple>
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
          <th>${window.i18n('source.mapping.key')}</th>
          <th>${window.i18n('source.mapping.value')}</th>
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
      const entityTypeName = _entityTypeNames[entityType] || window.i18n('source.mapping.type.agency');
      ui.el('mappings-container').innerHTML = 
        `<p class="panel__placeholder">${window.i18n('source.mapping.empty', { type: entityTypeName })}</p>`;
    }
  }
  
  function _getAllMappings() {
    _saveCurrentMappings();
    return [..._allMappings];
  }

  // Export mappings to CSV via API
  // Exports only the mappings for the currently selected entity type of the current source
  async function _exportMappingsToCSV() {
    if (!_editingSourceId) {
      ui.toast(window.i18n('source.error.save_first'), 'error');
      return;
    }

    const entityType = _currentDisplayedEntityType;
    const entityTypeName = _entityTypeNames[entityType] || entityType;

    try {
      // Make API call to get CSV file
      const token = localStorage.getItem('auth-token');
      const response = await fetch(`/api/sources/${_editingSourceId}/mappings/${entityType}/export`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) {
        throw new Error(window.i18n('source.mapping.import.error'));
      }

      // Get filename from Content-Disposition header or use default
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = `mappings-${_editingSourceId}-${entityType}.csv`;
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename=([^;]+)/);
        if (filenameMatch) {
          filename = filenameMatch[1].replace(/['"]/g, '');
        }
      }

      // Create blob and download
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      ui.toast(window.i18n('source.mapping.exported', { type: entityTypeName }), 'success');
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  // Import mappings from CSV via API
  // Imports only mappings for the currently selected entity type of the current source
  async function _importMappingsFromCSV() {
    if (!_editingSourceId) {
      ui.toast(window.i18n('source.error.save_first'), 'error');
      return;
    }

    const entityType = _currentDisplayedEntityType;
    const entityTypeName = _entityTypeNames[entityType] || entityType;

    // Create file input for CSV upload
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = '.csv,text/csv';
    fileInput.style.display = 'none';
    
    fileInput.addEventListener('change', async (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      
      // Validate file size on client side (10 MB max)
      const maxSize = 10 * 1024 * 1024; // 10 MB
      if (file.size > maxSize) {
        ui.toast(window.i18n('source.mapping.import.error.size'), 'error');
        return;
      }
      
      // Validate file extension
      if (!file.name.toLowerCase().endsWith('.csv')) {
        ui.toast(window.i18n('source.mapping.import.error.format'), 'error');
        return;
      }
      
      try {
        const token = localStorage.getItem('auth-token');
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`/api/sources/${_editingSourceId}/mappings/${entityType}/import`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          },
          body: formData
        });
        
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || window.i18n('source.mapping.import.error'));
        }
        
        const result = await response.json();
        
        // Reload the source to get updated mappings from server
        const source = await api.getSource(_editingSourceId);
        _initializeMappings(source.mappings || []);
        
        // Re-render current entity type
        _renderMappingsForEntityType(entityType);
        
        ui.toast(window.i18n('source.mapping.imported', { count: result.count, type: entityTypeName }), 'success');
      } catch (err) {
        ui.toast(err.message, 'error');
      }
    });
    
    document.body.appendChild(fileInput);
    fileInput.click();
    document.body.removeChild(fileInput);
  }

  // ========== ENRICHMENT MANAGEMENT ==========
  
  function _initializeEnrichments(enrichments) {
    _allEnrichments = enrichments || [];
  }
  
  function _saveCurrentEnrichments() {
    // Use currently displayed enrichment type
    const enrichmentTypeToSave = _currentDisplayedEnrichmentType;
    if (!enrichmentTypeToSave) return;
    
    // Get existing enrichments for this type (to preserve IDs)
    const existingEnrichments = _allEnrichments.filter(e => e.enrichment_type === enrichmentTypeToSave);
    
    // Remove existing enrichments for this type
    _allEnrichments = _allEnrichments.filter(e => e.enrichment_type !== enrichmentTypeToSave);
    
    // Add current UI enrichments for this type
    const container = ui.el('enrichments-container');
    if (!container) return;
    
    const rows = container.querySelectorAll('.enrichment-row');
    
    rows.forEach((row, index) => {
      const sourceField = row.querySelector('[name="enrichment-source-field"]')?.value?.trim();
      const key = row.querySelector('[name="enrichment-key"]')?.value?.trim();
      const value = row.querySelector('[name="enrichment-value"]')?.value?.trim();
      const sortOrder = parseInt(row.dataset.sortOrder || index.toString(), 10);
      
      if (sourceField && key && value) {
        // Try to preserve ID if enrichment already existed
        const existingEnrichment = existingEnrichments.find(e => 
          e.source_field === sourceField && e.key === key && e.value === value
        );
        const enrichment = {
          enrichment_type: enrichmentTypeToSave,
          source_field: sourceField,
          key,
          value,
          sort_order: sortOrder
        };
        // Preserve ID if it existed
        if (existingEnrichment && existingEnrichment.id) {
          enrichment.id = existingEnrichment.id;
        }
        _allEnrichments.push(enrichment);
      }
    });
  }
  
  function _renderEnrichmentsForType(enrichmentType) {
    const filteredEnrichments = _allEnrichments.filter(e => e.enrichment_type === enrichmentType);
    const container = ui.el('enrichments-container');
    
    if (!filteredEnrichments.length) {
      const enrichmentTypeName = _enrichmentTypeNames[enrichmentType] || window.i18n('source.enrichment.type.cause');
      container.innerHTML = `<p class="panel__placeholder">${window.i18n('source.enrichment.empty', { type: enrichmentTypeName })}</p>`;
      // Update tracking
      _currentDisplayedEnrichmentType = enrichmentType;
      return;
    }
    
    // Sort by sort_order before rendering
    filteredEnrichments.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    
    const table = document.createElement('table');
    table.className = 'mapping-table';
    table.innerHTML = `
      <thead><tr>
        <th style="min-width: 200px;">${window.i18n('source.enrichment.source_field')}</th>
        <th>${window.i18n('source.mapping.key')}</th>
        <th style="width: 240px;">${window.i18n('source.enrichment.value')}</th>
        <th style="width: 80px;"></th>
      </tr></thead>
      <tbody></tbody>`;
    
    const tbody = table.querySelector('tbody');
    filteredEnrichments.forEach(enrichment => {
      const row = _createEnrichmentRow(enrichment);
      tbody.appendChild(row);
    });
    
    container.innerHTML = '';
    container.appendChild(table);
    
    // Re-initialize ripples for new buttons
    initRipples(container);
    
    // Update tracking
    _currentDisplayedEnrichmentType = enrichmentType;
  }
  
  function _createEnrichmentRow(enrichment = {}) {
    const tr = document.createElement('tr');
    tr.className = 'enrichment-row';
    
    const currentEnrichmentType = enrichment.enrichment_type || ui.el('enrichment-type-select')?.value || 'cause';
    tr.dataset.enrichmentType = currentEnrichmentType;
    
    const sourceFieldValue = enrichment.source_field || 'header';
    const keyValue = ui.esc(enrichment.key || '');
    const valueValue = enrichment.value || '';
    const sortOrderValue = enrichment.sort_order || 0;
    
    // Store sort_order as data attribute
    tr.dataset.sortOrder = sortOrderValue;
    
    // Get valid values for the current enrichment type
    const validValues = _enrichmentValues[currentEnrichmentType] || [];
    const valueOptions = validValues.map(v => {
      const label = _getEnrichmentValueLabel(currentEnrichmentType, v);
      return `<option value="${v}" ${v === valueValue ? 'selected' : ''}>${ui.esc(label)}</option>`;
    }).join('');
    
    tr.innerHTML = `
      <td>
        <select name="enrichment-source-field" class="md-field__input" style="min-width: 200px;">
          <option value="header" ${sourceFieldValue === 'header' ? 'selected' : ''}>${window.i18n('source.enrichment.source_field.header')}</option>
          <option value="description" ${sourceFieldValue === 'description' ? 'selected' : ''}>${window.i18n('source.enrichment.source_field.description')}</option>
          <option value="header_description" ${sourceFieldValue === 'header_description' ? 'selected' : ''}>${window.i18n('source.enrichment.source_field.header_description')}</option>
        </select>
      </td>
      <td><input type="text" name="enrichment-key" class="md-field__input" value="${keyValue}" placeholder="${window.i18n('source.mapping.key.placeholder')}" /></td>
      <td>
        <select name="enrichment-value" class="md-field__input" style="width: 240px;">
          <option value="">${window.i18n('source.enrichment.value.placeholder')}</option>
          ${valueOptions}
        </select>
      </td>
      <td>
        <div style="display: flex; gap: 4px; justify-content: flex-end; align-items: center;">
          <div style="display: flex; flex-direction: column; gap: 0;">
            <button type="button" class="icon-btn icon-btn--compact" data-action="move-enrichment-up" title="${window.i18n('common.move_up')}" data-ripple>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M7 14l5-5 5 5z"/>
              </svg>
            </button>
            <button type="button" class="icon-btn icon-btn--compact" data-action="move-enrichment-down" title="${window.i18n('common.move_down')}" data-ripple>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M7 10l5 5 5-5z"/>
              </svg>
            </button>
          </div>
          <button type="button" class="icon-btn icon-btn--danger" data-action="remove-enrichment" title="${window.i18n('common.remove')}" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
          </button>
        </div>
      </td>`;
    
    return tr;
  }
  
  function _addEnrichmentRow() {
    const enrichmentType = ui.el('enrichment-type-select')?.value || 'cause';
    const container = ui.el('enrichments-container');
    
    // Create table if it doesn't exist
    let table = container.querySelector('.mapping-table');
    if (!table) {
      table = document.createElement('table');
      table.className = 'mapping-table';
      table.innerHTML = `
        <thead><tr>
          <th style="min-width: 200px;">${window.i18n('source.enrichment.source_field')}</th>
          <th>${window.i18n('source.mapping.key')}</th>
          <th style="width: 240px;">${window.i18n('source.enrichment.value')}</th>
          <th style="width: 80px;"></th>
        </tr></thead>
        <tbody></tbody>`;
      container.innerHTML = '';
      container.appendChild(table);
    }
    
    const tbody = table.querySelector('tbody');
    const row = _createEnrichmentRow({ enrichment_type: enrichmentType });
    tbody.appendChild(row);
    
    // Update sort_order for all rows
    _updateEnrichmentSortOrder();
    
    // Initialize ripples for new button
    initRipples(row);
  }
  
  function _removeEnrichmentRow(event) {
    const btn = event.target.closest('[data-action="remove-enrichment"]');
    if (!btn) return;
    
    const row = btn.closest('.enrichment-row');
    const tbody = row.parentElement;
    row.remove();
    
    // Show placeholder if no rows left
    if (tbody.children.length === 0) {
      const enrichmentType = ui.el('enrichment-type-select')?.value || 'cause';
      const enrichmentTypeName = _enrichmentTypeNames[enrichmentType] || window.i18n('source.enrichment.type.cause');
      ui.el('enrichments-container').innerHTML = 
        `<p class="panel__placeholder">${window.i18n('source.enrichment.empty', { type: enrichmentTypeName })}</p>`;
    } else {
      // Update sort_order for remaining rows
      _updateEnrichmentSortOrder();
    }
  }
  
  function _getAllEnrichments() {
    _saveCurrentEnrichments();
    return [..._allEnrichments];
  }

  function _moveEnrichmentUp(event) {
    const btn = event.target.closest('[data-action="move-enrichment-up"]');
    if (!btn) return;
    
    const row = btn.closest('.enrichment-row');
    const tbody = row.parentElement;
    const previousRow = row.previousElementSibling;
    
    if (previousRow) {
      // Swap rows
      tbody.insertBefore(row, previousRow);
      
      // Update sort_order data attributes
      _updateEnrichmentSortOrder();
      
      // Re-initialize ripples
      initRipples(tbody);
    }
  }

  function _moveEnrichmentDown(event) {
    const btn = event.target.closest('[data-action="move-enrichment-down"]');
    if (!btn) return;
    
    const row = btn.closest('.enrichment-row');
    const tbody = row.parentElement;
    const nextRow = row.nextElementSibling;
    
    if (nextRow) {
      // Swap rows
      tbody.insertBefore(nextRow, row);
      
      // Update sort_order data attributes
      _updateEnrichmentSortOrder();
      
      // Re-initialize ripples
      initRipples(tbody);
    }
  }

  function _updateEnrichmentSortOrder() {
    const container = ui.el('enrichments-container');
    if (!container) return;
    
    const rows = container.querySelectorAll('.enrichment-row');
    rows.forEach((row, index) => {
      row.dataset.sortOrder = (index * 10).toString();
    });
  }

  // Internal state management
  async function _loadSources() {
    try {
      _sources = await api.getSources();
      _renderSourcesList();
    } catch (err) {
      ui.toast(err.message, 'error');
      // Show error in UI
      const container = ui.el('sources-content');
      container.innerHTML = `<div class="panel__placeholder">${window.i18n('sources.error.load')}: ${err.message}</div>`;
    }
  }
  
  function _renderSourcesList() {
    const container = ui.el('sources-content');
    if (!_sources.length) {
      container.innerHTML = `<div class="panel__placeholder">${window.i18n('sources.empty')}</div>`;
      return;
    }
    
    const table = document.createElement('table');
    table.className = 'user-table';
    table.innerHTML = `
      <thead><tr>
        <th data-i18n="sources.table.name">${window.i18n('sources.table.name')}</th>
        <th data-i18n="sources.table.type">${window.i18n('sources.table.type')}</th>
        <th data-i18n="sources.table.cron">${window.i18n('sources.table.cron')}</th>
        <th data-i18n="sources.table.lastrun">${window.i18n('sources.table.lastrun')}</th>
        <th></th>
      </tr></thead>
      <tbody></tbody>`;
    
    const tbody = table.querySelector('tbody');
    _sources.forEach(source => {
      const tr = document.createElement('tr');
      if (!source.is_active) {
        tr.classList.add('user-table__row--inactive');
      }
      
      const cronText = source.cron || '—';
      const lastRunText = source.last_run_at 
        ? new Date(source.last_run_at).toLocaleString('de-DE', { 
            dateStyle: 'short', 
            timeStyle: 'short' 
          })
        : '—';
      
      // Inaktiv badge (like alerts) - will be shown in actions cell
      const inactiveBadge = !source.is_active ? `<span class="badge badge--system">${window.i18n('sources.badge.inactive')}</span>` : '';
      
      tr.innerHTML = `
        <td>${ui.esc(source.name)}</td>
        <td>${ui.esc(source.type)}</td>
        <td><code>${ui.esc(cronText)}</code></td>
        <td>${ui.esc(lastRunText)}</td>
        <td><div class="user-table__actions">
          ${inactiveBadge}
          <button class="icon-btn" data-action="run" data-id="${source.id}"
            title="${source.is_active ? window.i18n('sources.run.title') : window.i18n('sources.run.disabled')}" 
            aria-label="${window.i18n('sources.run.title')} ${ui.esc(source.name)}" 
            data-ripple ${!source.is_active ? 'disabled' : ''}>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
          </button>
          <button class="icon-btn" data-action="edit" data-id="${source.id}"
            title="${window.i18n('common.edit')}" aria-label="${window.i18n('common.edit')} ${ui.esc(source.name)}" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
          </button>
          <button class="icon-btn icon-btn--danger" data-action="delete" data-id="${source.id}"
            title="${window.i18n('common.delete')}" aria-label="${window.i18n('common.delete')} ${ui.esc(source.name)}" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          </button>
          <button class="icon-btn ${source.is_active ? 'icon-btn--success' : 'icon-btn--warning'}" data-action="toggle" data-id="${source.id}"
            title="${source.is_active ? window.i18n('common.deactivate') : window.i18n('common.activate')}" aria-label="${source.is_active ? window.i18n('common.deactivate') : window.i18n('common.activate')} ${ui.esc(source.name)}" data-ripple>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.59-5.41L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z"/></svg>
          </button>
        </div></td>`;
      tbody.appendChild(tr);
    });
    
    container.innerHTML = '';
    container.appendChild(table);
    if (window.initRipples) initRipples(container);
  }

  async function _loadAdapterTypes() {
    // Check permissions before loading adapter types
    if (!_isPoweruser()) {
      _adapterTypes = [];
      return;
    }
    
    try {
      const response = await api.getAdapterTypes();
      _adapterTypes = response.adapter_types || [];
    } catch (err) {
      ui.toast(err.message, 'error');
      _adapterTypes = [];
    }
  }

  // Source modal management
  function _openSourceModal({ title, name = '', type = '', config = {}, cron = '', is_active = true, invalid_reference_policy = 'not_specified', mappings = [], enrichments = [] } = {}) {
    ui.el('source-modal-title').textContent = title;
    ui.el('source-name').value = name;
    ui.el('source-name').readOnly = false;
    
    // Populate adapter type dropdown
    const typeSelect = ui.el('source-type');
    typeSelect.innerHTML = `<option value="">${window.i18n('source.type.placeholder')}</option>`;
    if (_adapterTypes && Array.isArray(_adapterTypes) && _adapterTypes.length > 0) {
      _adapterTypes.forEach(adapter => {
        const option = document.createElement('option');
        option.value = adapter.type;
        option.textContent = adapter.type;
        typeSelect.appendChild(option);
      });
    }
    typeSelect.value = type;
    
    // Ensure config is an object
    const configObj = (typeof config === 'object' && config !== null) ? config : {};
    _renderConfigFields(type, configObj);
    
    ui.el('source-cron').value = cron || '';
    ui.el('source-is-active').checked = is_active;
    ui.el('source-invalid-reference-policy').value = invalid_reference_policy || 'not_specified';
    
    // Initialize mappings
    _initializeMappings(mappings);
    const entityTypeSelect = ui.el('mapping-entity-type-select');
    if (entityTypeSelect) {
      // Default to 'agency'
      const defaultEntityType = 'agency';
      entityTypeSelect.value = defaultEntityType;
      _currentDisplayedEntityType = defaultEntityType;
      _renderMappingsForEntityType(defaultEntityType);
    }
    
    // Initialize enrichments
    _initializeEnrichments(enrichments);
    const enrichmentTypeSelect = ui.el('enrichment-type-select');
    if (enrichmentTypeSelect) {
      // Default to 'cause'
      const defaultEnrichmentType = 'cause';
      enrichmentTypeSelect.value = defaultEnrichmentType;
      _currentDisplayedEnrichmentType = defaultEnrichmentType;
      _renderEnrichmentsForType(defaultEnrichmentType);
    }
    
    // Reset to first tab (Configuration)
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
    ui.el('source-modal-submit-label').textContent = busy ? window.i18n('loading.saving') : window.i18n('common.save');
  }
  
  function _setSourceModalError(msg) {
    const e = ui.el('source-modal-error');
    e.textContent = msg ?? '';
    e.classList.toggle('is-visible', !!msg);
  }
  
  async function _openCreateSource() {
    // Load adapter types before opening modal
    if (!_adapterTypes || _adapterTypes.length === 0) {
      await _loadAdapterTypes();
    }
    
    _editingSourceId = null;
    _openSourceModal({
      title: window.i18n('source.modal.create'),
      name: '',
      type: '',
      config: {},
      cron: '',
      mappings: [],
      enrichments: []
    });
    
    // Setup submit handler for create mode
    document.getElementById('source-form').onsubmit = e => _saveSource(e);
  }

  async function _openEditSource(sourceId) {
    try {
      // Load adapter types before opening modal
      if (!_adapterTypes || _adapterTypes.length === 0) {
        await _loadAdapterTypes();
      }
      
      _editingSourceId = sourceId;
      const source = await api.getSource(sourceId);
      
      // Parse config JSON from backend
      let configObj = {};
      try {
        configObj = JSON.parse(source.config || '{}');
      } catch (err) {
        configObj = {};
      }
      
      _openSourceModal({
        title: window.i18n('source.modal.edit'),
        name: source.name,
        type: source.type,
        config: configObj,
        cron: source.cron || '',
        is_active: source.is_active !== undefined ? source.is_active : true,
        invalid_reference_policy: source.invalid_reference_policy || 'not_specified',
        mappings: source.mappings || [],
        enrichments: source.enrichments || []
      });
      
      // Setup submit handler for edit mode
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
    const isActive = ui.el('source-is-active').checked;
    const invalidReferencePolicy = ui.el('source-invalid-reference-policy').value;

    if (!name || !type) {
      _setSourceModalError(window.i18n('source.error.required'));
      return;
    }

    // Parse config from form - include input, textarea, and select elements
    let config = {};
    document.querySelectorAll('#source-config-fields input, #source-config-fields textarea, #source-config-fields select').forEach(input => {
      const fieldName = input.name.replace('config-', '');
      const value = input.value.trim();
      if (value) {
        config[fieldName] = value;
      }
    });

    // Collect mappings from internal mapping manager
    const mappings = _getAllMappings();
    
    // Collect enrichments from internal enrichment manager
    const enrichments = _getAllEnrichments();
    
    // Validate enrichments - all must have a value selected
    const invalidEnrichments = enrichments.filter(e => !e.value || e.value.trim() === '');
    if (invalidEnrichments.length > 0) {
      _setSourceModalError(window.i18n('source.error.enrichment_value_required'));
      return;
    }

    _setSourceModalBusy(true);
    try {
      // Backend expects config as JSON string
      const data = { 
        name, 
        type, 
        config: JSON.stringify(config), 
        cron: cron || null,
        is_active: isActive,
        invalid_reference_policy: invalidReferencePolicy,
        mappings,
        enrichments
      };
      if (!_editingSourceId) {
        await api.createSource(data);
      } else {
        await api.updateSource(_editingSourceId, data);
      }
      _closeSourceModal();
      await _loadSources();
      ui.toast(_editingSourceId ? window.i18n('sources.updated') : window.i18n('sources.created'));
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
      window.i18n('sources.delete.confirm', { name: source.name }),
      window.i18n('sources.delete.title')
    );

    if (!confirmed) return;

    try {
      await api.deleteSource(sourceId);
      await _loadSources();
      ui.toast(window.i18n('sources.deleted'));
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  async function _toggleSource(sourceId) {
    try {
      const result = await api.toggleSourceActive(sourceId);
      
      // Update source in local array
      const source = _sources.find(s => s.id === sourceId);
      if (source) {
        // Use result.is_active if available, otherwise toggle manually
        source.is_active = result?.is_active !== undefined ? result.is_active : !source.is_active;
      }
      
      // Update DOM without full reload
      const table = document.querySelector('#sources-content table');
      if (table) {
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(row => {
          const toggleBtn = row.querySelector(`[data-action="toggle"][data-id="${sourceId}"]`);
          if (toggleBtn) {
            const isActive = source.is_active;
            
            // Update row inactive class
            row.classList.toggle('user-table__row--inactive', !isActive);
            
            // Update/add/remove inactive badge in actions cell
            const actionsCell = row.cells[4]; // Last cell
            if (actionsCell) {
              const actionsDiv = actionsCell.querySelector('.user-table__actions');
              if (actionsDiv) {
                let inactiveBadge = actionsDiv.querySelector('.badge--system');
                
                if (!isActive && !inactiveBadge) {
                  // Add inactive badge at the beginning
                  const badge = document.createElement('span');
                  badge.className = 'badge badge--system';
                  badge.textContent = window.i18n('sources.badge.inactive');
                  actionsDiv.insertBefore(badge, actionsDiv.firstChild);
                } else if (isActive && inactiveBadge) {
                  // Remove inactive badge
                  inactiveBadge.remove();
                }
              }
            }
            
            // Update toggle button
            toggleBtn.classList.toggle('icon-btn--success', isActive);
            toggleBtn.classList.toggle('icon-btn--warning', !isActive);
            toggleBtn.title = isActive ? window.i18n('common.deactivate') : window.i18n('common.activate');
            
            // Update run button
            const runBtn = row.querySelector(`[data-action="run"][data-id="${sourceId}"]`);
            if (runBtn) {
              runBtn.disabled = !isActive;
              runBtn.title = isActive ? window.i18n('sources.run.title') : window.i18n('sources.run.disabled');
            }
          }
        });
      }
      
      ui.toast(source.is_active ? window.i18n('sources.activated') : window.i18n('sources.deactivated'), 'success');
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  async function _runSource(sourceId) {
    const source = _sources.find(s => s.id === sourceId);
    if (!source) return;

    // Check if source is active
    if (!source.is_active) {
      ui.toast(window.i18n('sources.run.error.inactive'), 'error');
      return;
    }

    try {
      await api.runSourceImport(sourceId);
      ui.toast(window.i18n('sources.run.started', { name: source.name }));
      // Reload to show updated last_run_at
      setTimeout(() => _loadSources(), 2000);
    } catch (err) {
      ui.toast(err.message, 'error');
    }
  }

  // Config fields rendering
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
      
      const value = configValues[field.name] || '';
      
      // Translate field properties
      const translatedLabel = window.i18n(field.label);
      const translatedHelpText = field.help_text ? window.i18n(field.help_text) : '';
      
      // Handle enum type as dropdown
      if (field.type === 'enum') {
        const options = field.options || [];
        const optionsHtml = options.map(opt => {
          // Generate translation key for option: adapter.{adapterType}.{fieldName}.option.{optionValue}
          // Replace special characters in option value (e.g., "/" becomes "_")
          const optionKey = opt.replace(/\//g, '_').replace(/-/g, '_');
          const translationKey = `adapter.${adapterType}.${field.name}.option.${optionKey}`;
          const translatedOption = window.i18n(translationKey);
          return `<option value="${ui.esc(opt)}" ${value === opt ? 'selected' : ''}>${ui.esc(translatedOption)}</option>`;
        }).join('');
        
        // Add has-value class if there's a selected value
        if (value) {
          fieldDiv.classList.add('md-field--has-value');
        }
        
        fieldDiv.innerHTML = `
          <select class="md-field__input" name="config-${field.name}" 
                  ${field.required ? ' required' : ''}>
            <option value="">${ui.esc(window.i18n('sources.select_option'))}</option>
            ${optionsHtml}
          </select>
          <label class="md-field__label" for="config-${field.name}">${ui.esc(translatedLabel)}</label>
          ${translatedHelpText ? `<div class="md-field__helper">${ui.esc(translatedHelpText)}</div>` : ''}
        `;
        
        // Add change listener to update label position
        const select = fieldDiv.querySelector('select');
        select.addEventListener('change', function() {
          if (this.value) {
            fieldDiv.classList.add('md-field--has-value');
          } else {
            fieldDiv.classList.remove('md-field--has-value');
          }
        });
      }
      // Handle textarea type
      else if (field.type === 'textarea') {
        fieldDiv.innerHTML = `
          <textarea class="md-field__input" name="config-${field.name}" 
                    placeholder=" " ${field.required ? ' required' : ''}>${ui.esc(value)}</textarea>
          <label class="md-field__label" for="config-${field.name}">${ui.esc(translatedLabel)}</label>
          ${translatedHelpText ? `<div class="md-field__helper">${ui.esc(translatedHelpText)}</div>` : ''}
        `;
      }
      // Handle text, url, password types
      else {
        const inputType = field.type === 'password' ? 'password' : 
                          field.type === 'url' ? 'url' : 'text';
        
        fieldDiv.innerHTML = `
          <input class="md-field__input" type="${inputType}" name="config-${field.name}" 
                 value="${ui.esc(value)}" placeholder=" " ${field.required ? ' required' : ''} />
          <label class="md-field__label" for="config-${field.name}">${ui.esc(translatedLabel)}</label>
          ${translatedHelpText ? `<div class="md-field__helper">${ui.esc(translatedHelpText)}</div>` : ''}
        `;
      }
      
      container.appendChild(fieldDiv);
    });
  }

  // Event handlers
  async function init() {
    // Load initial data
    await _loadAdapterTypes();
    
    // Register event listeners
    // Modal handlers
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
      _saveCurrentMappings(); // Save current mappings before switching
      _renderMappingsForEntityType(e.target.value);
    });

    // Add mapping button handler
    ui.el('add-mapping-btn')?.addEventListener('click', _addMappingRow);

    // Export mappings to CSV button handler
    ui.el('export-mappings-btn')?.addEventListener('click', _exportMappingsToCSV);

    // Import mappings from CSV button handler
    ui.el('import-mappings-btn')?.addEventListener('click', _importMappingsFromCSV);

    // Remove mapping button handler (delegated)
    document.addEventListener('click', (e) => {
      if (e.target.matches('[data-action="remove-mapping"]') || e.target.closest('[data-action="remove-mapping"]')) {
        _removeMappingRow(e);
      }
    });
    
    // Enrichment type change handler
    ui.el('enrichment-type-select')?.addEventListener('change', (e) => {
      _saveCurrentEnrichments(); // Save current enrichments before switching
      _renderEnrichmentsForType(e.target.value);
    });

    // Add enrichment button handler
    ui.el('add-enrichment-btn')?.addEventListener('click', _addEnrichmentRow);

    // Remove enrichment button handler (delegated)
    document.addEventListener('click', (e) => {
      if (e.target.matches('[data-action="remove-enrichment"]') || e.target.closest('[data-action="remove-enrichment"]')) {
        _removeEnrichmentRow(e);
      }
      if (e.target.matches('[data-action="move-enrichment-up"]') || e.target.closest('[data-action="move-enrichment-up"]')) {
        _moveEnrichmentUp(e);
      }
      if (e.target.matches('[data-action="move-enrichment-down"]') || e.target.closest('[data-action="move-enrichment-down"]')) {
        _moveEnrichmentDown(e);
      }
    });
    
    // Source modal tabs
    document.querySelectorAll('#source-modal .modal__tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const targetTab = tab.dataset.tab;
        
        // Save current tab data before switching
        const currentActiveTab = document.querySelector('#source-modal .modal__tab--active')?.dataset.tab;
        if (currentActiveTab === 'mapping') {
          _saveCurrentMappings();
        } else if (currentActiveTab === 'enrichment') {
          _saveCurrentEnrichments();
        }
        
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
      case 'toggle':
        _toggleSource(sourceId);
        break;
    }
  }

  // Public API
  return { 
    init, 
    load, 
    handleContentClick,
    openCreateModal: _openCreateSource
  };
})();