"""
Tests du snapshot contractuel typé de la Période (issue #14, ADR 0005/0006).

À la création, la Période fige les paramètres contractuels de la Souscription
sous une forme *typée* : `type_tarif_periode` est une clé de sélection
(`base`/`hphc`, jamais le libellé traduit `"Base"`) et
`puissance_souscrite_periode` un nombre (kVA, jamais la chaîne `"6 kVA"`). La
composition de facture lit ces valeurs directement, sans parsing.
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import ABO_ANNUEL_STD, SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_snapshot', 'post_install', '-at_install')
class TestPeriodeSnapshotType(SouscriptionsTestCase):
    def _periode(self, souscription, **vals):
        base = {
            'souscription_id': souscription.id,
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 2, 1),
            'type_periode': 'mensuelle',
        }
        base.update(vals)
        return self.env['souscription.periode'].create(base)

    @staticmethod
    def _dicts(lignes):
        return [vals for (_cmd, _id, vals) in lignes]

    def test_snapshot_fige_des_valeurs_typees(self):
        """type_tarif_periode = clé de sélection ; puissance = nombre (pas de chaîne)."""
        periode = self._periode(self.souscription_base)  # puissance '6', tarif base

        self.assertEqual(periode.type_tarif_periode, 'base')
        self.assertEqual(periode.puissance_souscrite_periode, 6.0)

    def test_changement_puissance_chaque_periode_facture_la_sienne(self):
        """Changement de puissance en cours d'année : chaque période facture la
        puissance figée à sa création (critère d'acceptation #14)."""
        sous = self.souscription_base  # 6 kVA au départ
        p_janvier = self._periode(
            sous, provision_base_kwh=100.0, date_debut=date(2024, 1, 1), date_fin=date(2024, 2, 1)
        )

        sous.puissance_souscrite = '9'  # passage à 9 kVA en cours d'année
        p_fevrier = self._periode(
            sous, provision_base_kwh=100.0, date_debut=date(2024, 2, 1), date_fin=date(2024, 3, 1)
        )

        self.assertEqual(p_janvier.puissance_souscrite_periode, 6.0)
        self.assertEqual(p_fevrier.puissance_souscrite_periode, 9.0)

        def abo_price(periode):
            dicts = self._dicts(periode._composer_lignes(self.grille_prix))
            abo = next(d for d in dicts if d.get('product_id') and 'Abonnement' in d.get('name', ''))
            return abo['price_unit']

        self.assertAlmostEqual(abo_price(p_janvier), ABO_ANNUEL_STD['6'] / 365.0, places=4)
        self.assertAlmostEqual(abo_price(p_fevrier), ABO_ANNUEL_STD['9'] / 365.0, places=4)

    def test_periode_editable_avant_facturation(self):
        """Tant qu'aucune facture ne la référence, la période reste éditable :
        c'est le brouillon de travail du·de la facturiste (#14)."""
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0)

        periode.write({'provision_base_kwh': 250.0})
        self.assertEqual(periode.provision_base_kwh, 250.0)

    def test_periode_editable_avec_facture_brouillon(self):
        """AC #267 : une facture en BROUILLON qui référence la période ne la
        fige plus — le gel suit l'émission, pas l'existence de la facture.
        Preuve, sans migration de données, que les Périodes gelées sous
        l'ancien régime (facture_id truthy = gelée) avec facture encore en
        brouillon sont DE FAIT dé-gelées par la condition dérivée."""
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0, energie_base_kwh=100.0)
        facture = periode._creer_facture()  # brouillon → période toujours éditable
        self.assertEqual(facture.state, 'draft')

        periode.write({'provision_base_kwh': 999.0})  # ne lève rien

        self.assertEqual(periode.provision_base_kwh, 999.0)

    def test_periode_figee_a_lemission(self):
        """Dès qu'une facture ÉMISE (postée) référence la période, ses champs
        facturables sont figés : toute réécriture est rejetée (UserError), y
        compris via RPC (#14, condition dérivée amendée #267)."""
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0, energie_base_kwh=100.0)
        facture = periode._creer_facture()
        facture.action_post()  # émission → période figée

        with self.assertRaises(UserError):
            periode.write({'provision_base_kwh': 999.0})

        # La valeur figée n'a pas bougé (tamponnée à l'émission : energie_base_kwh).
        self.assertEqual(periode.provision_base_kwh, 100.0)

    def test_lisse_periode_figee_a_lemission(self):
        """Fusion lisse/lisse_periode (#347) : `lisse_periode` pilote désormais
        la facture (template ×2, colonne liste) — il hérite donc du même
        verrou d'émission que les autres champs du snapshot figé, même
        patron que `test_periode_figee_a_lemission`."""
        self.souscription_base.lisse = True
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0, energie_base_kwh=100.0)
        self.assertTrue(periode.lisse_periode, 'snapshotté depuis la souscription à la création')
        facture = periode._creer_facture()
        facture.action_post()  # émission → période figée

        with self.assertRaises(UserError):
            periode.write({'lisse_periode': False})

        self.assertTrue(periode.lisse_periode, "la valeur figée n'a pas bougé")

    def test_champs_compat_deprecies_supprimes(self):
        """Les champs de compatibilité dépréciés ont disparu du modèle (#14,
        #347 pour `lisse` — fusionné sur `lisse_periode`, seul snapshot
        autoritaire du lissage à la maille Période)."""
        champs = self.env['souscription.periode']._fields
        self.assertNotIn('energie_kwh', champs)
        self.assertNotIn('provision_kwh', champs)
        self.assertNotIn('_fix_provision', champs)
        self.assertNotIn('lisse', champs)

    def test_snapshot_rsc_fige_a_la_creation(self):
        """La Période snapshotte la RSC de la Souscription à sa création — même
        logique que le snapshot des paramètres contractuels (#76, ADR 0020 §3)."""
        self.souscription_base.ref_situation_contractuelle = 'RSC0001234'
        periode = self._periode(self.souscription_base)

        self.assertEqual(periode.ref_situation_contractuelle, 'RSC0001234')

    def test_snapshot_rsc_ne_suit_pas_un_changement_ulterieur(self):
        """Un changement de RSC sur la Souscription après coup ne modifie pas la
        RSC déjà snapshottée sur une Période existante (historisation, ADR 0006)."""
        self.souscription_base.ref_situation_contractuelle = 'RSC_INITIALE'
        periode = self._periode(self.souscription_base)

        self.souscription_base.ref_situation_contractuelle = 'RSC_NOUVELLE'

        self.assertEqual(periode.ref_situation_contractuelle, 'RSC_INITIALE')
