/**
 * A small, quiet map with one pin: where we think "here" is.
 *
 * Same approach as the lawn tool — inline Leaflet, no API key, no account — but read-only and
 * calm: no controls, no interaction, just enough context to confirm "yes, that's my area" or
 * "no, that pin is nowhere near me", which is exactly the judgement an approximate answer needs.
 * On the web a WebView does not exist, so the same page renders in an iframe.
 */

import { Platform, StyleSheet, View } from 'react-native';
import { WebView } from 'react-native-webview';

import { colors, radius } from '@/theme';

const LEAFLET_VERSION = '1.9.4';

function page(lat: number, lng: number, zoom: number): string {
  return `<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/leaflet@${LEAFLET_VERSION}/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@${LEAFLET_VERSION}/dist/leaflet.js"></script>
<style>
  html, body, #map { height: 100%; margin: 0; background: #E7EEE2; }
  .pin { width: 26px; height: 26px; border-radius: 50% 50% 50% 0; transform: rotate(-45deg);
         background: #C75B39; border: 2.5px solid #FFFFFF; box-shadow: 0 2px 6px rgba(0,0,0,0.35); }
</style>
</head>
<body>
<div id="map"></div>
<script>
  var map = L.map('map', {
    zoomControl: false, attributionControl: true, dragging: false, scrollWheelZoom: false,
    doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false, tap: false
  }).setView([${lat}, ${lng}], ${zoom});
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(map);
  L.marker([${lat}, ${lng}], { icon: L.divIcon({ className: '', html: '<div class="pin"></div>',
    iconSize: [26, 26], iconAnchor: [13, 26] }) }).addTo(map);
</script>
</body>
</html>`;
}

export function MiniMap({
  lat,
  lng,
  zoom = 12,
  height = 150,
}: {
  lat: number;
  lng: number;
  zoom?: number;
  height?: number;
}) {
  const html = page(lat, lng, zoom);

  return (
    <View style={[styles.frame, { height }]}>
      {Platform.OS === 'web' ? (
        <iframe
          srcDoc={html}
          style={{ border: 'none', width: '100%', height: '100%', pointerEvents: 'none' }}
          title="Map"
          sandbox="allow-scripts"
        />
      ) : (
        <WebView
          source={{ html }}
          style={styles.web}
          scrollEnabled={false}
          // Read-only context; the page carries no state worth keeping across reloads.
          setSupportMultipleWindows={false}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    borderRadius: radius.md,
    overflow: 'hidden',
    backgroundColor: colors.surfaceMuted,
    borderWidth: 1,
    borderColor: colors.border,
  },
  web: { flex: 1 },
});
