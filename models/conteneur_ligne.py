from odoo import models, fields


class ConteneurLine(models.Model):
    _name = "collect.conteneur.line"
    _description = "Ligne de Conteneur"

    bordereau_id = fields.Many2one("collect.bordereau", string="Bordereau", required=True, ondelete="cascade")

    type = fields.Selection([
        ('120', 'Cont 120L'),
        ('240', 'Cont 240L'),
        ('360', 'Cont 360L'),
    ], string="Type de Conteneur", required=True)

    quantite = fields.Integer(string="Quantité", required=True)
