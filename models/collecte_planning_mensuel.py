from odoo import models, fields, api
from datetime import datetime, date, time, timedelta
import calendar
import logging
import math
from odoo.exceptions import UserError
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

import numpy as np
from sklearn.cluster import KMeans

# HuggingFace embeddings
try:
    from sentence_transformers import SentenceTransformer
    HF_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as e:
    HF_MODEL = None

_logger = logging.getLogger(__name__)


class CollectePlanningMensuel(models.Model):
    _name = 'collecte.planning_mensuel'
    _description = 'Planning Mensuel de Collecte'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Libellé", required=True, default="Planning", tracking=True)
    mois = fields.Selection([
        ('1', 'Janvier'), ('2', 'Février'), ('3', 'Mars'), ('4', 'Avril'),
        ('5', 'Mai'), ('6', 'Juin'), ('7', 'Juillet'), ('8', 'Août'),
        ('9', 'Septembre'), ('10', 'Octobre'), ('11', 'Novembre'), ('12', 'Décembre')
    ], string="Mois", required=True, tracking=True)
    annee = fields.Integer(string="Année", default=lambda self: datetime.today().year, tracking=True)

    line_ids = fields.One2many('collecte.planning_ligne', 'planning_id', string="Lignes de planning")
    state = fields.Selection([('draft', 'Brouillon'), ('done', 'Validé')], default='draft', tracking=True)

    capacite_journaliere = fields.Float(string="Capacité maximale par jour (kg)", default=10000, tracking=True)

    # Paramètres temps/service
    vitesse_kmh = fields.Float(string="Vitesse moyenne (km/h)", default=40.0)
    service_base_min = fields.Integer(string="Service base (min)", default=10)
    service_par_kg_sec = fields.Float(string="Service par kg (sec/kg)", default=0.5)

    # -----------------------
    # Vérifie si un client doit être collecté ce jour
    # -----------------------
    def _est_client_a_collecter(self, partner, jour):
        weekday_map = {
            0: 'lundi', 1: 'mardi', 2: 'mercredi',
            3: 'jeudi', 4: 'vendredi', 5: 'samedi', 6: 'dimanche'
        }
        if getattr(partner, 'jour_fixe', False) and partner.jour_fixe == weekday_map[jour.weekday()]:
            return True
        if getattr(partner, 'nbre_passage_semaine', False):
            nb = int(partner.nbre_passage_semaine)
            jours_ouvrables = [0, 1, 2, 3, 4]
            step = max(1, len(jours_ouvrables) // nb)
            selected_days = jours_ouvrables[::step][:nb]
            if jour.weekday() in selected_days:
                return True
        if getattr(partner, 'frequence_collecte', False):
            freq = int(partner.frequence_collecte)
            first_day = jour.replace(day=1)
            delta = (jour - first_day).days
            if delta % freq == 0:
                return True
        return False

    def _sec_from_hhmm(self, hh, mm):
        return hh * 3600 + mm * 60

    def _trajet_sec(self, meters):
        v = max(1.0, (self.vitesse_kmh or 40.0) * 1000.0 / 3600.0)
        return int(round(meters / v))

    def _service_time_sec(self, kg):
        base = (self.service_base_min or 10) * 60
        perkg = (self.service_par_kg_sec or 0.5) * (kg or 0.0)
        return int(round(base + perkg))

    def _haversine_m(self, a, b):
        lon1, lat1, lon2, lat2 = map(math.radians, [a[1], a[0], b[1], b[0]])
        dlon, dlat = lon2 - lon1, lat2 - lat1
        d = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        return int(6371 * 1000 * (2 * math.asin(math.sqrt(d))))

    def _time_window_for_partner(self, partner):
        return (self._sec_from_hhmm(8, 0), self._sec_from_hhmm(17, 0))

    # -----------------------
    # Clustering via embeddings (HF ou fallback KMeans)
    # -----------------------
    def _cluster_jobs(self, jobs, n_clusters=3):
        coords = [f"{j['location'][0]},{j['location'][1]}" for j in jobs]
        try:
            if HF_MODEL:
                embeddings = HF_MODEL.encode(coords)
            else:
                raise RuntimeError("HF indisponible")
        except Exception as e:
            _logger.warning("[CLUSTER] HuggingFace non dispo (%s), fallback KMeans", e)
            embeddings = np.array([j["location"] for j in jobs])

        # KMeans clustering
        kmeans = KMeans(n_clusters=min(n_clusters, len(jobs)), random_state=42, n_init="auto")
        labels = kmeans.fit_predict(embeddings)
        for j, lab in zip(jobs, labels):
            j["cluster"] = int(lab)
        return jobs

    # -----------------------
    # Génération du planning
    # -----------------------
    def action_generer_planning(self):
        self.ensure_one()
        num_vehicles = 3
        depot = (36.370651, 9.111696)

        _logger.info("[PLANNING] ==== Début génération planning pour %s/%s ====", self.mois, self.annee)

        partners = self.env['res.partner'].search([
            ('active', '=', True),
            '|', ('quantite_previsionnelle', '>', 0.0),
                ('quantite_estimee', '>', 0.0),
        ])
        jobs = []
        for p in partners:
            poids = float(p.quantite_previsionnelle or p.quantite_estimee or 0.0)
            if not (p.latitude and p.longitude and poids):
                continue
            if not (p.frequence_collecte or p.nbre_passage_semaine or p.jour_fixe):
                continue
            jobs.append({
                "id": p.id,
                "location": (p.latitude, p.longitude),
                "amount": poids,
                "tw": self._time_window_for_partner(p),
                "service": self._service_time_sec(poids),
            })

        if not jobs:
            self.message_post(body="⚠️ Aucun client trouvé à planifier.")
            return

        # Clustering pour organiser les zones
        jobs = self._cluster_jobs(jobs, n_clusters=num_vehicles)

        jours_du_mois = [date(self.annee, int(self.mois), d)
                         for d in range(1, calendar.monthrange(self.annee, int(self.mois))[1] + 1)
                         if date(self.annee, int(self.mois), d).weekday() != 6]

        self.line_ids.unlink()
        planning_lines, created = [], 0
        jobs_restants = jobs[:]

        for jour in jours_du_mois:
            # 1. Filtrer par jour fixe / fréquence
            jobs_du_jour = []
            for j in list(jobs_restants):
                partner = self.env['res.partner'].browse(j["id"])
                if self._est_client_a_collecter(partner, jour):
                    jobs_du_jour.append(j)

            if not jobs_du_jour:
                continue

            # 2. Organiser par clusters
            for cluster_id in set(j["cluster"] for j in jobs_du_jour):
                cluster_jobs = [j for j in jobs_du_jour if j["cluster"] == cluster_id]
                if not cluster_jobs:
                    continue

                all_points = [depot] + [j["location"] for j in cluster_jobs]
                n = len(all_points)

                # Matrices
                distance_m = [[0]*n for _ in range(n)]
                travel_sec = [[0]*n for _ in range(n)]
                for i in range(n):
                    for k in range(n):
                        if i != k:
                            d_m = self._haversine_m(all_points[i], all_points[k])
                            distance_m[i][k] = d_m
                            travel_sec[i][k] = self._trajet_sec(d_m)

                manager = pywrapcp.RoutingIndexManager(n, num_vehicles, 0)
                routing = pywrapcp.RoutingModel(manager)

                def dist_cb(from_index, to_index):
                    return distance_m[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]
                dist_idx = routing.RegisterTransitCallback(dist_cb)
                routing.SetArcCostEvaluatorOfAllVehicles(dist_idx)

                demands = [0] + [int(j["amount"]) for j in cluster_jobs]
                def demand_cb(from_index):
                    return demands[manager.IndexToNode(from_index)]
                demand_idx = routing.RegisterUnaryTransitCallback(demand_cb)
                routing.AddDimensionWithVehicleCapacity(
                    demand_idx, 0,
                    [int(self.capacite_journaliere or 10000)] * num_vehicles,
                    True, "Capacity")

                def time_cb(from_index, to_index):
                    from_node = manager.IndexToNode(from_index)
                    serv = cluster_jobs[from_node-1]["service"] if from_node != 0 else 0
                    return serv + travel_sec[from_node][manager.IndexToNode(to_index)]
                time_idx = routing.RegisterTransitCallback(time_cb)

                day_start, day_end = self._sec_from_hhmm(8, 0), self._sec_from_hhmm(17, 0)
                routing.AddDimension(time_idx, 3600, day_end+3600, False, "Time")
                time_dim = routing.GetDimensionOrDie("Time")

                for node in range(1, n):
                    idx = manager.NodeToIndex(node)
                    tw_start, tw_end = cluster_jobs[node-1]["tw"]
                    time_dim.CumulVar(idx).SetRange(max(day_start, tw_start), min(day_end, tw_end))

                search_params = pywrapcp.DefaultRoutingSearchParameters()
                search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
                search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
                search_params.time_limit.FromSeconds(5) 
                solution = routing.SolveWithParameters(search_params)
                if not solution:
                    continue

                affectes = []
                for veh in range(num_vehicles):
                    index = routing.Start(veh)
                    while not routing.IsEnd(index):
                        node = manager.IndexToNode(index)
                        if node != 0:
                            job = cluster_jobs[node-1]
                            partner = self.env['res.partner'].browse(job["id"])
                            arrival_sec = solution.Value(time_dim.CumulVar(index))
                            depart_sec = arrival_sec + job["service"]
                            arrival_dt = datetime.combine(jour, time.min) + timedelta(seconds=arrival_sec)
                            depart_dt = datetime.combine(jour, time.min) + timedelta(seconds=depart_sec)
                            planning_lines.append((0, 0, {
                                'planning_id': self.id,
                                'date': jour,
                                'partner_id': partner.id,
                                'quantite': job["amount"],
                                'arrival_dt': arrival_dt,
                                'depart_dt': depart_dt,
                            }))
                            created += 1
                            affectes.append(job)
                        index = solution.Value(routing.NextVar(index))
                jobs_restants = [j for j in jobs_restants if j not in affectes]

        if planning_lines:
            self.write({'line_ids': planning_lines, 'state': 'done'})
        else:
            self.message_post(body="⚠️ Aucun client planifié.")


class CollectePlanningLigne(models.Model):
    _name = 'collecte.planning_ligne'
    _description = 'Ligne de planning de collecte'
    _order = 'date, arrival_dt'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    planning_id = fields.Many2one(
        'collecte.planning_mensuel',
        string="Planning mensuel",
        required=True,
        ondelete="cascade",
        index=True
    )

    date = fields.Date(string="Date", required=True)
    partner_id = fields.Many2one('res.partner', string="Client", required=True)
    quantite = fields.Float(string="Quantité prévue (kg)")

    arrival_dt = fields.Datetime(string="Heure d'arrivée estimée")
    depart_dt  = fields.Datetime(string="Heure de départ estimée")

    name = fields.Char(string='Libellé', compute='_compute_name', store=True)
    zone = fields.Selection(
        related='partner_id.zone',
        string="Zone",
        store=True,
        readonly=True,
        index=True,
    )

    @api.depends('partner_id', 'quantite', 'arrival_dt')
    def _compute_name(self):
        for rec in self:
            eta = rec.arrival_dt and rec.arrival_dt.strftime("%H:%M") or "—"
            if rec.partner_id and rec.quantite:
                rec.name = f"{eta} • {rec.partner_id.name} – {rec.quantite:.2f} kg"
            else:
                rec.name = "Collecte"
