from odoo import models, fields, _
from odoo.exceptions import UserError  #type: ignore
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    x_asp_name = fields.Selection(
        related='company_id.x_default_asp_name',
        string="ASP",
        readonly=True,
        store=True
    )

    def action_send_invoice(self):
        from ..utils.xml_builder import build_xml_payload
        from ..utils.taxilla_client import TaxillaAPIClient
        from ..utils.taxilla_error import humanize_taxilla_error

        for move in self:
            if move.state != 'posted':
                raise UserError(_("Invoice must be posted before sending to Taxilla."))

            # ✅ ADD THIS HERE
            company = move.company_id

            # Refresh latest status from FastAPI
            company.action_refresh_license_status()

            if move.company_id.x_asp_license_status == 'expired':
                raise UserError(_(
                    "Your license has expired.\n\n"
                    "Please go to Settings → Companies → "
                    "Request Activation to renew."
                ))

            if company.x_asp_license_status != 'active':
                if company.x_asp_license_status == 'inactive':
                    raise UserError(_("Please request ASP activation first."))
                elif company.x_asp_license_status == 'pending':
                    raise UserError(_("ASP activation is still pending approval."))
                else:
                    raise UserError(_("ASP is not active. Please contact support."))
                
            if not move.x_asp_name:
                raise UserError(_(
                    "Please select a Default ASP in Company Settings."
                ))

            try:
                xml_payload = build_xml_payload(move)
                _logger.info("Generated XML for %s:\n%s", move.name, xml_payload)

                # ✅ pass env — reads tenant_id + hmac_secret from ir.config_parameter
                client = TaxillaAPIClient(env=self.env)
                result = client.send_invoice(xml_payload)

            except UserError:
                raise
            except Exception as e:
                _logger.error("Taxilla submission error: %s", str(e))
                raise UserError(_(
                    "Unable to process the invoice at the moment.\n\n"
                    "Please try again later or contact support."
                ))

            if result.get("status") != "success":
                errors = humanize_taxilla_error(result)
                _logger.error("Taxilla Validation Error: %s", result)
                move.message_post(
                    body="<br/>".join(errors),
                    subject="Invoice Submission Failed"
                )
                # raise UserError(_(
                #     "We couldn't process the invoice due to the following issue(s):\n\n"
                #     "• %s\n\nPlease review the invoice and try again."
                # ) % ("\n• ".join(errors)))
                raise UserError(_(
                        "Invoice rejected by Taxilla:\n\n%s"
                    ) % "\n• ".join(errors))

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Success"),
                    "message": result.get(
                        "message", "Invoice successfully submitted to Taxilla"
                    ),
                    "type": "success",
                    "sticky": False,
                }
            }