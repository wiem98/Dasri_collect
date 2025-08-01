from odoo import http
from odoo.http import request

class PartnerLocationController(http.Controller):

    @http.route('/update_partner_location', type='json', auth='user')
    def update_partner_location(self, partner_id, latitude, longitude):
        partner = request.env['res.partner'].browse(int(partner_id))
        if partner.exists():
            partner.write({
                'latitude': latitude,
                'longitude': longitude,
            })
            return {'status': 'success'}
        return {'status': 'error', 'message': 'Partner not found'}
    
    @http.route('/get_clients_with_location', type='json', auth='user')
    def get_clients_with_location(self):
        partners = request.env['res.partner'].sudo().search([
            ('latitude', '!=', False),
            ('longitude', '!=', False),
        ])
        return [{
            'id': p.id,
            'name': p.name,
            'latitude': p.latitude,
            'longitude': p.longitude,
            'street': p.street
        } for p in partners]