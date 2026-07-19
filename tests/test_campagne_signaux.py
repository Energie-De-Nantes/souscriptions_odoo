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

    def _creer_souscription_rsc(self, name, rsc, date_debut, date_fin=False):
        """Souscription minimale, RSC acquise, dates propres pilotées par le
        test — pour exercer le Périmètre de campagne (#175) sans perturber
        les fixtures partagées souscription_base/souscription_hphc."""
        sous = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': name,
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'date_debut': date_debut,
                'date_fin': date_fin,
                'provision_mensuelle_kwh': 300.0,
            }
        )
        sous.with_context(rsc_automatisme=True).write({'ref_situation_contractuelle': rsc})
        return sous

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

    def test_statut_redevient_a_facturer_apres_suppression_du_brouillon(self):
        """#267 AC : supprimer un brouillon ne laisse aucun gel résiduel — le
        statut de facturation, dérivé à zéro champ, retombe tout seul à
        « à facturer » (`periode.facture_id` recalculé)."""
        periode = self._periode(self.souscription_base)
        facture = periode._creer_facture()
        self.assertEqual(self.campagne._statut_facturation(self.souscription_base), 'facturee')

        facture.unlink()

        self.assertEqual(self.campagne._statut_facturation(self.souscription_base), 'a_facturer')

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

    def test_creer_factures_reste_a_faire_compte_tout_ce_qui_nest_pas_facture(self):
        """Reste-à-faire cumulatif amont : toute souscription pas encore
        facturée compte — celle « à facturer » ET celle encore « à tirer »
        (sinon « créer » lirait « fait » avant que tout soit tiré)."""
        self._periode(self.souscription_base)  # à facturer
        # souscription_hphc reste sans période -> à tirer : compte aussi.
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self._etape('creer_factures').nb_reste_a_faire, 2)
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

    # --- Envoyer factures (#314) : reste-à-faire dérivé d'`is_move_sent`,
    # champ NATIF d'account.move — zéro champ ajouté. Brouillons et
    # régularisations hors portée par construction (`_factures_du_mois`). ---

    def test_envoyer_factures_reste_a_faire_compte_les_postees_non_envoyees(self):
        p1 = self._periode(self.souscription_base)
        p2 = self._periode(self.souscription_hphc)
        f1 = p1._creer_facture()
        f1.action_post()
        p2._creer_facture()  # reste en brouillon : hors portée de l'envoi
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self._etape('envoyer_factures').nb_reste_a_faire, 1)
        self.assertEqual(self.campagne._factures_a_envoyer_du_mois(), f1)
        self.assertFalse(self._etape('envoyer_factures').fait)

    def test_envoyer_factures_reste_a_faire_decroit_quand_is_move_sent_passe(self):
        """AC : le reste-à-faire décroît quand `is_move_sent` passe — aucun
        appel à la machinerie d'envoi n'est nécessaire pour le prouver, le
        signal est le champ natif lui-même."""
        p1 = self._periode(self.souscription_base)
        p2 = self._periode(self.souscription_hphc)
        f1 = p1._creer_facture()
        f2 = p2._creer_facture()
        f1.action_post()
        f2.action_post()
        self.campagne.etape_ids.invalidate_recordset()
        self.assertEqual(self._etape('envoyer_factures').nb_reste_a_faire, 2)

        f1.is_move_sent = True
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self._etape('envoyer_factures').nb_reste_a_faire, 1)
        self.assertFalse(self._etape('envoyer_factures').fait)

    def test_envoyer_factures_fait_quand_toutes_envoyees(self):
        p1 = self._periode(self.souscription_base)
        f1 = p1._creer_facture()
        f1.action_post()
        f1.is_move_sent = True
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self._etape('envoyer_factures').nb_reste_a_faire, 0)
        self.assertTrue(self._etape('envoyer_factures').fait)

    def test_envoyer_factures_exclut_les_brouillons(self):
        periode = self._periode(self.souscription_base)
        periode._creer_facture()  # reste en brouillon
        self.campagne.etape_ids.invalidate_recordset()

        self.assertEqual(self.campagne._factures_a_envoyer_du_mois(), self.env['account.move'])

    def test_envoyer_factures_exclut_les_regularisations(self):
        """AC : une facture de régularisation n'est jamais dans la portée —
        elle ne porte pas `periode_id` (`_factures_du_mois` ne la rassemble
        donc jamais), sans cas particulier à écrire."""
        regularisation = self.env['souscription.regularisation'].create(
            {'souscription_id': self.souscription_base.id, 'date_debut': date(2024, 1, 1), 'date_fin': date(2024, 4, 1)}
        )
        self.env['souscription.regularisation.ligne'].create(
            {
                'regularisation_id': regularisation.id,
                'grille_id': self.grille_prix.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 2, 1),
                'tarif_solidaire': False,
                'cadran': 'base',
                'ecart_kwh': 50.0,
                'prix_kwh': 0.15,
                'detail': 'Janvier 2024 : +50.00 kWh',
            }
        )
        facture_regul = regularisation._creer_facture()
        facture_regul.action_post()
        self.campagne.etape_ids.invalidate_recordset()

        self.assertNotIn(facture_regul, self.campagne._factures_a_envoyer_du_mois())
        self.assertNotIn(facture_regul, self.campagne._factures_du_mois())

    # --- Périmètre de campagne (#175, CONTEXT.md) : recouvrement de
    # l'intervalle de service avec le mois M, sur les dates propres de la
    # Souscription — jamais l'instantané vivant `etat == 'en_service'`. ---

    def test_perimetre_exclut_souscription_entree_en_service_apres_le_mois(self):
        """Mise en service en avril, campagne de mars : hors périmètre — pas
        de sur-compte (le reste-à-faire ne l'attend jamais)."""
        self._creer_souscription_rsc('PDL_APRES', 'RSC-APRES', date(2024, 4, 1))
        self.campagne.invalidate_recordset()

        self.assertEqual(self._etape('pull_meta_periodes').nb_reste_a_faire, 2)

    def test_perimetre_inclut_souscription_en_service_pendant_le_mois_mais_resiliee_depuis(self):
        """En service dès janvier, sortie posée en juin (dans le passé par
        rapport à aujourd'hui) : concernée par mars, donc dans le
        périmètre — pas de sous-compte malgré `etat == 'en_attente_cloture'`
        (aucune Période ne couvre encore `date_fin` ici, clôture non soldée,
        ADR 0031 décision 3, #247 — le périmètre lit `date_fin`, jamais
        l'instantané vivant `etat`, quel que soit son état dérivé)."""
        resiliee = self._creer_souscription_rsc('PDL_RESILIEE', 'RSC-RESILIEE', date(2024, 1, 1), date(2024, 6, 30))
        self.assertEqual(resiliee.etat, 'en_attente_cloture')
        self.campagne.invalidate_recordset()

        self.assertIn(resiliee, self.campagne._souscriptions_facturables())
        self.assertEqual(self._etape('pull_meta_periodes').nb_reste_a_faire, 3)

    def test_perimetre_inclut_souscription_entree_en_service_en_cours_de_mois(self):
        """Mise en service le 15 mars : concernée par mars dès son entrée,
        pas seulement à partir du mois suivant."""
        en_cours = self._creer_souscription_rsc('PDL_EN_COURS', 'RSC-EN-COURS', date(2024, 3, 15))
        self.campagne.invalidate_recordset()

        self.assertIn(en_cours, self.campagne._souscriptions_facturables())
        self.assertEqual(self._etape('pull_meta_periodes').nb_reste_a_faire, 3)

    def test_drill_down_liste_exactement_les_souscriptions_du_perimetre(self):
        """Le drill-down d'une étape dérivée liste exactement les
        souscriptions comptées par son reste-à-faire (#175)."""
        self._creer_souscription_rsc('PDL_APRES', 'RSC-APRES-DD', date(2024, 4, 1))
        en_cours = self._creer_souscription_rsc('PDL_EN_COURS_DD', 'RSC-EN-COURS-DD', date(2024, 3, 15))
        self.campagne.invalidate_recordset()

        action = self._etape('pull_meta_periodes').action_drill_down()
        self.assertEqual(
            set(action['domain'][0][2]),
            {self.souscription_base.id, self.souscription_hphc.id, en_cours.id},
        )

    def test_sync_f15_et_portes_nont_pas_de_reste_a_faire(self):
        """Les étapes sans signal dérivé (action, portes) ont un
        reste-à-faire vide par construction — cf. ETAPES_CAMPAGNE."""
        for code in ('sync_f15', 'verif_periodes', 'verif_refacturations'):
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

    def test_drill_down_creer_factures_ouvre_les_factures_du_mois_groupees_par_etat(self):
        """#282 : « Créer factures » n'ouvre plus le reste-à-faire
        souscriptions mais les factures du mois (account.move), groupées par
        statut — brouillon (reste à émettre) vs comptabilisé (émis) d'un
        coup d'œil."""
        p1 = self._periode(self.souscription_base)
        p2 = self._periode(self.souscription_hphc)
        p1._creer_facture()
        p2._creer_facture().action_post()
        self.campagne.invalidate_recordset()

        action = self._etape('creer_factures').action_drill_down()

        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(set(action['domain'][0][2]), set(self.campagne._factures_du_mois().ids))
        group_by = action['context'].get('group_by')
        self.assertIn('state', [group_by] if isinstance(group_by, str) else group_by)

    def test_drill_down_emettre_factures_meme_action_que_creer_factures(self):
        """#282 : les deux étapes partagent la même action de drill-down."""
        p1 = self._periode(self.souscription_base)
        p1._creer_facture()
        self.campagne.invalidate_recordset()

        action = self._etape('emettre_factures').action_drill_down()

        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(set(action['domain'][0][2]), set(self.campagne._factures_du_mois().ids))
        group_by = action['context'].get('group_by')
        self.assertIn('state', [group_by] if isinstance(group_by, str) else group_by)

    def test_drill_down_gestes_commerciaux_ouvre_les_factures_du_mois_groupees_par_etat(self):
        """#287 : la porte « Gestes commerciaux » ouvre le même drill-down que
        Créer/Émettre — c'est sur ces brouillons du mois que la facturiste
        pose la ligne € manuelle avant que l'émission ne les gèle (ADR 0032)."""
        p1 = self._periode(self.souscription_base)
        p2 = self._periode(self.souscription_hphc)
        p1._creer_facture()
        p2._creer_facture().action_post()
        self.campagne.invalidate_recordset()

        action = self._etape('gestes_commerciaux').action_drill_down()

        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(set(action['domain'][0][2]), set(self.campagne._factures_du_mois().ids))
        group_by = action['context'].get('group_by')
        self.assertIn('state', [group_by] if isinstance(group_by, str) else group_by)

    def test_drill_down_verif_periodes_ouvre_les_periodes_mensuelles_du_mois(self):
        """#336 : la porte « Vérif périodes » ouvre les périodes du modèle
        souscription.periode, filtrées (mois de la campagne, mensuelle) — pas
        le fallback « souscriptions facturables ». Une période d'un autre
        mois n'apparaît pas (ADR 0031 : une régularisation ne produit aucune
        souscription.periode, le filtre type_periode='mensuelle' est la garde
        explicite demandée par le ticket)."""
        p1 = self._periode(self.souscription_base)
        p2 = self._periode(self.souscription_hphc)
        autre_mois = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 4, 1), date_fin=date(2024, 4, 30)
        )

        action = self._etape('verif_periodes').action_drill_down()

        self.assertEqual(action['res_model'], 'souscription.periode')
        self.assertIn(('mois', '=', self.MOIS), action['domain'])
        self.assertIn(('type_periode', '=', 'mensuelle'), action['domain'])
        trouvees = self.env['souscription.periode'].search(action['domain'])
        self.assertEqual(set(trouvees.ids), {p1.id, p2.id})
        self.assertNotIn(autre_mois.id, trouvees.ids)

    def test_drill_down_verif_refacturations_ouvre_lecran_prestations_adr0012(self):
        """#336 : la porte « Vérif refacturations » réutilise l'action
        existante de l'écran de vérification des prestations (ADR 0012) par
        référence à son XML id — aucune vue ni domaine dupliqués."""
        attendue = self.env.ref('souscriptions_odoo.action_souscription_refacturation')

        action = self._etape('verif_refacturations').action_drill_down()

        self.assertEqual(action['res_model'], 'souscription.refacturation')
        self.assertEqual(action.get('id'), attendue.id)

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

    def test_aucun_champ_denvoi_ajoute_pour_314(self):
        """AC #314 : zéro champ ajouté pour porter l'état d'envoi sur
        `account.move`/`souscription.periode`/`souscription.refacturation` —
        le signal est le champ NATIF `account.move.is_move_sent`, jamais un
        drapeau maison."""
        interdits = ('envoye', 'envoi', 'sent_state', 'mot_du_mois')
        natifs_ok = {'is_move_sent', 'move_sent_values', 'is_being_sent'}
        for modele in ('account.move', 'souscription.periode', 'souscription.refacturation'):
            for nom_champ in self.env[modele]._fields:
                if nom_champ in natifs_ok:
                    continue
                for mot in interdits:
                    self.assertNotIn(mot, nom_champ, f"{modele}.{nom_champ} : nouveau champ d'envoi suspecté")
