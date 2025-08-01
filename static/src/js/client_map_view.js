/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

class ClientMapView extends Component {
    setup() {
        this.state = useState({ clients: [] });
        this.mapRef = useRef("map");
        this.dialog = useService("dialog");
        this.markers = [];

        onMounted(async () => {
            this.initMap();                              // 1. create map
            await this.loadClients();                    // 2. first load
            setInterval(() => this.loadClients(), 10000); // 3. reload every 10s
        });
    }

    initMap = () => {
        this.map = L.map(this.mapRef.el).setView([36.85, 10.17], 10);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
        }).addTo(this.map);
    };

    loadClients = async () => {
        const clients = await rpc("/get_clients_with_location", {});
        this.state.clients = clients;

        // remove old markers
        if (this.markers && this.map) {
            this.markers.forEach(marker => this.map.removeLayer(marker));
        }

        this.markers = [];

        clients.forEach(client => {
            if (client.latitude && client.longitude) {
                const marker = L.marker([client.latitude, client.longitude])
                    .addTo(this.map)
                    .bindPopup(`<b>${client.name}</b><br>${client.street || ""}`);
                this.markers.push(marker);
            }
        });

        console.log("✅ Clients affichés :", clients.length);
    };
}

ClientMapView.template = "client_map_template";
registry.category("actions").add("client_map_view", ClientMapView);
