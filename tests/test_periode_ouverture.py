"""
Tests des Périodes d'ouverture backfillées (issue #107, ADR 0023 décision 3).

Une Période d'ouverture est une Période **légitime** créée par la migration
pour les mois non régularisés des contrats lissés : amorcée depuis le facturé
prod (provision, jours, prix appliqué — résolu via la grille comme toute
Période, ADR 0002), liée à une facture **legacy** (prod Odoo 17, hors du
système) plutôt qu'à un `account.move` du nouveau système (`facture_id` reste
dérivé de `move_ids`, ADR 0004 — pas de move fictif).

Rien ne doit l'exclure du périmètre de la future régularisation (#20) : elle
reste `type_periode='mensuelle'`, elle sied dans le même domaine qu'une
Période facturée normale.
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_periode_ouverture', 'post_install', '-at_install')
class TestPeriodeOuverture(SouscriptionsTestCase):
    def _periode_ouverture(self, souscription, **vals):
        base = {
            'souscription_id': souscription.id,
            'date_debut': date(2023, 6, 1),
            'date_fin': date(2023, 7, 1),
            'type_periode': 'mensuelle',
            'facture_legacy_ref': 'FACT-PROD-2023-0456',
        }
        base.update(vals)
        return self.env['souscription.periode'].create(base)

    def test_reference_facture_legacy_sans_account_move(self):
        """AC1 : une Période peut porter une référence de facture legacy, sans
        account.move du nouveau système — facture_id (dérivé de move_ids)
        reste vide, pas de move fictif (ADR 0004)."""
        periode = self._periode_ouverture(self.souscription_hphc, provision_hp_kwh=200.0, provision_hc_kwh=120.0)

        self.assertEqual(periode.facture_legacy_ref, 'FACT-PROD-2023-0456')
        self.assertFalse(periode.facture_id, 'Pas de account.move : facture_id doit rester vide')
        self.assertFalse(periode.move_ids)

    def test_porte_provision_base_jours_et_prix_via_grille(self):
        """AC2 (Base) : provision facturée et jours sont portés par la Période ;
        le prix appliqué reste résolvable par la même mécanique que toute
        Période (grille sélectionnée par régime + date de fin, ADR 0002/0006 —
        jamais recopié sur la Période)."""
        self.souscription_base.lisse = True
        periode = self._periode_ouverture(
            self.souscription_base,
            provision_base_kwh=280.0,
            date_debut=date(2024, 1, 1),
            date_fin=date(2024, 1, 31),
        )

        self.assertEqual(periode.provision_base_kwh, 280.0)
        self.assertEqual(periode.jours, 30)

        grille = self.env['grille.prix'].get_grille_active(periode.date_fin, regime=periode.regime_prix_periode)
        prix = grille.get_prix_dict()
        produit_base = self.env['souscription.produit'].produit_energie('base', periode.tarif_solidaire_periode)
        self.assertIn(produit_base.id, prix, 'Le prix appliqué se résout via la grille, comme toute Période')

    def test_porte_provision_hp_hc(self):
        """AC2 (HP/HC) : provision facturée par cadran, HP et HC."""
        periode = self._periode_ouverture(self.souscription_hphc, provision_hp_kwh=200.0, provision_hc_kwh=120.0)

        self.assertEqual(periode.provision_hp_kwh, 200.0)
        self.assertEqual(periode.provision_hc_kwh, 120.0)

    def test_identifiable_en_liste_et_formulaire(self):
        """AC3 : le champ facture_legacy_ref (identifiant de la Période
        d'ouverture) est exposé sur les vues liste et formulaire de la
        Période."""
        form_view = self.env['souscription.periode'].get_view(view_type='form')
        self.assertIn('facture_legacy_ref', form_view['arch'])

        list_view = self.env['souscription.periode'].get_view(view_type='list')
        self.assertIn('facture_legacy_ref', list_view['arch'])

    def test_expose_memes_donnees_qu_une_periode_facturee_normale(self):
        """AC4 : une Période d'ouverture reste `type_periode='mensuelle'` —
        rien ne l'exclut d'un domaine plausible de la future régularisation
        (#20) : périodes mensuelles lissées de la souscription, mêmes champs
        (snapshot, jours, écart) qu'une Période facturée normale."""
        sous = self.souscription_hphc
        periode = self._periode_ouverture(sous, provision_hp_kwh=200.0, provision_hc_kwh=120.0)

        perimetre = self.env['souscription.periode'].search(
            [
                ('souscription_id', '=', sous.id),
                ('type_periode', '=', 'mensuelle'),
                ('lisse_periode', '=', True),
            ]
        )
        self.assertIn(periode, perimetre)
        self.assertEqual(periode.type_tarif_periode, 'hphc')
        self.assertTrue(periode.jours)
        self.assertEqual(periode.ecart_hp_kwh, periode.energie_hp_kwh - periode.provision_hp_kwh)

    def test_figee_par_le_verrou_de_facturation_sans_account_move(self):
        """Le verrou de facturation (#14) protège aussi la Période
        d'ouverture : dès que `facture_legacy_ref` est posé, ses champs
        facturables sont figés — même sans account.move (pas de trou dans le
        verrou)."""
        periode = self._periode_ouverture(self.souscription_base, provision_base_kwh=280.0)

        with self.assertRaises(UserError):
            periode.write({'provision_base_kwh': 999.0})

    def test_creer_factures_ne_refacture_pas_une_periode_d_ouverture(self):
        """creer_factures() ne doit jamais émettre un second account.move sur
        une Période déjà facturée côté legacy (double facturation évitée) : le
        filtre anti-doublon (#23) tient compte de facture_legacy_ref, pas
        seulement de facture_id."""
        sous = self.souscription_base
        self._periode_ouverture(sous, provision_base_kwh=280.0, date_debut=date(2023, 6, 1), date_fin=date(2023, 7, 1))

        sous.creer_factures()

        self.assertFalse(sous.facture_ids, "Aucune facture ne doit être créée pour une Période d'ouverture")


@tagged('souscriptions', 'souscriptions_periode_ouverture', 'post_install', '-at_install')
class TestPeriodeOuvertureDemoLive(SouscriptionsTestCase):
    """Contrôles sur la démo « backfill migration » (#107), skippés si la démo
    n'est pas chargée sur cette base — même convention que
    `test_releve_demo.TestReleveDemoLive` (démontrable en dev, non chargée en
    CI standard)."""

    def _ref(self, xmlid):
        return self.env.ref(f'souscriptions_odoo.{xmlid}', raise_if_not_found=False)

    def setUp(self):
        super().setUp()
        if not self._ref('demo_periode_ouverture_novembre_2023'):
            self.skipTest('Données de démo non chargées sur cette base')

    def test_periode_ouverture_demo_liee_a_une_facture_legacy(self):
        periode = self._ref('demo_periode_ouverture_novembre_2023')
        self.assertTrue(periode.facture_legacy_ref)
        self.assertFalse(periode.facture_id)

    def test_periode_ouverture_demo_dans_l_historique_de_la_souscription(self):
        sous = self._ref('demo_souscription_migree_lissee')
        periodes_ouverture = self._ref('demo_periode_ouverture_novembre_2023') | self._ref(
            'demo_periode_ouverture_decembre_2023'
        )
        self.assertTrue(sous.lisse)
        self.assertTrue(periodes_ouverture <= sous.periode_ids, "Périodes d'ouverture absentes de l'historique")
