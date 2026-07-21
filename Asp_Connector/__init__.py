from . import models
from . import utils

import requests
import logging

_logger = logging.getLogger(__name__)

# GATEWAY_URL = "http://localhost:8000"
GATEWAY_URL = "https://odoo-einvoice.sedintechnologies.com"


def post_init_hook(env): 
    """
    Runs automatically after module installation.
    Stores credentials per company AND globally for backward compatibility.
    """
    ICP = env['ir.config_parameter'].sudo()
    company = env.company
    uniqueId = env['ir.config_parameter'].sudo().get_param('database.uuid')
                 
    # _logger.error("Unique id from db: unique id: %s", uniqueId)
    
    # ✏️ CHANGE: Check per company first, then global
    if company.x_asp_tenant_id or ICP.get_param('asp_connector.tenant_id'):
        _logger.info("Asp: company '%s' already registered, skipping.", company.name)
        return

    email = company.email or ""
    phone = company.phone or ""

    try:
        response = requests.post(
            f"{GATEWAY_URL}/register",
            json={
                "company_name":   company.name,
                "company_vat":    company.vat or "",
                "email":          email,
                "phone":          phone,
                # "odoo_client_id": env.uid,
                "odoo_client_id" : uniqueId,
            },
            timeout=5,
            verify=False,
        )
        data = response.json()

        if data.get("status") == "ok":
            # ✏️ CHANGE: Store on company record (per company)
            company.sudo().write({
                'x_asp_tenant_id':   data['tenant_id'],
                'x_asp_hmac_secret': data['hmac_secret'],
                'x_asp_gateway_url': GATEWAY_URL,
            })

            # Keep global params for backward compatibility ONLY
            # These act as fallback for existing installations
            if not ICP.get_param('asp_connector.tenant_id'):
                ICP.set_param('asp_connector.tenant_id', data['tenant_id'])
                ICP.set_param('asp_connector.hmac_secret', data['hmac_secret'])
                ICP.set_param('asp_connector.gateway_url', GATEWAY_URL)

            _logger.info(
                "Taxilla: company '%s' registered. tenant_id=%s",
                company.name, data['tenant_id']
            )
        else:
            _logger.error("Taxilla: registration failed: %s", data)

    except Exception as e:
        _logger.error("Taxilla: registration error: %s", str(e))