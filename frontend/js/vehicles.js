/* ==========================================================================
   VEHICLES MODULE - Vehicles map view
========================================================================== */

const vehicles = (() => {
  const MAP_STATE_STORAGE_KEY = 'vehicles.map.state';
  const DEFAULT_VIEW = {
    center: [8.5417, 47.3769],
    zoom: 11,
  };

  let _map = null;
  let _eventsBound = false;

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
  }

  function init() {
    // Map is initialized lazily when the vehicles panel is opened.
    _bindEvents();
  }

  function load() {
    _bindEvents();
    _initializeMap();

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
