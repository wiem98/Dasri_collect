/** @odoo-module **/

import AbstractAction from 'web.AbstractAction';
import core from 'web.core';

const RouteMapAction = AbstractAction.extend({
    template: 'RouteMapTemplate',
    start: function () {
        try {
            const params = this.params;
            if (!params || !params.origin || !params.route_geometry) {
                console.error("Missing parameters:", params);
                return;
            }

            const map = L.map(this.$('.o_route_map_container')[0])
                .setView([params.origin[1], params.origin[0]], 10);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png')
                .addTo(map);

            // Decode the ORS geometry
            const coords = L.PolylineUtil.decode(params.route_geometry);
            const route = L.polyline(coords, { color: 'blue' }).addTo(map);

            L.marker([params.origin[1], params.origin[0]])
                .addTo(map)
                .bindPopup("Départ");

            map.fitBounds(route.getBounds());
        } catch (err) {
            console.error("Error rendering map:", err);
        }
    }
});

// Register action so Odoo can find it
core.action_registry.add('show_route_map', RouteMapAction);
