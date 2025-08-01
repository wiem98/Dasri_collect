from odoo import fields, http
from odoo.exceptions import AccessDenied
from odoo.http import Response, request
import json
import logging

_logger = logging.getLogger(__name__)

class AuthController(http.Controller):

    def _add_cors_headers(self, response):
        """Add CORS headers to the response."""
        response.headers.update({
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '86400',
        })
        return response

    """ @http.route('/api/convoyeur/login', type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def options_login(self, **kwargs):
        response = Response("", content_type='text/plain', status=200)
        return self._add_cors_headers(response) """


    @http.route('/api/convoyeur/login', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False)
    def convoyeur_login(self, **kwargs):
        # Handle CORS preflight (OPTIONS request)
        if request.httprequest.method == 'OPTIONS':
            return self._add_cors_headers(Response(status=200))
    
        try:
            raw_data = request.httprequest.data
            if not raw_data:
                raise ValueError("Empty request body")

            data = json.loads(raw_data.decode('utf-8'))
            email = data.get('email')
            password = data.get('password')

            if not email or not password:
                return self._add_cors_headers(Response(
                    json.dumps({"error": "Email and password are required."}),
                    content_type='application/json',
                    status=400
                ))

            # Prepare authentication parameters
            credentials = {
                'type': 'password',
                'login': email,
                'password': password
            }
            user_agent_env = {
                'base_location': request.httprequest.host_url.rstrip('/'),
                'interactive': False,
            }

            # Authenticate user using Odoo's built-in method
            auth_info = request.env['res.users'].sudo().authenticate(
                request.db, credentials, user_agent_env
            )

            user_id = auth_info.get('uid')
            if not user_id:
                raise AccessDenied("Authentication failed.")

            # Load user and convoyeur
            user = request.env['res.users'].sudo().browse(user_id)
            convoyeur = request.env['collect.convoyeur'].sudo().search([('user_id', '=', user.id)], limit=1)

            if not convoyeur:
                return self._add_cors_headers(Response(
                    json.dumps({"error": "User is not a registered convoyeur."}),
                    content_type='application/json',
                    status=403
                ))

            # Generate token
            token = request.env['collect.convoyeur.token'].sudo().generate_token(user)

            response_data = {
                "token": token.token,
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.login,
                    "must_change_password": user.must_change_password,
                    'image_url': f'/web/image?model=collect.convoyeur&id={convoyeur.id}&field=profile_image',
                },
                "expires": token.expire_at.strftime("%Y-%m-%d %H:%M:%S"),
            }

            return self._add_cors_headers(Response(
                json.dumps(response_data),
                content_type='application/json',
                status=200
            ))

        except AccessDenied as e:
            _logger.warning("AccessDenied: %s", str(e))
            return self._add_cors_headers(Response(
                json.dumps({"error": "Invalid email or password."}),
                content_type='application/json',
                status=401
            ))

        except Exception as e:
            _logger.exception("Login failed")
            return self._add_cors_headers(Response(
                json.dumps({"error": str(e)}),
                content_type='application/json',
                status=500
            ))


    @http.route('/api/convoyeur/resetpassword', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False)
    def reset_password(self, **kwargs):
        headers = {
            'Access-Control-Allow-Origin': '*',  # Or use your frontend's origin
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        }

        # Handle preflight OPTIONS request
        if request.httprequest.method == 'OPTIONS':
            return Response("", status=200, headers=headers)

        try:
            body = request.httprequest.data
            data = json.loads(body.decode('utf-8'))
        except Exception:
            return Response(json.dumps({"error": "Invalid JSON"}), status=400, headers=headers, content_type='application/json')

        auth_header = request.httprequest.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return Response(json.dumps({"error": "Missing or invalid Authorization header"}), status=401, headers=headers, content_type='application/json')

        token = auth_header.split(' ')[1]  # actual token

        if not token:
            return Response(json.dumps({"error": "Missing token"}), status=401, headers=headers, content_type='application/json')

        user_token = request.env['collect.convoyeur.token'].sudo().search([('token', '=', token)], limit=1)
        if not user_token or user_token.expire_at < fields.Datetime.now():
            return Response(json.dumps({"error": "Invalid or expired token"}), status=401, headers=headers, content_type='application/json')

        new_password = data.get('new_password')
        if not new_password:
            return Response(json.dumps({"error": "Missing new password"}), status=400, headers=headers, content_type='application/json')

        user = user_token.user_id
        user.sudo().write({
            'password': new_password,
            'must_change_password': False
        })

        return Response(json.dumps({"success": True, "message": "Password changed successfully"}), status=200, headers=headers, content_type='application/json')

    def get_authenticated_user(self):
        auth_header = request.httprequest.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            raise AccessDenied("Missing or invalid Authorization header")

        token = auth_header.split(" ")[1]
        user_token = request.env['collect.convoyeur.token'].sudo().search([('token', '=', token)], limit=1)

        if not user_token or user_token.expire_at < fields.Datetime.now():
            raise AccessDenied("Invalid or expired token")

        return user_token.user_id

    @http.route('/api/convoyeur/me', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def get_current_convoyeur(self, **kwargs):
        headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        }

        if request.httprequest.method == 'OPTIONS':
            return Response("", status=200, headers=headers)

        try:
            user = self.get_authenticated_user()
            convoyeur = request.env['collect.convoyeur'].sudo().search([('user_id', '=', user.id)], limit=1)

            if not convoyeur:
                return Response(json.dumps({
                    'success': False,
                    'message': 'Convoyeur not found for this user.'
                }), headers=headers, content_type='application/json', status=404)

            data = {
                'id': convoyeur.id,
                'name': convoyeur.name,
                'email': convoyeur.email,
                'phone': convoyeur.phone,
                'mobile': convoyeur.mobile,
                'address': convoyeur.address,
                'job_title': convoyeur.job_title,
                'image_url': f'/web/image?model=collect.convoyeur&id={convoyeur.id}&field=profile_image',
                'gender': convoyeur.gender,
                'marital': convoyeur.marital,
                'birthday': str(convoyeur.birthday) if convoyeur.birthday else None,
                'children': convoyeur.children,
                'place_of_birth': convoyeur.place_of_birth,
                'permis_no': convoyeur.permis_no,
                'permis_expire': str(convoyeur.permis_expire) if convoyeur.permis_expire else None,
                'additional_note': convoyeur.additional_note,
                'country': convoyeur.country_id.name if convoyeur.country_id else None,
            }

            return Response(json.dumps({
                'success': True,
                'convoyeur': data
            }), headers=headers, content_type='application/json', status=200)

        except AccessDenied as e:
            return Response(json.dumps({
                'success': False,
                'message': str(e)
            }), headers=headers, content_type='application/json', status=401)

        except Exception as e:
            _logger.exception("Failed to get convoyeur info")
            return Response(json.dumps({
                'success': False,
                'message': 'Internal server error'
            }), headers=headers, content_type='application/json', status=500)