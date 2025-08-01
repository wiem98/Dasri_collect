from odoo import models, fields, api
from datetime import datetime
import calendar

class CollectePlanningMensuel(models.Model):
    _name = 'collecte.planning_mensuel'
    _description = 'Planning Mensuel de Collecte'

    name = fields.Char(string="Libellé", required=True, default="Planning")
    mois = fields.Selection([
        ('1', 'Janvier'), ('2', 'Février'), ('3', 'Mars'), ('4', 'Avril'),
        ('5', 'Mai'), ('6', 'Juin'), ('7', 'Juillet'), ('8', 'Août'),
        ('9', 'Septembre'), ('10', 'Octobre'), ('11', 'Novembre'), ('12', 'Décembre')
    ], string="Mois", required=True)

    annee = fields.Integer(string="Année", default=lambda self: datetime.today().year)
    line_ids = fields.One2many('collecte.planning_ligne', 'planning_id', string="Lignes de planning")
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('done', 'Validé')
    ], default='draft')

    capacite_journaliere = fields.Float(string="Capacité maximale par jour", default=10000)

    def action_generer_planning(self):
        self.ensure_one()

        mois_int = int(self.mois)
        _, last_day = calendar.monthrange(self.annee, mois_int)
        all_dates = [datetime(self.annee, mois_int, day).date() for day in range(1, last_day + 1)]

        used_capacity = {date: 0 for date in all_dates}
        planning_lines = []

        contrats = self.env['collecte.contrat'].search([])

        for contrat in contrats:
            poids = contrat.quantite_previsionnelle or 0.0
            if not poids:
                continue  
            freq_par_semaine = int(contrat.nbre_passage_semaine or 1)
            freq_par_mois = freq_par_semaine * 4

            dates_possibles = sorted(all_dates, key=lambda d: used_capacity[d])

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

        # Remplacement des lignes de planning précédentes
        self.line_ids.unlink()
        self.write({
            'line_ids': planning_lines,
            'state': 'done',
        })


class CollectePlanningLigne(models.Model):
    _name = 'collecte.planning_ligne'
    _description = 'Ligne de planning de collecte'
    _order = 'date'

    planning_id = fields.Many2one('collecte.planning_mensuel', required=True, ondelete='cascade')
    date = fields.Date(string="Date", required=True)
    partner_id = fields.Many2one('res.partner', string="Client")
    contrat_id = fields.Many2one('collecte.contrat', string="Contrat")
    quantite = fields.Float(string="Quantité prévue (kg)")
