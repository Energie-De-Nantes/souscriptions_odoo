"""Tests transverses du gel à l'émission (tranche 3 du PRD #264, #267).

Le gel de la Période passe de « une facture existe » à « la facture est
ÉMISE » (postée) — condition **dérivée** (`souscription.periode._est_facturee_emise`),
pas un champ écrit. Chaque mécanisme touché (tampon de provision, verrou
Période/Relevé, régénération au fil de l'eau) est déjà couvert au grain fin
dans son propre fichier de test (test_periode_composition.py,
test_periode_snapshot.py, test_releve.py, test_pull_meta_periodes.py,
test_sync_prestations.py, test_regularisation.py, test_periode_facture.py,
test_campagne_signaux.py). Ce fichier isole ce que ces suites, prises
séparément, ne montrent pas : l'ORDRE observable des effets à l'émission
(AC « effets observables dans cet ordre ») et la preuve consolidée, sur les
trois surfaces gouvernées par la même condition dérivée (Période, Relevé,
Régularisation), que rien ne migre — le dé-gel des enregistrements
« gelés » sous l'ancien régime est un pur effet de bord du changement de
condition.
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_gel_emission', 'post_install', '-at_install')
class TestOrdreEmission(SouscriptionsTestCase):
    """AC #267 : « L'émission tamponne la provision (non-lissé), re-génère,
    poste, verrouille Période et Relevés — effets observables dans cet
    ordre. »"""

    def test_tampon_regeneration_post_et_verrou_dans_cet_ordre(self):
        periode = self.create_test_periode(self.souscription_base, energie_base_kwh=280.0)
        Releve = self.env['souscription.releve']
        releve = Releve.create({'periode_id': periode.id, 'date': date(2024, 1, 1), 'index_base': 1000})
        facture = periode._creer_facture()

        # Avant émission : brouillon, rien de gelé — la fenêtre brouillon est
        # vivante (#267 AC « une Période dont la facture est en brouillon
        # reste éditable »).
        self.assertEqual(facture.state, 'draft')
        self.assertEqual(periode.provision_base_kwh, 0.0, 'pas encore tamponnée')
        periode.write({'provision_base_kwh': 42.0})  # ne lève rien : pas gelée
        releve.index_base = 1234  # ne lève rien : pas gelé
        self.assertEqual(periode.provision_base_kwh, 42.0)
        # La Période éditée a régénéré le brouillon (#267, point d'entrée b) —
        # la ligne Énergie Base reflète encore le mesuré (pas tamponnée).
        ligne_avant_post = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        self.assertEqual(ligne_avant_post.quantity, 280.0, 'mesuré, la provision écrite ci-dessus est ignorée')

        facture.action_post()  # ÉMISSION : unique événement de gel

        # 1. Tampon : provision_base_kwh := energie_base_kwh (280.0), écrase
        #    la valeur 42.0 écrite pendant la fenêtre brouillon.
        self.assertEqual(periode.provision_base_kwh, 280.0, '1. tamponnée')
        # 2. Re-génération finale : la ligne émise porte la quantité tamponnée.
        ligne = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        self.assertEqual(ligne.quantity, 280.0, '2. re-générée avec la provision tamponnée')
        # 3. Post : la facture est bien postée.
        self.assertEqual(facture.state, 'posted', '3. postée')
        # 4. Verrou dérivé : Période et Relevé sont désormais gelés, sans
        #    code de verrou dédié à l'émission — la condition dérivée
        #    (facture_id.state == 'posted') s'active toute seule.
        with self.assertRaises(UserError):
            periode.write({'provision_base_kwh': 999.0})
        with self.assertRaises(UserError):
            releve.index_base = 999


@tagged('souscriptions', 'souscriptions_gel_emission', 'post_install', '-at_install')
class TestDegelSansMigration(SouscriptionsTestCase):
    """AC #267 : « Les Périodes existantes gelées sous l'ancien régime avec
    facture encore en brouillon sont de fait dé-gelées par la condition
    dérivée — vérifié par test, sans migration de données. »

    Aucune migration n'accompagne #267 (grep du diff : aucun fichier sous
    `migrations/`) — la preuve tient entièrement dans le changement de
    condition (`facture_id` truthy -> `facture_id.state == 'posted'`), ici
    exercée sur les trois surfaces qui la partagent : Période, Relevé,
    Régularisation."""

    def test_periode_et_releve_geles_sous_lancien_regime_sont_de_fait_degeles(self):
        """Une Période + son Relevé, dans l'état EXACT que l'ancien régime
        aurait qualifié de « gelé » (`facture_id` posé, aucune migration
        n'y touche) — désormais librement éditables tant que ce move reste
        en brouillon."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        releve = self.env['souscription.releve'].create(
            {'periode_id': periode.id, 'date': date(2024, 1, 1), 'index_base': 1000}
        )
        facture = periode._creer_facture()
        self.assertTrue(periode.facture_id, 'gelée sous #14/#7 avant #267 (facture_id truthy)')
        self.assertEqual(facture.state, 'draft')

        periode.write({'provision_base_kwh': 250.0})  # ne lève rien
        releve.write({'index_base': 2000})  # ne lève rien

        self.assertEqual(periode.provision_base_kwh, 250.0)
        self.assertEqual(releve.index_base, 2000)

    def test_regularisation_geleee_sous_lancien_regime_est_de_fait_degelee(self):
        """Même dé-gel de fait sur la Régularisation : `_recalculer()`
        refusait dès qu'une Facture existait (tranche 5, #237) ; elle
        n'est plus bloquée que par l'ÉMISSION (#267)."""
        regularisation = self.env['souscription.regularisation'].create({'souscription_id': self.souscription_base.id})
        self.env['souscription.regularisation.ligne'].create(
            {
                'regularisation_id': regularisation.id,
                'grille_id': self.grille_prix.id,
                'cadran': 'base',
                'ecart_kwh': 10.0,
                'prix_kwh': 0.15,
                'detail': 'Janvier 2024 : 10.00 kWh',
            }
        )
        regularisation._creer_facture()
        self.assertTrue(regularisation.facture_id, 'gelée sous #237 avant #267 (facture_id truthy)')
        self.assertEqual(regularisation.facture_id.state, 'draft')

        regularisation._recalculer()  # ne lève plus UserError
