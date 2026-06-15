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

    def test_periode_emise_verrouillee_en_ecriture(self):
        """Période liée à une facture émise (postée) : toute réécriture d'une
        valeur facturable est rejetée (UserError), y compris via RPC (#14)."""
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()
        facture.action_post()  # émission = validation

        with self.assertRaises(UserError):
            periode.write({'provision_base_kwh': 999.0})

        # La valeur figée n'a pas bougé.
        self.assertEqual(periode.provision_base_kwh, 100.0)

    def test_periode_facture_brouillon_reste_modifiable(self):
        """Tant que la facture est en brouillon, le·la facturiste corrige encore
        la période : la valeur facturable reste modifiable (#14)."""
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0)
        periode._creer_facture()  # facture créée en brouillon

        periode.write({'provision_base_kwh': 250.0})
        self.assertEqual(periode.provision_base_kwh, 250.0)

    def test_champs_compat_deprecies_supprimes(self):
        """Les champs de compatibilité dépréciés ont disparu du modèle (#14)."""
        champs = self.env['souscription.periode']._fields
        self.assertNotIn('energie_kwh', champs)
        self.assertNotIn('provision_kwh', champs)
        self.assertNotIn('_fix_provision', champs)
