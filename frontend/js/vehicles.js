/* ==========================================================================
   VEHICLES MODULE - Vehicles map view
========================================================================== */

const vehicles = (() => {
  const MAP_STATE_STORAGE_KEY = 'vehicles.map.state';
  const VEHICLE_SOURCE_ID = 'vehicles-source';
  const VEHICLE_LAYER_ID = 'vehicles-layer';
  const POLL_INTERVAL_MS = 5_000;
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

  function _toVehicleFeatureCollection() {
    const features = _vehicles
      .filter((vehicle) => Number.isFinite(Number(vehicle.longitude)) && Number.isFinite(Number(vehicle.latitude)))
      .map((vehicle) => ({
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [Number(vehicle.longitude), Number(vehicle.latitude)],
        },
        properties: {
          id: vehicle.id,
          vehicle_id: vehicle.vehicle_id,
          is_active: Boolean(vehicle.is_active),
        },
      }));

    return {
      type: 'FeatureCollection',
      features,
    };
  }

  function _updateVehiclesOnMap() {
    if (!_map) return;

    if (!_map.isStyleLoaded()) {
      _map.once('load', _updateVehiclesOnMap);
      return;
    }

    const geojsonData = _toVehicleFeatureCollection();
    const existingSource = _map.getSource(VEHICLE_SOURCE_ID);

    if (existingSource) {
      existingSource.setData(geojsonData);
      return;
    }

    _map.addSource(VEHICLE_SOURCE_ID, {
      type: 'geojson',
      data: geojsonData,
    });

    _map.addLayer({
      id: VEHICLE_LAYER_ID,
      type: 'circle',
      source: VEHICLE_SOURCE_ID,
      paint: {
        'circle-radius': 6,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
        'circle-color': [
          'case',
          ['boolean', ['get', 'is_active'], true],
          '#008c99',
          '#9e9e9e',
        ],
      },
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
      const response = await api.getVehicles(1, 500, _filterText, _filters);
      _vehicles = response.items || [];
      _updateVehiclesOnMap();
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
