/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useRef } from "@odoo/owl";

export class TraccarHistoryMap extends Component {
    setup() {
        this.mapRef = useRef("map");
        onMounted(this.initMap.bind(this));
    }

    async initMap() {
        const { device_id, date_from, date_to } = this.props.action?.params || {};
        console.log("Received props:", this.props.action?.params);

        const auth = btoa("pprologic138@gmail.com:oumaima123@");

        const from = new Date(date_from).toISOString();
        const to = new Date(date_to).toISOString();

        const url = `https://demo4.traccar.org/api/reports/route?deviceId=${device_id}&from=${from}&to=${to}`;
        console.log("Fetching Traccar data from:", url);

        const response = await fetch(url, {
            headers: {
                "Authorization": `Basic ${auth}`,
                "Accept": "application/json"
            }
        });

        if (!response.ok) {
            console.error("Traccar API error:", response.status, response.statusText);
            alert(`Erreur API Traccar: ${response.statusText}`);
            return;
        }

        let data;
        try {
            data = await response.json();
        } catch (err) {
            console.error("Erreur de parsing JSON:", err);
            alert("Réponse API non valide (pas du JSON)");
            return;
        }

        if (!data.length) {
            alert("Aucune donnée trouvée pour cette période.");
            return;
        }

        const coordinates = data.map(pos => [pos.latitude, pos.longitude]);
        const map = L.map(this.mapRef.el).setView(coordinates[0], 13);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
        }).addTo(map);

        const route = L.polyline(coordinates, { color: 'blue' }).addTo(map);
        map.fitBounds(route.getBounds());

        L.marker(coordinates[0]).addTo(map).bindPopup("Début").openPopup();
        L.marker(coordinates[coordinates.length - 1]).addTo(map).bindPopup("Fin");
    }
}

TraccarHistoryMap.template = "traccar_history_map_template";
registry.category("actions").add("traccar_history_map", TraccarHistoryMap);
