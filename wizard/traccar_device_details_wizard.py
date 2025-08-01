from odoo import models, fields

class TraccarDeviceDetailsWizard(models.TransientModel):
    _name = 'wizard.traccar.device.details'
    _description = 'Traccar Device Details Wizard'

    device_id = fields.Char(string='Device ID')
    name = fields.Char(string='Device Name')
    status = fields.Char(string='Status')
    uniqueId = fields.Char(string='Unique ID')
    position_id = fields.Char(string='Position ID')

    driver_name = fields.Char(string='Driver')
    latitude = fields.Float()
    longitude = fields.Float()
    altitude = fields.Float()
    speed = fields.Float()
    accuracy = fields.Float()
    odometer_logs = fields.Text(string='Odometer Logs')
    distance = fields.Float(string='Distance (last trip)', digits=(6, 2))
    total_distance = fields.Float(string='Total Distance', digits=(10, 2))

