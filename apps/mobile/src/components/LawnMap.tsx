/**
 * The satellite drawing surface, as a self-contained web page in a WebView.
 *
 * The obvious choice was react-native-maps, and it was the wrong one: on Android it needs a Google
 * Maps API key, which is an account, a billing profile, and a secret to manage — real friction for
 * a free student project, and a thing that breaks for anyone who clones the repo. Leaflet over Esri
 * World Imagery needs no key at all and renders identically on iOS, Android, and the web, so there
 * is one implementation instead of three.
 *
 * The page is inlined rather than fetched, so drawing a lawn works with no network beyond the map
 * tiles themselves, and there is no third-party script in the trust path.
 */

import { useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import { WebView } from 'react-native-webview';

export interface LatLng {
  latitude: number;
  longitude: number;
}

const LEAFLET_VERSION = '1.9.4';

function page(lat: number, lng: number): string {
  return `<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/leaflet@${LEAFLET_VERSION}/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@${LEAFLET_VERSION}/dist/leaflet.js"></script>
<style>
  html, body, #map { height: 100%; margin: 0; background: #1c1b18; }
  .leaflet-container { background: #1c1b18; }
</style>
</head>
<body>
<div id="map"></div>
<script>
  var map = L.map('map', { zoomControl: true, attributionControl: true })
             .setView([${lat}, ${lng}], 19);

  // Esri World Imagery: free, no key, attribution required and given.
  L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 21, attribution: 'Imagery: Esri, Maxar, Earthstar Geographics' }
  ).addTo(map);

  var points = [];
  var markers = [];
  var polygon = null;

  function send() {
    // The native side owns the state that matters; this page just reports what was tapped.
    window.ReactNativeWebView.postMessage(JSON.stringify({ points: points }));
  }

  function redraw() {
    markers.forEach(function (m) { map.removeLayer(m); });
    markers = points.map(function (p) {
      return L.circleMarker(p, {
        radius: 7, color: '#ffffff', weight: 2, fillColor: '#1F5F73', fillOpacity: 1
      }).addTo(map);
    });

    if (polygon) { map.removeLayer(polygon); polygon = null; }
    if (points.length >= 3) {
      polygon = L.polygon(points, {
        color: '#1F5F73', weight: 3, fillColor: '#1F5F73', fillOpacity: 0.35
      }).addTo(map);
    }
    send();
  }

  map.on('click', function (e) {
    points.push([e.latlng.lat, e.latlng.lng]);
    redraw();
  });

  // Commands from the native side.
  function handle(raw) {
    var msg = JSON.parse(raw);
    if (msg.action === 'undo') { points.pop(); redraw(); }
    if (msg.action === 'clear') { points = []; redraw(); }
  }
  document.addEventListener('message', function (e) { handle(e.data); });
  window.addEventListener('message', function (e) { handle(e.data); });
</script>
</body>
</html>`;
}

export interface LawnMapHandle {
  undo: () => void;
  clear: () => void;
}

export function LawnMap({
  lat,
  lng,
  onChange,
  controlsRef,
}: {
  lat: number;
  lng: number;
  onChange: (points: LatLng[]) => void;
  controlsRef?: React.MutableRefObject<LawnMapHandle | null>;
}) {
  const webRef = useRef<WebView>(null);

  if (controlsRef) {
    controlsRef.current = {
      undo: () => webRef.current?.postMessage(JSON.stringify({ action: 'undo' })),
      clear: () => webRef.current?.postMessage(JSON.stringify({ action: 'clear' })),
    };
  }

  return (
    <View style={styles.wrap}>
      <WebView
        ref={webRef}
        source={{ html: page(lat, lng) }}
        style={styles.web}
        originWhitelist={['*']}
        onMessage={(event) => {
          try {
            const data = JSON.parse(event.nativeEvent.data);
            onChange(
              (data.points ?? []).map((p: [number, number]) => ({
                latitude: p[0],
                longitude: p[1],
              })),
            );
          } catch {
            // A malformed message means a tap we cannot use; the next one will be fine.
          }
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1 },
  web: { flex: 1, backgroundColor: '#1c1b18' },
});
