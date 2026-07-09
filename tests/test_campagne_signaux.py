"""Tests des signaux dérivés de la Campagne de facturation (#157, ADR 0025).

Statut de facturation par (souscription, mois de la campagne) — 0 champ
stocké sur souscription.souscription — et compteurs reste-à-faire dérivés
sur les étapes pull/créer/émettre (#156 les traitait comme jamais faites ;
cette tranche leur donne leur vrai signal, cf. ETAPES_CAMPAGNE).

Les dates utilisées tombent dans la couverture de la grille de prix fixture
(2024, cf. tests/common.py) : `_creer_facture()` a besoin d'une grille active.
"""

from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneSignauxDerives(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write({'ref_situation_contractuelle': 'RSC-SIG-BASE'})
        self.souscription_hphc.with_context(rsc_automatisme=True).write({'ref_situation_contractuelle': 'RSC-SIG-HPHC'})
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def _etape(self, code):
        return self.campagne.etape_ids.filtered(lambda e: e.code == code)

    def _periode(self, souscription):
        return self.create_test_periode(souscription, date_debut=self.MOIS, date_fin=self.FIN_MOIS)

    # --- Statut par souscription, quatre configurations fixture (AC #157) ---

    def test_statut_a_tirer_sans_periode_du_mois(self):
        """Config 1 : aucune période -> à tirer."""
        self.assertEqual(self.campagne._statut_facturation(self.souscription_base), 'a_tirer')

    def test_statut_a_facturer_periode_sans_facture(self):
        """Config 2 : période existe, pas de facture -> à facturer."""
        self._periode(self.souscription_base)
        self.assertEqual(self.campagne._statut_facturation(self.souscription_base), 'a_facturer')

    def test_statut_facturee_facture_brouillon(self):
        """Config 3 : facture existe en brouillon -> facturée."""
        periode = self._periode(self.souscription_base)
        periode._creer_facture()
        self.assertEqual(self.campagne._statut_facturation(self.souscription_base), 'facturee')

    def test_statut_emise_facture_postee(self):
        """Config 4 : facture postée -> émise."""
        periode = self._periode(self.souscription_base)
        periode._creer_facture().action_post()
        self.assertEqual(self.campagne._statut_facturation(self.souscription_base), 'emise')

    def test_statut_ignore_les_periodes_dun_autre_mois(self):
        """Une période existante mais d'un AUTRE mois ne compte pas : la
        souscription reste « à tirer » pour le mois de la campagne."""
        self.create_test_periode(self.souscription_base, date_debut=date(2024, 2, 1), date_fin=date(2024, 2, 29))
        self.assertEqual(self.campagne._statut_facturation(self.souscription_base), 'a_tirer')

    # --- Compteurs reste-à-faire dérivés sur les étapes (#157) ---

    def test_pull_reste_a_faire_compte_les_souscriptions_sans_periode(self):
        """Les deux souscriptions facturables (base + hphc) sont « à tirer »
        au départ : reste-à-faire = 2, étape non faite."""
        self.assertEqual(self._etape('pull_meta_periodes').nb_reste_a_faire, 2)
        self.assertFalse(self._etape('pull_meta_periodes').fait)

    def test_pull_fait_quand_toutes_les_souscriptions_ont_leur_periode(self):
        self._periode(self.souscription_base)
        self._periode(self.souscription_hphc)
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self._etape('pull_meta_periodes').nb_reste_a_faire, 0)
        self.assertTrue(self._etape('pull_meta_periodes').fait)

    def test_creer_factures_reste_a_faire_compte_periodes_sans_facture(self):
        """Seules les souscriptions « à facturer » comptent — pas celles
        encore « à tirer »."""
        self._periode(self.souscription_base)  # à facturer
        # souscription_hphc reste sans période -> à tirer, hors décompte créer.
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self._etape('creer_factures').nb_reste_a_faire, 1)
        self.assertFalse(self._etape('creer_factures').fait)

    def test_emettre_factures_reste_a_faire_compte_brouillons(self):
        p1 = self._periode(self.souscription_base)
        p2 = self._periode(self.souscription_hphc)
        p1._creer_facture()
        p2._creer_facture()
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self._etape('emettre_factures').nb_reste_a_faire, 2)
        self.assertFalse(self._etape('emettre_factures').fait)

    def test_emettre_factures_fait_quand_toutes_postees(self):
        p1 = self._periode(self.souscription_base)
        p2 = self._periode(self.souscription_hphc)
        p1._creer_facture().action_post()
        p2._creer_facture().action_post()
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self._etape('emettre_factures').nb_reste_a_faire, 0)
        self.assertTrue(self._etape('emettre_factures').fait)

    def test_sync_f15_et_portes_nont_pas_de_reste_a_faire(self):
        """Les étapes sans signal dérivé (action, portes) ont un
        reste-à-faire vide par construction — cf. ETAPES_CAMPAGNE."""
        for code in ('sync_f15', 'releves_index', 'verif_periodes', 'verif_refacturations'):
            self.assertEqual(self._etape(code).nb_reste_a_faire, 0, code)

    # --- Drill-down (#157) ---

    def test_drill_down_ouvre_la_liste_filtree_des_souscriptions_concernees(self):
        action = self._etape('pull_meta_periodes').action_drill_down()
        self.assertEqual(action['res_model'], 'souscription.souscription')
        self.assertEqual(set(action['domain'][0][2]), {self.souscription_base.id, self.souscription_hphc.id})

    def test_drill_down_retrecit_a_mesure_que_les_periodes_arrivent(self):
        self._periode(self.souscription_base)
        action = self._etape('pull_meta_periodes').action_drill_down()
        self.assertEqual(action['domain'][0][2], [self.souscription_hphc.id])

    # --- Décompte factures créées / émises du mois (AC) ---

    def test_compte_factures_creees_et_emises_du_mois(self):
        p1 = self._periode(self.souscription_base)
        p2 = self._periode(self.souscription_hphc)
        p1._creer_facture().action_post()
        p2._creer_facture()
        self.campagne.invalidate_recordset()

        self.assertEqual(self.campagne.nb_factures_creees, 2)
        self.assertEqual(self.campagne.nb_factures_emises, 1)

    def test_aucun_nouveau_champ_stocke_sur_souscription(self):
        """AC : 0 nouveau champ stocké sur souscription.souscription — le
        statut est une méthode, jamais un champ persisté sur ce modèle."""
        for nom_champ in self.env['souscription.souscription']._fields:
            self.assertNotIn('statut_facturation', nom_champ)
            if nom_champ.startswith('campagne'):
                self.fail(f'Champ inattendu lié à la campagne sur souscription.souscription : {nom_champ}')
