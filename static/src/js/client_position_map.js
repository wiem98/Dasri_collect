/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

export class ClientPositionMap extends Component {
    setup() {
        this.state = useState({
            partner_id: this.props.action.params.partner_id,
            latitude: this.props.action.params.latitude || 36.8065,
            longitude: this.props.action.params.longitude || 10.1815,
        });

        this.mapRef = useRef("map");
        this.dialog = useService("dialog");
        onMounted(this.initMap);
    }

    initMap = () => {
        const map = L.map(this.mapRef.el).setView([this.state.latitude, this.state.longitude], 13);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
        }).addTo(map);

        const marker = L.marker([this.state.latitude, this.state.longitude], { draggable: true }).addTo(map);
        this.marker = marker;

        marker.on("dragend", () => {
            const { lat, lng } = marker.getLatLng();
            this.state.latitude = lat;
            this.state.longitude = lng;
        });

        map.on("click", (e) => {
            const { lat, lng } = e.latlng;
            marker.setLatLng([lat, lng]);
            this.state.latitude = lat;
            this.state.longitude = lng;
        });

        this.map = map;
    };

    async saveLocation() {
        await rpc("/update_partner_location", {
            partner_id: this.state.partner_id,
            latitude: this.state.latitude,
            longitude: this.state.longitude,
        });

        this.env.services.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: this.state.partner_id,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }


    cancel() {
        this.env.services.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: this.state.partner_id,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }
}

ClientPositionMap.template = "client_position_template";
registry.category("actions").add("client_position_map", ClientPositionMap);

