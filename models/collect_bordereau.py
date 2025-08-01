# collect/models/collect_bordereau.py

from odoo import api, models, fields
from odoo.exceptions import ValidationError

STATE_BORDEREAU = [
    ("draft", "Brouillon"),
    ("producteur_signed", "Signé par le Producteur"),
    ("transporteur_signed", "Signé par le Transporteur"),
    ("operateur_signed", "Signé par l’Opérateur"),
    ("done", "Terminé"),
    ("cancelled", "Annulé"),
    ("active", "Actif"),
]

STATE_NUMBER = [
    ("draft", "Brouillon"),
    ("active", "Actif"),
    ("done", "Terminé"),
    ("cancelled", "Annulé"),
]


class CollectBordereau(models.Model):
    _name = "collect.bordereau"
    _description = "Bordereau de Suivi de Déchets Dangereux"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="Référence", copy=False, readonly=True, default="Nouveau"
    )
    state = fields.Selection(
        selection=STATE_BORDEREAU,
        string="Status",
        default="draft",
        tracking=True,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nouveau") == "Nouveau":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("collect.bordereau") or "/"
                )
        return super().create(vals_list)

    partner_id = fields.Many2one(
        "res.partner",
        string="Nom de l'entreprise",
        domain="[('function', '=', 'Client')]"
    )

    num_registre = fields.Many2one(
        "collect.numero.registre", string="Numéro", required=True
    )

    denomination_dechet = fields.Text(string="Dénomination du Déchet", default="DASRI")

    # Conteneurs
    conteneur_line_ids = fields.One2many(
        "collect.conteneur.line", "bordereau_id", string="Conteneurs"
    )

    # Collecteurs
    collecteur_line_ids = fields.One2many(
        "collect.collecteur.line", "bordereau_id", string="Collecteurs d’aiguilles"
    )

    immatriculation = fields.Char(string="Immatriculation")
    poids_facture = fields.Float(string="Poids Facturé (kg)")

    # Producteur
    producteur_num = fields.Char(string="N° Unique du Producteur")
    producteur_heure = fields.Char(string="Heure")
    producteur_date_enlevement = fields.Date(string="Date d'enlèvement")
    producteur_info = fields.Text(string="Nom, Adresse de l'Entreprise")

    # Transporteur
    transporteur_id = fields.Many2one(
        "collect.convoyeur", string="Transporteur", required=True
    )
    transporteur_num = fields.Char(string="N° Unique du Transporteur")
    transporteur_heure = fields.Char(string="Heure")
    transporteur_date_prise = fields.Date(string="Date de Prise en charge")
    transporteur_info = fields.Text(string="Nom, Adresse de l'Entreprise")

    # Opérateur
    operateur_num = fields.Char(string="N° Unique de l'Opérateur")
    operateur_heure = fields.Char(string="Heure")
    operateur_date_reception = fields.Date(string="Date de Réception")
    operateur_info = fields.Text(string="Nom, Adresse de l'Entreprise")

    observations = fields.Text(string="Observations")

    signature_producteur = fields.Binary(string="Signature Producteur")
    signature_transporteur = fields.Binary(string="Signature Transporteur")
    signature_operateur = fields.Binary(string="Signature Opérateur")
    group = fields.Many2one("collect.numero.registre", string="Groupe", readonly=True)


    def action_sign_producteur(self):
        for record in self:
            if record.signature_producteur:
                record.state = "producteur_signed"

    def action_sign_transporteur(self):
        for record in self:
            if record.signature_transporteur:
                record.state = "transporteur_signed"

    def action_sign_operateur(self):
        for record in self:
            if record.signature_operateur:
                record.state = "operateur_signed"

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id:
            name = self.partner_id.name or ""
            street = self.partner_id.street or ""
            city = self.partner_id.city or ""
            self.producteur_info = f"{name}, {street} {city}".strip().strip(",")


class RegistreNumber(models.Model):
    _name = "collect.numero.registre"
    _description = "Numéro de Registre de bordereau de suivi de déchets dangereux"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Référence", readonly=True)
    numero = fields.Char(string="Numéro", required=True)
    description = fields.Text(string="Description")
    nbr_copie = fields.Integer(string="Nombre de copies", default=30)
    user_id = fields.Many2one("collect.convoyeur", string="Personnel")
    state = fields.Selection(
        selection=STATE_NUMBER, string="Status", default="draft", tracking=True, readonly=True,
    )

    group = fields.Many2one(
        "collect.numero.registre", string="Groupe", ondelete="cascade"
    )
    is_generated = fields.Boolean(
        string="Généré automatiquement", default=False, readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        created_records = self.env["collect.numero.registre"]

        for vals in vals_list:
            start_number_str = vals.get("numero")
            nbr_copie = vals.get("nbr_copie", 30)

            # Validate: numero must be a numeric string (e.g., "00454")
            if not start_number_str or not start_number_str.isdigit():
                raise ValidationError("Le numéro de départ doit être un nombre valide.")

            start_number = int(start_number_str)
            num_length = len(start_number_str)  # <- preserve leading zero length

            def format_num(num):
                return f"NR{str(num).zfill(num_length)}"

            # Step 1: Create parent record
            parent_vals = {
                "numero": start_number_str,  # Keep original string with leading zeros
                "name": format_num(start_number),
                "description": vals.get("description"),
                "user_id": vals.get("user_id"),
                "nbr_copie": nbr_copie,
                "state": vals.get("state", "draft"),
                "is_generated": False,
            }
            parent_record = super().create(parent_vals)
            created_records |= parent_record

            # Step 2: Set group to self
            parent_record.group = parent_record.id

            # Step 3: Create children
            for i in range(1, nbr_copie):
                current_num = start_number + i
                child_vals = {
                    "numero": str(current_num).zfill(num_length),  # preserve leading zeros
                    "name": format_num(current_num),
                    "description": parent_record.description,
                    "user_id": parent_record.user_id.id,
                    "group": parent_record.id,
                    "state": vals.get("state", "draft"),
                    "is_generated": True,
                }
                created_records |= super().create(child_vals)

        return created_records


    """ def action_activate(self):
        for rec in self:
            if rec.state != "draft":
                continue

            # Get all records in the group (parent + children)
            group_members = self.env['collect.numero.registre'].search([('group', '=', rec.group.id)])

            for reg in group_members:
                # Prevent duplicates
                existing_bordereau = self.env['collect.bordereau'].search([('num_registre', '=', reg.id)], limit=1)
                if not existing_bordereau:
                    self.env['collect.bordereau'].create({
                        'num_registre': reg.id,
                        'group': rec.group.id,
                    })

            # Finally, update state for the group
            group_members.write({'state': 'active'}) """

    def action_activate(self):
        for rec in self:
            if rec.state != "draft":
                continue

            # Update state
            rec.write({"state": "active"})
            rec.mapped("group").write({"state": "active"})

            # Create Bordereaux
            bordereaux = []
            all_registres = self.search([("group", "=", rec.group.id)])
            for registre in all_registres:
                bordereaux.append({
                    "num_registre": registre.id,
                    "group": rec.group.id,
                    "transporteur_id": rec.user_id.id,
                })

            self.env["collect.bordereau"].create(bordereaux)

    def action_cancel(self):
        for rec in self:
            all_related = self.env['collect.numero.registre'].search([('group', '=', rec.group.id)])
            (rec | all_related).write({'state': 'cancelled'})

    def action_draft(self):
        for rec in self:
            all_related = self.env['collect.numero.registre'].search([('group', '=', rec.group.id)])
            (rec | all_related).write({'state': 'draft'})

    def action_done(self):
        for rec in self:
            all_related = self.env['collect.numero.registre'].search([('group', '=', rec.group.id)])
            (rec | all_related).write({'state': 'done'})
