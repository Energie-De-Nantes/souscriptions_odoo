"""Tests de la Régularisation (solde) — CONTEXT.md, ADR 0030 décisions 3-4,
tranche 4 du PRD #231 (#236).

Modèle propre (même motif que la Refacturation, ADR 0009) : en-tête par
Souscription + lignes typées grille × cadran, calculées à partir des mois
« candidats » (facturés, écart non nul, mesuré connu, non soldés en legacy,
compteur communicant). Toujours en brouillon dans cette tranche : ni
génération de facture (tranche 5, #237) ni tampon (tranche 6, #238).

« Facturée », dans ces tests, est simulée par `facture_legacy_ref` (même
convention que `creer_factures` : `facture_id OU facture_legacy_ref`) — plus
simple qu'une vraie facture, et sémantiquement identique pour le calcul des
candidats.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import (
    SouscriptionsTestCase,
    build_grille_lignes,
    client_flux_factice,
    flux_electricore,
    patcher_client_fabrique,
)


def _meta_stub(**kwargs):
    """Stub duck-typé minimal de `PeriodeMeta` (contrat v3) — mêmes attributs
    que le stub de test_pull_meta_periodes.py, dupliqué ici (petit, local)
    pour ne pas coupler les deux suites de tests."""
    base = dict(
        ref_situation_contractuelle='RSC-REGUL-AC4',
        debut='2024-02-01',
        fin='2024-03-01',
        mois_annee='2024-02',
        puissance_moyenne_kva=6.0,
        energie_base_kwh=230.0,
        energie_hp_kwh=None,
        energie_hc_kwh=None,
        turpe_fixe_eur=0.0,
        turpe_variable_eur=0.0,
        cta_eur=0.0,
        taux_accise_eur_mwh=0.0,
        has_changement=False,
        qualite='réelle',
        statut_communication='communicante',
        releves_utilises=[],
        source_hash='H-FEB',
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@tagged('souscriptions', 'souscriptions_regularisation', 'post_install', '-at_install')
class TestRegularisationCandidats(SouscriptionsTestCase):
    """Calcul des candidats et ventilation des lignes (`_recalculer`)."""

    def _souscription_lissee(self, ref='RSC-REGUL', pdl='PDL_REGUL', provision=200.0, tarif_solidaire=False):
        return self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': pdl,
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'date_debut': date(2023, 1, 1),
                'lisse': True,
                'provision_mensuelle_kwh': provision,
                'regime_prix': 'moulin',  # regime dédié : n'entre pas en collision
                'ref_situation_contractuelle': ref,
                'tarif_solidaire': tarif_solidaire,
            }
        )

    def _grille_moulin(self, name='Grille Moulin', date_debut=date(2024, 1, 1), prix_base=0.15):
        # date_fin est dérivée (#309) : jamais passée en création.
        grille = self.env['grille.prix'].create(
            {
                'name': name,
                'date_debut': date_debut,
                'active': True,
                'regime_prix': 'moulin',
            }
        )
        build_grille_lignes(self.env, grille, prix_base=prix_base, prix_hp=0.18, prix_hc=0.12)
        return grille

    def _periode_facturee(self, souscription, mois_index, **overrides):
        """Une Période mensuelle 2024, déjà « facturée » côté legacy
        (`facture_legacy_ref` — même convention que `creer_factures`),
        candidate par défaut (réelle, communicante, non soldée)."""
        debut = date(2024, mois_index, 1)
        fin = date(2024, mois_index + 1, 1) if mois_index < 12 else date(2025, 1, 1)
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

    # --- AC1 : lissée, écart ventilé par grille × cadran ---

    def test_ac1_ecart_ventile_par_grille_cadran(self):
        """12 mensuelles à 200 kWh provisionnés, mesuré total 2 600 kWh ->
        brouillon avec Σ écarts = 200 kWh, une ligne grille × cadran (une
        seule grille sur toute la période)."""
        souscription = self._souscription_lissee(ref='RSC-REGUL-AC1', pdl='PDL_REGUL_AC1')
        grille = self._grille_moulin(name='Grille AC1')

        energies = {6: 220.0, 12: 380.0}  # écarts concentrés sur 2 mois : 20 + 180 = 200
        for m in range(1, 13):
            self._periode_facturee(souscription, m, energie_base_kwh=energies.get(m, 200.0))

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with patcher_client_fabrique(client_flux_factice('meta_periodes', [])):
            regularisation._recalculer()

        self.assertEqual(len(regularisation.ligne_ids), 1)
        ligne = regularisation.ligne_ids
        self.assertEqual(ligne.cadran, 'base')
        self.assertEqual(ligne.grille_id, grille)
        self.assertAlmostEqual(ligne.ecart_kwh, 200.0, places=2)
        self.assertAlmostEqual(ligne.prix_kwh, 0.15, places=6)
        self.assertAlmostEqual(ligne.montant, 30.0, places=2)
        self.assertEqual(regularisation.date_debut, date(2024, 1, 1))
        self.assertEqual(regularisation.date_fin, date(2025, 1, 1))
        self.assertAlmostEqual(regularisation.montant_total, 30.0, places=2)
        self.assertFalse(ligne.tarif_solidaire, 'snapshot standard par défaut')

    def test_ac1bis_tarif_solidaire_snapshotte_sur_la_ligne(self):
        """Le solidaire (ADR 0013) est figé sur la ligne au calcul des
        candidats — support du choix du produit de facturation à la
        projection facture (tranche 5, #237), sans relire la Souscription."""
        souscription = self._souscription_lissee(ref='RSC-REGUL-AC1BIS', pdl='PDL_REGUL_AC1BIS', tarif_solidaire=True)
        self._grille_moulin(name='Grille AC1BIS')
        self._periode_facturee(souscription, 1, energie_base_kwh=220.0)

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with patcher_client_fabrique(client_flux_factice('meta_periodes', [])):
            regularisation._recalculer()

        self.assertTrue(regularisation.ligne_ids.tarif_solidaire)

    # --- AC2 : changement de grille en cours d'année ---

    def test_ac2_changement_de_grille_deux_lignes(self):
        """Un changement de grille en cours d'année -> deux lignes (une par
        grille), chacune aux prix de sa sous-période."""
        souscription = self._souscription_lissee(ref='RSC-REGUL-AC2', pdl='PDL_REGUL_AC2')
        grille1 = self._grille_moulin(name='Grille AC2 - 1', date_debut=date(2024, 1, 1), prix_base=0.15)
        # Nouvelle grille moulin à partir du 1er juillet (un changement de
        # grille tombe toujours un 1er, #309) : la Période de juin
        # (date_debut = 2024-06-01) sélectionne toujours grille1, celle de
        # juillet (date_debut = 2024-07-01) sélectionne grille2.
        grille2 = self._grille_moulin(name='Grille AC2 - 2', date_debut=date(2024, 7, 1), prix_base=0.20)

        for m in range(1, 7):  # janvier à juin : écart 10 kWh/mois -> grille1
            self._periode_facturee(souscription, m, energie_base_kwh=210.0)
        for m in range(7, 13):  # juillet à décembre : écart 25 kWh/mois -> grille2
            self._periode_facturee(souscription, m, energie_base_kwh=225.0)

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with patcher_client_fabrique(client_flux_factice('meta_periodes', [])):
            regularisation._recalculer()

        self.assertEqual(len(regularisation.ligne_ids), 2)
        ligne1 = regularisation.ligne_ids.filtered(lambda l: l.grille_id == grille1)
        ligne2 = regularisation.ligne_ids.filtered(lambda l: l.grille_id == grille2)
        self.assertAlmostEqual(ligne1.ecart_kwh, 60.0, places=2)
        self.assertAlmostEqual(ligne1.prix_kwh, 0.15, places=6)
        self.assertAlmostEqual(ligne2.ecart_kwh, 150.0, places=2)
        self.assertAlmostEqual(ligne2.prix_kwh, 0.20, places=6)

    # --- AC3 : exclusions ---

    def test_ac3_mois_incalculable_hors_candidats_et_signale(self):
        souscription = self._souscription_lissee(ref='RSC-REGUL-AC3A', pdl='PDL_REGUL_AC3A')
        self._grille_moulin(name='Grille AC3A')
        exclue = self._periode_facturee(souscription, 1, qualite='incalculable', energie_base_kwh=250.0)
        self._periode_facturee(souscription, 2, energie_base_kwh=220.0)  # candidate, écart 20

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with patcher_client_fabrique(client_flux_factice('meta_periodes', [])):
            regularisation._recalculer()

        self.assertEqual(len(regularisation.ligne_ids), 1)
        self.assertAlmostEqual(regularisation.ligne_ids.ecart_kwh, 20.0, places=2)
        self.assertNotIn(exclue.id, regularisation.ligne_ids.periode_ids.ids)
        self.assertIn('hors candidats', regularisation.signalements)
        self.assertIn(exclue.mois_annee, regularisation.signalements)

    def test_ac3_mois_absent_hors_candidats_et_signale(self):
        """Un verdict absent (qualité vide/False) est traité comme
        « incalculable » — hors candidats, signalé."""
        souscription = self._souscription_lissee(ref='RSC-REGUL-AC3B', pdl='PDL_REGUL_AC3B')
        self._grille_moulin(name='Grille AC3B')
        exclue = self._periode_facturee(souscription, 1, qualite=False, energie_base_kwh=250.0)

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with patcher_client_fabrique(client_flux_factice('meta_periodes', [])):
            regularisation._recalculer()

        self.assertFalse(regularisation.ligne_ids)
        self.assertIn('hors candidats', regularisation.signalements)
        self.assertIn(exclue.mois_annee, regularisation.signalements)

    def test_ac3_mois_legacy_regularisee_exclu_silencieusement(self):
        souscription = self._souscription_lissee(ref='RSC-REGUL-AC3C', pdl='PDL_REGUL_AC3C')
        self._grille_moulin(name='Grille AC3C')
        soldee = self._periode_facturee(
            souscription, 1, legacy_regularisee=True, energie_base_kwh=300.0
        )  # écart 100, mais déjà soldée en legacy
        self._periode_facturee(souscription, 2, energie_base_kwh=220.0)  # candidate, écart 20

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with patcher_client_fabrique(client_flux_factice('meta_periodes', [])):
            regularisation._recalculer()

        self.assertEqual(len(regularisation.ligne_ids), 1)
        self.assertAlmostEqual(regularisation.ligne_ids.ecart_kwh, 20.0, places=2)
        self.assertNotIn(soldee.id, regularisation.ligne_ids.periode_ids.ids)

    def test_ac3_souscription_non_communicante_ecartee_avec_message(self):
        souscription = self._souscription_lissee(ref='RSC-REGUL-AC3D', pdl='PDL_REGUL_AC3D')
        self._grille_moulin(name='Grille AC3D')
        self._periode_facturee(souscription, 1, statut_communication='non_communicante', energie_base_kwh=250.0)

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        regularisation._recalculer()  # aucun appel réseau : écarté avant le refresh

        self.assertFalse(regularisation.ligne_ids)
        self.assertIn('non communicant', regularisation.signalements)

    # --- AC4 : mois conservé au refresh -> « estimation locale » ---

    def test_ac4_mois_conserve_marque_estimation_locale(self):
        """Un mois dont le refresh n'a rien pu confirmer (flux vide ce
        tour-ci) reste candidat sur son verdict déjà stocké, mais son détail
        est marqué « estimation locale » — contrairement au mois voisin
        effectivement rafraîchi ce tour-ci."""
        souscription = self._souscription_lissee(ref='RSC-REGUL-AC4', pdl='PDL_REGUL_AC4')
        self._grille_moulin(name='Grille AC4')
        janvier = self._periode_facturee(souscription, 1, qualite='estimée', energie_base_kwh=220.0)
        fevrier = self._periode_facturee(souscription, 2, qualite='réelle', energie_base_kwh=230.0)

        client = MagicMock()
        # Un appel par mois candidat, dans l'ordre chronologique : janvier
        # d'abord (flux vide -> conservée), février ensuite (flux fiable,
        # nouvelle empreinte -> rafraîchie).
        client.meta_periodes.side_effect = [
            flux_electricore([]),
            flux_electricore([_meta_stub()]),
        ]

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with patcher_client_fabrique(client):
            regularisation._recalculer()

        self.assertEqual(len(regularisation.ligne_ids), 1)
        detail_lignes = regularisation.ligne_ids.detail.split('\n')
        ligne_janvier = next(l for l in detail_lignes if janvier.mois_annee in l)
        ligne_fevrier = next(l for l in detail_lignes if fevrier.mois_annee in l)
        self.assertIn('estimation locale', ligne_janvier)
        self.assertNotIn('estimation locale', ligne_fevrier)

    # --- AC5 : recalcul idempotent ---

    def test_ac5_recalcul_idempotent_a_donnees_constantes(self):
        souscription = self._souscription_lissee(ref='RSC-REGUL-AC5', pdl='PDL_REGUL_AC5')
        self._grille_moulin(name='Grille AC5')
        for m in range(1, 4):
            self._periode_facturee(souscription, m, energie_base_kwh=220.0)  # écart 20/mois

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        client = client_flux_factice('meta_periodes', [])
        with patcher_client_fabrique(client):
            regularisation._recalculer()
        self.assertEqual(len(regularisation.ligne_ids), 1)
        ecart_1, montant_1 = regularisation.ligne_ids.ecart_kwh, regularisation.ligne_ids.montant

        with patcher_client_fabrique(client):
            regularisation._recalculer()

        self.assertEqual(len(regularisation.ligne_ids), 1, 'reconstruites, pas dupliquées')
        self.assertAlmostEqual(regularisation.ligne_ids.ecart_kwh, ecart_1, places=2)
        self.assertAlmostEqual(regularisation.ligne_ids.montant, montant_1, places=2)


@tagged('souscriptions', 'souscriptions_regularisation', 'post_install', '-at_install')
class TestRegularisationBouton(SouscriptionsTestCase):
    """Bouton « Régulariser » sur la Souscription : trouve ou crée le
    brouillon puis délègue le recalcul (#236)."""

    def test_action_regulariser_trouve_ou_cree_le_brouillon(self):
        self.assertFalse(self.souscription_base.regularisation_ids)

        self.souscription_base.action_regulariser()
        self.assertEqual(len(self.souscription_base.regularisation_ids), 1)
        premiere = self.souscription_base.regularisation_ids

        self.souscription_base.action_regulariser()
        self.assertEqual(len(self.souscription_base.regularisation_ids), 1, 'jamais un second brouillon')
        self.assertEqual(self.souscription_base.regularisation_ids, premiere)

    def test_action_regulariser_nouveau_brouillon_si_la_precedente_est_facturee(self):
        """Une fois la Régularisation facturée (verrouillée, tranche 5 #237),
        le bouton en ouvre une nouvelle plutôt que de heurter le verrou de
        `_recalculer`."""
        self.souscription_base.action_regulariser()
        premiere = self.souscription_base.regularisation_ids
        self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner_test.id,
                'regularisation_id': premiere.id,
            }
        )
        self.assertEqual(premiere.etat, 'facturee')

        self.souscription_base.action_regulariser()

        self.assertEqual(len(self.souscription_base.regularisation_ids), 2)
        nouvelle = self.souscription_base.regularisation_ids - premiere
        self.assertEqual(nouvelle.etat, 'brouillon')


@tagged('souscriptions', 'souscriptions_regularisation', 'post_install', '-at_install')
class TestRegularisationLiens(SouscriptionsTestCase):
    """Contraintes des liens posés (ADR 0030 décision 5, amende ADR-0004)."""

    def test_move_jamais_periode_et_regularisation(self):
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        regularisation = self.env['souscription.regularisation'].create({'souscription_id': self.souscription_base.id})
        with self.assertRaises(ValidationError):
            self.env['account.move'].create(
                {
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_test.id,
                    'periode_id': periode.id,
                    'regularisation_id': regularisation.id,
                }
            )

    def test_move_periode_seule_ok(self):
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        move = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner_test.id,
                'periode_id': periode.id,
            }
        )
        self.assertTrue(move.periode_id)
        self.assertFalse(move.regularisation_id)

    def test_releve_exactement_un_parent_regularisation_seule(self):
        regularisation = self.env['souscription.regularisation'].create({'souscription_id': self.souscription_base.id})
        releve = self.env['souscription.releve'].create(
            {'regularisation_id': regularisation.id, 'date': date(2024, 1, 1), 'nature': 'reel'}
        )
        self.assertIn(releve, regularisation.releve_ids)
        self.assertFalse(releve.periode_id)

    # Contrainte SQL (pas un `@api.constrains`, qui ne se déclencherait pas
    # sur un create omettant les deux parents) : violation à la flush, même
    # idiome que les tests d'unicité du repo.
    def test_releve_sans_parent_refuse(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['souscription.releve'].create({'date': date(2024, 1, 1), 'nature': 'reel'})

    def test_releve_deux_parents_refuse(self):
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        regularisation = self.env['souscription.regularisation'].create({'souscription_id': self.souscription_base.id})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['souscription.releve'].create(
                {
                    'periode_id': periode.id,
                    'regularisation_id': regularisation.id,
                    'date': date(2024, 1, 1),
                    'nature': 'reel',
                }
            )


@tagged('souscriptions', 'souscriptions_regularisation', 'post_install', '-at_install')
class TestRegularisationVuesEtSecurite(SouscriptionsTestCase):
    """Sécurité/vues du nouveau modèle (dernier point de l'AC #236)."""

    def test_action_regularisation_existe(self):
        action = self.env.ref('souscriptions_odoo.action_souscription_regularisation')
        self.assertEqual(action.res_model, 'souscription.regularisation')
        self.assertIn('list', action.view_mode)

    def test_menu_regularisation_sous_souscriptions(self):
        menu = self.env.ref('souscriptions_odoo.menu_souscription_regularisation')
        self.assertEqual(menu.parent_id, self.env.ref('souscriptions_odoo.menu_souscription_root'))

    def test_acl_enregistrees_pour_les_deux_nouveaux_modeles(self):
        for model_name in ('souscription.regularisation', 'souscription.regularisation.ligne'):
            accesses = self.env['ir.model.access'].search([('model_id.model', '=', model_name)])
            self.assertTrue(accesses, f'ACL manquante pour {model_name}')


@tagged('souscriptions', 'souscriptions_regularisation', 'post_install', '-at_install')
class TestRegularisationEtatEtVerrou(SouscriptionsTestCase):
    """État dérivé du lien facture + verrou du recalcul (tranche 5, #237) —
    même motif que le verrou de facturation de la Période (#14)."""

    def test_brouillon_par_defaut_sans_facture(self):
        regularisation = self.env['souscription.regularisation'].create({'souscription_id': self.souscription_base.id})
        self.assertEqual(regularisation.etat, 'brouillon')
        self.assertFalse(regularisation.facture_id)

    def test_facturee_des_qu_une_facture_ou_un_avoir_reference_la_regularisation(self):
        regularisation = self.env['souscription.regularisation'].create({'souscription_id': self.souscription_base.id})
        move = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner_test.id,
                'regularisation_id': regularisation.id,
            }
        )
        self.assertEqual(regularisation.facture_id, move)
        self.assertEqual(regularisation.etat, 'facturee')

    def _regularisation_avec_ligne(self):
        regularisation = self.env['souscription.regularisation'].create({'souscription_id': self.souscription_base.id})
        self.env['souscription.regularisation.ligne'].create(
            {
                'regularisation_id': regularisation.id,
                'grille_id': self.grille_prix.id,
                'cadran': 'base',
                'ecart_kwh': 20.0,
                'prix_kwh': 0.15,
                'detail': 'Janvier 2024 : 20.00 kWh',
            }
        )
        return regularisation

    def test_recalcul_autorise_tant_que_la_facture_liee_est_en_brouillon(self):
        """#267 : le recalcul reste autorisé pendant la fenêtre brouillon
        d'une Facture liée — avant #267, toute Facture (brouillon compris)
        bloquait le recalcul dès qu'elle existait."""
        regularisation = self._regularisation_avec_ligne()
        regularisation._creer_facture()
        self.assertEqual(regularisation.facture_id.state, 'draft')

        regularisation._recalculer()  # ne lève rien

    def test_recalcul_refuse_une_fois_la_facture_emise(self):
        """La Facture ÉMISE (postée), pas seulement existante, verrouille le
        recalcul (#267, condition dérivée)."""
        regularisation = self._regularisation_avec_ligne()
        regularisation._creer_facture()
        regularisation.facture_id.action_post()

        with self.assertRaises(UserError):
            regularisation._recalculer()

    def test_action_recalculer_recompose_le_brouillon_lie(self):
        """#267, point d'entrée (d) : `action_recalculer` recompose le
        brouillon de Facture lié juste après avoir reconstruit les lignes —
        le facturiste voit tout de suite l'effet du recalcul sur le
        document, sans devoir le rouvrir. `souscription_base` ne porte aucune
        Période facturée : un recalcul réel n'y trouve aucun candidat, donc
        vide `ligne_ids` — la preuve que le brouillon suit est que sa ligne
        produit disparaît avec, dans le même geste."""
        regularisation = self._regularisation_avec_ligne()
        facture = regularisation._creer_facture()
        self.assertTrue(facture.invoice_line_ids.filtered(lambda l: l.product_id))

        regularisation.action_recalculer()

        self.assertFalse(regularisation.ligne_ids, 'aucun candidat réel : le recalcul vide les lignes')
        self.assertFalse(
            facture.invoice_line_ids.filtered(lambda l: l.product_id),
            'le brouillon a été recomposé en phase avec le recalcul',
        )
