from odoo import models, fields, api
from odoo.exceptions import UserError
from sklearn.cluster import KMeans
import logging
import requests

_logger = logging.getLogger(__name__)

class DailyVehiclePlanning(models.Model):
    _name = 'collecte.planning_journalier'
    _description = 'Planification journalière par véhicule'

    date = fields.Date(required=True, index=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string="Véhicule", index=True)
    ligne_ids = fields.One2many('collecte.planning_journalier_ligne', 'planning_id', string="Destinations")
    total_quantite = fields.Float(string="Quantité totale (kg)", compute="_compute_total")
    monthly_id = fields.Many2one('collecte.planning_mensuel', string="Planning mensuel", index=True)

    sql_constraints = [
        ('uniq_vehicle_date', 'unique(date, vehicle_id)', "Un planning existe déjà pour ce véhicule et cette date."),
    ]

    @api.depends('ligne_ids.quantite_collectee')
    def _compute_total(self):
        for rec in self:
            rec.total_quantite = sum(l.quantite_collectee for l in rec.ligne_ids)

    # ---------- UTIL ----------
    @api.model
    def _get_origin_coords(self):
        ICP = self.env['ir.config_parameter'].sudo()
        try:
            lat = float(ICP.get_param('collecte.origin_lat'))
            lon = float(ICP.get_param('collecte.origin_lon'))
        except Exception:
            lat = 36.37065151015154
            lon = 9.111696141592383
        return lat, lon

    @api.model
    def _get_time_params(self):
        ICP = self.env['ir.config_parameter'].sudo()

        def _f(key, default):
            try:
                return float(ICP.get_param(key, default))
            except Exception:
                return float(default)

        speed_kmh = _f('collecte.avg_speed_kmh', 40.0)
        service_base = _f('collecte.service_time_min_base', 5.0)
        service_per_kg = _f('collecte.service_time_min_per_kg', 0.02)
        return speed_kmh, service_base, service_per_kg

    @staticmethod
    def _haversine_km(lat1, lon1, lat2, lon2):
        from math import radians, sin, cos, asin, sqrt
        R = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2.0)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2.0)**2
        return 2.0 * R * asin(sqrt(a))

    # ---------- SERVICE ----------
    @api.model
    def generate_for_date(self, selected_date, replace_existing=True):
        if not selected_date:
            raise UserError("Aucune date fournie.")

        # 1) Planning mensuel
        dom = [('annee', '=', selected_date.year), ('mois', '=', str(selected_date.month))]
        monthly = self.env['collecte.planning_mensuelle'].search(dom + [('state', '=', 'done')], limit=1)
        if not monthly:
            monthly = self.env['collecte.planning_mensuel'].search(dom, limit=1)
        if not monthly:
            raise UserError(f"Aucun planning mensuel trouvé pour {selected_date.strftime('%m/%Y')}.")

        # 2) Lignes du jour
        lines = monthly.line_ids.filtered(lambda l: l.date == selected_date)
        if not lines:
            monthly.message_post(body=f"ℹ️ Aucune ligne pour {selected_date}.")
            return self.browse()

        # 3) Origine & paramètres
        ORIGIN_LAT, ORIGIN_LON = self._get_origin_coords()
        speed_kmh, service_base, service_per_kg = self._get_time_params()

        # 4) Points
        points = []
        for l in lines:
            p = l.partner_id
            if p.latitude and p.longitude and l.quantite:
                if p.distance_from_origin and p.distance_from_origin > 0:
                    dist_from_depot = float(p.distance_from_origin)
                else:
                    dist_from_depot = self._haversine_km(ORIGIN_LAT, ORIGIN_LON, p.latitude, p.longitude)

                points.append({
                    'partner_id': p.id,
                    'adresse': p.contact_address,
                    'quantite': float(l.quantite),
                    'lat': p.latitude,
                    'lon': p.longitude,
                    'dist': dist_from_depot,
                    'zone': (p.zone or 'unknown'),
                })
        if not points:
            monthly.message_post(body=f"⚠️ Aucun client géolocalisé pour {selected_date}.")
            return self.browse()

        # 5) Véhicules
        vehicles = self.env['fleet.vehicle'].search([])
        if not vehicles:
            raise UserError("Aucun véhicule disponible.")
        n_clusters = max(1, min(len(points), len(vehicles)))

        # 6) Clustering
        DIST_THRESHOLD = 150.0  # km – you can adjust this value

        # Split into near vs far
        near_points = [pt for pt in points if pt['dist'] <= DIST_THRESHOLD]
        far_points = [pt for pt in points if pt['dist'] > DIST_THRESHOLD]

        clusters = {}

        # --- Normal clustering for near points ---
        if near_points:
            zones_sorted = sorted({pt['zone'] for pt in near_points})
            zone_to_idx = {z: i for i, z in enumerate(zones_sorted)}
            for pt in near_points:
                pt['zone_idx'] = zone_to_idx[pt['zone']]

            dists = [pt['dist'] for pt in near_points]
            max_dist = max(dists) if dists else 1.0
            zone_weight = max_dist * 2.0

            X = [[pt['dist'], pt['zone_idx'] * zone_weight] for pt in near_points]
            kmeans = KMeans(n_clusters=n_clusters, random_state=0).fit(X)

            for idx, label in enumerate(kmeans.labels_):
                clusters.setdefault(label, []).append(near_points[idx])

        if far_points:
            clusters[max(clusters.keys(), default=-1) + 1] = far_points
            
           
        def cluster_sort_key(kv):
            _, pts = kv
            zmin = min(p.get('zone_idx', 999) for p in pts)  # handle far pts without zone_idx
            dmin = min(p['dist'] for p in pts)
            return (zmin, dmin)

        ordered = sorted(clusters.items(), key=cluster_sort_key)

        # 7) Remplacer les tournées existantes
        if replace_existing:
            self.search([('date', '=', selected_date)]).unlink()

        # 8) Création des tournées avec contrainte de capacité
        created = self.browse()
        vehicle_index = 0
        for _, pts in ordered:
            pts.sort(key=lambda p: p['dist'])

            while pts and vehicle_index < len(vehicles):
                vehicle = vehicles[vehicle_index]
                capacity = vehicle.capacity_kg or 999999

                current_load = 0.0
                sub_pts = []
                remaining_pts = []

                for pt in pts:
                    if current_load + pt['quantite'] <= capacity:
                        sub_pts.append(pt)
                        current_load += pt['quantite']
                    else:
                        remaining_pts.append(pt)

                # Création de la tournée
                lignes_vals = []
                cum_min = 0.0
                for ordre, pt in enumerate(sub_pts, start=1):
                    drive_dist = float(pt['dist'])
                    speed = max(speed_kmh, 1e-3)
                    drive_min = (drive_dist / speed) * 60.0
                    service_min = (service_base + service_per_kg * pt['quantite'])
                    cum_min += drive_min + service_min

                    lignes_vals.append((0, 0, {
                        'partner_id': pt['partner_id'],
                        'adresse': pt['adresse'],
                        'quantite_collectee': pt['quantite'],
                        'latitude': pt['lat'],
                        'longitude': pt['lon'],
                        'ordre': ordre,
                        'vehicle_id': vehicle.id,
                        'prev_partner_id': False,
                        'drive_distance_km': round(drive_dist, 3),
                        'drive_time_min': round(drive_min, 1),
                        'service_time_min': round(service_min, 1),
                        'cumulative_time_min': round(cum_min, 1),
                        'zone': pt['zone'],
                    }))

                if lignes_vals:
                    created |= self.create({
                        'date': selected_date,
                        'vehicle_id': vehicle.id,
                        'monthly_id': monthly.id,
                        'ligne_ids': lignes_vals,
                    })

                pts = remaining_pts
                vehicle_index += 1

        monthly.message_post(body=f"✅ {len(created)} tournée(s) créée(s) pour le {selected_date}.")
        return created

    def action_generate_from_monthly(self):
        self.ensure_one()
        if not self.date:
            raise UserError("Veuillez renseigner la date du planning.")
        recs = self.generate_for_date(self.date, replace_existing=True)
        if not recs:
            return
        action = self.env.ref('collecte_module.action_collecte_planning_journalier').read()[0]
        action['domain'] = [('id', 'in', recs.ids)]
        return action
    
    ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjMxMzdlMmE5MjRlZjQ2OWFiN2QzYzM0OWM1ZjBmOWIzIiwiaCI6Im11cm11cjY0In0="

    def action_show_optimized_route(self):
        self.ensure_one()

        origin = [9.111696, 36.370651]  # lon, lat depot
        coords = [origin]
        clients = []

        for line in self.ligne_ids:
            if line.partner_id.latitude and line.partner_id.longitude:
                coords.append([line.partner_id.longitude, line.partner_id.latitude])
                clients.append(line.partner_id.name)

        if len(coords) < 2:
            return

        try:
            response = requests.post(
                "https://api.openrouteservice.org/v2/directions/driving-car/geojson",
                json={"coordinates": coords},
                headers={"Authorization": self.ORS_API_KEY},
                timeout=15
            )
            data = response.json()

            route = data["features"][0]
            geometry_coords = route["geometry"]["coordinates"]
            
            # Get the waypoints from the response
            way_points = route["properties"]["way_points"]
            
            # Create custom steps for each client
            client_steps = []
            for i in range(1, len(way_points)):
                # Calculate distance and duration for this segment if needed
                # For simplicity, we're just setting the way_points
                client_steps.append({
                    "name": clients[i-1] if i-1 < len(clients) else f"Client {i}",
                    "way_points": [way_points[i-1], way_points[i]],
                    "distance": 0,  # You might calculate this from the steps
                    "duration": 0   # You might calculate this from the steps
                })

            return {
                "type": "ir.actions.client",
                "tag": "show_route_map",
                "params": {
                    "origin": origin,
                    "route_geometry": route,
                    "steps": client_steps,
                    "partner_name": self.display_name or _("Trajet Collecte")
                }
            }
        except Exception as e:
            _logger.error(f"ORS error: {e}")

class DailyVehiclePlanningLine(models.Model):
    _name = 'collecte.planning_journalier_ligne'
    _description = 'Destination journalière'

    planning_id = fields.Many2one('collecte.planning_journalier', ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string="Client", index=True)
    prev_partner_id = fields.Many2one('res.partner', string="Depuis", help="Arrêt précédent (vide = dépôt)")

    adresse = fields.Char()
    quantite_collectee = fields.Float()
    latitude = fields.Float()
    longitude = fields.Float()
    ordre = fields.Integer()
    vehicle_id = fields.Many2one('fleet.vehicle', string="Véhicule")
    zone = fields.Selection(related='partner_id.zone', store=True, readonly=True, index=True)

    drive_distance_km = fields.Float(string="Distance (km)")
    drive_time_min = fields.Float(string="Trajet (min)")
    service_time_min = fields.Float(string="Service (min)")
    cumulative_time_min = fields.Float(string="Cumul (min)")