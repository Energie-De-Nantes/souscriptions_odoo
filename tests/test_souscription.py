from datetime import date

from odoo.tests.common import TransactionCase, tagged


@tagged('souscriptions', 'post_install', '-at_install')
class TestSouscription(TransactionCase):
    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create(
            {
                'name': 'Test Client',
                'is_company': False,
            }
        )

        self.etat_actif = self.env['souscription.etat'].create(
            {
                'name': 'Actif',
                'sequence': 1,
            }
        )

    def test_souscription_creation(self):
        """Test création basique d'une souscription"""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL123456',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_actif.id,
                'date_debut': date(2024, 1, 1),
            }
        )

        self.assertEqual(souscription.partner_id, self.partner)
        self.assertEqual(souscription.puissance_souscrite, '6')
        self.assertEqual(souscription.type_tarif, 'base')
        self.assertTrue(souscription.name != 'Nouveau')  # Séquence générée

    def test_souscription_hphc(self):
        """Test création souscription HP/HC"""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL789',
                'puissance_souscrite': '9',
                'type_tarif': 'hphc',
                'etat_facturation_id': self.etat_actif.id,
                'provision_mensuelle_kwh': 500.0,
            }
        )

        self.assertEqual(souscription.type_tarif, 'hphc')
        self.assertEqual(souscription.provision_mensuelle_kwh, 500.0)

    def test_coefficient_pro(self):
        """Test majoration PRO"""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL456',
                'puissance_souscrite': '12',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_actif.id,
                'coeff_pro': 15.5,
            }
        )

        self.assertEqual(souscription.coeff_pro, 15.5)

    def test_tarif_solidaire(self):
        """Test tarif solidaire"""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL999',
                'puissance_souscrite': '3',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_actif.id,
                'tarif_solidaire': True,
            }
        )

        self.assertTrue(souscription.tarif_solidaire)

    def test_rsc_et_id_affaire_saisissables_a_la_main(self):
        """`ref_situation_contractuelle` (clé d'articulation) et `id_affaire`
        (amorce de réconciliation, ADR 0010) sont saisissables à la main tant
        que le raccordement ne les peuple pas (#76, ADR 0020 §3)."""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_RSC',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_actif.id,
                'ref_situation_contractuelle': 'RSC0001234',
                'id_affaire': 'AFF-56789',
            }
        )

        self.assertEqual(souscription.ref_situation_contractuelle, 'RSC0001234')
        self.assertEqual(souscription.id_affaire, 'AFF-56789')
