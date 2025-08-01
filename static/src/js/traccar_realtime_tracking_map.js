/* @odoo-module */

import { registry } from "@web/core/registry";
import { Component, onMounted, useRef } from "@odoo/owl";
import { onWillUnmount } from "@odoo/owl";

export class TraccarRealtimeTrackingMap extends Component {
    setup() {
        this.mapRef = useRef("map");
        this.map = null;
        this.marker = null;
        this.polyline = null;
        this.path = [];
        this.positionInterval = null;

        onMounted(this.initTracking.bind(this));

        onWillUnmount(() => {
            if (this.positionInterval) {
                clearInterval(this.positionInterval);
            }
        });
    }

    async initTracking() {
        const { device_id } = this.props.action.params;
        const deviceIdNum = Number(device_id);
        const auth = btoa("pprologic138@gmail.com:oumaima123@");
        const url = "https://demo4.traccar.org/api/positions";

        if (!device_id) {
            alert("ID de l'appareil manquant.");
            return;
        }

        // Initialize the map
        this.map = L.map(this.mapRef.el).setView([0, 0], 2);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
        }).addTo(this.map);

        const updatePosition = async () => {
            try {
                const response = await fetch(url, {
                    headers: {
                        "Authorization": `Basic ${auth}`,
                        "Accept": "application/json"
                    }
                });

                if (!response.ok) {
                    throw new Error(`Erreur API: ${response.statusText}`);
                }

                const data = await response.json();
                const devicePosition = data.find(d =>
                    d.deviceId === deviceIdNum ||
                    String(d.deviceId) === String(device_id)
                );

                if (!devicePosition) {
                    console.warn(`Pas de position pour l'appareil ${device_id}`);
                    return;
                }

                const latlng = [devicePosition.latitude, devicePosition.longitude];

                // Always zoom to the new position
                this.map.setView(latlng, 20, {
                    animate: true,
                    pan: { duration: 1 }
                });

                // Add current point to trajectory
                this.path.push(latlng);

                // Update or create polyline
                if (!this.polyline) {
                    this.polyline = L.polyline(this.path, { color: "blue" }).addTo(this.map);
                } else {
                    this.polyline.setLatLngs(this.path);
                }

                // Update or create marker
                if (!this.marker) {
                const customCursor = L.divIcon({
                    className: 'live-tracking-icon',
                    html: '<div class="pulse-icon"></div>',
                    iconSize: [20, 20],
                    iconAnchor: [10, 10]  // center the icon
                });

                this.marker = L.marker(latlng, { icon: customCursor }).addTo(this.map);         
                this.marker.bindPopup(`Appareil ID: ${device_id}<br>Position suivie`).openPopup();
                } else {
                    this.marker.setLatLng(latlng);
                    this.marker.getPopup().setContent(`Appareil ID: ${device_id}<br>Position mise à jour`);
                }

            } catch (error) {
                console.error("Erreur de mise à jour de la position :", error);
            }
        };

        // First fetch
        await updatePosition();

        // Refresh every 5 seconds
        this.positionInterval = setInterval(updatePosition, 5000);
    }
}

TraccarRealtimeTrackingMap.template = "TraccarRealtimeTrackingMap";
registry.category("actions").add("traccar_realtime_tracking_map", TraccarRealtimeTrackingMap);
