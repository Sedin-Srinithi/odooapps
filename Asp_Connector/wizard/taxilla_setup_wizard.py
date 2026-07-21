# from odoo import models, fields, _

# class TaxillaSetupWizard(models.TransientModel):
#     _name = "taxilla.setup.wizard"
#     _description = "Taxilla Setup Wizard"

#     odoo_url = fields.Char()
#     db_name = fields.Char()
#     username = fields.Char()
#     api_key = fields.Char()

#     def action_connect(self):
#         self.env['taxilla.connection'].create({
#             'odoo_url': self.odoo_url,
#             'db_name': self.db_name,
#             'username': self.username,
#             'api_key': self.api_key,
#         })

#         return {
#             "type": "ir.actions.client",
#             "tag": "display_notification",
#             "params": {
#                 "title": "Connected",
#                 "message": "Taxilla connection saved successfully",
#                 "type": "success",
#             }
#         }


# from odoo import models, fields, _
# from odoo.exceptions import UserError
# import xmlrpc.client

# class TaxillaSetupWizard(models.TransientModel):
#     _name = "taxilla.setup.wizard"
#     _description = "Taxilla Setup Wizard"

#     odoo_url = fields.Char(string="Odoo URL")
#     db_name = fields.Char(string="Database Name")
#     username = fields.Char(string="Username")
#     api_key = fields.Char(string="API Key")

#     def action_connect(self):
#         # Step 1 - Verify credentials
#         try:
#             common = xmlrpc.client.ServerProxy(
#                 f"{self.odoo_url}/xmlrpc/2/common"
#             )
#             uid = common.authenticate(
#                 self.db_name, self.username, self.api_key, {}
#             )
#             if not uid:
#                 raise UserError(_("Invalid credentials. Please check and try again."))
#         except UserError:
#             raise
#         except Exception as e:
#             raise UserError(_("Connection failed: %s") % str(e))

#         # Step 2 - Deactivate old connections
#         self.env['taxilla.connection'].search([]).write({'active': False})

#         # Step 3 - Save verified connection
#         self.env['taxilla.connection'].create({
#             'odoo_url': self.odoo_url,
#             'db_name': self.db_name,
#             'username': self.username,
#             'api_key': self.api_key,
#             'active': True,
#         })

#         return {
#             "type": "ir.actions.client",
#             "tag": "display_notification",
#             "params": {
#                 "title": _("Connected"),
#                 "message": "Taxilla connection verified and saved successfully!",
#                 "type": "success",
#             }
#         }

from odoo import models, fields, _
from odoo.exceptions import UserError # pyright: ignore[reportMissingImports]

class TaxillaSetupWizard(models.TransientModel):
    _name = "taxilla.setup.wizard"
    _description = "Taxilla Setup Wizard"

    odoo_url = fields.Char(string="Odoo URL")
    db_name = fields.Char(string="Database Name")
    username = fields.Char(string="Username")
    api_key = fields.Char(string="API Key")

    def action_connect(self):
        # Validate all fields are filled
        if not all([self.odoo_url, self.db_name, self.username, self.api_key]):
            raise UserError(_("Please fill in all fields before connecting."))

        # Deactivate old connections
        self.env['taxilla.connection'].search([]).write({'active': False})

        # Save new connection
        self.env['taxilla.connection'].create({
            'odoo_url': self.odoo_url,
            'db_name': self.db_name,
            'username': self.username,
            'api_key': self.api_key,
            'active': True,
        })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Connected"),
                "message": "Taxilla connection saved successfully!",
                "type": "success",
            }
        }