from odoo import models, fields, _
from odoo.exceptions import UserError  #type:ignore
import requests

GATEWAY_URL = "https://odoo-einvoice.sedintechnologies.com"
# GATEWAY_URL = "http://localhost:8000"

class ResCompany(models.Model):
    _inherit = "res.company"

    x_default_asp_name = fields.Selection(
        selection=[('Taxilla', 'Taxilla')],
        string="Default ASP",
        default='Taxilla'
    )

    x_asp_license_status = fields.Selection([
        ('inactive', 'Inactive'),
        ('pending',  'Pending'),
        ('active',   'Active'),
        ('expired',  'Expired'),
        ('renewal_pending', 'Renewal Pending'),
    ],
        string="License Status",
        default='inactive',
        readonly=True
    )

    x_activation_code = fields.Char(
        string="Activation Code",
        help="Enter the activation code shared by Sedin Technologies"
    )

    # ✏️ NEW: Per-company credential fields
    x_asp_tenant_id = fields.Char(
        string='Taxilla Tenant ID',
        readonly=True,
        copy=False,
        help='Set automatically during registration'
    )
    x_asp_hmac_secret = fields.Char(
        string='Taxilla HMAC Secret',
        readonly=True,
        copy=False,
        help='Set automatically during registration'
    )
    x_asp_gateway_url = fields.Char(
        string='Taxilla Gateway URL',
        readonly=True,
        copy=False,
    )

    def _get_tenant_id(self):
        """
        ✏️ NEW: Helper to get tenant_id for this company.
        Reads from company field first, falls back to global param
        for backward compatibility with existing installations.
        """
        tenant_id = self.x_asp_tenant_id
        if not tenant_id:
            ICP = self.env['ir.config_parameter'].sudo()
            tenant_id = ICP.get_param('asp_connector.tenant_id')
        return tenant_id

    def action_request_activation(self):
        self.ensure_one()

        # ✏️ CHANGE: Use helper instead of reading global param directly
        tenant_id = self._get_tenant_id()

        if not tenant_id:
            raise UserError(_(
                "This company is not registered with Taxilla yet.\n"
                "Please contact support or reinstall the module."
            ))

        if not self.email:
            raise UserError(_("Company email is required."))

        if not self.phone:
            raise UserError(_("Company phone is required."))

        try:
            response = requests.post(
                f"{GATEWAY_URL}/request-activation",
                json={
                    "tenant_id":    tenant_id,
                    "company_name": self.name,
                    "email":        self.email,
                    "phone":        self.phone,
                    "company_vat":  self.vat or "", 
                },
                timeout=20,
                verify=False
            )
            data = response.json()


            if response.status_code >= 400:
                raise UserError(
                    data.get("detail") or
                    data.get("message") or
                    _("Request failed.")
                )

            if data.get("status") != "ok":
                raise UserError(_("Request failed. Please try again."))

            self.write({'x_asp_license_status': 'pending'})

            # ✏️ CHANGE: Reload form so status updates immediately in UI
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        except UserError:
            raise
        except Exception as e:
            raise UserError(str(e))

    def action_refresh_license_status(self):
        self.ensure_one()

        # ✏️ CHANGE: Use helper
        tenant_id = self._get_tenant_id()

        if not tenant_id:
            raise UserError(_("This company is not registered with Taxilla yet."))

        response = requests.get(
            f"{GATEWAY_URL}/license-status/{tenant_id}/{self.name}",
            timeout=10,
            verify=False
        )

        data = response.json()
        status = data.get("status", "inactive")

        self.write({'x_asp_license_status': status})

        # ✏️ CHANGE: Reload form so status updates immediately in UI
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_verify_activation(self):
        self.ensure_one()

        if not self.x_activation_code:
            raise UserError(_("Please enter activation code."))

        # ✏️ CHANGE: Use helper
        tenant_id = self._get_tenant_id()

        if not tenant_id:
            raise UserError(_("This company is not registered with Taxilla yet."))

        try:
            response = requests.post(
                f"{GATEWAY_URL}/verify-activation",
                json={
                    "tenant_id": tenant_id,
                    "company_name":self.name,
                    "code":      self.x_activation_code
                },
                timeout=20,
                verify=False
            )

            data = response.json()

            if response.status_code >= 400:
                raise UserError(
                    data.get("detail") or
                    data.get("message") or
                    _("Verification failed.")
                )


            if data.get("status") != "ok":
                raise UserError(data.get("message", "Verification failed"))

            self.write({"x_asp_license_status": "active"})

            # ✏️ CHANGE: Reload form so status updates immediately in UI
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        except UserError:
            raise
        except Exception as e:
            raise UserError(str(e))

    def action_request_renewal(self):
        self.ensure_one()

        # ✏️ CHANGE: Use helper
        tenant_id = self._get_tenant_id()

        if not tenant_id:
            raise UserError(_("This company is not registered with Taxilla yet."))

        try:
            response = requests.post(
                f"{GATEWAY_URL}/request-activation",
                json={
                    "tenant_id":    tenant_id,
                    "company_name": self.name,
                    "email":        self.email,
                    "phone":        self.phone,
                },
                timeout=20,
                verify=False
            )

            data = response.json()

            if data.get("status") != "ok":
                raise UserError(_("Renewal request failed"))

            self.write({"x_asp_license_status": "renewal_pending"})

            # ✏️ CHANGE: Reload form so status updates immediately in UI
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        except UserError:
            raise
        except Exception as e:
            raise UserError(str(e))