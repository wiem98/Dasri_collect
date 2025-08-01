from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CollecteContrat(models.Model):
    _name = 'collecte.contrat'
    _description = 'Contrat de collecte'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    partner_id = fields.Many2one(
        'res.partner', 
        string='Client', 
        required=True, 
        tracking=True,
        help="Client concerné par ce contrat de collecte."
    )

    type_contrat = fields.Selection([
        ('passage', 'Par Passage'),
        ('quantite', 'Par Quantité'),
    ],
        string='Type de Contrat',
        required=True,
        tracking=True,
        help="Type de facturation : soit par passage, soit par quantité collectée."
    )

    duree_marche = fields.Integer(
        string="Durée du marché",
        help="Durée totale du contrat (en fonction de l'unité sélectionnée).",
        tracking=True
    )

    unite_duree = fields.Selection([
        ('mois', 'Mois'),
        ('annees', 'Années')
    ],
        default='mois',
        string='Unité',
        required=True,
        help="Unité de durée : mois ou années."
    )

    montant_marche = fields.Float(
        string='Montant total du marché',
        tracking=True,
        help="Montant global du contrat sur toute la durée."
    )

    quantite_estimee = fields.Float(
    string='Quantité estimée à collecter (kg)',
    tracking=True,
    help="Quantité prévue dans le cadre du contrat (en kg)."
    )
    frequence_collecte = fields.Selection([
        ('1', 'Chaque jour'),
        ('2', 'Tous les 2 jours'),
        ('3', 'Tous les 3 jours'),
        ('7', 'Chaque semaine'),
        ('15', 'Tous les 15 jours'),
        ('30', 'Chaque mois'),
    ],
        string="Fréquence de collecte",
        required=True,
        tracking=True,
        help="Rythme auquel la collecte doit être effectuée."
    )

    quantite_previsionnelle = fields.Float(
        string='Quantité moyenne collectée par passage (kg)',
        compute='_compute_quantite_previsionnelle',
        store=True,
        readonly=True,
        tracking=True
    )

    prix_kg = fields.Float(
        string='Prix par kg (en TND)',
        tracking=True,
        help="Prix facturé par kilogramme collecté."
    )

    prix_par_passage = fields.Float(
        string='Prix par passage (en TND)',
        tracking=True,
        help="Montant facturé pour chaque passage de collecte."
    )

    seuil_annuel_kg = fields.Float(
        string="Seuil annuel estimé (kg)",
        tracking=True,
        help="Quantité annuelle estimée (en kg) servant de seuil avant facturation au kilo."
    )

    appliquer_tarif_surplus = fields.Boolean(
        string="Facturer le surplus au-delà du seuil ?",
        default=False,
        tracking=True,
        help="Si activé, tout dépassement du seuil annuel sera facturé au prix par kg."
    )
    nbre_passage_semaine = fields.Selection(
        selection=[
            ('1', '1 fois par semaine'),
            ('2', '2 fois par semaine'),
            ('3', '3 fois par semaine'),
            ('4', '4 fois par semaine'),
            ('5', '5 fois par semaine'),
        ],
        string='Passages par semaine',
        tracking=True
    )
    @api.depends('quantite_estimee', 'frequence_collecte', 'nbre_passage_semaine')
    def _compute_quantite_previsionnelle(self):
        for record in self:
            print("🧮 Calcul quantite_previsionnelle pour:", record.id)

            record.quantite_previsionnelle = 0.0
            if not record.quantite_estimee:
                continue

            nb_passages = 0

            if record.nbre_passage_semaine:
                try:
                    nb = int(record.nbre_passage_semaine)
                    nb_passages = nb * 4  # environ 4 semaines par mois
                except Exception:
                    pass
            elif record.frequence_collecte:
                try:
                    jours = int(record.frequence_collecte)
                    nb_passages = 30 // jours
                except Exception:
                    pass

            if nb_passages > 0:
                record.quantite_previsionnelle = record.quantite_estimee / nb_passages

    @api.onchange('quantite_estimee', 'frequence_collecte', 'nbre_passage_semaine')
    def _onchange_trigger_compute(self):
        for record in self:
            record._compute_quantite_previsionnelle()
