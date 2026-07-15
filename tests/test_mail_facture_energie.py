"""Tests du mail de facture d'énergie (#313, ADR 0034) : racine unique de
résolution du modèle (`account.move._get_mail_template()`), Lettre du mois
tirée par la Facture via son propre mois, instruction de paiement fusionnée
en un `t-if`, deux bugs vivants corrigés (salutation particulier·ère,
sign-off inconditionnel).

Seam testé (prior art : tests/test_mails_raccordement.py pour l'assertion
sur le corps produit, tests/test_campagne_notes.py pour le report M-1 -> M) :
on résout le modèle via la racine surchargée, on rend le corps pour la
facture, on assert sur le HTML sortant — jamais un envoi SMTP complet.
"""

from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_facturation', 'post_install', '-at_install')
class TestGetMailTemplateFactureEnergie(SouscriptionsTestCase):
    """AC : racine unique — facture d'énergie -> notre modèle ; facture
    hors énergie / avoir -> le modèle standard d'Odoo, jamais le nôtre."""

    def test_facture_energie_route_vers_notre_modele(self):
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )
        template = facture._get_mail_template()
        self.assertEqual(template, self.env.ref('souscriptions_odoo.mail_template_facture_energie'))

    def test_facture_hors_energie_route_vers_le_modele_standard(self):
        facture_normale = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner_test.id,
                'invoice_line_ids': [(0, 0, {'name': 'Produit test', 'quantity': 1, 'price_unit': 100.0})],
            }
        )
        self.assertFalse(facture_normale.is_facture_energie)
        template = facture_normale._get_mail_template()
        self.assertEqual(template, self.env.ref('account.email_template_edi_invoice'))

    def test_avoir_de_regularisation_route_vers_le_modele_standard(self):
        """Un avoir (écart négatif) n'est jamais routé vers notre modèle."""
        regularisation = self.env['souscription.regularisation'].create(
            {'souscription_id': self.souscription_base.id, 'date_debut': date(2024, 1, 1), 'date_fin': date(2024, 2, 1)}
        )
        self.env['souscription.regularisation.ligne'].create(
            {
                'regularisation_id': regularisation.id,
                'grille_id': self.grille_prix.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 2, 1),
                'tarif_solidaire': False,
                'cadran': 'base',
                'ecart_kwh': -50.0,
                'prix_kwh': 0.15,
                'detail': 'Janvier 2024 : -50.00 kWh',
            }
        )
        avoir = regularisation._creer_facture()
        self.assertEqual(avoir.move_type, 'out_refund')

        template = avoir._get_mail_template()

        self.assertEqual(template, self.env.ref('account.email_template_edi_credit_note'))

    def test_regularisation_sans_periode_pas_de_lettre_pas_derreur(self):
        """AC : facture de régularisation (sans période) -> pas de lettre,
        pas d'erreur (ni au compute, ni au rendu)."""
        regularisation = self.env['souscription.regularisation'].create(
            {'souscription_id': self.souscription_base.id, 'date_debut': date(2024, 1, 1), 'date_fin': date(2024, 2, 1)}
        )
        self.env['souscription.regularisation.ligne'].create(
            {
                'regularisation_id': regularisation.id,
                'grille_id': self.grille_prix.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 2, 1),
                'tarif_solidaire': False,
                'cadran': 'base',
                'ecart_kwh': 50.0,
                'prix_kwh': 0.15,
                'detail': 'Janvier 2024 : 50.00 kWh',
            }
        )
        facture = regularisation._creer_facture()
        self.assertFalse(facture.periode_id)

        self.assertFalse(facture.lettre_du_mois)
        template = facture._get_mail_template()
        self.assertEqual(template, self.env.ref('souscriptions_odoo.mail_template_facture_energie'))
        body = template._render_field('body_html', facture.ids)[facture.id]
        self.assertIn('À très bientôt', body, 'le rendu doit aboutir (pas d’erreur), squelette intact')


@tagged('souscriptions', 'souscriptions_facturation', 'post_install', '-at_install')
class TestRenduCorpsFactureEnergie(SouscriptionsTestCase):
    """AC : rendu du corps — Lettre du mois, instruction de paiement,
    salutation, sign-off."""

    def _campagne(self, mois, lettre_mois=False):
        return self.env['souscription.campagne.facturation'].create({'mois': mois, 'lettre_mois': lettre_mois})

    def _rendre(self, facture):
        template = facture._get_mail_template()
        return template._render_field('body_html', facture.ids)[facture.id]

    def test_lettre_du_mois_ecrite_sur_la_campagne_apparait_dans_le_corps(self):
        self._campagne(date(2026, 5, 1), lettre_mois='<p>Nos permanences reprennent le mardi.</p>')
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )

        body = self._rendre(facture)

        self.assertIn('permanences reprennent le mardi', body)

    def test_lettre_vide_naffiche_aucun_bloc(self):
        """AC : lettre vide -> aucun bloc, aucun résidu de mise en forme —
        même avec une lettre écrite sur un AUTRE mois dans la même base
        (aucune fuite entre mois)."""
        self._campagne(date(2026, 6, 1), lettre_mois='<p>Marqueur unique ARDOISE-JUIN.</p>')
        _periode2, facture_avec_lettre = self.create_test_invoice(
            self.souscription_hphc, date_debut=date(2026, 6, 1), date_fin=date(2026, 6, 30)
        )
        body_avec = self._rendre(facture_avec_lettre)

        _periode, facture_sans_lettre = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )
        body_sans = self._rendre(facture_sans_lettre)

        self.assertNotIn('ARDOISE-JUIN', body_sans)
        self.assertLess(body_sans.count('<div'), body_avec.count('<div'), 'la lettre vide ne doit laisser aucun bloc')

    def test_chaque_facture_porte_la_lettre_de_son_propre_mois(self):
        """AC : deux campagnes portant deux lettres -> chaque facture porte
        celle de SON mois, jamais celle du mois courant."""
        self._campagne(date(2026, 5, 1), lettre_mois='<p>Lettre de mai.</p>')
        self._campagne(date(2026, 6, 1), lettre_mois='<p>Lettre de juin.</p>')

        _periode_mai, facture_mai = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )
        _periode_juin, facture_juin = self.create_test_invoice(
            self.souscription_hphc, date_debut=date(2026, 6, 1), date_fin=date(2026, 6, 30)
        )

        body_mai = self._rendre(facture_mai)
        body_juin = self._rendre(facture_juin)

        self.assertIn('Lettre de mai', body_mai)
        self.assertNotIn('Lettre de juin', body_mai)
        self.assertIn('Lettre de juin', body_juin)
        self.assertNotIn('Lettre de mai', body_juin)

    def test_html_riche_emis_non_echappe(self):
        """AC : gras, listes, liens, emoji sont émis en HTML, pas échappé."""
        self._campagne(
            date(2026, 5, 1),
            lettre_mois=(
                '<p><strong>Gras</strong>, une liste :</p>'
                '<ul><li>Un</li><li>Deux</li></ul>'
                '<p><a href="https://exemple.org">un lien</a> 🎉</p>'
            ),
        )
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )

        body = self._rendre(facture)

        self.assertIn('<strong>Gras</strong>', body)
        self.assertIn('<li>Un</li>', body)
        self.assertIn('exemple.org', body)
        self.assertIn('🎉', body)
        self.assertNotIn('&lt;strong&gt;', body)

    def test_mode_paiement_monnaie_locale_affiche_qr_code_pas_prelevement(self):
        self.souscription_base.mode_paiement = 'monnaie_locale'
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )

        body = self._rendre(facture)

        self.assertIn('qr_moneko.png', body)
        self.assertNotIn('prélèvement automatique', body)

    def test_mode_paiement_prelevement_affiche_echeance_pas_qr_code(self):
        self.souscription_base.mode_paiement = 'prelevement'
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )

        body = self._rendre(facture)

        self.assertIn('prélèvement automatique', body)
        self.assertNotIn('qr_moneko.png', body)

    def test_salutation_presente_pour_usager_particulier_sans_societe(self):
        """AC : bug vivant corrigé — la salutation n'était présente que dans
        la branche « client rattaché à une société »."""
        self.assertFalse(self.partner_test.parent_id)
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )

        body = self._rendre(facture)

        self.assertIn('Bonjour', body)
        self.assertIn(self.partner_test.name, body)

    def test_sign_off_present_sans_signature_configuree(self):
        """AC : bug vivant corrigé — le sign-off n'était plus conditionné à
        la présence d'une signature."""
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )

        body = self._rendre(facture)

        self.assertIn('très bientôt', body)
