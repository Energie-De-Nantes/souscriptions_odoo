"""
Tests des Prestations à refacturer (#8 / ADR 0009).

Une `souscription.presta` est un poste Enedis refacturable, indépendant de la
Période : c'est un en-cours (`facture_id` NULL = file « à refacturer ») que la
Souscription **rassemble** sur la facture de la période au moment de
`creer_factures()`, puis flague (`facture_id`).
"""

from datetime import date

from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_presta', 'post_install', '-at_install')
class TestPresta(SouscriptionsTestCase):
    def _presta(self, souscription, **vals):
        base = {
            'souscription_id': souscription.id,
            'reference_enedis': 'F15-001',
            'libelle': 'Déplacement technicien',
            'prix': 45.0,
            'quantite': 1.0,
        }
        base.update(vals)
        return self.env['souscription.presta'].create(base)

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

    @mute_logger('odoo.sql_db')
    def test_reference_enedis_unique(self):
        """Deux prestations ne peuvent partager la même référence Enedis : c'est
        la clé de dédup du sync electricore (ADR 0009)."""
        self._presta(self.souscription_base, reference_enedis='F15-DUP')
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self._presta(self.souscription_base, reference_enedis='F15-DUP')
            self.env.flush_all()


@tagged('souscriptions', 'souscriptions_presta', 'post_install', '-at_install')
class TestDemoPrestas(TransactionCase):
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
