/* Australia Environmental Monitoring — WebGIS logic */

const BASEMAPS = {
  imagery: L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { attribution: '© Esri, Maxar, Earthstar Geographics', maxZoom: 19 }
  ),
  streets: L.tileLayer(
    'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    { attribution: '© OpenStreetMap contributors', maxZoom: 19 }
  ),
  terrain: L.tileLayer(
    'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    { attribution: '© OpenTopoMap (CC-BY-SA)', maxZoom: 17 }
  ),
};

const map = L.map('map', {
  center: [-25.5, 134.0],
  zoom: 4,
  zoomControl: true,
  preferCanvas: true,
});
BASEMAPS.imagery.addTo(map);
L.control.scale({ imperial: false, position: 'bottomright' }).addTo(map);

const state = {
  layers: {},
  metadata: [],
  tileUrls: {},
};

Promise.all([
  fetch('data/layer_metadata.json').then(r => r.json()),
  fetch('data/tile_urls.json').then(r => r.json()),
])
.then(([meta, tiles]) => {
  state.metadata = meta.layers;
  state.tileUrls = tiles.tiles || tiles;
  buildLayerPanel();
  buildLayers();
  updateTimestamp(tiles.generated_at);
})
.catch(err => {
  document.getElementById('layerList').innerHTML =
    `<span style="color:#f87171">❌ Could not load data.<br>
     Make sure <code>data/layer_metadata.json</code> and
     <code>data/tile_urls.json</code> exist and you're serving via HTTP.</span>`;
  console.error(err);
});

function buildLayerPanel() {
  const list = document.getElementById('layerList');
  list.innerHTML = '';
  state.metadata.forEach(meta => {
    const row = document.createElement('div');
    row.className = 'layer-item';
    row.innerHTML = `
      <input type="checkbox" id="chk_${meta.key}" ${meta.defaultOn ? 'checked' : ''}>
      <div>
        <div class="name">${meta.icon} ${meta.name}</div>
        <div class="desc">${meta.description}</div>
      </div>
      <input type="range" id="op_${meta.key}" min="0" max="100"
             value="${Math.round((meta.defaultOpacity ?? 0.8) * 100)}">
    `;
    list.appendChild(row);

    row.querySelector(`#chk_${meta.key}`).addEventListener('change', e => {
      const layer = state.layers[meta.key];
      if (!layer) return;
      if (e.target.checked) { layer.addTo(map); showLegend(meta); }
      else { map.removeLayer(layer); hideLegendIfActive(meta.key); }
    });

    row.querySelector(`#op_${meta.key}`).addEventListener('input', e => {
      const layer = state.layers[meta.key];
      if (layer) layer.setOpacity(e.target.value / 100);
    });
  });

  document.querySelectorAll('input[name="basemap"]').forEach(r => {
    r.addEventListener('change', e => {
      Object.values(BASEMAPS).forEach(b => map.removeLayer(b));
      BASEMAPS[e.target.value].addTo(map);
    });
  });
}

function buildLayers() {
  state.metadata.forEach(meta => {
    const url = state.tileUrls[meta.key];
    if (!url) { console.warn('No tile URL for', meta.key); return; }
    const layer = L.tileLayer(url, {
      attribution: 'GEE · Australia Monitoring',
      maxZoom: 18,
      opacity: meta.defaultOpacity ?? 0.8,
      pane: 'overlayPane',
      crossOrigin: true,
    });
    state.layers[meta.key] = layer;
    if (meta.defaultOn) layer.addTo(map);
  });
  const topVisible = state.metadata.filter(m => m.defaultOn).pop();
  if (topVisible) showLegend(topVisible);
}

let activeLegendKey = null;
function showLegend(meta) {
  activeLegendKey = meta.key;
  document.getElementById('legendTitle').textContent = `${meta.icon} ${meta.name}`;
  const items = document.getElementById('legendItems');
  items.innerHTML = '';
  (meta.legend || []).forEach(item => {
    const row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = `<span class="sw" style="background:${item.color}"></span><span>${item.label}</span>`;
    items.appendChild(row);
  });
  document.getElementById('legendBox').hidden = false;
}

function hideLegendIfActive(key) {
  if (activeLegendKey === key) {
    document.getElementById('legendBox').hidden = true;
    activeLegendKey = null;
  }
}

document.getElementById('fitBtn').addEventListener('click', () => {
  map.fitBounds([[-44.5, 112.0], [-8.0, 160.0]]);
});

document.getElementById('togglePanel').addEventListener('click', () => {
  document.getElementById('layerPanel').classList.toggle('hidden');
});

map.on('mousemove', e => {
  document.getElementById('coords').textContent =
    `Lat ${e.latlng.lat.toFixed(4)}   Lon ${e.latlng.lng.toFixed(4)}   Zoom ${map.getZoom()}`;
});

function updateTimestamp(iso) {
  if (!iso) return;
  const d = new Date(iso);
  document.getElementById('timestamp').textContent = `Tiles generated: ${d.toLocaleString()}`;
}