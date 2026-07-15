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

from .common import ABO_ANNUEL_STD, SouscriptionsTestCase, build_grille_lignes


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
        """Tarif HP/HC lissé : deux lignes énergie (HP, HC) facturées sur la
        provision, pas de ligne Base. (souscription_hphc est lissée.)"""
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

    def test_composer_lignes_non_lissee_lit_le_mesure_avant_tampon(self):
        """Choix documenté #267 (`_quantite_facturee`) : un contrat non lissé
        PAS ENCORE tamponné (aucune Facture ÉMISE) facture le MESURÉ
        (energie_*), pas la provision — le tampon `provision := energie` a
        migré de `_creer_facture` à l'émission (`account.move._post()`), donc
        la provision reste vide pendant toute la fenêtre brouillon. Le
        brouillon montre la meilleure connaissance du moment, même si une
        valeur de provision est déjà stockée par ailleurs (pas encore gelée
        tant que rien n'a émis)."""
        periode = self._periode(
            self.souscription_base,
            energie_base_kwh=280.0,
            provision_base_kwh=999.0,  # pas encore tamponnée : ignorée tant que non émise
        )
        self.assertFalse(periode.lisse_periode)

        produits = [d for d in self._dicts(periode._composer_lignes(self.grille_prix)) if d.get('product_id')]
        base = next(d for d in produits if d['name'] == 'Énergie Base')
        self.assertEqual(base['quantity'], 280.0)

    def test_composer_lignes_non_lissee_lit_la_provision_gelee_apres_emission(self):
        """Une fois ÉMISE, la provision (gelée par le tampon) fait foi — même
        si le mesuré continue de vivre à côté (ADR 0030, mesuré vivant) :
        `_composer_lignes` appelée directement après coup ne doit PAS suivre
        un mesuré qui a bougé depuis l'émission."""
        periode = self._periode(self.souscription_base, energie_base_kwh=280.0)
        facture = periode._creer_facture()
        facture.action_post()  # tampon : provision_base_kwh := 280.0, gelée
        self.assertEqual(periode.provision_base_kwh, 280.0)

        # Le mesuré continue de vivre (exemption ciblée du verrou, ADR 0030) :
        # une correction directe reste possible après émission.
        periode.energie_base_kwh = 310.0

        produits = [d for d in self._dicts(periode._composer_lignes(self.grille_prix)) if d.get('product_id')]
        base = next(d for d in produits if d['name'] == 'Énergie Base')
        self.assertEqual(base['quantity'], 280.0, 'le facturé gelé, pas le mesuré rafraîchi')

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

    def test_composer_lignes_coeff_pro_majore_energie_base(self):
        """La majoration PRO s'applique aussi à l'énergie Base (#67)."""
        self.souscription_base.coeff_pro = 10.0
        periode = self._periode(self.souscription_base, energie_base_kwh=200.0)

        base = next(
            d for d in self._dicts(periode._composer_lignes(self.grille_prix)) if d.get('name') == 'Énergie Base'
        )
        # prix_base = 0.15 dans la grille de test (cf. common.setUpSouscriptionsData)
        self.assertAlmostEqual(base['price_unit'], 0.15 * 1.10, places=6)

    def test_composer_lignes_coeff_pro_majore_energie_hphc(self):
        """La majoration PRO s'applique aux deux lignes énergie HP et HC (#67)."""
        self.souscription_hphc.coeff_pro = 20.0
        periode = self._periode(self.souscription_hphc, provision_hp_kwh=150.0, provision_hc_kwh=100.0)
        produits = [d for d in self._dicts(periode._composer_lignes(self.grille_prix)) if d.get('product_id')]

        hp = next(d for d in produits if d['name'] == 'Énergie HP')
        hc = next(d for d in produits if d['name'] == 'Énergie HC')
        # prix_hp = 0.18, prix_hc = 0.12 dans la grille de test.
        self.assertAlmostEqual(hp['price_unit'], 0.18 * 1.20, places=6)
        self.assertAlmostEqual(hc['price_unit'], 0.12 * 1.20, places=6)

    def test_composer_lignes_sans_pro_energie_au_prix_grille(self):
        """Sans coeff PRO, l'énergie est facturée au prix brut de la grille (pas de régression)."""
        self.assertEqual(self.souscription_base.coeff_pro, 0.0)
        periode = self._periode(self.souscription_base, energie_base_kwh=200.0)

        base = next(
            d for d in self._dicts(periode._composer_lignes(self.grille_prix)) if d.get('name') == 'Énergie Base'
        )
        self.assertAlmostEqual(base['price_unit'], 0.15, places=6)

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

    def test_creer_facture_ne_tamponne_plus_la_provision(self):
        """#267 (tranche 3 du PRD #264) : `_creer_facture` ne tamponne plus —
        le tampon a migré à l'ÉMISSION (`account.move._post()`). Le
        brouillon fraîchement créé porte donc encore une provision vide ;
        c'est `_quantite_facturee` qui compense en facturant le mesuré en
        direct (cf. test_composer_lignes_non_lissee_lit_le_mesure_avant_tampon)."""
        periode = self._periode(self.souscription_base, energie_base_kwh=280.0)
        self.assertFalse(periode.lisse_periode)

        facture = periode._creer_facture()

        self.assertEqual(facture.state, 'draft')
        self.assertEqual(periode.provision_base_kwh, 0.0, 'toujours pas tamponnée au brouillon')
        ligne = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        self.assertEqual(ligne.quantity, 280.0, 'la ligne porte déjà le mesuré, en attendant le tampon')

    def test_emission_tamponne_la_provision_non_lissee(self):
        """AC1 (#234, ADR 0030 décision 2 ; déplacé à l'émission par #267) :
        ÉMETTRE une Période non lissée tamponne provision_* aux valeurs
        mesurées du moment (energie_*) — la facture porte ces quantités
        tamponnées, désormais gelées."""
        periode = self._periode(self.souscription_base, energie_base_kwh=280.0)
        facture = periode._creer_facture()

        facture.action_post()

        self.assertEqual(periode.provision_base_kwh, 280.0, 'tamponnée par _post()')
        ligne = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        self.assertEqual(ligne.quantity, 280.0)

    def test_creer_facture_lissee_ne_touche_pas_la_provision(self):
        """AC3 (#234) : comportement lissé inchangé — la provision contractuelle
        fixée à la création n'est pas écrasée par le mesuré, ni au brouillon
        ni à l'émission (#267)."""
        periode = self._periode(self.souscription_hphc, provision_hp_kwh=150.0, provision_hc_kwh=100.0)
        self.assertTrue(periode.lisse_periode)

        facture = periode._creer_facture()
        self.assertEqual(periode.provision_hp_kwh, 150.0)
        hp = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie HP')
        self.assertEqual(hp.quantity, 150.0)

        facture.action_post()

        self.assertEqual(periode.provision_hp_kwh, 150.0)
        self.assertEqual(periode.provision_hc_kwh, 100.0)

    def test_reouverture_puis_remission_retamponne(self):
        """#267 : plus de « supprimer la facture pour dé-figer » — la
        correction pendant la fenêtre brouillon se fait directement (édition
        de energie_*, mesuré toujours vivant), et un nouveau passage par
        l'émission (`button_draft` puis `action_post`) rejoue le tampon aux
        valeurs courantes (une mesure raffinée après coup est reprise)."""
        periode = self._periode(self.souscription_base, energie_base_kwh=280.0)
        facture = periode._creer_facture()
        facture.action_post()
        self.assertEqual(periode.provision_base_kwh, 280.0)

        facture.button_draft()  # ré-ouvre la fenêtre brouillon
        periode.energie_base_kwh = 310.0  # mesure raffinée par electricore

        facture.action_post()  # ré-émission : re-tamponne

        self.assertEqual(periode.provision_base_kwh, 310.0)
        ligne = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        self.assertEqual(ligne.quantity, 310.0)

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

    def test_composer_lignes_solidaire_isole_abonnement_et_energie(self):
        """Contrat solidaire : abonnement ET énergie facturés sur les produits de
        l'univers solidaire, jamais les produits standard (isolation, ADR 0013)."""
        sous_sol = self.env['souscription.souscription'].create(
            {
                'partner_id': self.souscription_base.partner_id.id,
                'pdl': 'PDL_TEST_SOLIDAIRE',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'tarif_solidaire': True,
                'date_debut': date(2024, 1, 1),
            }
        )
        periode = self._periode(
            sous_sol, provision_base_kwh=100.0, date_debut=date(2024, 6, 1), date_fin=date(2024, 7, 1)
        )

        def ref(xmlid):
            return self.env.ref(f'souscriptions_odoo.{xmlid}').id

        produit_ids = {
            d['product_id'] for d in self._dicts(periode._composer_lignes(self.grille_prix)) if d.get('product_id')
        }
        self.assertIn(ref('souscriptions_product_abonnement_solidaire'), produit_ids)
        self.assertIn(ref('souscriptions_product_energie_base_solidaire'), produit_ids)
        self.assertNotIn(ref('souscriptions_product_abonnement_standard'), produit_ids)
        self.assertNotIn(ref('souscriptions_product_energie_base'), produit_ids)

    # === Régime de prix (standard | Moulin) — #105 ===

    def _grille_moulin(self, **kwargs):
        # date_fin est dérivée (#309) : jamais passée en création.
        vals = {
            'name': 'Grille Moulin Test',
            'date_debut': date(2024, 1, 1),
            'regime_prix': 'moulin',
        }
        vals.update(kwargs)
        grille = self.env['grille.prix'].create(vals)
        build_grille_lignes(self.env, grille, prix_base=0.30, prix_hp=0.35, prix_hc=0.25)
        return grille

    def test_regime_moulin_facture_au_bareme_moulin(self):
        """Une Souscription en régime Moulin facture aux prix de la grille
        Moulin : la sélection de grille se fait par (régime, date de la
        Période), pas seulement par date."""
        self._grille_moulin()
        sous_moulin = self.env['souscription.souscription'].create(
            {
                'partner_id': self.souscription_base.partner_id.id,
                'pdl': 'PDL_TEST_MOULIN',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'regime_prix': 'moulin',
                'date_debut': date(2024, 1, 1),
            }
        )
        periode = self._periode(sous_moulin, energie_base_kwh=200.0)
        self.assertEqual(periode.regime_prix_periode, 'moulin')

        facture = periode._creer_facture()
        base = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        self.assertAlmostEqual(base.price_unit, 0.30, places=6)

    def test_regime_standard_meme_periode_facture_au_bareme_standard(self):
        """Une souscription standard, sur la même période qu'une Moulin, facture
        au barème standard — les deux régimes sont résolus indépendamment."""
        self._grille_moulin()
        periode_std = self._periode(self.souscription_base, energie_base_kwh=200.0)
        self.assertEqual(periode_std.regime_prix_periode, 'standard')

        facture = periode_std._creer_facture()
        base = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        # prix_base = 0.15 dans la grille standard de test (cf. common.py).
        self.assertAlmostEqual(base.price_unit, 0.15, places=6)

    def test_composition_regime_solidaire_pro_jusqu_a_la_ligne_de_facture(self):
        """Les trois axes (régime, tarif solidaire, majoration PRO) se composent
        librement : produit de l'univers solidaire, prix de la grille Moulin,
        majoré PRO — sans aucun produit dédié Moulin (CONTEXT.md « Tarif
        Moulin » : seul le prix change, fiscalité/comptes restent standard)."""
        self._grille_moulin()
        sous = self.env['souscription.souscription'].create(
            {
                'partner_id': self.souscription_base.partner_id.id,
                'pdl': 'PDL_TEST_MOULIN_SOL_PRO',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'regime_prix': 'moulin',
                'tarif_solidaire': True,
                'coeff_pro': 10.0,
                'date_debut': date(2024, 1, 1),
            }
        )
        periode = self._periode(sous, energie_base_kwh=200.0)
        facture = periode._creer_facture()

        def ref(xmlid):
            return self.env.ref(f'souscriptions_odoo.{xmlid}').id

        produit_energie_sol = ref('souscriptions_product_energie_base_solidaire')
        ligne = facture.invoice_line_ids.filtered(lambda l: l.product_id.id == produit_energie_sol)
        self.assertTrue(ligne, 'La ligne doit porter le produit énergie solidaire (aucun produit dédié Moulin).')
        # Prix Moulin (0.30) x majoration PRO (1.10).
        self.assertAlmostEqual(ligne.price_unit, 0.30 * 1.10, places=6)

        produit_ids = facture.invoice_line_ids.mapped('product_id').ids
        self.assertNotIn(ref('souscriptions_product_energie_base'), produit_ids)


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
