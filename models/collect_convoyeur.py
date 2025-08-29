from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import random
import string
import logging

_logger = logging.getLogger(__name__)

class Convoyeur(models.Model):
    _name = 'collect.convoyeur'
    _description = 'Convoyeur'
    _inherit = ['mail.thread']
    _sql_constraints = [
        ('num_unique_uniq', 'unique(num_unique)', 'Identifiant unique déjà existant.')
    ]


    name = fields.Char(string="Nom complet", required=True)
    user_type = fields.Selection([
        ('driver', 'Chauffeur'),
        ('convoyeur', 'Convoyeur')
    ], string="Type d'utilisateur", default='convoyeur', required=True, tracking=True)

    num_unique = fields.Char(
        string='Identifiant Unique',
        required=True,
        copy=False,
        index=True,
        default=lambda self: self._generate_num_unique()
    )


    job_title = fields.Char(string="Poste", readonly=True)
    phone = fields.Char(string="Téléphone Professionnel")
    mobile = fields.Char(string="Mobile Professionnel")
    email = fields.Char(string="Email Professionnel", required=True)
    user_id = fields.Many2one('res.users', string="Utilisateur associé", ondelete="cascade")
    address = fields.Text(
        string="Adresse au Travail",
        default=lambda self: self._get_formatted_company_address()
    )

    # private info
    private_street = fields.Char(string="Rue")
    private_street2 = fields.Char(string="Rue2")
    private_city = fields.Char(string="Ville")
    private_state_id = fields.Many2one(
        "res.country.state", string="État",
        domain="[('country_id', '=?', private_country_id)]")
    private_zip = fields.Char(string="Code Postal")
    private_country_id = fields.Many2one("res.country", string="Pays")
    private_phone = fields.Char(string="Téléphone")
    private_email = fields.Char(string="Email")
    country_id = fields.Many2one(
        'res.country', 'Nationalité (Pays)', tracking=True)
    gender = fields.Selection([
        ('male', 'Mâle'),
        ('female', 'Femelle'),
    ], tracking=True)
    marital = fields.Selection(
        selection='_get_marital_status_selection',
        string='État civil',
        
        default='single',
        required=True,
        tracking=True)
    children = fields.Integer(string='Nombre d\'enfants', tracking=True)
    place_of_birth = fields.Char('Lieu de naissance', tracking=True)
    birthday = fields.Date('Date de naissance', tracking=True)
    permis_no = fields.Char('Permis No', tracking=True)
    permis_expire = fields.Date('Date d’expiration du permis', tracking=True)
    additional_note = fields.Text(string='Additional Note', tracking=True)
    has_conduire_permis = fields.Binary(string="Permis de conduire")
    profile_image = fields.Binary(string="Profile Image", attachment=True)
    parent_id = fields.Many2one('hr.employee', 'Manager', store=True, readonly=False)
    

    def _get_marital_status_selection(self):
        return [
                ('single', _('Célibataire')),
                ('married', _('Marié')),
                ('widower', _('Veuf')),
                ('divorced', _('Divorcé')),
        ]
    @api.constrains('email')
    def _check_email(self):
        """Validate email format"""
        for record in self:
            if not record.email or '@' not in record.email:
                raise ValidationError(_("Veuillez entrer une adresse email valide (format: user@example.com)"))
    
    def _generate_password(self):
        """Generate a secure 12-character password"""
        chars = string.ascii_letters + string.digits + '!@$%^&'
        return ''.join(random.SystemRandom().choice(chars) for _ in range(12))
    
    def _prepare_user_vals(self, password):
        """Prepare values for user creation"""
        return {
            'name': self.name,
            'login': self.email,
            'password': password,
            'groups_id': [(6, 0, [self.env.ref('collecte_module.group_convoyeur').id])],
            'email': self.email,
            'phone': self.phone,
            'notification_type': 'email',
            'share': False,
        }
    
    def _check_email_configuration(self):
        """Verify all required email parameters are set"""
        if not self.env['ir.mail_server'].search([], limit=1):
            raise UserError(_("No outgoing mail server configured - please contact your administrator"))
        return True
    
    def _send_credentials_email(self, password):
        """Send convoyeur credentials email with multiple fallbacks"""
        self.ensure_one()
        
        try:
            self._check_email_configuration()
            
            # Get mail server and default from address
            mail_server = self.env['ir.mail_server'].search([], limit=1)
            email_from = self.env['ir.config_parameter'].get_param('mail.default.from') or \
                       f'"{self.env.user.company_id.name}" <noreply@{self.env.user.company_id.name.lower().replace(" ", "-")}.com>'

            # Prepare email body
            body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <p style="font-size: 16px;">Bonjour {self.name},</p>
                
                <p style="font-size: 14px;">Votre compte convoyeur a été créé avec succès.</p>
                
                <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <p style="font-weight: bold; margin-bottom: 5px;">Vos informations de connexion :</p>
                    <ul style="margin: 0; padding-left: 20px;">
                        <li><strong>Email :</strong> {self.email}</li>
                        <li><strong>Mot de passe :</strong> {password}</li>
                    </ul>
                </div>
                
                <p style="font-size: 14px; margin-top: 20px;">Cordialement,</p>
                <p style="font-size: 14px; font-weight: bold;">L'équipe de collecte</p>
            </div>
            """
            
            # Create and send mail directly
            mail = self.env['mail.mail'].sudo().create({
                'body_html': body,
                'subject': _("Vos identifiants de convoyeur"),
                'email_to': self.email,
                'email_from': email_from,
                'reply_to': email_from,
                'mail_server_id': mail_server.id,
            })
            
            mail.send(auto_commit=True)
            _logger.info("Credentials email sent to %s", self.email)
            return True
            
        except Exception as e:
            _logger.error("Failed to send credentials email to %s: %s", self.email, str(e))
            raise UserError(_("Failed to send email. Please check your email configuration."))
    
    @api.model_create_multi
    def create(self, vals_list):
        """Create convoyeur with associated user and send credentials"""
        # Map user_type values to job titles
        user_type_to_title = dict(self._fields['user_type'].selection)

        # Inject job_title into each vals dict based on user_type
        for vals in vals_list:
            if 'user_type' in vals:
                vals['job_title'] = user_type_to_title.get(vals['user_type'], 'Convoyeur')  # Fallback default

        convoyeurs = super(Convoyeur, self).create(vals_list)
        
        for convoyeur in convoyeurs:
            if not convoyeur.email:
                _logger.warning("Skipping email for convoyeur %s - no email provided", convoyeur.name)
                continue
                
            try:
                # Generate password
                password = convoyeur._generate_password()
                
                # Create user
                user = self.env['res.users'].with_context(
                    no_reset_password=True,
                    create_user=True
                ).create(convoyeur._prepare_user_vals(password))
                
                convoyeur.write({'user_id': user.id})
                
                # Send credentials email
                convoyeur._send_credentials_email(password)
                
            except Exception as e:
                _logger.error("Error processing convoyeur %s: %s", convoyeur.name, str(e))
                # Continue with next record even if this one fails
        
        return convoyeurs
    
    def write(self, vals):
        """Ensure job title is synced on user_type change"""
        if 'user_type' in vals:
            vals['job_title'] = dict(self._fields['user_type'].selection).get(vals['user_type'])
        return super().write(vals)
    
    @api.model
    def _generate_num_unique(self):
        """Generate a unique identifier """
        while True:
            code = 'N' + ''.join(random.choices(string.digits, k=6))
            if not self.search([('num_unique', '=', code)]):
                return code
 
    @api.constrains('email')
    def _check_unique_email(self):
        for record in self:
            if record.email:
                duplicates = self.search([
                    ('email', '=', record.email),
                    ('id', '!=', record.id)
                ], limit=1)
                if duplicates:
                    raise ValidationError(_("L'adresse email '%s' est déjà utilisée. Veuillez en choisir une autre.") % record.email)

    @api.constrains('num_unique')
    def _check_unique_num_unique(self):
        for record in self:
            if record.num_unique:
                duplicates = self.search([
                    ('num_unique', '=', record.num_unique),
                    ('id', '!=', record.id)
                ], limit=1)
                if duplicates:
                    raise ValidationError(_("L'identifiant unique '%s' existe déjà. Veuillez réessayer.") % record.num_unique)

    def _get_formatted_company_address(self):
        company = self.env.user.company_id
        street = company.street or ''
        state = company.state_id.name or ''
        city = company.city or ''
        
        # Remove empty parts and join with commas
        parts = [part for part in [street, state, city] if part]
        return ', '.join(parts)


class ResUsers(models.Model):
    _inherit = 'res.users'

    must_change_password = fields.Boolean(string="Must Change Password", default=True)