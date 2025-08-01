from odoo import fields, models


class ConfirmationWizard(models.TransientModel):
    _name = 'confirmation.wizard'
    _description = 'Deletion Confirmation'
    
    message = fields.Text('Confirmation Message')
    
    def action_confirm(self):
        convoyeur_ids = self.env.context.get('convoyeur_ids', [])
        if convoyeur_ids:
            self.env['collect.convoyeur'].with_context(
                bypass_confirmation=True
            ).browse(convoyeur_ids).unlink()
        return {'type': 'ir.actions.act_window_close'}