import requests
import hmac
import hashlib
import time
import uuid
import logging
from odoo.tools import config  # type: ignore

_logger = logging.getLogger(__name__)

GATEWAY_URL = "https://odoo-einvoice.sedintechnologies.com"  
# GATEWAY_URL = "http://localhost:8000"  


class TaxillaAPIClient:
    def __init__(self, env):
        """
        Reads tenant credentials from ir.config_parameter.
        These were saved automatically during module installation.
        """
        ICP = env['ir.config_parameter'].sudo()
        self.tenant_id   = ICP.get_param('asp_connector.tenant_id')
        self.hmac_secret = ICP.get_param('asp_connector.hmac_secret')
        self.gateway_url = ICP.get_param('asp_connector.gateway_url') or GATEWAY_URL

        if not self.tenant_id or not self.hmac_secret:
            raise Exception(
                "Taxilla credentials not found. "
                "Please reinstall the module or contact support."
            )

    def _build_headers(self) -> dict:
        """
        Builds HMAC signed headers for every request.
        """
        timestamp = str(int(time.time()))
        nonce     = str(uuid.uuid4()).replace("-", "")
        message   = f"{self.tenant_id}:{timestamp}:{nonce}"
        signature = hmac.new(
            self.hmac_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        return {
            "X-TENANT-ID": self.tenant_id,
            "X-TIMESTAMP": timestamp,
            "X-NONCE":     nonce,
            "X-HMAC-SIG":  signature,
            "Content-Type": "application/xml",
            "Accept":       "application/json",
        }

    def send_invoice(self, xml_payload: str) -> dict:
        _logger.info("Sending invoice via gateway: %s", self.gateway_url)
        _logger.info("XML Payload:\n%s", xml_payload)

        try:
            response = requests.post(
                f"{self.gateway_url}/asp/submit",
                data=xml_payload.encode("utf-8"),
                headers=self._build_headers(),
                timeout=120,
                verify=False 
            )

            _logger.info("Gateway response status: %s", response.status_code)
            _logger.info("Gateway response body: %s", response.text)

            result = response.json()

        except Exception as e:
            return {
                "status": "error",
                "message": f"Gateway call failed: {str(e)}"
            }

        resp = result.get("response", {})

        if resp.get("status") == "SUCCESS":
            return {"status": "success", "message": "Invoice submitted successfully"}

        if resp.get("status") == "VALIDATION_ERROR":
            return {
                "status": "error",
                "message": resp.get("message", "Validation error"),
                "raw": result
            }

        return result