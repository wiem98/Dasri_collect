import logging
from odoo import models, fields, api
from datetime import datetime, timedelta

from odoo.exceptions import UserError

class TraccarTrackHistoryWizard(models.TransientModel):
    _name = 'wizard.traccar.track.history'
    _description = 'Traccar History Viewer'

    vehicle_id = fields.Many2one('fleet.vehicle', string="Device", required=True)
    period = fields.Selection([
        ('today', "Aujourd'hui"),
        ('yesterday', "Hier"),
        ('last_7_days', "7 derniers jours"),
        ('custom', "Personnalisé"),
    ], default='today')
    date_from = fields.Datetime(string="Date de début")
    date_to = fields.Datetime(string="Date de fin")

    @api.onchange('period')
    def _onchange_period(self):
        now = fields.Datetime.now()
        if self.period == 'today':
            self.date_from = datetime.combine(now.date(), datetime.min.time())
            self.date_to = now
        elif self.period == 'yesterday':
            yesterday = now - timedelta(days=1)
            self.date_from = datetime.combine(yesterday.date(), datetime.min.time())
            self.date_to = datetime.combine(yesterday.date(), datetime.max.time())
        elif self.period == 'last_7_days':
            self.date_from = now - timedelta(days=7)
            self.date_to = now

    def action_show_track(self):
        logger = logging.getLogger(name_)

        return {
            'type': 'ir.actions.client',
            'tag': 'traccar_history_map',
            'params': {
                'device_id': self.vehicle_id.traccar_device_id,
                'date_from': self.date_from.isoformat() if self.date_from else '',
                'date_to': self.date_to.isoformat() if self.date_to else '',
            }
        }