"""
Tests des Prestations à refacturer (#8 / ADR 0009).

Une `souscription.refacturation` est un poste Enedis refacturable, indépendant de la
Période : c'est un en-cours (`facture_id` NULL = file « à refacturer ») que la
Souscription **rassemble** sur la facture de la période au moment de
`creer_factures()`, puis flague (`facture_id`).
"""

from datetime import date

from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_refacturation', 'post_install', '-at_install')
class TestRefacturation(SouscriptionsTestCase):
    def _presta(self, souscription, **vals):
        base = {
            'souscription_id': souscription.id,
            'reference_enedis': 'F15-001',
            'libelle': 'Déplacement technicien',
            'prix': 45.0,
            'quantite': 1.0,
        }
        base.update(vals)
        return self.env['souscription.refacturation'].create(base)

    def test_presta_a_refacturer_ramassee_et_flaggee(self):
        """Tracer bullet : une presta à refacturer (non mise en attente) atterrit
        sur la facture mensuelle et reçoit son facture_id quand creer_factures()
        tourne."""
        presta = self._presta(self.souscription_base)
        self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        self.assertFalse(presta.facture_id, 'à refacturer avant facturation')

        self.souscription_base.creer_factures()

        self.assertTrue(presta.facture_id, 'flaggée après facturation')
        self.assertIn('Déplacement technicien', presta.facture_id.invoice_line_ids.mapped('name'))

    def test_presta_en_attente_exclue_de_la_facturation_auto(self):
        """Opt-out (ADR 0012) : une prestation mise en attente par le·la
        facturiste n'est PAS ramassée par creer_factures() — elle reste dans
        la file, facture_id NULL."""
        presta = self._presta(self.souscription_base, reference_enedis='F15-HOLD', en_attente=True)
        self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)

        self.souscription_base.creer_factures()

        self.assertFalse(presta.facture_id, 'la presta en attente reste hors facture')

    def test_etat_a_refacturer_par_defaut(self):
        """Sans facture ni mise en attente, l'état dérivé est « à refacturer »."""
        presta = self._presta(self.souscription_base, reference_enedis='F15-ETAT-AR')
        self.assertEqual(presta.etat, 'a_refacturer')

    def test_etat_en_attente_quand_mise_en_attente(self):
        """Mise en attente par le·la facturiste, pas encore facturée → « en attente »."""
        presta = self._presta(self.souscription_base, reference_enedis='F15-ETAT-EA', en_attente=True)
        self.assertEqual(presta.etat, 'en_attente')

    def test_etat_facturee_sur_facture_brouillon(self):
        """Ramassée sur une facture encore en brouillon → « facturée »."""
        presta = self._presta(self.souscription_base, reference_enedis='F15-ETAT-FACT')
        self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        self.souscription_base.creer_factures()
        self.assertEqual(presta.facture_id.state, 'draft')
        self.assertEqual(presta.etat, 'facturee')

    def test_etat_emise_apres_emission_facture(self):
        """Émission de la facture (brouillon → posted) : l'état dérivé passe
        « facturée » → « émise » automatiquement (recalcul, pas de cron)."""
        presta = self._presta(self.souscription_base, reference_enedis='F15-ETAT-EMISE')
        self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        self.souscription_base.creer_factures()
        self.assertEqual(presta.etat, 'facturee')

        presta.facture_id.action_post()

        self.assertEqual(presta.facture_id.state, 'posted')
        self.assertEqual(presta.etat, 'emise')

    def test_composer_ligne_porte_libelle_prix_quantite(self):
        """La ligne composée porte libellé/prix/quantité de la presta et le
        produit générique de prestation."""
        presta = self._presta(self.souscription_base, libelle='Mise en service', prix=52.30, quantite=2.0)
        _cmd, _id, vals = presta._composer_ligne()

        self.assertEqual(vals['name'], 'Mise en service')
        self.assertEqual(vals['price_unit'], 52.30)
        self.assertEqual(vals['quantity'], 2.0)
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_prestation_enedis')
        self.assertEqual(vals['product_id'], produit.id)

    def test_refacturation_non_majoree_par_coeff_pro(self):
        """La majoration PRO ne touche jamais la refacturation (transit Enedis, #67).

        Même sur une souscription PRO, la ligne refacturée garde son prix brut.
        """
        self.souscription_base.coeff_pro = 30.0
        presta = self._presta(self.souscription_base, reference_enedis='F15-PRO', prix=45.0)

        _cmd, _id, vals = presta._composer_ligne()
        self.assertEqual(vals['price_unit'], 45.0)

    def test_composer_ligne_indemnite_utilise_produit_sans_tva(self):
        """Une presta de nature « indemnité » (pénalité hors champ TVA) compose
        sa ligne avec le produit Indemnité dédié, pas le produit Prestation
        (TVA). La TVA suit le produit choisi par la nature (ADR 0009), jamais un
        override de ligne."""
        presta = self._presta(self.souscription_base, reference_enedis='F15-IND', nature='indemnite')
        _cmd, _id, vals = presta._composer_ligne()

        produit_indemnite = self.env.ref('souscriptions_odoo.souscriptions_product_indemnite_enedis')
        self.assertEqual(vals['product_id'], produit_indemnite.id)

    def test_facture_postee_porte_la_tva_du_produit_par_nature(self):
        """Sur une facture posée : la ligne d'une presta « prestation » hérite de
        la TVA configurée sur le produit Prestation ; la ligne d'une « indemnité »
        n'en porte aucune (hors champ). La TVA vient du produit (ADR 0009 §5),
        jamais d'un override de ligne — et la facture se pose proprement."""
        tva = self.env['account.tax'].create(
            {'name': 'TVA F15 20%', 'amount': 20.0, 'amount_type': 'percent', 'type_tax_use': 'sale'}
        )
        self.env.ref('souscriptions_odoo.souscriptions_product_prestation_enedis').taxes_id = tva

        self._presta(self.souscription_base, reference_enedis='F15-TVA', libelle='Déplacement', prix=50.0)
        self._presta(
            self.souscription_base,
            reference_enedis='F15-IND2',
            libelle='Pénalité coupure',
            prix=-30.0,
            nature='indemnite',
        )
        self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)

        self.souscription_base.creer_factures()
        facture = self.souscription_base.refacturation_ids.filtered(
            lambda p: p.reference_enedis == 'F15-TVA'
        ).facture_id
        facture.action_post()

        self.assertEqual(facture.state, 'posted', 'la facture avec lignes prestation + indemnité se pose')
        ligne_presta = facture.invoice_line_ids.filtered(lambda l: l.name == 'Déplacement')
        ligne_indemnite = facture.invoice_line_ids.filtered(lambda l: l.name == 'Pénalité coupure')
        self.assertEqual(ligne_presta.tax_ids, tva, 'la prestation hérite de la TVA du produit')
        self.assertFalse(ligne_indemnite.tax_ids, "l'indemnité reste hors champ TVA")

    def test_presta_negative_se_nette_dans_la_facture(self):
        """Une prestation négative (pénalité de coupure due par Enedis) atterrit
        comme ligne négative sur la facture mensuelle."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        self._presta(self.souscription_base, reference_enedis='F15-NEG', libelle='Pénalité coupure', prix=-30.0)

        self.souscription_base.creer_factures()

        ligne_neg = periode.facture_id.invoice_line_ids.filtered(lambda l: l.name == 'Pénalité coupure')
        self.assertEqual(len(ligne_neg), 1)
        self.assertEqual(ligne_neg.price_unit, -30.0)
        self.assertLess(ligne_neg.price_subtotal, 0, 'la ligne réduit le total')

    def test_presta_facturee_une_seule_fois_sur_plusieurs_periodes(self):
        """Deux périodes facturées en un run : la presta n'atterrit que sur UNE
        facture, jamais dupliquée (pas de double facturation)."""
        self._presta(self.souscription_base, reference_enedis='F15-UNIQ')
        p1 = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 1, 1), date_fin=date(2024, 1, 31), provision_base_kwh=100.0
        )
        p2 = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 2, 1), date_fin=date(2024, 2, 29), provision_base_kwh=100.0
        )

        self.souscription_base.creer_factures()

        lignes = (p1.facture_id | p2.facture_id).invoice_line_ids.filtered(lambda l: l.name == 'Déplacement technicien')
        self.assertEqual(len(lignes), 1, 'facturée exactement une fois')

    def test_supprimer_facture_remet_presta_dans_la_file(self):
        """Supprimer la facture (échappatoire de correction, ADR 0007) re-met la
        prestation dans la file « à refacturer » (ondelete=set null)."""
        presta = self._presta(self.souscription_base, reference_enedis='F15-DEL')
        self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        self.souscription_base.creer_factures()
        facture = presta.facture_id
        self.assertTrue(facture)
        self.assertEqual(presta.etat, 'facturee')

        facture.unlink()  # brouillon → suppression autorisée

        self.assertFalse(presta.facture_id, 'remise dans la file après suppression de la facture')
        self.assertEqual(presta.etat, 'a_refacturer', 'état dérivé recalculé : de retour dans la file')

    def test_action_prestations_groupe_par_etat(self):
        """L'écran de vérification : une action Prestations existe, sur le bon
        modèle, et s'ouvre groupée par état (stats par groupe)."""
        action = self.env.ref('souscriptions_odoo.action_souscription_refacturation')
        self.assertEqual(action.res_model, 'souscription.refacturation')
        self.assertIn('list', action.view_mode)
        self.assertIn('search_default_group_etat', action.context or '')

    def test_menu_prestations_sous_souscriptions(self):
        """Le menu « Prestations » est rangé sous la racine Souscriptions."""
        menu = self.env.ref('souscriptions_odoo.menu_souscription_refacturation')
        self.assertEqual(menu.parent_id, self.env.ref('souscriptions_odoo.menu_souscription_root'))

    @mute_logger('odoo.sql_db')
    def test_reference_enedis_unique(self):
        """Deux prestations ne peuvent partager la même référence Enedis : c'est
        la clé de dédup du sync electricore (ADR 0009)."""
        self._presta(self.souscription_base, reference_enedis='F15-DUP')
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self._presta(self.souscription_base, reference_enedis='F15-DUP')
            self.env.flush_all()


@tagged('souscriptions', 'souscriptions_refacturation', 'post_install', '-at_install')
class TestDemoRefacturations(TransactionCase):
    """Les prestations de démonstration illustrent la file « à refacturer » :
    à refacturer (positive et négative) et déjà facturée."""

    def test_demo_prestas_etats_file_et_facturee(self):
        a_refacturer = self.env.ref('souscriptions_odoo.demo_presta_mise_en_service', raise_if_not_found=False)
        if not a_refacturer:
            self.skipTest('Données de démo non chargées')

        # À refacturer : pas de facture (dans la file)
        self.assertFalse(a_refacturer.facture_id)

        # Montant négatif : pénalité de coupure
        negative = self.env.ref('souscriptions_odoo.demo_presta_penalite_coupure')
        self.assertLess(negative.prix, 0)
        self.assertFalse(negative.facture_id)

        # Déjà facturée : rattachée à la facture mars (brouillon)
        facturee = self.env.ref('souscriptions_odoo.demo_presta_deplacement')
        self.assertEqual(facturee.facture_id, self.env.ref('souscriptions_odoo.demo_facture_mars_admin'))
