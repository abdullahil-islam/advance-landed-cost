from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    hs_code_id = fields.Many2one(
        'customs.hs.code',
        string='Default HS Code',
        help='Default HS code for products in this category. '
             'Products can inherit this or override it with their own.',
    )
