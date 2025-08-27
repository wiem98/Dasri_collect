from odoo import models, fields, api
from datetime import datetime, date, time, timedelta
import calendar
import logging
import math
from odoo.exceptions import UserError
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

_logger = logging.getLogger(__name__)


class CollectePlanningMensuel(models.Model):
    _name = 'collecte.planning_mensuelle'
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

    # New planning knobs
    vitesse_kmh = fields.Float(string="Vitesse moyenne (km/h)", default=40.0, help="Utilisée pour convertir distance en temps de trajet.")
    service_base_min = fields.Integer(string="Service base (min)", default=10, help="Temps de service fixe par client (minutes).")
    service_par_kg_sec = fields.Float(string="Service par kg (sec/kg)", default=0.5, help="Temps additionnel par kg ramassé.")

    # -----------------------
    # Vérifie si un client doit être collecté ce jour
    # -----------------------
    def _est_client_a_collecter(self, partner, jour):
        weekday_map = {
            0: 'lundi', 1: 'mardi', 2: 'mercredi',
            3: 'jeudi', 4: 'vendredi', 5: 'samedi', 6: 'dimanche'
        }

        # Jour fixe prioritaire
        if getattr(partner, 'jour_fixe', False) and partner.jour_fixe == weekday_map[jour.weekday()]:
            return True

        # Passages par semaine
        if getattr(partner, 'nbre_passage_semaine', False):
            nb = int(partner.nbre_passage_semaine)
            jours_ouvrables = [0, 1, 2, 3, 4]  # lundi-vendredi
            step = max(1, len(jours_ouvrables) // nb)
            selected_days = jours_ouvrables[::step][:nb]
            if jour.weekday() in selected_days:
                return True

        # Fréquence (tous les X jours)
        if getattr(partner, 'frequence_collecte', False):
            freq = int(partner.frequence_collecte)
            first_day = jour.replace(day=1)
            delta = (jour - first_day).days
            if delta % freq == 0:
                return True

        return False

    # Helpers temps
    def _sec_from_hhmm(self, hh, mm):
        return hh * 3600 + mm * 60

    def _trajet_sec(self, meters):
        # vitesse m/s
        v = max(1.0, (self.vitesse_kmh or 40.0) * 1000.0 / 3600.0)
        return int(round(meters / v))

    def _service_time_sec(self, kg):
        base = (self.service_base_min or 10) * 60
        perkg = (self.service_par_kg_sec or 0.5) * (kg or 0.0)
        return int(round(base + perkg))

    # Distance haversine (m)
    def _haversine_m(self, a, b):
        # a = (lat, lon), b = (lat, lon)
        lon1, lat1, lon2, lat2 = map(math.radians, [a[1], a[0], b[1], b[0]])
        dlon, dlat = lon2 - lon1, lat2 - lat1
        d = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        return int(6371 * 1000 * (2 * math.asin(math.sqrt(d))))

    # Fenêtres horaires par type de client
    def _time_window_for_partner(self, partner):
        # Par défaut : 08:00–17:00
        start = self._sec_from_hhmm(8, 0)
        end_default = self._sec_from_hhmm(17, 0)
        type_client = getattr(partner, 'type_client', False)  
        if type_client == 'prive':
            return (start, self._sec_from_hhmm(13, 0))
        # étatique ou autres
        return (start, end_default)

    # -----------------------
    # Génération du planning
    # -----------------------
    def action_generer_planning(self):
        self.ensure_one()

        # 1) Collecter clients actifs
        partners = self.env['res.partner'].search([
            ('active', '=', True),
            '|', ('quantite_previsionnelle', '>', 0.0),
                 ('quantite_estimee', '>', 0.0),
        ])

        jobs = []
        for p in partners:
            if not (p.latitude and p.longitude):
                continue
            poids = float(p.quantite_previsionnelle or p.quantite_estimee or 0.0)
            if not poids:
                continue
            jobs.append({
                "id": p.id,
                "location": (p.latitude, p.longitude),  # (lat, lon)
                "amount": poids,
                "tw": self._time_window_for_partner(p),   # (start_sec, end_sec)
                "service": self._service_time_sec(poids)  # seconds
            })

        if not jobs:
            self.message_post(body="⚠️ Aucun client à planifier.")
            return

        # 2) Liste des jours (hors dimanches)
        jours_du_mois = []
        _, nb_jours = calendar.monthrange(self.annee, int(self.mois))
        for day in range(1, nb_jours + 1):
            d = date(self.annee, int(self.mois), day)
            if d.weekday() != 6:  # exclure dimanche
                jours_du_mois.append(d)

        if not jours_du_mois:
            raise UserError("⚠️ Aucun jour ouvrable trouvé pour ce mois.")

        # 3) Dépôt (lat, lon)
        depot = (36.370651, 9.111696)

        # 4) Reset planning
        self.line_ids.unlink()
        planning_lines = []
        created = 0

        # 5) Boucle journalière
        jobs_restants = jobs[:]
        for jour in jours_du_mois:
            # Clients qui doivent être collectés ce jour
            jobs_du_jour = []
            for j in list(jobs_restants):
                partner = self.env['res.partner'].browse(j["id"])
                if self._est_client_a_collecter(partner, jour):
                    jobs_du_jour.append(j)

            if not jobs_du_jour:
                continue

            # Construire matrices distance & temps
            all_points = [depot] + [j["location"] for j in jobs_du_jour]
            n = len(all_points)

            distance_m = [[0]*n for _ in range(n)]
            travel_sec = [[0]*n for _ in range(n)]
            for i in range(n):
                for k in range(n):
                    if i == k:
                        continue
                    d_m = self._haversine_m(all_points[i], all_points[k])
                    distance_m[i][k] = d_m
                    travel_sec[i][k] = self._trajet_sec(d_m)

            # OR-Tools index manager & routing
            manager = pywrapcp.RoutingIndexManager(n, 1, 0)  # 1 véhicule, dépôt index 0
            routing = pywrapcp.RoutingModel(manager)

            # Coût = distance
            def dist_cb(from_index, to_index):
                return distance_m[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]
            dist_idx = routing.RegisterTransitCallback(dist_cb)
            routing.SetArcCostEvaluatorOfAllVehicles(dist_idx)

            # Capacité (kg)
            demands = [0] + [int(j["amount"]) for j in jobs_du_jour]
            capacities = [int(self.capacite_journaliere or 10000)]
            def demand_cb(from_index):
                return demands[manager.IndexToNode(from_index)]
            demand_idx = routing.RegisterUnaryTransitCallback(demand_cb)
            routing.AddDimensionWithVehicleCapacity(demand_idx, 0, capacities, True, "Capacity")

            # Dimension TEMPS
            def time_cb(from_index, to_index):
                # trajet + service du node source (sauf dépôt)
                from_node = manager.IndexToNode(from_index)
                serv = 0
                if from_node != 0:
                    serv = jobs_du_jour[from_node - 1]["service"]
                return serv + travel_sec[from_node][manager.IndexToNode(to_index)]
            time_idx = routing.RegisterTransitCallback(time_cb)

            # Horizon: journée
            day_start = self._sec_from_hhmm(8, 0)
            day_end = self._sec_from_hhmm(17, 0)
            routing.AddDimension(
                time_idx,
                300,                # slack max
                day_end,            # horizon max
                False,              # don't force start cumul to 0 (we’ll set windows)
                "Time",
            )
            time_dim = routing.GetDimensionOrDie("Time")

            # Fenêtre dépôt: 08:00–17:00
            start_idx = routing.Start(0)
            end_idx = routing.End(0)
            time_dim.CumulVar(start_idx).SetRange(day_start, day_end)
            time_dim.CumulVar(end_idx).SetRange(day_start, day_end)

            # Fenêtres clients (index 1..n-1)
            for node in range(1, n):
                idx = manager.NodeToIndex(node)
                tw_start, tw_end = jobs_du_jour[node - 1]["tw"]
                # Clamp within the day horizon
                tw_s = max(day_start, tw_start)
                tw_e = min(day_end, tw_end)
                # empêcher visites après 13:00 pour privé (set via tw)
                # empêcher visites après 17:00 pour étatique (tw_e already 17:00)
                time_dim.CumulVar(idx).SetRange(tw_s, tw_e)

            # Chercher solution
            search_params = pywrapcp.DefaultRoutingSearchParameters()
            search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            search_params.time_limit.seconds = 5

            solution = routing.SolveWithParameters(search_params)
            if not solution:
                _logger.warning("[VRP] Pas de solution trouvée pour %s (fenêtres horaires).", jour)
                continue

            # Extraire la tournée + ETAs
            affectes = []
            index = routing.Start(0)

            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                if node != 0:
                    job = jobs_du_jour[node - 1]
                    partner = self.env['res.partner'].browse(job["id"])

                    # arrival seconds from midnight via Time dimension
                    arrival_sec = solution.Value(time_dim.CumulVar(index))
                    # departure = arrival + service time
                    depart_sec = arrival_sec + job["service"]

                    # Convertir en datetimes (mixer avec la date du jour)
                    arrival_dt = datetime.combine(jour, time.min) + timedelta(seconds=arrival_sec)
                    depart_dt = datetime.combine(jour, time.min) + timedelta(seconds=depart_sec)

                    planning_lines.append((0, 0, {
                        'date': jour,
                        'partner_id': partner.id,
                        'quantite': job["amount"],
                        'arrival_dt': arrival_dt,
                        'depart_dt': depart_dt,
                    }))
                    created += 1
                    affectes.append(job)

                index = solution.Value(routing.NextVar(index))

            # Retirer du pool global
            jobs_restants = [j for j in jobs_restants if j not in affectes]

        # 6) Save
        if not planning_lines:
            self.message_post(body="⚠️ Aucun client planifié (contraintes horaires/capacité).")
            return
        self.write({'line_ids': planning_lines, 'state': 'done'})
        _logger.info("[ORTOOLS] Lignes créées pour %s/%s: %s", self.mois, self.annee, created)


class CollectePlanningLigne(models.Model):
    _name = 'collecte.planning_ligne'
    _description = 'Ligne de planning de collecte'
    _order = 'date, arrival_dt'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    date = fields.Date(string="Date", required=True)
    partner_id = fields.Many2one('res.partner', string="Client", required=True)
    quantite = fields.Float(string="Quantité prévue (kg)")

    # New: ETAs
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
