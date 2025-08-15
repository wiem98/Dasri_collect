from odoo import models, fields, api
import requests
import logging
_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    latitude = fields.Float('Latitude', digits=(16, 5))
    longitude = fields.Float('Longitude', digits=(16, 5))
    type_client = fields.Selection([
        ('etatique', 'Etatique'),
        ('prive', 'Privé'),
    ], string='Type Client')

    zone = fields.Selection([
        ('ariana', 'Ariana'),
        ('beja', 'Béja'),
        ('ben_arous', 'Ben Arous'),
        ('bizerte', 'Bizerte'),
        ('gabes', 'Gabès'),
        ('gafsa', 'Gafsa'),
        ('jendouba', 'Jendouba'),
        ('kairouan', 'Kairouan'),
        ('kasserine', 'Kasserine'),
        ('kebili', 'Kébili'),
        ('kef', 'Le Kef'),
        ('mahdia', 'Mahdia'),
        ('manouba', 'La Manouba'),
        ('medenine', 'Médenine'),
        ('monastir', 'Monastir'),
        ('nabeul', 'Nabeul'),
        ('sfax', 'Sfax'),
        ('sidi_bouzid', 'Sidi Bouzid'),
        ('siliana', 'Siliana'),
        ('sousse', 'Sousse'),
        ('tataouine', 'Tataouine'),
        ('tozeur', 'Tozeur'),
        ('tunis', 'Tunis'),
        ('zaghouan', 'Zaghouan'),
    ], string='Gouvernorat', index=True, tracking=True, help="Gouvernorat (zone) du partenaire")
    distance_from_origin = fields.Float(
        string="Distance routière (km)",
        compute="_calculate_distance",
            store=True,

    )
    type_contrat = fields.Selection([
        ('passage', 'Par Passage'),
        ('quantite', 'Par Quantité'),
    ],
        string='Type de Contrat',
        required=True,
        tracking=True,
        help="Type de facturation : soit par passage, soit par quantité collectée."
    )

    duree_marche = fields.Integer(
        string="Durée du marché",
        help="Durée totale du contrat (en fonction de l'unité sélectionnée).",
        tracking=True
    )

    unite_duree = fields.Selection([
        ('mois', 'Mois'),
        ('annees', 'Années')
    ],
        default='mois',
        string='Unité',
        required=True,
        help="Unité de durée : mois ou années."
    )

    montant_marche = fields.Float(
        string='Montant total du marché',
        tracking=True,
        help="Montant global du contrat sur toute la durée."
    )

    quantite_estimee = fields.Float(
    string='Quantité estimée à collecter (kg)',
    tracking=True,
    help="Quantité prévue dans le cadre du contrat (en kg)."
    )
    frequence_collecte = fields.Selection([
        ('1', 'Chaque jour'),
        ('2', 'Tous les 2 jours'),
        ('3', 'Tous les 3 jours'),
        ('7', 'Chaque semaine'),
        ('15', 'Tous les 15 jours'),
        ('30', 'Chaque mois'),
    ],
        string="Fréquence de collecte",
        required=True,
        tracking=True,
        help="Rythme auquel la collecte doit être effectuée."
    )

    quantite_previsionnelle = fields.Float(
        string='Quantité moyenne collectée par passage (kg)',
        compute='_compute_quantite_previsionnelle',
        store=True,
        readonly=True,
        tracking=True
    )

    prix_kg = fields.Float(
        string='Prix par kg (en TND)',
        tracking=True,
        help="Prix facturé par kilogramme collecté."
    )

    prix_par_passage = fields.Float(
        string='Prix par passage (en TND)',
        tracking=True,
        help="Montant facturé pour chaque passage de collecte."
    )

    seuil_annuel_kg = fields.Float(
        string="Seuil annuel estimé (kg)",
        tracking=True,
        help="Quantité annuelle estimée (en kg) servant de seuil avant facturation au kilo."
    )

    appliquer_tarif_surplus = fields.Boolean(
        string="Facturer le surplus au-delà du seuil ?",
        default=False,
        tracking=True,
        help="Si activé, tout dépassement du seuil annuel sera facturé au prix par kg."
    )
    nbre_passage_semaine = fields.Selection(
        selection=[
            ('1', '1 fois par semaine'),
            ('2', '2 fois par semaine'),
            ('3', '3 fois par semaine'),
            ('4', '4 fois par semaine'),
            ('5', '5 fois par semaine'),
        ],
        string='Passages par semaine',
        tracking=True
    )
    jour_fixe = fields.Selection(
        selection=[
            ('lundi', 'Lundi'),
            ('mardi', 'Mardi'),
            ('mercredi', 'Mercredi'),
            ('jeudi', 'Jeudi'),
            ('vendredi', 'Vendredi'),
            ('samedi', 'Samedi'),
            ('dimanche', 'Dimanche'),
        ],
        string='Jour fixe de collecte',
        tracking=True,
        help="Jour fixe de collecte "
    )
    @api.depends('quantite_estimee', 'frequence_collecte', 'nbre_passage_semaine')
    def _compute_quantite_previsionnelle(self):
        for record in self:
            print("🧮 Calcul quantite_previsionnelle pour:", record.id)

            record.quantite_previsionnelle = 0.0
            if not record.quantite_estimee:
                continue

            nb_passages = 0

            if record.nbre_passage_semaine:
                try:
                    nb = int(record.nbre_passage_semaine)
                    nb_passages = nb * 4  # environ 4 semaines par mois
                except Exception:
                    pass
            elif record.frequence_collecte:
                try:
                    jours = int(record.frequence_collecte)
                    nb_passages = 30 // jours
                except Exception:
                    pass

            if nb_passages > 0:
                record.quantite_previsionnelle = record.quantite_estimee / nb_passages

    @api.onchange('quantite_estimee', 'frequence_collecte', 'nbre_passage_semaine')
    def _onchange_trigger_compute(self):
        for record in self:
            record._compute_quantite_previsionnelle()

    # Your origin coordinates:
    ORIGIN_LAT = 36.37065151015154
    ORIGIN_LON = 9.111696141592383
    ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjMxMzdlMmE5MjRlZjQ2OWFiN2QzYzM0OWM1ZjBmOWIzIiwiaCI6Im11cm11cjY0In0="
    @api.depends('latitude', 'longitude')
    def _calculate_distance(self):
        origin_lat = self.ORIGIN_LAT
        origin_lon = self.ORIGIN_LON

        url = "https://api.openrouteservice.org/v2/matrix/driving-car"
        headers = {
            'Authorization': self.ORS_API_KEY,
            'Content-Type': 'application/json'
        }

        valid_partners = self.filtered(lambda p: p.latitude and p.longitude)
        if not valid_partners:
            for partner in self:
                partner.distance_from_origin = 0.0
            return

        destinations = []
        partner_map = {}
        for idx, partner in enumerate(valid_partners):
            try:
                lat = float(str(partner.latitude).replace(',', '.'))
                lon = float(str(partner.longitude).replace(',', '.'))
                destinations.append([lon, lat])
                partner_map[idx] = partner
            except Exception as e:
                _logger.error(f"[DISTANCE] Failed to parse coordinates for {partner.name}: {e}")
                partner.distance_from_origin = 0.0

        payload = {
            "locations": [[origin_lon, origin_lat]] + destinations,
            "sources": [0],
            "destinations": list(range(1, len(destinations) + 1)),
            "metrics": ["distance"],
            "units": "km"
        }

        try:
            _logger.info(f"[DISTANCE] Sending matrix payload to ORS API: {payload}")
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            distances = data.get("distances", [[]])[0]

            for i, dist in enumerate(distances):
                partner = partner_map.get(i)
                if partner:
                    partner.distance_from_origin = round(dist, 2)
                    _logger.info(f"[DISTANCE] Distance to {partner.name}: {dist:.2f} km")

        except Exception as e:
            _logger.error(f"[DISTANCE] Matrix API call failed: {str(e)}", exc_info=True)
            for partner in valid_partners:
                partner.distance_from_origin = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        for partner in partners:
            partner._calculate_distance()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if 'latitude' in vals or 'longitude' in vals:
            for partner in self:
                partner._calculate_distance()
        return res
        
    
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




