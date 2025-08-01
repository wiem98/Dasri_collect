from odoo import models, fields, api
from datetime import datetime, timedelta
import secrets


class ConvoyeurToken(models.Model):
    _name = 'collect.convoyeur.token'
    _description = 'Convoyeur Auth Token'

    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade')
    token = fields.Char('Token', required=True, index=True)
    expire_at = fields.Datetime('Expiration', required=True)

    @api.model
    def generate_token(self, user):
        # Create a secure token valid for 24 hours
        token = secrets.token_urlsafe(32)
        expire_at = datetime.utcnow() + timedelta(hours=24)

        # Remove any existing tokens for this user
        self.search([('user_id', '=', user.id)]).unlink()

        return self.create({
            'user_id': user.id,
            'token': token,
            'expire_at': expire_at,
        })
