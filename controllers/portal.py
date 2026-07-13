from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import MissingError
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
    def portal_my_souscription(self, souscription_id=None, access_token=None, **kw):
        # Accès soit par le·la souscripteur·rice (propriétaire), soit via un
        # access_token signé — c'est ce qui alimente le bouton « Aperçu » côté
        # back-office (portal.mixin), sans se connecter en tant que client.
        # AccessError (ni propriétaire ni token valide) remonte en 403 ;
        # MissingError (id inexistant) → retour à l'accueil portail.
        try:
            souscription = self._document_check_access('souscription.souscription', souscription_id, access_token)
        except MissingError:
            return request.redirect('/my')

        # Historique des consommations intégré à la page : uniquement les périodes
        # dont la facture est émise (postée) — un brouillon ne fuite pas côté usager
        # (ADR 0004). Plus récente en premier.
        periodes = souscription.periode_ids.filtered(lambda p: p.facture_id and p.facture_id.state == 'posted').sorted(
            'date_debut', reverse=True
        )

        # Factures de régularisation ÉMISES (tranche 8 du PRD #231, #240,
        # ADR 0030) : même règle que les périodes — un brouillon ne fuite
        # jamais côté usager·ère. Pas de fusion avec `periodes` (le group_by
        # mensuelles/réguls est hors périmètre, ADR 0030) : section propre.
        regularisations = souscription.regularisation_ids.filtered(
            lambda r: r.facture_id and r.facture_id.state == 'posted'
        ).sorted('date_fin', reverse=True)

        values = {
            'souscription': souscription,
            'periodes': periodes,
            'regularisations': regularisations,
            'page_name': 'souscription',
        }

        return request.render('souscriptions_odoo.portal_souscription_page', values)
