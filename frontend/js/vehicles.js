/* ==========================================================================
   VEHICLES MODULE - Vehicles map view
========================================================================== */

const vehicles = (() => {
  const MAP_STATE_STORAGE_KEY = 'vehicles.map.state';
  const POLL_INTERVAL_MS = 5_000;
  const VEHICLE_ICON_PATH = 'M240-120q-17 0-28.5-11.5T200-160v-82q-18-20-29-44.5T160-340v-380q0-83 77-121.5T480-880q172 0 246 37t74 123v380q0 29-11 53.5T760-242v82q0 17-11.5 28.5T720-120h-40q-17 0-28.5-11.5T640-160v-40H320v40q0 17-11.5 28.5T280-120h-40Zm242-640h224-448 224Zm158 280H240h480-80Zm-400-80h480v-120H240v120Zm142.5 222.5Q400-355 400-380t-17.5-42.5Q365-440 340-440t-42.5 17.5Q280-405 280-380t17.5 42.5Q315-320 340-320t42.5-17.5Zm280 0Q680-355 680-380t-17.5-42.5Q645-440 620-440t-42.5 17.5Q560-405 560-380t17.5 42.5Q595-320 620-320t42.5-17.5ZM258-760h448q-15-17-64.5-28.5T482-800q-107 0-156.5 12.5T258-760Zm62 480h320q33 0 56.5-23.5T720-360v-120H240v120q0 33 23.5 56.5T320-280Z';
  const WARNING_ICON_PATH = 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z';
  const CLOCK_ICON_PATH = 'M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.2 3.2.8-1.3-4.5-2.7V7z';
  const WHEELCHAIR_ICON_PATH = 'M12 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm7 6h-4.31l-1.38-1.38A2 2 0 0 0 11.9 6H9v7h2v9h2v-6h2l1.1 3.3c.3.9 1.2 1.7 2.2 1.7H20v-2h-1.7l-1.5-4.5c-.2-.6-.7-1.1-1.3-1.4L14 12v-2h2.2l1.8 1.8V16h2V8z';
  const POWER_ICON_PATH = 'M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.59-5.41L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z';
  const DEFAULT_VIEW = {
    center: [8.5417, 47.3769],
    zoom: 11,
  };

  let _map = null;
  let _eventsBound = false;
  let _pollTimer = null;
  let _filterText = '';
  let _filterTimeout = null;
  let _filters = {
    active: true,
    inactive: true,
  };
  let _vehicles = [];
  let _markers = [];
  let _selectedVehicleId = null;
  let _sheetElement = null;

  function _getVehicleDisplayTitle(vehicle) {
    return vehicle.vehicle_label || vehicle.vehicle_license_plate || vehicle.vehicle_id || window.i18n('vehicles.title');
  }

  function _getVehicleSearchValue(vehicle) {
    if (vehicle?.vehicle_label) {
      return String(vehicle.vehicle_label).toLowerCase();
    }
    if (vehicle?.vehicle_license_plate) {
      return String(vehicle.vehicle_license_plate).toLowerCase();
    }
    if (vehicle?.vehicle_id) {
      return String(vehicle.vehicle_id).toLowerCase();
    }
    return String(vehicle?.id || '').toLowerCase();
  }

  function _matchesVehicleSearch(vehicle) {
    if (!_filterText) {
      return true;
    }

    return _getVehicleSearchValue(vehicle).includes(_filterText);
  }

  function _formatRelativeTimestamp(timestamp) {
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
      return '-';
    }

    const secondsDiff = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (secondsDiff < 60) {
      return secondsDiff === 1
        ? window.i18n('vehicles.time.second_ago', { count: secondsDiff })
        : window.i18n('vehicles.time.seconds_ago', { count: secondsDiff });
    }

    const minutesDiff = Math.floor(secondsDiff / 60);
    return minutesDiff === 1
      ? window.i18n('vehicles.time.minute_ago', { count: minutesDiff })
      : window.i18n('vehicles.time.minutes_ago', { count: minutesDiff });
  }

  function _getRouteDisplayName(vehicle) {
    return vehicle?.trip?.route_name || vehicle?.trip?.route_id || '-';
  }

  function _getTripDisplayId(vehicle) {
    return vehicle?.trip?.trip_id || vehicle?.trip_id || '-';
  }

  function _getLineTripDisplay(vehicle) {
    return `${_getRouteDisplayName(vehicle)} / ${_getTripDisplayId(vehicle)}`;
  }

  function _getVehicleIdentityDisplay(vehicle) {
    const label = vehicle?.vehicle_label == null ? '' : String(vehicle.vehicle_label).trim();
    if (label) {
      return label;
    }

    const licensePlate = vehicle?.vehicle_license_plate == null ? '' : String(vehicle.vehicle_license_plate).trim();
    if (licensePlate) {
      return licensePlate;
    }

    const vehicleId = vehicle?.vehicle_id == null ? '' : String(vehicle.vehicle_id).trim();
    return vehicleId || '-';
  }

  function _getWheelchairStatusText(vehicle) {
    const rawValue = vehicle?.wheelchair_accessible ?? vehicle?.vehicle_wheelchair_accessible;
    const value = String(rawValue ?? '').trim().toUpperCase();
    if (value === '2' || value === 'WHEELCHAIR_ACCESSIBLE') {
      return window.i18n('vehicles.wheelchair.accessible');
    }
    if (value === '3' || value === 'WHEELCHAIR_INACCESSIBLE') {
      return window.i18n('vehicles.wheelchair.inaccessible');
    }
    return window.i18n('vehicles.wheelchair.unknown');
  }

  function _findVehicleById(vehicleId) {
    return _vehicles.find((vehicle) => vehicle.id === vehicleId) || null;
  }

  function _ensureBottomSheet() {
    if (_sheetElement) return _sheetElement;

    const mapContainer = document.getElementById('vehicles-map');
    if (!mapContainer) return null;

    const sheet = document.createElement('div');
    sheet.className = 'vehicle-map-sheet';
    sheet.hidden = true;
    sheet.innerHTML = `
      <div class="vehicle-map-sheet__header">
        <h3 class="vehicle-map-sheet__title" id="vehicle-map-sheet-title"></h3>
        <div class="vehicle-map-sheet__header-actions">
          <button type="button" class="md-icon-btn vehicle-map-sheet__toggle" id="vehicle-map-sheet-toggle" title="${window.i18n('common.deactivate')}" aria-label="${window.i18n('common.deactivate')}">
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${POWER_ICON_PATH}"/></svg>
          </button>
          <button type="button" class="md-icon-btn vehicle-map-sheet__close" id="vehicle-map-sheet-close" title="${window.i18n('common.close')}" aria-label="${window.i18n('common.close')}">
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>
      </div>
      <div class="vehicle-map-sheet__details">
        <div class="vehicle-map-sheet__detail-row">
          <svg class="vehicle-map-sheet__detail-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${CLOCK_ICON_PATH}"/></svg>
          <span id="vehicle-map-sheet-updated"></span>
        </div>
        <div class="vehicle-map-sheet__detail-row">
          <svg class="vehicle-map-sheet__detail-icon" viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true"><path d="${VEHICLE_ICON_PATH}"/></svg>
          <span id="vehicle-map-sheet-vehicle"></span>
        </div>
        <div class="vehicle-map-sheet__detail-row">
          <svg class="vehicle-map-sheet__detail-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="${WHEELCHAIR_ICON_PATH}"/></svg>
          <span id="vehicle-map-sheet-wheelchair"></span>
        </div>
      </div>
    `;

    mapContainer.appendChild(sheet);

    const closeBtn = sheet.querySelector('#vehicle-map-sheet-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        _selectedVehicleId = null;
        _renderBottomSheet();
      });
    }

    const toggleBtn = sheet.querySelector('#vehicle-map-sheet-toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', async () => {
        const selectedVehicle = _findVehicleById(_selectedVehicleId);
        if (!selectedVehicle) return;

        toggleBtn.disabled = true;
        try {
          await api.toggleVehicleActive(selectedVehicle.id);
          await _loadVehicles();
        } catch (err) {
          ui.toast(err.message, 'error');
        } finally {
          toggleBtn.disabled = false;
        }
      });
    }

    _sheetElement = sheet;
    return _sheetElement;
  }

  function _renderBottomSheet() {
    const sheet = _ensureBottomSheet();
    if (!sheet) return;

    const selectedVehicle = _findVehicleById(_selectedVehicleId);
    if (!selectedVehicle) {
      sheet.hidden = true;
      return;
    }

    const titleEl = sheet.querySelector('#vehicle-map-sheet-title');
    const vehicleEl = sheet.querySelector('#vehicle-map-sheet-vehicle');
    const updatedEl = sheet.querySelector('#vehicle-map-sheet-updated');
    const wheelchairEl = sheet.querySelector('#vehicle-map-sheet-wheelchair');
    const toggleBtn = sheet.querySelector('#vehicle-map-sheet-toggle');

    if (titleEl) {
      titleEl.textContent = _getLineTripDisplay(selectedVehicle);
    }

    if (vehicleEl) {
      vehicleEl.textContent = window.i18n('vehicles.sheet.vehicle', {
        value: _getVehicleIdentityDisplay(selectedVehicle),
      });
    }

    if (updatedEl) {
      updatedEl.textContent = window.i18n('vehicles.sheet.updated', {
        value: _formatRelativeTimestamp(selectedVehicle.timestamp),
      });
    }

    if (wheelchairEl) {
      wheelchairEl.textContent = _getWheelchairStatusText(selectedVehicle);
    }

    if (toggleBtn) {
      const isActive = Boolean(selectedVehicle.is_active);
      toggleBtn.classList.toggle('is-active', isActive);
      const title = isActive ? window.i18n('common.deactivate') : window.i18n('common.activate');
      toggleBtn.title = title;
      toggleBtn.setAttribute('aria-label', title);
    }

    sheet.hidden = false;
  }

  function _createVehicleMarkerElement(vehicle) {
    const marker = document.createElement('div');
    marker.className = 'vehicle-map-marker' + (vehicle.is_active ? '' : ' vehicle-map-marker--inactive');
    marker.setAttribute('role', 'button');
    marker.setAttribute('tabindex', '0');
    marker.setAttribute('aria-label', _getVehicleDisplayTitle(vehicle));
    marker.innerHTML = `
      <span class="vehicle-map-marker__dot">
        <svg viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true">
          <path d="${VEHICLE_ICON_PATH}"/>
        </svg>
      </span>
      ${vehicle.is_valid === false ? `<span class="vehicle-map-marker__warning" title="${window.i18n('trips.resolution.warning')}">
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="${WARNING_ICON_PATH}"/>
        </svg>
      </span>` : ''}
    `;

    const selectVehicle = () => {
      _selectedVehicleId = vehicle.id;
      _renderBottomSheet();
    };

    marker.addEventListener('click', selectVehicle);
    marker.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectVehicle();
      }
    });

    return marker;
  }

  function _clearMarkers() {
    _markers.forEach((marker) => marker.remove());
    _markers = [];
  }

  function _updateVehiclesOnMap() {
    if (!_map) return;

    if (!_map.isStyleLoaded()) {
      _map.once('load', _updateVehiclesOnMap);
      return;
    }

    _clearMarkers();

    _vehicles
      .filter((vehicle) => Number.isFinite(Number(vehicle.longitude)) && Number.isFinite(Number(vehicle.latitude)))
      .forEach((vehicle) => {
        const markerElement = _createVehicleMarkerElement(vehicle);
        const marker = new maplibregl.Marker({
          element: markerElement,
          anchor: 'center',
        })
          .setLngLat([Number(vehicle.longitude), Number(vehicle.latitude)])
          .addTo(_map);

        _markers.push(marker);
      });
  }

  function _isPanelActive() {
    const panel = document.querySelector('.panel[data-panel="vehicles"]');
    return Boolean(panel?.classList.contains('is-active'));
  }

  function _startPolling() {
    if (_pollTimer) return;
    _pollTimer = window.setInterval(() => {
      if (_isPanelActive()) {
        _loadVehicles();
      }
    }, POLL_INTERVAL_MS);
  }

  async function _loadVehicles() {
    try {
      const response = await api.getVehicles(1, 500, '', _filters);
      _vehicles = (response.items || []).filter(_matchesVehicleSearch);
      _updateVehiclesOnMap();
      _renderBottomSheet();
    } catch {
    }
  }

  function _handleFilterChange() {
    const activeCheckbox = document.getElementById('filter-vehicles-active');
    const inactiveCheckbox = document.getElementById('filter-vehicles-inactive');

    _filters.active = activeCheckbox ? activeCheckbox.checked : true;
    _filters.inactive = inactiveCheckbox ? inactiveCheckbox.checked : true;
    _loadVehicles();
  }

  function _handleSearchChange(e) {
    _filterText = e.target.value.trim().toLowerCase();

    if (_filterTimeout) {
      clearTimeout(_filterTimeout);
    }

    _filterTimeout = setTimeout(() => {
      _loadVehicles();
    }, 300);
  }

  function _handleOutsideClick(e) {
    const popout = document.getElementById('filter-vehicles-popout');
    const container = e.target.closest('.filter-dropdown-container');

    if (!container && popout && !popout.hidden) {
      popout.hidden = true;
      document.removeEventListener('click', _handleOutsideClick);
    }
  }

  function _toggleFilterPopout() {
    const popout = document.getElementById('filter-vehicles-popout');
    if (!popout) return;

    if (popout.hidden) {
      popout.hidden = false;
      setTimeout(() => {
        document.addEventListener('click', _handleOutsideClick);
      }, 0);
    } else {
      popout.hidden = true;
      document.removeEventListener('click', _handleOutsideClick);
    }
  }

  function _bindEvents() {
    if (_eventsBound) return;

    const filterBtn = document.getElementById('filter-vehicles-btn');
    if (filterBtn) {
      filterBtn.addEventListener('click', _toggleFilterPopout);
    }

    const filterInput = document.getElementById('vehicle-filter');
    if (filterInput) {
      filterInput.addEventListener('input', _handleSearchChange);
    }

    const activeCheckbox = document.getElementById('filter-vehicles-active');
    const inactiveCheckbox = document.getElementById('filter-vehicles-inactive');
    if (activeCheckbox) {
      activeCheckbox.addEventListener('change', _handleFilterChange);
    }
    if (inactiveCheckbox) {
      inactiveCheckbox.addEventListener('change', _handleFilterChange);
    }

    _eventsBound = true;
  }

  function _loadMapState() {
    try {
      const rawState = localStorage.getItem(MAP_STATE_STORAGE_KEY);
      if (!rawState) {
        return DEFAULT_VIEW;
      }

      const parsedState = JSON.parse(rawState);
      const lng = Number(parsedState?.center?.lng);
      const lat = Number(parsedState?.center?.lat);
      const zoom = Number(parsedState?.zoom);

      if (!Number.isFinite(lng) || !Number.isFinite(lat) || !Number.isFinite(zoom)) {
        return DEFAULT_VIEW;
      }

      return {
        center: [lng, lat],
        zoom,
      };
    } catch {
      return DEFAULT_VIEW;
    }
  }

  function _saveMapState() {
    if (!_map) return;

    const center = _map.getCenter();
    const zoom = _map.getZoom();
    const state = {
      center: {
        lng: Number(center.lng.toFixed(6)),
        lat: Number(center.lat.toFixed(6)),
      },
      zoom: Number(zoom.toFixed(3)),
    };

    localStorage.setItem(MAP_STATE_STORAGE_KEY, JSON.stringify(state));
  }

  function _initializeMap() {
    if (_map) return;

    if (typeof maplibregl === 'undefined') {
      return;
    }

    const mapContainer = document.getElementById('vehicles-map');
    if (!mapContainer) {
      return;
    }

    const mapState = _loadMapState();

    _map = new maplibregl.Map({
      container: mapContainer,
      style: 'https://tiles.openfreemap.org/styles/liberty',
      center: mapState.center,
      zoom: mapState.zoom,
      attributionControl: true,
    });

    _map.addControl(new maplibregl.NavigationControl(), 'top-right');
    _map.on('moveend', _saveMapState);
    _map.on('zoomend', _saveMapState);
    _map.on('load', _updateVehiclesOnMap);

    _ensureBottomSheet();
  }

  function init() {
    // Map is initialized lazily when the vehicles panel is opened.
    _bindEvents();
    _startPolling();
  }

  function load() {
    _bindEvents();
    _initializeMap();
    _loadVehicles();

    if (_map) {
      // Ensure the map adapts when panel visibility changes.
      window.requestAnimationFrame(() => {
        _map.resize();
      });
    }
  }

  function handleContentClick() {
    // Reserved for future interactions.
  }

  return {
    init,
    load,
    handleContentClick,
  };
})();
