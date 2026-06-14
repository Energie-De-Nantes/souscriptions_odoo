from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.http import request


class SouscriptionPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'souscription_count' in counters:
            partner = request.env.user.partner_id
            souscription_count = request.env['souscription.souscription'].search_count(
                [('partner_id', '=', partner.id)]
            )
            values['souscription_count'] = souscription_count
        return values

    @http.route(['/my/souscriptions', '/my/souscriptions/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_souscriptions(self, page=1, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        Souscription = request.env['souscription.souscription']

        domain = [('partner_id', '=', partner.id)]

        # Pagination
        souscription_count = Souscription.search_count(domain)
        pager = portal_pager(url='/my/souscriptions', total=souscription_count, page=page, step=self._items_per_page)

        # Contenu
        souscriptions = Souscription.search(
            domain, limit=self._items_per_page, offset=pager['offset'], order='create_date desc'
        )

        values.update(
            {
                'souscriptions': souscriptions,
                'pager': pager,
                'default_url': '/my/souscriptions',
            }
        )

        return request.render('souscriptions_odoo.portal_my_souscriptions', values)

    @http.route(['/my/souscription/<int:souscription_id>'], type='http', auth='user', website=True)
    def portal_my_souscription(self, souscription_id=None, **kw):
        partner = request.env.user.partner_id
        souscription = request.env['souscription.souscription'].browse(souscription_id)

        # Vérifier que la souscription appartient bien au partenaire
        if not souscription.exists() or souscription.partner_id != partner:
            return request.redirect('/my')

        # Historique des consommations intégré à la page : uniquement les périodes
        # dont la facture est émise (postée) — un brouillon ne fuite pas côté usager
        # (ADR 0004). Plus récente en premier.
        periodes = souscription.periode_ids.filtered(lambda p: p.facture_id and p.facture_id.state == 'posted').sorted(
            'date_debut', reverse=True
        )

        values = {
            'souscription': souscription,
            'periodes': periodes,
            'page_name': 'souscription',
        }

        return request.render('souscriptions_odoo.portal_souscription_page', values)
