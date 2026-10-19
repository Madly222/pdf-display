import logging
from urllib.parse import quote

import requests
from markupsafe import escape

from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

_logger = logging.getLogger(__name__)

TIMEOUT = 60
MAX_SIZE = 100 * 1024 * 1024


class RapidlinkPreview(http.Controller):

    @http.route('/rapidlink_preview/view/<int:attachment_id>', type='http', auth='user', methods=['GET'])
    def view(self, attachment_id, **kwargs):
        _ = request.env._
        attachment = request.env['ir.attachment'].browse(attachment_id).exists()
        try:
            if not attachment or attachment.type != 'binary':
                raise MissingError("not found")
            attachment.check_access('read')
            attachment.check('read')
        except (AccessError, MissingError):
            return self._message(_("You don't have access to this file."), 403)
        if attachment.file_size and attachment.file_size > MAX_SIZE:
            return self._message(_("The file is too large to preview. Download it instead."), 413)

        params = request.env['ir.config_parameter'].sudo()
        url = (params.get_param('rapidlink_preview.url') or '').rstrip('/')
        secret = params.get_param('rapidlink_preview.secret')
        if not url or not secret:
            return self._message(_("Preview is not configured."), 503)

        try:
            response = requests.post(
                f'{url}/api/render',
                data=attachment.sudo().raw,
                headers={
                    'Authorization': f'Bearer {secret}',
                    'Content-Type': 'application/octet-stream',
                    'X-Filename': quote(attachment.name or 'file'),
                    'X-Lang': request.env.lang or 'en_US',
                },
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            _logger.exception("Render service is unreachable")
            return self._message(_("The preview service is unavailable. Try again later or download the file."), 502)
        if response.status_code != 200:
            _logger.warning("Render service answered %s for attachment %s", response.status_code, attachment_id)
            return self._message(_("This file cannot be previewed. Download it instead."), 502)
        return request.redirect(response.json()['view_url'], local=False)

    def _message(self, text, status):
        lang = (request.env.lang or 'en_US').split('_')[0]
        body = (
            f'<!doctype html><html lang="{escape(lang)}"><head><meta charset="utf-8"></head>'
            '<body style="margin:0;display:grid;place-items:center;min-height:100vh;'
            'font:15px system-ui,sans-serif;color:#555;background:#f4f4f4">'
            f'<p style="padding:16px;text-align:center">{escape(text)}</p></body></html>'
        )
        return request.make_response(body, headers=[('Content-Type', 'text/html; charset=utf-8')], status=status)
