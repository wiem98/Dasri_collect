from odoo import api, models, fields
import requests
import random
from datetime import datetime, timezone, timedelta

class CollectVehicle(models.Model):
    _inherit = 'fleet.vehicle'


    capacity_kg = fields.Float(
        string="Capacité (kg)",
        digits=(10, 2),
        help="Charge utile maximale que le véhicule peut transporter."
    )

    traccar_device_id = fields.Char(string='Traccar Device ID', required=False)
    traccar_name = fields.Char(string='Device Name')
    traccar_status = fields.Char(string='Status')
    traccar_unique_id = fields.Char(string='Unique ID')
    traccar_position_id = fields.Char(string='Position ID')

    traccar_driver_name = fields.Char(string='Driver Name')
    traccar_latitude = fields.Float()
    traccar_longitude = fields.Float()
    traccar_altitude = fields.Float()
    traccar_speed = fields.Float()
    traccar_accuracy = fields.Float()
    traccar_distance = fields.Float(string='Distance (last trip)', digits=(6, 2))
    traccar_total_distance = fields.Float(string='Total Distance', digits=(10, 2))


    @api.onchange('traccar_unique_id')
    def _onchange_generate_unique_id(self):
        if not self.traccar_unique_id:
            existing_ids = self.search_read([], ['traccar_unique_id'])
            existing_unique_ids = {rec['traccar_unique_id'] for rec in existing_ids if rec['traccar_unique_id']}

            new_unique_id = None
            for _ in range(10):  # Try up to 10 times
                candidate = str(random.randint(10000000, 99999999))
                if candidate not in existing_unique_ids:
                    new_unique_id = candidate
                    break

            if not new_unique_id:
                raise ValueError("Unable to generate a unique ID. Please try again.")

            self.traccar_unique_id = new_unique_id

    def update_tracking_info(self):
        url = "https://demo4.traccar.org/api/positions"
        auth = ('pprologic138@gmail.com', 'oumaima123@')

        try:
            response = requests.get(url, auth=auth)
            response.raise_for_status()
            positions = response.json()
            for position in positions:
                vehicle = self.search([('traccar_device_id', '=', str(position['deviceId']))], limit=1)
                if vehicle:
                    vehicle.write({
                        'traccar_latitude': position.get('latitude'),
                        'traccar_longitude': position.get('longitude'),
                        'traccar_speed': position.get('speed'),
                    })
        except Exception as e:
            raise Exception(f"Error while updating tracking info: {e}")

    @staticmethod
    def compute_device_status(device):
        last_update_str = device.get('lastUpdate')
        if not last_update_str:
            return 'offline'
        try:
            if last_update_str.endswith('Z'):
                last_update = datetime.strptime(last_update_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            else:
                last_update = datetime.fromisoformat(last_update_str)
                if last_update.tzinfo is None:
                    last_update = last_update.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            delta = now - last_update

            if delta < timedelta(minutes=5):
                return 'online'
            else:
                return f"last seen {int(delta.total_seconds() // 60)} mins ago"

        except Exception as e:
            return f"unknown ({str(e)})"

    def action_sync_traccar_device(self):
        self.ensure_one()

        url = "https://demo4.traccar.org/api/devices"
        auth = ('pprologic138@gmail.com', 'oumaima123@')
        headers = {'Content-Type': 'application/json'}

        try:
            # Step 1: Get all devices
            response = requests.get(url, auth=auth)
            response.raise_for_status()
            devices = response.json()

            # Step 2: Check if device already exists using our uniqueId
            device = next((d for d in devices if d['uniqueId'] == self.traccar_unique_id), None)

            # Step 3: Create device in Traccar if not exists
            if not device:
                if not self.traccar_unique_id:
                    raise ValueError("Unique ID is required to sync with Traccar.")

                payload = {
                    "name": self.name,
                    "uniqueId": self.traccar_unique_id,
                }
                create_response = requests.post(url, auth=auth, headers=headers, json=payload)
                if create_response.status_code in [200, 201]:
                    device = create_response.json()
                    self.traccar_device_id = str(device['id'])
                else:
                    raise Exception(f"Failed to create device in Traccar. Error: {create_response.text}")
            else:
                self.traccar_device_id = str(device['id'])

            # Step 4: Fetch device details
            device_url = f"https://demo4.traccar.org/api/devices/{self.traccar_device_id}"
            device_response = requests.get(device_url, auth=auth)
            device_response.raise_for_status()
            device = device_response.json()
            position_id = device.get('positionId')

            # Step 5: Fetch latest position
            latitude = longitude = altitude = speed = accuracy = 0.0
            distance = total_distance = 0.0

            if position_id:
                pos_url = f"https://demo4.traccar.org/api/positions?deviceId={device['id']}"
                positions = requests.get(pos_url, auth=auth).json()
                if positions:
                    pos_data = positions[0]
                    latitude = pos_data.get('latitude')
                    longitude = pos_data.get('longitude')
                    altitude = pos_data.get('altitude')
                    speed = pos_data.get('speed')
                    accuracy = pos_data.get('accuracy')

                    attributes = pos_data.get('attributes', {})
                    distance = round(attributes.get('distance', 0.0) / 1000, 2)
                    total_distance = round(attributes.get('totalDistance', 0.0) / 1000, 2)

                    odometer_m = attributes.get('odometer')
                    if odometer_m:
                        self.env['fleet.vehicle.odometer'].create({
                            'vehicle_id': self.id,
                            'value': round(odometer_m / 1000, 2),
                            'unit': 'kilometers',
                            'date': fields.Datetime.now(),
                        })

            # Step 6: Final write (DO NOT overwrite your original unique ID!)
            self.write({
                'traccar_name': device.get('name'),
                'traccar_status': self.compute_device_status(device),
                'traccar_position_id': str(position_id) if position_id else '',
                'traccar_driver_name': self.driver_id.name,
                'traccar_latitude': latitude,
                'traccar_longitude': longitude,
                'traccar_altitude': altitude,
                'traccar_speed': speed,
                'traccar_accuracy': accuracy,
                'traccar_distance': distance,
                'traccar_total_distance': total_distance,
            })

        except Exception as e:
            raise Exception(f"Error syncing with Traccar: {str(e)}")



class FleetVehicleModel(models.Model):
    _inherit = 'fleet.vehicle.model'

    vehicle_type = fields.Selection(
        selection_add=[('truck', 'Truck')],
        default='truck',
        tracking=True,
        ondelete={'truck': 'set default'},
    )