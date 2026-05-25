from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    inherit_hs_from_category = fields.Boolean(
        string='Inherit HS Code from Category',
        default=True,
        help='When enabled, the HS code is taken from the product category.',
    )
    hs_code_id = fields.Many2one(
        'customs.hs.code',
        string='HS Code',
        help='Harmonised System code for customs classification. '
             'Only used when "Inherit from Category" is disabled.',
    )
    effective_hs_code_id = fields.Many2one(
        'customs.hs.code',
        string='Effective HS Code',
        compute='_compute_effective_hs_code',
        store=True,
        help='Resolved HS code: product-level if set directly, '
             'otherwise inherited from the product category.',
    )

    @api.depends(
        'hs_code_id',
        'inherit_hs_from_category',
        'categ_id',
        'categ_id.hs_code_id',
    )
    def _compute_effective_hs_code(self):
        for product in self:
            if not product.inherit_hs_from_category and product.hs_code_id:
                product.effective_hs_code_id = product.hs_code_id
            elif product.categ_id.hs_code_id:
                product.effective_hs_code_id = product.categ_id.hs_code_id
            else:
                product.effective_hs_code_id = False
