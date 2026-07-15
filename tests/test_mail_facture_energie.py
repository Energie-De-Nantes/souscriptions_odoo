"""Tests du mail de facture d'énergie (#313, ADR 0034, grill 3e passage
2026-07-15) : racine unique de résolution du modèle
(`account.move._get_mail_template()`, contrat multi-record honoré), Lettre
du mois tirée par la Facture via son propre mois, instruction de paiement en
branches EXPLICITES par valeur de `mode_paiement` (jamais de `t-else`, cf.
ADR 0034), QR-code Moneko téléversable résolu par un compute non stocké,
deux bugs vivants corrigés (salutation particulier·ère, sign-off
inconditionnel).

Seam testé (prior art : tests/test_mails_raccordement.py pour l'assertion
sur le corps produit, tests/test_campagne_notes.py pour le report M-1 -> M) :
on résout le modèle via la racine surchargée, on rend le corps pour la
facture, on assert sur le HTML sortant — jamais un envoi SMTP complet. NB :
une assertion sur le HTML produit ne prouve jamais qu'un client mail réel
affiche l'image du QR-code — seul le lien (`/web/image/...?access_token=`)
est vérifié ici.
"""

import base64
from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase

# PNG 1x1 transparent valide (67 octets) — suffisant pour passer la
# validation Pillow de `fields.Image`, jamais un vrai QR-code (peu importe
# ici : on teste la présence du lien, pas son contenu visuel).
_PNG_1X1 = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


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

    def test_contrat_multi_record_honore_par_le_core(self):
        """AC : le core appelle `_get_mail_template()` sur un recordset de
        plusieurs factures (envoi en masse) — lire `is_facture_energie` nu
        sur `self` lève `Expected singleton` avant même d'atteindre
        `all(...)` ; un renvoi groupé de 2 factures d'énergie ne doit plus
        planter (grill 2026-07-15, 3e passage)."""
        _periode1, facture1 = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )
        _periode2, facture2 = self.create_test_invoice(
            self.souscription_hphc, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )
        lot = facture1 + facture2

        template = lot._get_mail_template()

        self.assertEqual(template, self.env.ref('souscriptions_odoo.mail_template_facture_energie'))

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
        self.assertIn('très bientôt', body, 'le rendu doit aboutir (pas d’erreur), squelette intact')


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

    def _config_mail(self):
        """L'unique enregistrement de configuration (data/souscription_mail_
        config_data.xml, ADR 0034) — jamais recréé en test, seulement lu ou
        réécrit, pour rester fidèle au singleton posé en prod."""
        return self.env.ref('souscriptions_odoo.souscription_mail_config_singleton')

    def test_mode_paiement_prelevement_cite_le_10_du_mois_en_cours(self):
        """AC : citation prod EXACTE — pas de paraphrase sur un chemin
        d'argent. Le build précédent avait écrit « le 10 du mois prochain »,
        une affirmation fausse sur QUAND l'argent quitte le compte."""
        self.souscription_base.mode_paiement = 'prelevement'
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )

        body = self._rendre(facture)

        self.assertIn('déclenché le 10 du mois en cours', body)
        self.assertNotIn('<img', body, 'aucun QR pour un·e payeur·euse en prélèvement')

    def test_mode_paiement_monnaie_locale_sans_qr_configure_ne_promet_aucun_qr(self):
        """AC : le QR est un champ téléversable qui peut rester vide — le
        corps donne l'échéance et la marche à suivre in-app SEULES, et ne
        promet jamais un QR absent (contrat hérité de la Lettre du mois)."""
        self.souscription_base.mode_paiement = 'monnaie_locale'
        self.assertFalse(self._config_mail().qr_code_moneko, 'précondition : aucun QR configuré')
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )

        body = self._rendre(facture)

        self.assertIn("d'ici le 10 de ce mois", body)
        self.assertIn('Opérations', body)
        self.assertNotIn('<img', body)
        self.assertNotIn('flashe', body, 'aucune promesse de QR quand aucun QR n’est configuré')
        self.assertNotIn('prélèvement automatique', body)

    def test_mode_paiement_monnaie_locale_avec_qr_configure_affiche_limage(self):
        """AC : un QR téléversé sur le foyer de config s'ajoute au corps
        (« Ou flashe directement ce QR-code : » + l'image), en plus de
        l'échéance et de la marche à suivre in-app qui tiennent déjà
        seules."""
        self.souscription_base.mode_paiement = 'monnaie_locale'
        self._config_mail().qr_code_moneko = base64.b64encode(_PNG_1X1)
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
        )

        body = self._rendre(facture)

        self.assertIn('Ou flashe directement ce QR-code', body)
        self.assertIn('<img', body)
        self.assertIn('/web/image/', body)
        self.assertIn('access_token=', body)

    def test_modes_sans_texte_prod_naffichent_aucun_bloc_de_paiement(self):
        """AC : espèces, virement, chèque et mode vide n'ont AUCUN ancêtre
        prod (le mail de prod ne connaît que 2 circuits) -> aucun bloc, et
        surtout aucune mention de prélèvement — c'est le bug corrigé : un
        `t-else` sur `monnaie_locale` faisait annoncer un prélèvement sans
        mandat à ces circuits."""
        for mode in ('especes', 'virement', 'cheque', False):
            with self.subTest(mode_paiement=mode):
                souscription = self.env['souscription.souscription'].create(
                    {
                        'partner_id': self.partner_test.id,
                        'pdl': f'PDL_TEST_MODE_{mode}',
                        'puissance_souscrite': '6',
                        'type_tarif': 'base',
                        'date_debut': date(2024, 1, 1),
                        'provision_mensuelle_kwh': 300.0,
                        'ref_compteur': f'COMP_TEST_MODE_{mode}',
                        'mode_paiement': mode,
                    }
                )
                _periode, facture = self.create_test_invoice(
                    souscription, date_debut=date(2026, 5, 1), date_fin=date(2026, 5, 31)
                )

                body = self._rendre(facture)

                self.assertNotIn('prélèvement automatique', body)
                self.assertNotIn('Moneko', body)
                self.assertNotIn('QR-code', body)
                self.assertNotIn('<img', body)

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
