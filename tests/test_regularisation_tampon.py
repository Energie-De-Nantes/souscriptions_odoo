"""Tampon d'émission — provision += écart, trace, idempotence (ADR 0030
décision 4, tranche 6 du PRD #231, #238).

`_recalculer()` (candidats, tranche 4 #236) et `_creer_facture()` (projection
facture, tranche 5 #237) sont déjà couverts par test_regularisation.py et
test_regularisation_facture.py — ici on isole le TAMPON : ce qui se passe à
l'ÉMISSION (jamais au brouillon) d'une facture portant `regularisation_id`.
Invariant gravé (ADR 0030) : la provision n'évolue que par l'émission d'une
facture qui la porte.
"""

from datetime import date
from types import SimpleNamespace

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase, build_grille_lignes, client_flux_factice, patcher_client_fabrique


def _meta_stub(**kwargs):
    """Stub duck-typé minimal de `PeriodeMeta` (contrat v3), même idiome que
    test_regularisation.py — simule un mesuré raffiné (nouvelle empreinte)
    après le solde d'une première Régularisation (AC « re-régul »)."""
    base = dict(
        ref_situation_contractuelle='RSC-TAMPON',
        debut='2024-01-01',
        fin='2024-02-01',
        mois_annee='2024-01',
        puissance_moyenne_kva=6.0,
        energie_base_kwh=0.0,
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
        source_hash='H-TAMPON',
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@tagged('souscriptions', 'souscriptions_regularisation', 'post_install', '-at_install')
class TestRegularisationTamponEmission(SouscriptionsTestCase):
    """Le solde par tampon (#238) : émission -> provisions tamponnées, écarts
    à zéro, trace posée — jamais au brouillon."""

    def _souscription_lissee(self, ref, pdl, type_tarif='base', provision=200.0, tarif_solidaire=False):
        vals = {
            'partner_id': self.partner_test.id,
            'pdl': pdl,
            'puissance_souscrite': '6',
            'type_tarif': type_tarif,
            'date_debut': date(2023, 1, 1),
            'lisse': True,
            'regime_prix': 'moulin',  # regime dédié : n'entre pas en collision avec cls.grille_prix
            'ref_situation_contractuelle': ref,
            'tarif_solidaire': tarif_solidaire,
        }
        if type_tarif == 'hphc':
            vals['provision_hp_kwh'] = 200.0
            vals['provision_hc_kwh'] = 120.0
        else:
            vals['provision_mensuelle_kwh'] = provision
        return self.env['souscription.souscription'].create(vals)

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

    def _periode_facturee(self, souscription, mois_index, **overrides):
        """Une Période mensuelle 2024 déjà « facturée » côté legacy
        (`facture_legacy_ref`, même convention que test_regularisation.py) —
        candidate par défaut (réelle, communicante)."""
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

    def _sans_appel_reseau(self):
        return patcher_client_fabrique(client_flux_factice('meta_periodes', []))

    # --- AC1 : émission -> provisions tamponnées, écarts à zéro, trace ---

    def test_emission_tamponne_lecart_et_pose_la_trace_meme_a_ecart_nul(self):
        """Une mensuelle à écart non nul reçoit `provision += écart` (écart
        retombe à zéro) ; une mensuelle couverte à écart NUL ne reçoit aucun
        tampon utile (+=0) mais porte quand même la trace — « chaque
        mensuelle couverte », pas seulement celles à écart non nul."""
        souscription = self._souscription_lissee(ref='RSC-TAMPON-1', pdl='PDL_TAMPON_1')
        self._grille_moulin('Grille Tampon 1')
        zero = self._periode_facturee(souscription, 1, energie_base_kwh=200.0)  # écart 0
        non_zero = self._periode_facturee(souscription, 2, energie_base_kwh=225.0)  # écart 25

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with self._sans_appel_reseau():
            regularisation._recalculer()
        self.assertEqual(len(regularisation.ligne_ids), 1)
        self.assertAlmostEqual(regularisation.ligne_ids.ecart_kwh, 25.0, places=2)

        facture = regularisation._creer_facture()
        self.assertEqual(facture.state, 'draft')
        # Avant émission : rien ne bouge (brouillon).
        self.assertFalse(non_zero.regularisation_id)
        self.assertEqual(non_zero.provision_base_kwh, 200.0)

        facture.action_post()

        self.assertEqual(non_zero.provision_base_kwh, 225.0)
        self.assertEqual(non_zero.ecart_base_kwh, 0.0)
        self.assertEqual(non_zero.regularisation_id, regularisation)
        # Écart nul : provision inchangée (200 = 200 + 0), trace posée quand même.
        self.assertEqual(zero.provision_base_kwh, 200.0)
        self.assertEqual(zero.ecart_base_kwh, 0.0)
        self.assertEqual(zero.regularisation_id, regularisation)

    def test_emission_tamponne_hp_et_hc_independamment_sur_la_meme_periode(self):
        """Une Période HP/HC contribue à DEUX lignes (une par cadran) : le
        tampon doit ajouter l'écart HP à la provision HP et l'écart HC à la
        provision HC, sans se marcher dessus."""
        souscription = self._souscription_lissee(ref='RSC-TAMPON-HPHC', pdl='PDL_TAMPON_HPHC', type_tarif='hphc')
        self._grille_moulin('Grille Tampon HPHC')
        periode = self._periode_facturee(
            souscription,
            1,
            provision_hp_kwh=200.0,
            provision_hc_kwh=120.0,
            energie_hp_kwh=215.0,  # écart +15
            energie_hc_kwh=100.0,  # écart -20
        )

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with self._sans_appel_reseau():
            regularisation._recalculer()
        self.assertEqual(len(regularisation.ligne_ids), 2, 'une ligne par cadran')

        facture = regularisation._creer_facture()
        facture.action_post()

        self.assertEqual(periode.provision_hp_kwh, 215.0)
        self.assertEqual(periode.provision_hc_kwh, 100.0)
        self.assertEqual(periode.ecart_hp_kwh, 0.0)
        self.assertEqual(periode.ecart_hc_kwh, 0.0)
        self.assertEqual(periode.regularisation_id, regularisation)

    # --- AC2 : Σ provisions == énergie totale facturée, sans double comptage ---

    def test_somme_des_provisions_egale_lenergie_totale_facturee(self):
        souscription = self._souscription_lissee(ref='RSC-TAMPON-SUM', pdl='PDL_TAMPON_SUM')
        self._grille_moulin('Grille Tampon Sum')
        p1 = self._periode_facturee(souscription, 1, energie_base_kwh=200.0)  # écart 0
        p2 = self._periode_facturee(souscription, 2, energie_base_kwh=220.0)  # écart +20
        p3 = self._periode_facturee(souscription, 3, energie_base_kwh=170.0)  # écart -30
        periodes = p1 + p2 + p3
        energie_totale = sum(periodes.mapped('energie_base_kwh'))

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with self._sans_appel_reseau():
            regularisation._recalculer()
        facture = regularisation._creer_facture()
        self.assertEqual(facture.move_type, 'out_refund', 'net -10 : avoir')

        facture.action_post()

        self.assertAlmostEqual(sum(periodes.mapped('provision_base_kwh')), energie_totale, places=2)
        for periode in periodes:
            self.assertAlmostEqual(periode.ecart_base_kwh, 0.0, places=6)

    # --- AC5 : rien avant émission ---

    def test_facture_brouillon_non_postee_aucun_tampon_ni_trace(self):
        souscription = self._souscription_lissee(ref='RSC-TAMPON-DRAFT', pdl='PDL_TAMPON_DRAFT')
        self._grille_moulin('Grille Tampon Draft')
        periode = self._periode_facturee(souscription, 1, energie_base_kwh=230.0)  # écart 30

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with self._sans_appel_reseau():
            regularisation._recalculer()
        facture = regularisation._creer_facture()

        self.assertEqual(facture.state, 'draft')
        self.assertEqual(periode.provision_base_kwh, 200.0)
        self.assertFalse(periode.regularisation_id)

    def test_supprimer_une_facture_non_postee_ne_laisse_aucune_trace_et_delock_le_recalcul(self):
        """Supprimer un brouillon (facture non postée) : aucun tampon, aucune
        trace — et la Régularisation redevient recalculable (verrou #237
        levé, `facture_id` retombe à vide)."""
        souscription = self._souscription_lissee(ref='RSC-TAMPON-DEL', pdl='PDL_TAMPON_DEL')
        self._grille_moulin('Grille Tampon Del')
        periode = self._periode_facturee(souscription, 1, energie_base_kwh=230.0)

        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with self._sans_appel_reseau():
            regularisation._recalculer()
        facture = regularisation._creer_facture()

        facture.unlink()

        self.assertFalse(periode.regularisation_id)
        self.assertEqual(periode.provision_base_kwh, 200.0)
        self.assertEqual(regularisation.etat, 'brouillon')

        with self._sans_appel_reseau():
            regularisation._recalculer()  # ne lève plus UserError : dé-verrouillée
        self.assertEqual(len(regularisation.ligne_ids), 1)

    # --- AC3 : idempotence — relancer juste après émission -> zéro candidat ---

    def test_relancer_une_regularisation_juste_apres_emission_zero_candidat(self):
        souscription = self._souscription_lissee(ref='RSC-TAMPON-IDEMP', pdl='PDL_TAMPON_IDEMP')
        self._grille_moulin('Grille Tampon Idemp')
        self._periode_facturee(souscription, 1, energie_base_kwh=222.0)  # écart 22

        regularisation1 = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with self._sans_appel_reseau():
            regularisation1._recalculer()
        facture1 = regularisation1._creer_facture()
        facture1.action_post()

        regularisation2 = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with self._sans_appel_reseau():
            regularisation2._recalculer()

        self.assertFalse(regularisation2.ligne_ids, 'écarts soldés par le tampon : plus aucun candidat')

    # --- AC4 : re-régul — mesuré raffiné après solde, la trace pointe la dernière ---

    def test_mesure_raffine_apres_solde_fait_renaitre_lecart_la_trace_pointe_la_derniere(self):
        souscription = self._souscription_lissee(ref='RSC-TAMPON-REGUL2', pdl='PDL_TAMPON_REGUL2')
        self._grille_moulin('Grille Tampon Regul2')
        periode = self._periode_facturee(souscription, 1, energie_base_kwh=220.0)  # écart 20

        regularisation1 = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with self._sans_appel_reseau():
            regularisation1._recalculer()
        facture1 = regularisation1._creer_facture()
        facture1.action_post()

        self.assertEqual(periode.provision_base_kwh, 220.0)
        self.assertEqual(periode.ecart_base_kwh, 0.0)
        self.assertEqual(periode.regularisation_id, regularisation1)

        # Mesuré raffiné (nouvelle empreinte, exemption ciblée du verrou #235) :
        # l'écart renaît.
        periode._rafraichir_depuis_meta(_meta_stub(source_hash='H-TAMPON-REFINE', energie_base_kwh=235.0))
        self.assertAlmostEqual(periode.ecart_base_kwh, 15.0, places=2)

        regularisation2 = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with self._sans_appel_reseau():
            regularisation2._recalculer()
        self.assertEqual(len(regularisation2.ligne_ids), 1)
        self.assertAlmostEqual(regularisation2.ligne_ids.ecart_kwh, 15.0, places=2)

        facture2 = regularisation2._creer_facture()
        facture2.action_post()

        self.assertEqual(periode.provision_base_kwh, 235.0)
        self.assertEqual(periode.ecart_base_kwh, 0.0)
        self.assertEqual(periode.regularisation_id, regularisation2, 'la trace pointe la dernière')

    # --- Émise = immuable (grill #259) : la correction passe par une nouvelle
    # Régularisation ou par un avoir, jamais par mutation du move émis — sans
    # quoi un re-post re-consommerait les écarts figés (double-tampon).

    def _regul_emise(self):
        souscription = self._souscription_lissee(ref='RSC-IMMU', pdl='PDL_TAMPON_IMMU')
        self._grille_moulin('Grille immuable')
        periode = self._periode_facturee(souscription, 1, energie_base_kwh=225.0)
        regularisation = self.env['souscription.regularisation'].create({'souscription_id': souscription.id})
        with self._sans_appel_reseau():
            regularisation._recalculer()
        facture = regularisation._creer_facture()
        facture.action_post()
        return periode, regularisation, facture

    def test_remise_en_brouillon_dune_regul_emise_refusee(self):
        periode, _regularisation, facture = self._regul_emise()
        self.assertEqual(periode.provision_base_kwh, 225.0)
        with self.assertRaises(UserError):
            facture.button_draft()
        self.assertEqual(facture.state, 'posted')
        self.assertEqual(periode.provision_base_kwh, 225.0, 'provision intacte après la tentative')

    def test_annulation_dune_regul_emise_refusee(self):
        periode, _regularisation, facture = self._regul_emise()
        with self.assertRaises(UserError):
            facture.button_cancel()
        self.assertEqual(facture.state, 'posted')
        self.assertEqual(periode.provision_base_kwh, 225.0)

    def test_copie_dune_regul_emise_ne_porte_pas_la_regularisation(self):
        """`copy=False` : un duplicate — et l'avoir Odoo, qui passe par
        `copy_data` — ne porte pas `regularisation_id`, donc son post ne
        re-tamponne rien (le chemin « avoir manuel » reste sûr)."""
        periode, _regularisation, facture = self._regul_emise()
        double = facture.copy()
        self.assertFalse(double.regularisation_id)
        self.assertEqual(periode.provision_base_kwh, 225.0)
