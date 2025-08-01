from odoo import models, fields, api

class RealTimeTrackingWizard(models.TransientModel):
    _name = 'wizard.traccar.realtime.tracking'
    _description = 'Assistant de Suivi Temps Réel'

    device_realtime_track_id = fields.Many2one(
        'fleet.vehicle',
        string="Appareil ID",
        required=True
    )

    def action_start_tracking(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'traccar_realtime_tracking_map',
            'params': {
                'device_id': self.device_realtime_track_id.traccar_device_id,
            }
        }
