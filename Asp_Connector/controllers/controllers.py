# from odoo import http


# class TaxillaConnector(http.Controller):
#     @http.route('/taxilla_connector/taxilla_connector', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/taxilla_connector/taxilla_connector/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('taxilla_connector.listing', {
#             'root': '/taxilla_connector/taxilla_connector',
#             'objects': http.request.env['taxilla_connector.taxilla_connector'].search([]),
#         })

#     @http.route('/taxilla_connector/taxilla_connector/objects/<model("taxilla_connector.taxilla_connector"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('taxilla_connector.object', {
#             'object': obj
#         })

