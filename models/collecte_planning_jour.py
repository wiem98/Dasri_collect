from odoo import models, fields, api

class DailyVehiclePlanning(models.Model):
    _name = 'collecte.planning_journalier'
    _description = 'Planification journalière par véhicule'

    date = fields.Date(required=True)
        
    vehicle_id = fields.Many2one('fleet.vehicle', string="Véhicule")
    ligne_ids = fields.One2many('collecte.planning_journalier_ligne', 'planning_id', string="Destinations")
    total_quantite = fields.Float(string="Quantité totale (kg)", compute="_compute_total")
    partner_id = fields.Many2one('res.partner', string="Client")
    
    latitude = fields.Float(related='partner_id.latitude', store=True)
    longitude = fields.Float(related='partner_id.longitude', store=True)

    @api.depends('ligne_ids.quantite_collectee')
    def _compute_total(self):
        for rec in self:
            rec.total_quantite = sum(l.quantite_collectee for l in rec.ligne_ids)
    
    def action_planifier_auto(self):
        for rec in self:
            # Exemple de logique de remplissage automatique
            clients = self.env['res.partner'].search([('is_company', '=', True)], limit=5)
            lignes = []
            for client in clients:
                lignes.append((0, 0, {
                    'partner_id': client.id,
                    'adresse': client.street or '',
                    'quantite_collectee': 0.0,
                    'latitude': client.partner_latitude,
                    'longitude': client.partner_longitude,
                }))
            rec.ligne_ids = lignes

class DailyVehiclePlanningLine(models.Model):
    _name = 'collecte.planning_journalier_ligne'
    _description = 'Destination journalière'

    planning_id = fields.Many2one('collecte.planning_journalier', ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string="Client")
    adresse = fields.Char()
    quantite_collectee = fields.Float()
    latitude = fields.Float()
    longitude = fields.Float()
    ordre = fields.Integer()
    vehicle_id = fields.Many2one('fleet.vehicle', string="Véhicule")
