/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useRef } from "@odoo/owl";

export class RouteMapAction extends Component {
    setup() {
        console.log("✅ RouteMapAction setup called");
        this.mapRef = useRef("mapContainer");

        onMounted(() => {
            console.log("✅ onMounted triggered, mapRef:", this.mapRef);
            this.initMap();
        });
    }

    initMap() {
        const params = this.props.action ? this.props.action.params : this.props;
        console.log("🔍 Received params:", params);

        if (!params?.origin || !params?.route_geometry) {
            console.error("❌ Missing required parameters", params);
            return;
        }

        if (!this.mapRef.el) {
            console.error("❌ Map container element not found!");
            return;
        }

        // Initialize map
        const map = L.map(this.mapRef.el).setView(
            [params.origin[1], params.origin[0]],
            10
        );

        // Tile layer
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
        }).addTo(map);

        // Draw route
        const route = L.geoJSON(params.route_geometry, {
            style: { color: "blue", weight: 4 },
        }).addTo(map);

        // Origin marker
        L.marker([params.origin[1], params.origin[0]])
            .addTo(map)
            .bindPopup("Dasri Sterile");

        // Client markers
        if (params.steps && Array.isArray(params.steps)) {
            console.log("📌 Adding client markers:", params.steps.length);
            const coords = params.route_geometry.geometry.coordinates;

            params.steps.forEach((step, i) => {
                console.log(`➡️ Step ${i + 1}:`, step);

                let lat, lon;

                if (step.way_points && Array.isArray(step.way_points) && step.way_points.length >= 2) {
                    // Use the end waypoint of each segment (should be client location)
                    const pointIndex = step.way_points[1];
                    if (coords[pointIndex]) {
                        [lon, lat] = coords[pointIndex];
                    }
                }

                if (lat !== undefined && lon !== undefined) {
                    L.marker([lat, lon])
                        .addTo(map)
                        .bindPopup(`
                            <b>${step.name || `Client ${i + 1}`}</b><br>
                            ${step.distance ? `Distance: ${(step.distance/1000).toFixed(1)} km<br>` : ""}
                            ${step.duration ? `Duration: ${(step.duration/60).toFixed(1)} min` : ""}
                        `);
                } else {
                    console.warn(`⚠️ No coords for step ${i + 1}`, step);
                }
            });
        }

        // Fit map to route
        map.fitBounds(route.getBounds());

        // Fix Odoo resize issues
        setTimeout(() => {
            map.invalidateSize();
            map.panTo([params.origin[1], params.origin[0]]);
        }, 300);
    }
}

RouteMapAction.template = "collecte_module.RouteMapTemplate";
registry.category("actions").add("show_route_map", RouteMapAction);
