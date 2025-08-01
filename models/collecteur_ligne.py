from odoo import models, fields


class CollecteurLine(models.Model):
    _name = "collect.collecteur.line"
    _description = "Ligne de Collecteur d’aiguilles"

    bordereau_id = fields.Many2one("collect.bordereau", string="Bordereau", required=True, ondelete="cascade")

    type = fields.Selection([
        ('2', '2 L'),
        ('3', '3 L'),
        ('5', '5 L'),
        ('12', '12 L'),
    ], string="Type de Collecteur", required=True)

    quantite = fields.Integer(string="Quantité", required=True)
