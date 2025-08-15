from odoo import models, fields, api
from datetime import datetime
import calendar
from sklearn.cluster import KMeans
import random
from datetime import date as dt
import logging
from collections import defaultdict
from odoo.exceptions import UserError
from math import radians, sin, cos, asin, sqrt
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

    capacite_journaliere = fields.Float(string="Capacité maximale par jour", default=10000, tracking=True)

    def haversine(lon1, lat1, lon2, lat2):
        """Distance in km between two lat/lon points."""
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return 6371 * c  # Earth radius in km

    def action_generer_planning(self):
        self.ensure_one()

        mois_int = int(self.mois)
        _, last_day = calendar.monthrange(self.annee, mois_int)
        all_dates = [
            datetime(self.annee, mois_int, day).date()
            for day in range(1, last_day + 1)
            if datetime(self.annee, mois_int, day).weekday() != 6  # exclure dimanche
        ]

        used_capacity = {d: 0.0 for d in all_dates}
        day_zone = {d: None for d in all_dates}
        planning_lines = []

        partners = self.env['res.partner'].search([
            ('active', '=', True),
            '|', ('quantite_previsionnelle', '>', 0.0),
                ('quantite_estimee', '>', 0.0),
        ])

        # --- Step 1: Prepare data for clustering ---
        coords = []
        partner_list = []
        for p in partners:
            if p.latitude and p.longitude:
                coords.append([p.latitude, p.longitude])
                partner_list.append(p)

        clusters = {}
        if coords and len(coords) >= 3:  # minimum to cluster
            try:
                k = min(5, len(coords))  # choose up to 5 clusters, adjust as needed
                km = KMeans(n_clusters=k, random_state=42)
                labels = km.fit_predict(coords)
                for label, partner in zip(labels, partner_list):
                    clusters.setdefault(f"Cluster_{label}", []).append(partner)
            except Exception as e:
                _logger.error(f"[PLANNING] Clustering failed: {e}")
        else:
            clusters["Cluster_0"] = partner_list

        # --- Step 2: Add partners without coords to a separate group ---
        for p in partners:
            if not p.latitude or not p.longitude:
                clusters.setdefault("NoCoords", []).append(p)

        jours_mapping = {'lundi':0,'mardi':1,'mercredi':2,'jeudi':3,'vendredi':4,'samedi':5}

        # --- Step 3: Loop over each cluster ---
        created = 0
        for zone, zone_partners in clusters.items():
            # Sort fixed days first
            def fix_rank(p): return 0 if p.jour_fixe else 1
            zone_partners.sort(key=lambda p: (fix_rank(p), p.id or 0))

            for partner in zone_partners:
                poids = float(partner.quantite_previsionnelle or partner.quantite_estimee or 0.0)
                if not poids:
                    continue

                # Frequency per month
                freq_par_mois = 0
                if partner.nbre_passage_semaine:
                    try: freq_par_mois = int(partner.nbre_passage_semaine) * 4
                    except: pass
                elif partner.frequence_collecte:
                    try: freq_par_mois = max(1, 30 // int(partner.frequence_collecte))
                    except: pass
                if not freq_par_mois:
                    freq_par_mois = 1

                # Candidate dates
                candidate_dates = list(all_dates)
                if partner.jour_fixe:
                    jour_index = jours_mapping.get((partner.jour_fixe or '').lower())
                    if jour_index is not None:
                        candidate_dates = [d for d in all_dates if d.weekday() == jour_index]
                        if not candidate_dates:
                            _logger.warning("[PLANNING] %s jour_fixe=%s non planifiable. Fallback tous jours.",
                                            partner.display_name, partner.jour_fixe)
                            candidate_dates = list(all_dates)

                # Prefer same cluster on same day
                preferred = [d for d in candidate_dates if day_zone[d] in (None, zone)]
                preferred.sort(key=lambda d: used_capacity[d])

                count = 0
                for d in preferred:
                    if count >= freq_par_mois:
                        break
                    if used_capacity[d] + poids <= self.capacite_journaliere:
                        planning_lines.append((0, 0, {
                            'date': d,
                            'partner_id': partner.id,
                            'quantite': poids,
                        }))
                        used_capacity[d] += poids
                        if day_zone[d] is None:
                            day_zone[d] = zone
                        count += 1
                        created += 1

                # Fallback dates
                if count < freq_par_mois:
                    fallback = [d for d in candidate_dates if d not in preferred]
                    fallback.sort(key=lambda d: used_capacity[d])
                    for d in fallback:
                        if count >= freq_par_mois:
                            break
                        if used_capacity[d] + poids <= self.capacite_journaliere:
                            planning_lines.append((0, 0, {
                                'date': d,
                                'partner_id': partner.id,
                                'quantite': poids,
                            }))
                            used_capacity[d] += poids
                            count += 1
                            created += 1

        # --- Step 4: Save results ---
        if not planning_lines:
            self.message_post(body="⚠️ Aucun planning généré.")
            self.write({'state': 'draft'})
            return

        self.line_ids.unlink()
        self.write({'line_ids': planning_lines, 'state': 'done'})
        _logger.info("[PLANNING] Lignes créées: %s", created)
    @api.model
    def _get_thread_with_access(self, thread_id, **kwargs):
        record = self.browse(thread_id)
        record.check_access_rights('read')
        record.check_access_rule('read')
        return record

    

class CollectePlanningLigne(models.Model):
    _name = 'collecte.planning_ligne'
    _description = 'Ligne de planning de collecte'
    _order = 'date'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    planning_id = fields.Many2one('collecte.planning_mensuel', required=True, ondelete='cascade')
    date = fields.Date(string="Date", required=True)
    partner_id = fields.Many2one('res.partner', string="Client", required=True)
    quantite = fields.Float(string="Quantité prévue (kg)")
    name = fields.Char(string='Libellé', compute='_compute_name', store=True)
    zone = fields.Selection(
    related='partner_id.zone',
    string="Zone",
    store=True,
    readonly=True,
    index=True,
)
    @api.depends('partner_id', 'quantite')
    def _compute_name(self):
        for rec in self:
            if rec.partner_id and rec.quantite:
                rec.name = f"{rec.partner_id.name} - {rec.quantite:.2f} kg"
            else:
                rec.name = "Collecte"
