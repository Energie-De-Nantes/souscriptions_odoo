"""Tests du bandeau de stats natif de la Campagne de facturation (#301).

Buckets EXACTS du statut de facturation par souscription — chaque
souscription du Périmètre de campagne apparaît dans exactement un bucket
(à tirer / à facturer / facturée / émise), Périmètre = somme des quatre —
à distinguer du reste-à-faire CUMULATIF amont de la matrice des étapes
(#157, `_reste_a_faire`), qui garde sa sémantique propre et n'est pas
touché par cette tranche. Tout dérivé, `store=False` (esprit ADR 0025) :
0 nouveau champ stocké.
"""

from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneBandeauStats(SouscriptionsTestCase):
    MOIS = date(2024, 3, 1)
    FIN_MOIS = date(2024, 3, 31)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-BAND-BASE'}
        )
        self.souscription_hphc.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-BAND-HPHC'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def _periode(self, souscription):
        return self.create_test_periode(souscription, date_debut=self.MOIS, date_fin=self.FIN_MOIS)

    # --- Buckets exacts (AC #301) ---

    def test_toutes_a_tirer_au_depart(self):
        self.assertEqual(self.campagne.nb_a_tirer, 2)
        self.assertEqual(self.campagne.nb_a_facturer, 0)
        self.assertEqual(self.campagne.nb_facturees_brouillon, 0)
        self.assertEqual(self.campagne.nb_emises_bucket, 0)
        self.assertEqual(self.campagne.nb_perimetre, 2)

    def test_buckets_sont_exacts_pas_cumulatifs(self):
        """Contrairement à `_reste_a_faire` (cumulatif amont), une
        souscription « émise » ne compte plus dans « à tirer »/« à
        facturer »/« facturée » — chaque souscription est dans EXACTEMENT un
        bucket."""
        self._periode(self.souscription_base)._creer_facture().action_post()  # émise
        self._periode(self.souscription_hphc)  # reste à facturer
        self.campagne.invalidate_recordset()

        self.assertEqual(self.campagne.nb_a_tirer, 0)
        self.assertEqual(self.campagne.nb_a_facturer, 1)
        self.assertEqual(self.campagne.nb_facturees_brouillon, 0)
        self.assertEqual(self.campagne.nb_emises_bucket, 1)

    def test_perimetre_egale_la_somme_des_quatre_buckets(self):
        self._periode(self.souscription_base)._creer_facture()  # facturée (brouillon)
        self.campagne.invalidate_recordset()

        total_buckets = (
            self.campagne.nb_a_tirer
            + self.campagne.nb_a_facturer
            + self.campagne.nb_facturees_brouillon
            + self.campagne.nb_emises_bucket
        )
        self.assertEqual(self.campagne.nb_perimetre, total_buckets)
        self.assertEqual(self.campagne.nb_perimetre, 2)

    # --- Total émis TTC (AC #301) ---

    def test_total_emis_ttc_ne_compte_que_les_factures_postees_du_mois(self):
        facture_emise = self._periode(self.souscription_base)._creer_facture()
        facture_emise.action_post()
        self._periode(self.souscription_hphc)._creer_facture()  # brouillon, jamais compté
        self.campagne.invalidate_recordset()

        self.assertAlmostEqual(self.campagne.total_emis_ttc, facture_emise.amount_total, places=2)

    def test_total_emis_ttc_nul_sans_facture_postee(self):
        self._periode(self.souscription_base)._creer_facture()  # brouillon seulement
        self.campagne.invalidate_recordset()

        self.assertEqual(self.campagne.total_emis_ttc, 0.0)

    # --- Drill-down par tuile (AC #301) ---

    def test_drill_down_perimetre_ouvre_toutes_les_souscriptions_facturables(self):
        action = self.campagne.action_drill_down_perimetre()
        self.assertEqual(action['res_model'], 'souscription.souscription')
        self.assertEqual(set(action['domain'][0][2]), {self.souscription_base.id, self.souscription_hphc.id})

    def test_drill_down_a_tirer_ouvre_exactement_le_bucket(self):
        self._periode(self.souscription_base)  # sort du bucket à tirer
        self.campagne.invalidate_recordset()

        action = self.campagne.action_drill_down_a_tirer()

        self.assertEqual(action['domain'][0][2], [self.souscription_hphc.id])

    def test_drill_down_a_facturer_ouvre_exactement_le_bucket(self):
        self._periode(self.souscription_base)
        self.campagne.invalidate_recordset()

        action = self.campagne.action_drill_down_a_facturer()

        self.assertEqual(action['domain'][0][2], [self.souscription_base.id])

    def test_drill_down_facturees_ouvre_exactement_le_bucket(self):
        self._periode(self.souscription_base)._creer_facture()
        self.campagne.invalidate_recordset()

        action = self.campagne.action_drill_down_facturees()

        self.assertEqual(action['domain'][0][2], [self.souscription_base.id])

    def test_drill_down_emises_ouvre_exactement_le_bucket(self):
        self._periode(self.souscription_base)._creer_facture().action_post()
        self.campagne.invalidate_recordset()

        action = self.campagne.action_drill_down_emises()

        self.assertEqual(action['domain'][0][2], [self.souscription_base.id])

    def test_drill_down_total_emis_ouvre_les_factures_postees_du_mois(self):
        facture_emise = self._periode(self.souscription_base)._creer_facture()
        facture_emise.action_post()
        self._periode(self.souscription_hphc)._creer_facture()  # brouillon exclu
        self.campagne.invalidate_recordset()

        action = self.campagne.action_drill_down_total_emis()

        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(action['domain'][0][2], [facture_emise.id])

    # --- Étapes faites X/Y (AC #301, liste des campagnes enrichie) ---

    def test_etapes_faites_compte_x_sur_y(self):
        # Campagne fraîche : « préparer les prélèvements » est déjà faite par
        # construction — son « fait » est un signal dérivé (#186) et il n'y a
        # encore aucune facture prélèvement due. Le compteur part donc de 1.
        total = len(self.campagne.etape_ids)
        self.assertEqual(self.campagne.etapes_faites, f'1/{total}')

        self.campagne.etape_ids.filtered(lambda e: e.code == 'verif_periodes').write({'valide': True})
        self.campagne.invalidate_recordset()

        self.assertEqual(self.campagne.etapes_faites, f'2/{total}')

    # --- 0 champ stocké (AC #301, esprit ADR 0025) ---

    def test_les_nouveaux_compteurs_sont_des_computes_non_stockes(self):
        champs_bandeau = (
            'nb_perimetre',
            'nb_a_tirer',
            'nb_a_facturer',
            'nb_facturees_brouillon',
            'nb_emises_bucket',
            'total_emis_ttc',
            'etapes_faites',
        )
        Campagne = self.env['souscription.campagne.facturation']
        for nom_champ in champs_bandeau:
            champ = Campagne._fields[nom_champ]
            self.assertTrue(champ.compute, f'{nom_champ} doit être un compute')
            self.assertFalse(champ.store, f'{nom_champ} ne doit pas être stocké')
