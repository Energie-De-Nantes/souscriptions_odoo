"""Tests des mails de Régularisation (#316, ADR 0034 « Extension : les mails
sans mois »). Le même et unique template (#313) branche désormais par
situation — régularisation -> facture, régularisation -> avoir, régularisation
de clôture — et croise un bloc Paiement UNIQUE, orthogonal (mode × facture/
avoir). Matrice testée cellule par cellule, dont `avoir × monnaie_locale` :
jamais écrite en production (le cas RFAC/2024/00001, un avoir de 54,25 €
envoyé sur le modèle « paie-nous par QR-code », impayé 20 mois) doit devenir
impossible ici.

Seam testé : identique à #313 (`tests/test_mail_facture_energie.py`) — on
résout le modèle via la racine surchargée (`_get_mail_template`), on rend le
corps pour la facture (ou l'avoir), on assert sur le HTML sortant.

La détection de la Régularisation de CLÔTURE ne repose sur AUCUN champ
ajouté (AC #316) : même prédicat de faits que
`souscription.regularisation._marquer_regularisee_si_cloture` — les
`periode_couverte_ids` de la Régularisation couvrent la Période de clôture de
la Souscription (`souscription._periode_cloture()`). Les tests posent donc
ce lien directement (`write`), sans passer par `_recalculer()` (dépendant du
pull méta-périodes / electricore, hors seam ici).
"""

import base64
from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase

# PNG 1x1 transparent valide (67 octets) — même fixture que #313
# (test_mail_facture_energie.py) : suffit à passer la validation Pillow d'un
# `fields.Image`, jamais un vrai QR-code.
_PNG_1X1 = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


@tagged('souscriptions', 'souscriptions_facturation', 'post_install', '-at_install')
class TestRenduCorpsRegularisation(SouscriptionsTestCase):
    """AC : situation (facture / avoir / clôture), matrice paiement
    (mode × facture/avoir) — y compris `avoir × monnaie_locale` —, bloc de
    paiement unique partagé avec la mensuelle, Textes permanents."""

    def _regularisation(self, souscription, ecart_kwh, *, periode=None):
        """Régularisation avec une seule ligne — écart positif -> facture,
        négatif -> avoir (même prédicat que `_creer_facture`, ADR 0030
        décision 3). `periode`, si fourni, est posé sur `periode_couverte_ids`
        (simule le tampon d'émission sans passer par `_recalculer()`)."""
        regularisation = self.env['souscription.regularisation'].create(
            {'souscription_id': souscription.id, 'date_debut': date(2024, 1, 1), 'date_fin': date(2024, 2, 1)}
        )
        self.env['souscription.regularisation.ligne'].create(
            {
                'regularisation_id': regularisation.id,
                'grille_id': self.grille_prix.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 2, 1),
                'tarif_solidaire': False,
                'cadran': 'base',
                'ecart_kwh': ecart_kwh,
                'prix_kwh': 0.15,
                'detail': 'Janvier 2024 : test',
            }
        )
        if periode is not None:
            regularisation.periode_couverte_ids = [(6, 0, periode.ids)]
        return regularisation

    def _souscription_cloturee(self, ref):
        """Souscription sortie (`date_fin` posé au milieu d'une Période) +
        sa Période de clôture, prêtes pour une Régularisation de clôture."""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': f'PDL_TEST_{ref}',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 2, 15),
                'provision_mensuelle_kwh': 300.0,
                'ref_compteur': f'COMP_TEST_{ref}',
            }
        )
        periode = self.create_test_periode(souscription, date_debut=date(2024, 2, 1), date_fin=date(2024, 2, 29))
        self.assertTrue(periode._est_periode_cloture(), 'précondition : la Période couvre bien date_fin')
        return souscription, periode

    def _rendre(self, facture):
        template = facture._get_mail_template()
        return template._render_field('body_html', facture.ids)[facture.id]

    def _config_mail(self):
        return self.env.ref('souscriptions_odoo.souscription_mail_config_singleton')

    # --- Situation ---

    def test_regularisation_facture_parle_de_regularisation(self):
        regularisation = self._regularisation(self.souscription_base, 50.0)
        facture = regularisation._creer_facture()
        self.assertEqual(facture.move_type, 'out_invoice')

        body = self._rendre(facture)

        self.assertIn('régularisation', body)
        self.assertNotIn("mois qui vient de s'écouler", body)

    def test_regularisation_avoir_parle_davoir_et_ninvite_jamais_a_payer(self):
        regularisation = self._regularisation(self.souscription_base, -50.0)
        avoir = regularisation._creer_facture()
        self.assertEqual(avoir.move_type, 'out_refund')

        body = self._rendre(avoir)

        self.assertIn('avoir', body)
        self.assertNotIn('réaliser le paiement', body)
        self.assertNotIn('prélèvement automatique sera déclenché', body)

    def test_regularisation_cloture_registre_du_depart_sans_champ_ajoute(self):
        """AC : « détectable sans champ ajouté » — seule
        `periode_couverte_ids` (donnée déjà posée par le tampon d'émission,
        ADR 0030 décision 4) pilote le branchement, aucun booléen dédié."""
        souscription, periode = self._souscription_cloturee('CLOTURE_FACTURE')
        regularisation = self._regularisation(souscription, 50.0, periode=periode)
        facture = regularisation._creer_facture()
        self.assertTrue(facture.is_regularisation_cloture)

        body = self._rendre(facture)

        self.assertIn('résiliation', body)
        self.assertIn('bien prise en compte', body)

    def test_regularisation_non_cloture_ne_declenche_pas_le_registre_du_depart(self):
        """Non-régression : une Régularisation ordinaire (souscription en
        vie, ou clôture non couverte par CE recalcul) ne bascule jamais sur
        la branche clôture."""
        regularisation = self._regularisation(self.souscription_base, 50.0)
        facture = regularisation._creer_facture()
        self.assertFalse(facture.is_regularisation_cloture)

        body = self._rendre(facture)

        self.assertNotIn('bien prise en compte', body)

    # --- Matrice paiement (mode × facture/avoir) ---

    def test_prelevement_facture(self):
        self.souscription_base.mode_paiement = 'prelevement'
        regularisation = self._regularisation(self.souscription_base, 50.0)
        facture = regularisation._creer_facture()

        body = self._rendre(facture)

        self.assertIn('déclenché le 10 du mois en cours', body)
        self.assertNotIn('<img', body)

    def test_prelevement_avoir(self):
        self.souscription_base.mode_paiement = 'prelevement'
        regularisation = self._regularisation(self.souscription_base, -50.0)
        avoir = regularisation._creer_facture()

        body = self._rendre(avoir)

        self.assertIn('remboursement', body)
        self.assertNotIn('prélèvement automatique sera déclenché', body)
        self.assertNotIn('<img', body)

    def test_monnaie_locale_facture_qr_code_aucune_mention_de_prelevement(self):
        self.souscription_base.mode_paiement = 'monnaie_locale'
        regularisation = self._regularisation(self.souscription_base, 50.0)
        facture = regularisation._creer_facture()

        body = self._rendre(facture)

        self.assertIn("d'ici le 10 de ce mois", body)
        self.assertNotIn('prélèvement', body)

    def test_monnaie_locale_avoir_remboursement_moneko_direct_jamais_de_qr(self):
        """AC critique (#316) : la cellule qui n'a JAMAIS existé en
        production — même avec un QR-code téléversé (précondition la plus
        défavorable), l'avoir Moneko ne doit jamais promettre de QR ni
        inviter à payer."""
        self.souscription_base.mode_paiement = 'monnaie_locale'
        self._config_mail().qr_code_moneko = base64.b64encode(_PNG_1X1)
        regularisation = self._regularisation(self.souscription_base, -50.0)
        avoir = regularisation._creer_facture()

        body = self._rendre(avoir)

        self.assertIn('remboursement en Moneko direct', body)
        self.assertNotIn('<img', body)
        self.assertNotIn('QR-code', body)
        self.assertNotIn('flashe', body)
        self.assertNotIn('réaliser le paiement', body)

    def test_bloc_paiement_partage_entre_mensuelle_et_regularisation_facture(self):
        """AC : « le bloc de paiement existe une seule fois » — même texte
        MOT POUR MOT sur la mensuelle (#313, inchangée) et la Régularisation
        projetée en facture, preuve que le paragraphe n'est pas réécrit par
        situation."""
        self.souscription_base.mode_paiement = 'prelevement'
        _periode, facture_mensuelle = self.create_test_invoice(
            self.souscription_base, date_debut=date(2024, 5, 1), date_fin=date(2024, 5, 31)
        )
        regularisation = self._regularisation(self.souscription_base, 50.0)
        facture_regul = regularisation._creer_facture()

        body_mensuelle = self._rendre(facture_mensuelle)
        body_regul = self._rendre(facture_regul)

        phrase = 'Le prélèvement automatique sera déclenché le 10 du mois en cours.'
        self.assertIn(phrase, body_mensuelle)
        self.assertIn(phrase, body_regul)

    # --- Textes permanents (#316) ---

    def test_texte_permanent_difficultes_vide_naffiche_aucun_bloc(self):
        self.assertFalse(self._config_mail().texte_regul_difficultes)
        regularisation = self._regularisation(self.souscription_base, 50.0)
        facture = regularisation._creer_facture()

        body = self._rendre(facture)

        self.assertNotIn('étaler', body)

    def test_texte_permanent_difficultes_configure_apparait_sur_facture_regul(self):
        self._config_mail().texte_regul_difficultes = '<p>Contacte-nous si besoin, on peut étaler.</p>'
        regularisation = self._regularisation(self.souscription_base, 50.0)
        facture = regularisation._creer_facture()

        body = self._rendre(facture)

        self.assertIn('on peut étaler', body)

    def test_texte_permanent_appel_don_configure_apparait_sur_avoir(self):
        self._config_mail().texte_regul_appel_don = '<p>Envie de nous soutenir ? Fais un don.</p>'
        regularisation = self._regularisation(self.souscription_base, -50.0)
        avoir = regularisation._creer_facture()

        body = self._rendre(avoir)

        self.assertIn('Fais un don', body)

    def test_texte_permanent_appel_don_najamais_sur_une_facture(self):
        """Le texte « appel au don » est scopé à l'avoir — une facture de
        régularisation ne doit jamais l'afficher, même s'il est configuré."""
        self._config_mail().texte_regul_appel_don = '<p>Marqueur unique DON-JAMAIS-ICI.</p>'
        regularisation = self._regularisation(self.souscription_base, 50.0)
        facture = regularisation._creer_facture()

        body = self._rendre(facture)

        self.assertNotIn('DON-JAMAIS-ICI', body)

    def test_texte_permanent_cloture_configure_apparait_sur_regul_cloture(self):
        self._config_mail().texte_regul_cloture = '<p>Merci pour ces années ensemble.</p>'
        souscription, periode = self._souscription_cloturee('CLOTURE_TEXTE')
        regularisation = self._regularisation(souscription, 50.0, periode=periode)
        facture = regularisation._creer_facture()

        body = self._rendre(facture)

        self.assertIn('Merci pour ces années ensemble', body)

    def test_mensuelle_313_inchangee(self):
        """AC : « la mensuelle de #313 est inchangée : même lettre, même
        instruction de paiement, mêmes textes » — non-régression explicite de
        cette tranche."""
        self.souscription_base.mode_paiement = 'prelevement'
        campagne = self.env['souscription.campagne.facturation'].create(
            {'mois': date(2024, 5, 1), 'lettre_mois': '<p>Marqueur MENSUELLE-INCHANGEE.</p>'}
        )
        self.assertTrue(campagne)
        _periode, facture = self.create_test_invoice(
            self.souscription_base, date_debut=date(2024, 5, 1), date_fin=date(2024, 5, 31)
        )

        body = self._rendre(facture)

        self.assertIn("Voici ta facture d'électricité", body)
        self.assertIn('déclenché le 10 du mois en cours', body)
        self.assertIn('MENSUELLE-INCHANGEE', body)
        self.assertFalse(facture.is_regularisation_cloture)


@tagged('souscriptions', 'souscriptions_security', 'post_install', '-at_install')
class TestTextesPermanentsAclFacturiste(SouscriptionsTestCase):
    """AC #316 : un·e Facturiste (`group_souscriptions_manager`, SANS
    `group_system` ni `group_erp_manager`) peut éditer les Textes permanents
    depuis le menu — et ses édits sont posés sur un enregistrement `noupdate`
    (data/souscription_mail_config_data.xml), donc survivent à un
    `-u souscriptions_odoo` (non exécutable ici — cf. ADR 0034 « noupdate et
    le stylo du·de la Facturiste sont mutuellement exclusifs »)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.facturiste = cls.env['res.users'].create(
            {
                'name': 'Facturiste Test 316',
                'login': 'facturiste_316',
                'email': 'facturiste_316@souscriptions.test',
                'group_ids': [(6, 0, [cls.env.ref('souscriptions_odoo.group_souscriptions_manager').id])],
            }
        )

    def test_facturiste_sans_group_system_ni_erp_manager(self):
        """Précondition de l'AC : le rôle testé n'est PAS un·e admin."""
        self.assertFalse(self.facturiste.has_group('base.group_system'))
        self.assertFalse(self.facturiste.has_group('base.group_erp_manager'))

    def test_facturiste_peut_editer_les_textes_permanents(self):
        config = self.env.ref('souscriptions_odoo.souscription_mail_config_singleton')

        config.with_user(self.facturiste).write(
            {
                'texte_regul_difficultes': '<p>Édit facturiste — difficultés</p>',
                'texte_regul_appel_don': '<p>Édit facturiste — don</p>',
                'texte_regul_cloture': '<p>Édit facturiste — clôture</p>',
            }
        )

        self.assertIn('difficultés', config.texte_regul_difficultes)
        self.assertIn('don', config.texte_regul_appel_don)
        self.assertIn('clôture', config.texte_regul_cloture)

    def test_config_singleton_reste_noupdate(self):
        """Le foyer d'écriture sûre (ADR 0034) : `noupdate=1` sur le record —
        c'est ce qui garantit qu'un `-u souscriptions_odoo` ne réaffirme
        jamais les valeurs XML par-dessus l'édit humain."""
        record_data = self.env['ir.model.data'].search(
            [('module', '=', 'souscriptions_odoo'), ('name', '=', 'souscription_mail_config_singleton')]
        )
        self.assertTrue(record_data, 'le singleton doit exister comme external id du module')
        self.assertTrue(record_data.noupdate, 'noupdate=1 requis : sinon un -u écraserait les Textes permanents')
