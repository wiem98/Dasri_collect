from odoo import models, fields, api
from datetime import datetime
import calendar
from sklearn.cluster import KMeans
import random
from datetime import date as dt

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
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('done', 'Validé')
    ], default='draft', tracking=True)

    capacite_journaliere = fields.Float(string="Capacité maximale par jour", default=10000, tracking=True)
    def action_generer_planning(self):
        self.ensure_one()

        mois_int = int(self.mois)
        _, last_day = calendar.monthrange(self.annee, mois_int)

        # Toutes les dates du mois sauf dimanche
        all_dates = [
            datetime(self.annee, mois_int, day).date()
            for day in range(1, last_day + 1)
            if datetime(self.annee, mois_int, day).weekday() != 6  # 6 = dimanche
        ]
        used_capacity = {date: 0 for date in all_dates}
        planning_lines = []

        contrats = self.env['collecte.contrat'].search([])

        # Mapping de jour_fixe vers weekday (0=lundi, ..., 6=dimanche)
        jours_mapping = {
            'lundi': 0,
            'mardi': 1,
            'mercredi': 2,
            'jeudi': 3,
            'vendredi': 4,
            'samedi': 5,
            'dimanche': 6
        }

        for contrat in contrats:
            poids = contrat.quantite_previsionnelle or 0.0
            if not poids:
                continue

            freq_par_semaine = int(contrat.nbre_passage_semaine or 1)
            freq_par_mois = freq_par_semaine * 4

            # ✅ Appliquer le filtre sur jour fixe s'il est défini
            if contrat.jour_fixe:
                jour_index = jours_mapping.get(contrat.jour_fixe.lower())
                dates_possibles = [
                    d for d in all_dates if d.weekday() == jour_index
                ]
            else:
                dates_possibles = all_dates

            # Trier par capacité restante
            dates_possibles = sorted(dates_possibles, key=lambda d: used_capacity[d])
            count = 0

            for d in dates_possibles:
                if count >= freq_par_mois:
                    break
                if used_capacity[d] + poids <= self.capacite_journaliere:
                    planning_lines.append((0, 0, {
                        'date': d,
                        'partner_id': contrat.partner_id.id,
                        'contrat_id': contrat.id,
                        'quantite': poids,
                    }))
                    used_capacity[d] += poids
                    count += 1

        # Nettoyage et sauvegarde
        self.line_ids.unlink()
        self.write({
            'line_ids': planning_lines,
            'state': 'done',
        })

    @api.model
    def _get_thread_with_access(self, thread_id, **kwargs):
        record = self.browse(thread_id)
        record.check_access_rights('read')
        record.check_access_rule('read')
        return record
    
        
    def action_generer_plan_journalier(self):
        for planning in self:
            today = dt.today()
            lignes_du_jour = planning.line_ids.filtered(lambda l: l.date == today)

            if not lignes_du_jour:
                continue

            # Extraire les points avec coordonnées
            points = []
            for ligne in lignes_du_jour:
                partner = ligne.partner_id
                if partner.latitude and partner.longitude:
                    quantite = ligne.quantite * (1 + random.uniform(0.1, 0.2))  # ajout aléatoire
                    points.append({
                        'partner_id': partner.id,
                        'adresse': partner.contact_address,
                        'quantite': round(quantite, 2),
                        'latitude': partner.latitude,
                        'longitude': partner.longitude,
                    })

            if not points:
                continue

            coords = [[p['latitude'], p['longitude']] for p in points]

            # Récupérer les véhicules
            vehicles = self.env['fleet.vehicle'].search([], limit=len(points))
            NB_CLUSTERS = min(len(points), len(vehicles))

            kmeans = KMeans(n_clusters=NB_CLUSTERS).fit(coords)
            clusters = {}
            for idx, label in enumerate(kmeans.labels_):
                clusters.setdefault(label, []).append(points[idx])

            for idx, (label, cluster_points) in enumerate(clusters.items()):
                if idx >= len(vehicles):
                    continue  # ou utiliser vehicles[0] si tu veux réutiliser le même véhicule
                vehicle = vehicles[idx]

                lignes = []
                ordre = 1
                for pt in sorted(cluster_points, key=lambda p: p['quantite'], reverse=True):
                    lignes.append((0, 0, {
                        'partner_id': pt['partner_id'],
                        'adresse': pt['adresse'],
                        'quantite_collectee': pt['quantite'],
                        'latitude': pt['latitude'],
                        'longitude': pt['longitude'],
                        'ordre': ordre,
                        'vehicle_id': vehicle.id,  

                    }))
                    ordre += 1

                self.env['collecte.planning_journalier'].create({
                    'date': today,
                    'vehicle_id': vehicle.id,
                    'ligne_ids': lignes,
                })


class CollectePlanningLigne(models.Model):
    _name = 'collecte.planning_ligne'
    _description = 'Ligne de planning de collecte'
    _order = 'date'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    planning_id = fields.Many2one('collecte.planning_mensuel', required=True, ondelete='cascade')
    date = fields.Date(string="Date", required=True)
    partner_id = fields.Many2one('res.partner', string="Client")
    contrat_id = fields.Many2one('collecte.contrat', string="Contrat")
    quantite = fields.Float(string="Quantité prévue (kg)")
    name = fields.Char(string='Libellé', compute='_compute_name', store=True)

    @api.depends('partner_id', 'quantite')
    def _compute_name(self):
        for rec in self:
            if rec.partner_id and rec.quantite:
                rec.name = f"{rec.partner_id.name} - {rec.quantite:.2f} kg"
            else:
                rec.name = "Collecte"
    