"""Clôture facturée à la campagne (tranche 3 du chantier #21, ADR 0031
décision 4, #248) : ordre de campagne (pull des sorties -> date_fin ->
périmètre -> pull des méta-périodes -> mensuelles -> réguls de clôture),
dernière mensuelle d'un lissé sorti facturée au réel (branche tampon `ADR
0030 décision 2), régul de clôture ordinaire (ADR 0030), tous les mois
« régularisée » à son émission (second auteur du marqueur, PRD #207/#208).

`test_regularisation_tampon.py` couvre déjà le tampon d'émission générique ;
`test_souscription_etat.py::TestEtatEnAttenteCloture` couvre déjà le prédicat
de faits « clôture soldée » en émettant la Régularisation directement (sans
passer par la Campagne, #247). Ici : le câblage dans la Campagne
(`action_pull_sorties_c15`/`action_regulariser_clotures`) et la bascule au
réel de la dernière mensuelle d'un lissé (`_tamponner_provision`).
"""

from datetime import date
from types import SimpleNamespace

from odoo.tests.common import tagged

from .common import (
    SouscriptionsTestCase,
    build_grille_lignes,
    client_flux_factice,
    client_sorties_factice,
    ligne_sortie,
    patcher_client_fabrique,
)


@tagged('souscriptions', 'souscriptions_cloture_campagne', 'post_install', '-at_install')
class TestCampagnePullSortiesC15Etape(SouscriptionsTestCase):
    """Ordre de campagne : `pull_sorties_c15` est la nouvelle racine du DAG,
    `pull_meta_periodes` en dépend (#248, ADR 0031 décision 4)."""

    MOIS = date(2024, 6, 1)

    def setUp(self):
        super().setUp()
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC-CLOTURE-PULL'}
        )
        self.campagne = self.env['souscription.campagne.facturation'].create({'mois': self.MOIS})

    def _etape(self, code):
        return self.campagne.etape_ids.filtered(lambda e: e.code == code)

    def test_pull_sorties_c15_est_racine_et_gate_pull_meta_periodes(self):
        racine = self._etape('pull_sorties_c15')
        meta = self._etape('pull_meta_periodes')
        self.assertEqual(racine.etat_prerequis, 'prete')
        self.assertEqual(meta.etat_prerequis, 'bloquee')

        with patcher_client_fabrique(client_sorties_factice([])):
            racine.action_executer()
        self.campagne.etape_ids.invalidate_recordset()

        self.assertTrue(racine.fait)
        self.assertEqual(self._etape('pull_meta_periodes').etat_prerequis, 'prete')

    def test_action_delegue_au_bouton_autonome_et_ecrit_date_fin(self):
        """Aucune nouvelle couture réseau : même chemin que le bouton
        autonome `action_tirer_sorties_c15` (#246)."""
        client = client_sorties_factice([ligne_sortie('RSC-CLOTURE-PULL', date(2024, 6, 12))])
        with patcher_client_fabrique(client):
            notification = self.campagne.action_pull_sorties_c15()

        self.assertEqual(self.souscription_base.date_fin, date(2024, 6, 11))
        self.assertEqual(notification['type'], 'ir.actions.client')

    def test_bouton_generique_dispatch_vers_pull_sorties(self):
        etape = self._etape('pull_sorties_c15')
        with patcher_client_fabrique(client_sorties_factice([])):
            action = etape.action_executer()
        self.assertEqual(action['tag'], 'display_notification')


@tagged('souscriptions', 'souscriptions_cloture_campagne', 'post_install', '-at_install')
class TestPeriodeClotureAuReel(SouscriptionsTestCase):
    """`_tamponner_provision` : la Période de clôture d'un lissé sorti se
    facture au réel (ADR 0031 décision 4) ; non-régression sur le cas
    normal (pas de clôture ici)."""

    def _souscription_lissee(self, ref, pdl, provision=200.0):
        return self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': pdl,
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'date_debut': date(2023, 1, 1),
                'lisse': True,
                'provision_mensuelle_kwh': provision,
                'regime_prix': 'moulin',
                'ref_situation_contractuelle': ref,
            }
        )

    def _grille_moulin(self, name):
        grille = self.env['grille.prix'].create(
            {
                'name': name,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 12, 31),
                'active': True,
                'regime_prix': 'moulin',
            }
        )
        build_grille_lignes(self.env, grille, prix_base=0.15, prix_hp=0.18, prix_hc=0.12)
        return grille

    def test_est_periode_cloture_predicat_de_bornes(self):
        souscription = self._souscription_lissee('RSC-CLOTURE-PREDICAT', 'PDL_CLOTURE_PREDICAT')
        periode = self.env['souscription.periode'].create(
            {
                'souscription_id': souscription.id,
                'date_debut': date(2024, 6, 1),
                'date_fin': date(2024, 7, 1),
                'type_periode': 'mensuelle',
            }
        )
        self.assertFalse(periode._est_periode_cloture(), 'pas de date_fin sur la souscription')

        souscription.date_fin = date(2024, 6, 11)
        self.assertTrue(periode._est_periode_cloture())

        souscription.date_fin = date(2024, 5, 31)
        self.assertFalse(periode._est_periode_cloture(), 'date_fin hors bornes de cette Période')

    def test_tamponner_provision_ne_touche_pas_un_lisse_normal_sans_sortie(self):
        """Non-régression : une Période lissée normale (pas de clôture)
        garde la provision contractuelle après facturation."""
        souscription = self._souscription_lissee('RSC-CLOTURE-NORMAL', 'PDL_CLOTURE_NORMAL')
        self._grille_moulin('Grille Clôture Normal')
        periode = self.env['souscription.periode'].create(
            {
                'souscription_id': souscription.id,
                'date_debut': date(2024, 3, 1),
                'date_fin': date(2024, 4, 1),
                'type_periode': 'mensuelle',
                'energie_base_kwh': 250.0,
            }
        )
        periode._creer_facture()
        self.assertEqual(periode.provision_base_kwh, 200.0, 'provision contractuelle : pas de clôture ici')

    def test_periode_de_cloture_lissee_tamponnee_au_reel_a_la_facturation(self):
        """AC1 (partiel) : la Période de clôture d'un lissé sorti (jours
        exacts déjà tronqués par electricore) se voit tamponner sa provision
        à la conso réelle, comme une non-lissée, à la création de la
        facture."""
        souscription = self._souscription_lissee('RSC-CLOTURE-REEL-UNIT', 'PDL_CLOTURE_REEL_UNIT')
        self._grille_moulin('Grille Clôture Réel Unit')
        souscription.date_fin = date(2024, 6, 11)

        periode = self.env['souscription.periode']._amorcer_depuis_meta(
            souscription,
            SimpleNamespace(
                ref_situation_contractuelle='RSC-CLOTURE-REEL-UNIT',
                debut='2024-06-01',
                fin='2024-06-12',
                mois_annee='2024-06',
                puissance_moyenne_kva=6.0,
                energie_base_kwh=90.0,
                energie_hp_kwh=None,
                energie_hc_kwh=None,
                turpe_fixe_eur=3.0,
                turpe_variable_eur=1.2,
                cta_eur=0.4,
                taux_accise_eur_mwh=21.0,
                has_changement=False,
                qualite='réelle',
                statut_communication='communicante',
                releves_utilises=[],
                source_hash='H-CLOTURE-REEL-UNIT',
            ),
        )
        self.assertEqual(periode.jours, 11, 'jours exacts, déjà tronqués côté electricore')
        self.assertEqual(periode.provision_base_kwh, 200.0, 'provision contractuelle avant facturation')

        facture = periode._creer_facture()

        self.assertEqual(periode.provision_base_kwh, 90.0, 'au réel : tamponnée à la conso réelle')
        ligne_abo = facture.invoice_line_ids.filtered(lambda l: l.quantity == 11)
        self.assertEqual(len(ligne_abo), 1, "l'abonnement porte les 11 jours exacts")


@tagged('souscriptions', 'souscriptions_cloture_campagne', 'post_install', '-at_install')
class TestRegulariserClotures(SouscriptionsTestCase):
    """`souscription.campagne.facturation.action_regulariser_clotures` : la
    régul de clôture, ordinaire, émise pour toute souscription
    `en_attente_cloture` — critères d'acceptation de #248."""

    def _souscription_lissee(self, ref, pdl, provision=200.0):
        return self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': pdl,
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'date_debut': date(2023, 1, 1),
                'lisse': True,
                'provision_mensuelle_kwh': provision,
                'regime_prix': 'moulin',
                'ref_situation_contractuelle': ref,
            }
        )

    def _grille_moulin(self, name):
        grille = self.env['grille.prix'].create(
            {
                'name': name,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 12, 31),
                'active': True,
                'regime_prix': 'moulin',
            }
        )
        build_grille_lignes(self.env, grille, prix_base=0.15, prix_hp=0.18, prix_hc=0.12)
        return grille

    def _periode_legacy(self, souscription, mois_index, **overrides):
        debut = date(2024, mois_index, 1)
        fin = date(2024, mois_index + 1, 1)
        vals = {
            'souscription_id': souscription.id,
            'date_debut': debut,
            'date_fin': fin,
            'type_periode': 'mensuelle',
            'provision_base_kwh': 200.0,
            'energie_base_kwh': 200.0,
            'qualite': 'réelle',
            'statut_communication': 'communicante',
            'facture_legacy_ref': f'LEGACY-{souscription.pdl}-{mois_index}',
        }
        vals.update(overrides)
        return self.env['souscription.periode'].create(vals)

    def _campagne(self, mois):
        return self.env['souscription.campagne.facturation'].create({'mois': mois})

    def _sans_appel_reseau(self):
        return patcher_client_fabrique(client_flux_factice('meta_periodes', []))

    # --- AC1 : sortie d'un lissé, dernière mensuelle au réel + régul de
    # clôture soldant les mois antérieurs ---

    def test_derniere_mensuelle_lissee_au_reel_puis_regul_solde_le_passe(self):
        souscription = self._souscription_lissee('RSC-CLOTURE-REEL', 'PDL_CLOTURE_REEL')
        self._grille_moulin('Grille Clôture Réel')

        mai = self._periode_legacy(souscription, 5, energie_base_kwh=225.0)  # écart +25

        souscription.date_fin = date(2024, 6, 11)
        self.assertEqual(souscription.etat, 'en_attente_cloture')

        periode_juin = self.env['souscription.periode']._amorcer_depuis_meta(
            souscription,
            SimpleNamespace(
                ref_situation_contractuelle='RSC-CLOTURE-REEL',
                debut='2024-06-01',
                fin='2024-06-12',
                mois_annee='2024-06',
                puissance_moyenne_kva=6.0,
                energie_base_kwh=90.0,
                energie_hp_kwh=None,
                energie_hc_kwh=None,
                turpe_fixe_eur=3.0,
                turpe_variable_eur=1.2,
                cta_eur=0.4,
                taux_accise_eur_mwh=21.0,
                has_changement=False,
                qualite='réelle',
                statut_communication='communicante',
                releves_utilises=[],
                source_hash='H-CLOTURE-REEL-JUIN',
            ),
        )
        self.assertEqual(periode_juin.jours, 11)

        # « Mensuelles » : facturation normale de la campagne.
        facture_juin = periode_juin._creer_facture()
        facture_juin.action_post()
        self.assertEqual(periode_juin.provision_base_kwh, 90.0, 'juin au réel')
        self.assertEqual(souscription.etat, 'en_attente_cloture', 'mai pas encore soldé')

        # « Réguls de clôture ».
        campagne = self._campagne(date(2024, 6, 1))
        with self._sans_appel_reseau():
            notification = campagne.action_regulariser_clotures()
        self.assertIn('Émises : 1', notification['params']['message'])

        regularisations = souscription.regularisation_ids.filtered(lambda r: r.etat == 'facturee')
        self.assertEqual(len(regularisations), 1)
        regularisation = regularisations
        self.assertEqual(len(regularisation.ligne_ids), 1, 'seul mai porte un écart')
        self.assertAlmostEqual(regularisation.ligne_ids.ecart_kwh, 25.0, places=2)

        # AC3 : tous les mois « régularisée », souscription resiliee.
        self.assertEqual(mai.regularisation_id, regularisation)
        self.assertEqual(periode_juin.regularisation_id, regularisation, 'écart nul compris : couverte quand même')
        self.assertTrue(mai.legacy_regularisee)
        self.assertTrue(periode_juin.legacy_regularisee)
        self.assertEqual(souscription.etat, 'resiliee')

    # --- AC2 (+ AC5) : mensualité déjà émise avant détection -> la régul
    # avale l'écart, trop-perçu -> avoir ---

    def test_mensualite_deja_emise_avant_detection_lecart_est_avale_par_la_regul(self):
        souscription = self._souscription_lissee('RSC-CLOTURE-DEJA-EMISE', 'PDL_CLOTURE_DEJA_EMISE')
        self._grille_moulin('Grille Clôture Déjà Émise')

        periode_juin = self.env['souscription.periode'].create(
            {
                'souscription_id': souscription.id,
                'date_debut': date(2024, 6, 1),
                'date_fin': date(2024, 7, 1),
                'type_periode': 'mensuelle',
                'qualite': 'réelle',
                'statut_communication': 'communicante',
                'energie_base_kwh': 200.0,
                'source_hash': 'H-JUIN-AVANT-SORTIE',
            }
        )
        self.assertEqual(periode_juin.provision_base_kwh, 200.0)

        facture_juin = periode_juin._creer_facture()
        facture_juin.action_post()
        self.assertEqual(periode_juin.provision_base_kwh, 200.0, 'déjà facturée avant détection : aucun tampon')

        # Sortie détectée après coup : la clôture tombe rétroactivement dans
        # le mois déjà facturé — aucun cas spécial (`facture_id` bloque déjà
        # `_tamponner_provision`).
        souscription.date_fin = date(2024, 6, 11)
        self.assertTrue(periode_juin._est_periode_cloture())

        # electricore raffine ensuite le mesuré (nouvelle empreinte) : la
        # vraie conso des 11 jours, plus faible que le mois plein provisionné.
        periode_juin._rafraichir_depuis_meta(
            SimpleNamespace(
                source_hash='H-JUIN-REEL-TRONQUE',
                energie_base_kwh=80.0,
                energie_hp_kwh=None,
                energie_hc_kwh=None,
                puissance_moyenne_kva=6.0,
                turpe_fixe_eur=0.0,
                turpe_variable_eur=0.0,
                cta_eur=0.0,
                taux_accise_eur_mwh=0.0,
                has_changement=False,
                qualite='réelle',
                statut_communication='communicante',
            )
        )
        self.assertAlmostEqual(periode_juin.ecart_base_kwh, -120.0, places=2)

        campagne = self._campagne(date(2024, 6, 1))
        with self._sans_appel_reseau():
            campagne.action_regulariser_clotures()

        self.assertEqual(periode_juin.provision_base_kwh, 80.0, "l'écart est avalé : même conso au total")
        self.assertEqual(periode_juin.ecart_base_kwh, 0.0)
        regularisation = souscription.regularisation_ids.filtered(lambda r: r.etat == 'facturee')
        self.assertEqual(len(regularisation), 1)
        self.assertEqual(regularisation.facture_id.move_type, 'out_refund', 'trop-perçu -> avoir')
        self.assertTrue(periode_juin.legacy_regularisee)
        self.assertEqual(souscription.etat, 'resiliee')

    # --- AC4 : plus aucune Période ni facture créée après la sortie ---

    def test_plus_aucune_periode_ni_facture_creee_apres_la_sortie(self):
        souscription = self._souscription_lissee('RSC-CLOTURE-APRES', 'PDL_CLOTURE_APRES')
        self._grille_moulin('Grille Clôture Après')
        souscription.date_fin = date(2024, 6, 11)

        campagne_juillet = self._campagne(date(2024, 7, 1))
        self.assertNotIn(souscription, campagne_juillet._souscriptions_facturables())

        # Même si electricore renverrait encore une méta-période de juillet
        # pour cette RSC, le périmètre — pas le flux — est la garde.
        meta_juillet = SimpleNamespace(
            ref_situation_contractuelle='RSC-CLOTURE-APRES',
            pdl='PDL_CLOTURE_APRES',
            mois_annee='2024-07',
            debut='2024-07-01',
            fin='2024-08-01',
            nb_jours=31,
            puissance_moyenne_kva=6.0,
            energie_base_kwh=200.0,
            energie_hp_kwh=None,
            energie_hc_kwh=None,
            turpe_fixe_eur=8.5,
            turpe_variable_eur=3.0,
            cta_eur=1.0,
            taux_accise_eur_mwh=21.0,
            has_changement=False,
            qualite='réelle',
            statut_communication='communicante',
            releves_utilises=[],
            source_hash='H-JUILLET-JAMAIS',
        )
        with patcher_client_fabrique(client_flux_factice('meta_periodes', [meta_juillet])):
            campagne_juillet.action_pull_meta_periodes()

        self.assertFalse(
            self.env['souscription.periode'].search(
                [('souscription_id', '=', souscription.id), ('mois', '=', date(2024, 7, 1))]
            ),
            'souscription hors périmètre de juillet : aucune Période créée malgré le flux',
        )

    # --- Idempotence structurelle : hors de la file, non-événement ---

    def test_regulariser_clotures_reste_no_op_une_fois_resiliee(self):
        souscription = self._souscription_lissee('RSC-CLOTURE-IDEMP', 'PDL_CLOTURE_IDEMP')
        self._grille_moulin('Grille Clôture Idemp')
        self._periode_legacy(souscription, 1, energie_base_kwh=225.0)
        souscription.date_fin = date(2024, 1, 31)

        campagne = self._campagne(date(2024, 2, 1))
        with self._sans_appel_reseau():
            campagne.action_regulariser_clotures()
        self.assertEqual(souscription.etat, 'resiliee')
        nb_regularisations = len(souscription.regularisation_ids)

        with self._sans_appel_reseau():
            campagne.action_regulariser_clotures()

        self.assertEqual(len(souscription.regularisation_ids), nb_regularisations, 'plus dans la file : non-événement')
