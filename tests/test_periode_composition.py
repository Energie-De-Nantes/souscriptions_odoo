"""
Tests de la composition de facture portée par la Période (candidate A / ADR 0006).

`souscription.periode._composer_lignes(grille)` renvoie les lignes de facture
(`[(0, 0, {...})]`) à partir du snapshot figé de la période et de la grille
passée en paramètre — sans créer de `account.move`. C'est la surface de test
des règles de facturation (sections, abonnement proratisé, énergie par tarif,
notes TURPE, majoration PRO).
"""

from datetime import date

from odoo.tests.common import TransactionCase, tagged

from .common import ABO_ANNUEL_STD, SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_composition', 'post_install', '-at_install')
class TestPeriodeComposition(SouscriptionsTestCase):
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
        """Extrait les dicts de valeurs des commandes One2many (0, 0, vals)."""
        return [vals for (_cmd, _id, vals) in lignes]

    def test_composer_lignes_base_abonnement_prorata(self):
        """Tarif Base : ligne d'abonnement proratisée au nombre de jours réel."""
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0)
        self.assertEqual(periode.jours, 31)

        lignes = periode._composer_lignes(self.grille_prix)
        dicts = self._dicts(lignes)

        abo = next(d for d in dicts if d.get('product_id') and 'Abonnement' in d.get('name', ''))
        self.assertEqual(abo['quantity'], 31)
        self.assertAlmostEqual(abo['price_unit'], ABO_ANNUEL_STD['6'] / 365.0, places=4)

        sections = [d['name'] for d in dicts if d.get('display_type') == 'line_section']
        self.assertIn('Abonnement', sections)

    def test_composer_lignes_hphc_deux_lignes_energie(self):
        """Tarif HP/HC : deux lignes énergie (HP, HC), pas de ligne Base."""
        periode = self._periode(self.souscription_hphc, provision_hp_kwh=150.0, provision_hc_kwh=100.0)
        produits = [d for d in self._dicts(periode._composer_lignes(self.grille_prix)) if d.get('product_id')]
        noms = [d['name'] for d in produits]

        self.assertIn('Énergie HP', noms)
        self.assertIn('Énergie HC', noms)
        self.assertNotIn('Énergie Base', noms)

        hp = next(d for d in produits if d['name'] == 'Énergie HP')
        hc = next(d for d in produits if d['name'] == 'Énergie HC')
        self.assertEqual(hp['quantity'], 150.0)
        self.assertEqual(hc['quantity'], 100.0)

    def test_composer_lignes_note_turpe_uniquement_si_positif(self):
        """Les notes TURPE n'apparaissent que si le montant est > 0."""
        avec = self._periode(
            self.souscription_base,
            provision_base_kwh=100.0,
            turpe_fixe=8.5,
            turpe_variable=4.5,
            date_debut=date(2024, 3, 1),
            date_fin=date(2024, 4, 1),
        )
        notes = [
            d['name']
            for d in self._dicts(avec._composer_lignes(self.grille_prix))
            if d.get('display_type') == 'line_note'
        ]
        self.assertTrue(any('turpe fixe' in n for n in notes))
        self.assertTrue(any('turpe variable' in n for n in notes))

        sans = self._periode(
            self.souscription_base,
            provision_base_kwh=100.0,
            turpe_fixe=0.0,
            turpe_variable=0.0,
            date_debut=date(2024, 4, 1),
            date_fin=date(2024, 5, 1),
        )
        notes_vides = [
            d for d in self._dicts(sans._composer_lignes(self.grille_prix)) if d.get('display_type') == 'line_note'
        ]
        self.assertEqual(notes_vides, [])

    def test_composer_lignes_coeff_pro_majore_abonnement(self):
        """Un coeff PRO historisé majore le prix d'abonnement et marque la ligne PRO."""
        self.souscription_base.coeff_pro = 10.0
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0)

        abo = next(
            d
            for d in self._dicts(periode._composer_lignes(self.grille_prix))
            if d.get('product_id') and 'Abonnement' in d.get('name', '')
        )
        self.assertIn('PRO', abo['name'])
        self.assertAlmostEqual(abo['price_unit'], (ABO_ANNUEL_STD['6'] / 365.0) * 1.10, places=4)

    def test_creer_facture_pose_periode_id_et_partner(self):
        """La coquille _creer_facture émet le move avec periode_id et le bon partner."""
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()

        self.assertEqual(facture.move_type, 'out_invoice')
        self.assertEqual(facture.periode_id, periode)
        self.assertEqual(facture.partner_id, self.souscription_base.partner_id)
        self.assertEqual(facture.invoice_date, periode.date_fin)
        # facture_id dérivé de account.move.periode_id (ADR 0004)
        self.assertEqual(periode.facture_id, facture)

    def test_periode_surface_facture_brouillon(self):
        """Une facture en BROUILLON liée à une période reste visible côté gestion :
        facture_id la référence, facture_state l'expose, move_ids la contient."""
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()  # créée en brouillon (non postée)

        self.assertEqual(facture.state, 'draft')
        self.assertEqual(periode.facture_id, facture)  # liée même en brouillon
        self.assertEqual(periode.facture_state, 'draft')  # état exposé sur la période
        self.assertIn(facture, periode.move_ids)  # présente dans les documents liés

    def test_periode_facture_state_suit_la_remise_en_brouillon(self):
        """facture_state suit l'état réel : postée puis remise en brouillon."""
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()

        facture.action_post()
        self.assertEqual(periode.facture_state, 'posted')

        facture.button_draft()
        self.assertEqual(periode.facture_state, 'draft')
        # toujours liée et visible après remise en brouillon
        self.assertEqual(periode.facture_id, facture)


@tagged('souscriptions', 'souscriptions_composition', 'post_install', '-at_install')
class TestDemoFactures(TransactionCase):
    """Les données de démo illustrent les deux états : postée (visible portail)
    et brouillon (visible gestion uniquement)."""

    def test_demo_a_des_factures_postee_et_brouillon(self):
        posted = self.env.ref('souscriptions_odoo.demo_facture_janvier_admin', raise_if_not_found=False)
        if not posted:
            self.skipTest('Données de démo non chargées')
        draft = self.env.ref('souscriptions_odoo.demo_facture_mars_admin')
        self.assertEqual(posted.state, 'posted')
        self.assertEqual(draft.state, 'draft')
