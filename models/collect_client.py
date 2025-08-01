from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    latitude = fields.Float('Latitude', digits=(16, 5))
    longitude = fields.Float('Longitude', digits=(16, 5))
    type_client = fields.Selection([
        ('etatique', 'Etatique'),
        ('prive', 'Privé'),
    ], string='Type Client')

    contrat_ids = fields.One2many('collecte.contrat', 'partner_id', string="Contrats de collecte")

    def action_view_contrats(self):
        self.ensure_one()
        action = self.env.ref('collecte_module.action_collecte_contrat').read()[0]
        action['domain'] = [('partner_id', '=', self.id)]
        if len(self.contrat_ids) == 1:
            action['views'] = [(self.env.ref('collecte_module.view_collecte_contrat_form').id, 'form')]
            action['res_id'] = self.contrat_ids.id
        return action

    def action_get_geolocation(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'client_position_map',
            'params': {
                'partner_id': self.id,
                'latitude': self.latitude,
                'longitude': self.longitude,
            }
        }




