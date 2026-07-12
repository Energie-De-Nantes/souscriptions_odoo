"""
Tests du bouton « Chronologie » (#200, ADR 0024).

Deux tranches, même découpage que `test_pull_meta_periodes.py` :
- `_vals_depuis_ligne` : mapping pur des 3 types de ligne (`LigneEvenement` /
  `LigneReleve` / `LignePeriodeEnergie`) vers les `vals` de `create()`, testé
  avec des stubs duck-typés (aucune dépendance à `electricore_client`).
- `action_ouvrir_chronologie` : sans RSC (UserError actionnable), purge entre
  deux clics, erreurs typées mappées — client mocké.

Fixtures RSC/PDL : identifiants factices (jamais des vrais échantillons).
"""

from types import SimpleNamespace

from odoo.addons.souscriptions_odoo.models.core import souscription_chronologie as chronologie_module
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase, client_flux_factice, patcher_client_fabrique


def _ligne_evenement(**kwargs):
    """Stub duck-typé de `LigneEvenement` (contrat v1 chronologie)."""
    base = dict(
        type_ligne='evenement',
        date='2024-01-01',
        pdl='14000000000001',
        ref_situation_contractuelle='RSC-00000000000001',
        source='flux_C15',
        type_fait='MES',
        evenement_declencheur='MES',
        puissance_souscrite_kva=6.0,
        formule_tarifaire_acheminement='CU4',
        niveau_ouverture_services='service_complet',
        impacte_abonnement=True,
        resume_modification='Mise en service',
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _ligne_releve(**kwargs):
    """Stub duck-typé de `LigneReleve` (contrat v1 chronologie)."""
    base = dict(
        type_ligne='releve',
        date='2024-01-31',
        pdl='14000000000001',
        ref_situation_contractuelle='RSC-00000000000001',
        source='flux_R151',
        releve_id='ELC-RELEVE-001',
        nature_index='reel',
        origine_releve='périodique',
        ordre_index=1,
        evenement_declencheur=None,
        index_base_kwh=1000,
        index_hp_kwh=None,
        index_hc_kwh=None,
        index_hph_kwh=None,
        index_hch_kwh=None,
        index_hpb_kwh=None,
        index_hcb_kwh=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _ligne_periode_energie(**kwargs):
    """Stub duck-typé de `LignePeriodeEnergie` (contrat v1 chronologie)."""
    base = dict(
        type_ligne='periode_energie',
        date='2024-01-01',
        pdl='14000000000001',
        ref_situation_contractuelle='RSC-00000000000001',
        debut='2024-01-01',
        fin='2024-02-01',
        nb_jours=31,
        qualite='réelle',
        statut_communication='communicante',
        energie_base_kwh=280.0,
        energie_hp_kwh=None,
        energie_hc_kwh=None,
        energie_hph_kwh=None,
        energie_hch_kwh=None,
        energie_hpb_kwh=None,
        energie_hcb_kwh=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@tagged('souscriptions', 'souscriptions_chronologie', 'post_install', '-at_install')
class TestValsDepuisLigne(SouscriptionsTestCase):
    """Mapping pur des 3 types de ligne (aucun client requis)."""

    def test_mappe_une_ligne_evenement(self):
        Ligne = self.env['souscription.chronologie.ligne']
        vals = Ligne._vals_depuis_ligne(self.souscription_base, _ligne_evenement())

        self.assertEqual(vals['type_ligne'], 'evenement')
        self.assertEqual(vals['date'], '2024-01-01')
        self.assertEqual(vals['pdl'], '14000000000001')
        self.assertEqual(vals['ref_situation_contractuelle'], 'RSC-00000000000001')
        self.assertEqual(vals['type_fait'], 'MES')
        self.assertEqual(vals['puissance_souscrite_kva'], 6.0)
        self.assertEqual(vals['formule_tarifaire_acheminement'], 'CU4')
        self.assertEqual(vals['niveau_ouverture_services'], 'service_complet')
        self.assertTrue(vals['impacte_abonnement'])
        self.assertEqual(vals['resume_modification'], 'Mise en service')
        # Colonnes des deux autres types absentes du mapping evenement.
        self.assertNotIn('releve_id', vals)
        self.assertNotIn('qualite', vals)

    def test_mappe_une_ligne_releve(self):
        Ligne = self.env['souscription.chronologie.ligne']
        vals = Ligne._vals_depuis_ligne(self.souscription_base, _ligne_releve())

        self.assertEqual(vals['type_ligne'], 'releve')
        self.assertEqual(vals['releve_id'], 'ELC-RELEVE-001')
        self.assertEqual(vals['nature_index'], 'reel')
        self.assertEqual(vals['origine_releve'], 'périodique')
        self.assertEqual(vals['ordre_index'], 1)
        self.assertEqual(vals['index_base_kwh'], 1000)
        self.assertIsNone(vals['index_hp_kwh'])
        # Colonnes des deux autres types absentes du mapping releve.
        self.assertNotIn('type_fait', vals)
        self.assertNotIn('qualite', vals)

    def test_mappe_une_ligne_periode_energie(self):
        Ligne = self.env['souscription.chronologie.ligne']
        vals = Ligne._vals_depuis_ligne(self.souscription_base, _ligne_periode_energie())

        self.assertEqual(vals['type_ligne'], 'periode_energie')
        self.assertEqual(vals['debut'], '2024-01-01')
        self.assertEqual(vals['fin'], '2024-02-01')
        self.assertEqual(vals['nb_jours'], 31)
        self.assertEqual(vals['qualite'], 'réelle')
        self.assertEqual(vals['statut_communication'], 'communicante')
        self.assertEqual(vals['energie_base_kwh'], 280.0)
        # Colonnes des deux autres types absentes du mapping periode_energie.
        self.assertNotIn('type_fait', vals)
        self.assertNotIn('releve_id', vals)


# === Bouton « Chronologie » : client mocké ===
#
# Les exceptions levées sont les vraies classes du module chronologie
# (réelles si electricore_client est présent, stubs de la fabrique sinon,
# ADR 0024/#222) : aucun échange de symbole par patch.


@tagged('souscriptions', 'souscriptions_chronologie', 'post_install', '-at_install')
class TestActionOuvrirChronologie(SouscriptionsTestCase):
    def setUp(self):
        super().setUp()
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'

    def _cliquer_avec_client(self, client, souscription=None):
        """Clique le bouton avec un client factice fourni directement par la
        fabrique (ADR 0024) : la garde paquet/config de la fabrique est
        testée une fois dans test_electricore_client_fabrique.py, pas ici."""
        with patcher_client_fabrique(client):
            return (souscription or self.souscription_base).action_ouvrir_chronologie()

    def test_sans_rsc_leve_userror_actionnable(self):
        """AC : sans RSC, UserError actionnable renvoyant vers la résolution
        RSC — pas de repli pdl (aucun appel au client)."""
        self.souscription_base.ref_situation_contractuelle = False
        client = client_flux_factice('chronologie', [])
        with patcher_client_fabrique(client):
            with self.assertRaises(UserError) as cm:
                self.souscription_base.action_ouvrir_chronologie()
        self.assertIn('RSC', str(cm.exception))
        client.chronologie.assert_not_called()

    def test_tire_et_cree_les_trois_types_de_lignes(self):
        """AC : les 3 types de lignes sont créés, scopés sur la souscription,
        au grain RSC (jamais pdl)."""
        lignes = [_ligne_evenement(), _ligne_releve(), _ligne_periode_energie()]
        client = client_flux_factice('chronologie', lignes)

        action = self._cliquer_avec_client(client)

        client.chronologie.assert_called_once_with(rsc='RSC-00000000000001')
        self.assertEqual(action['res_model'], 'souscription.chronologie.ligne')
        self.assertEqual(action['domain'], [('souscription_id', '=', self.souscription_base.id)])

        creees = self.env['souscription.chronologie.ligne'].search(
            [('souscription_id', '=', self.souscription_base.id)]
        )
        self.assertEqual(len(creees), 3)
        self.assertEqual(set(creees.mapped('type_ligne')), {'evenement', 'releve', 'periode_energie'})

    def test_purge_entre_deux_clics_pas_de_doublons(self):
        """AC : chaque clic purge et recrée les lignes de la souscription —
        pas de doublons, l'ancien contenu disparaît."""
        premier_lot = [_ligne_evenement(date='2024-01-01')]
        self._cliquer_avec_client(client_flux_factice('chronologie', premier_lot))
        premiere_ligne = self.env['souscription.chronologie.ligne'].search(
            [('souscription_id', '=', self.souscription_base.id)]
        )
        self.assertEqual(len(premiere_ligne), 1)
        premier_id = premiere_ligne.id

        second_lot = [_ligne_releve(date='2024-02-01'), _ligne_periode_energie(date='2024-02-01')]
        self._cliquer_avec_client(client_flux_factice('chronologie', second_lot))

        apres = self.env['souscription.chronologie.ligne'].search([('souscription_id', '=', self.souscription_base.id)])
        self.assertEqual(len(apres), 2, 'Le premier lot doit avoir été purgé, pas cumulé')
        self.assertNotIn(premier_id, apres.ids)

    def test_ne_purge_pas_les_lignes_dune_autre_souscription(self):
        """Purge scopée par souscription (#200) : un clic sur `A` ne touche
        pas les lignes déjà affichées pour `B`."""
        autre = self.souscription_hphc
        autre.ref_situation_contractuelle = 'RSC-00000000000099'
        self._cliquer_avec_client(
            client_flux_factice('chronologie', [_ligne_evenement(ref_situation_contractuelle='RSC-00000000000099')]),
            souscription=autre,
        )
        ligne_autre = self.env['souscription.chronologie.ligne'].search([('souscription_id', '=', autre.id)])
        self.assertEqual(len(ligne_autre), 1)

        self._cliquer_avec_client(client_flux_factice('chronologie', [_ligne_releve()]))

        self.assertEqual(
            self.env['souscription.chronologie.ligne'].search_count([('souscription_id', '=', autre.id)]),
            1,
            "Les lignes de l'autre souscription ne doivent pas être purgées",
        )

    def test_ingestion_en_cours_mappee_en_userror_reessayable(self):
        client = client_flux_factice('chronologie', leve=chronologie_module.IngestionEnCours('verrou'))
        with self.assertRaises(UserError) as cm:
            self._cliquer_avec_client(client)
        self.assertIn('plus tard', str(cm.exception))

    def test_precondition_non_remplie_mappee_en_userror_actionnable(self):
        client = client_flux_factice(
            'chronologie', leve=chronologie_module.PreconditionNonRemplie('réconciliez les RSC avant de facturer')
        )
        with self.assertRaises(UserError) as cm:
            self._cliquer_avec_client(client)
        self.assertIn('réconciliez les RSC', str(cm.exception))

    def test_contract_version_error_mappee_en_userror(self):
        client = client_flux_factice(
            'chronologie', leve=chronologie_module.ContractVersionError('serveur v2 < attendu v3')
        )
        with self.assertRaises(UserError) as cm:
            self._cliquer_avec_client(client)
        self.assertIn('v2', str(cm.exception))

    def test_erreur_ne_purge_pas_les_lignes_dun_clic_precedent(self):
        """Le flux est matérialisé avant toute écriture (#200) : une erreur
        réseau/contrat n'efface jamais un affichage déjà réussi."""
        self._cliquer_avec_client(client_flux_factice('chronologie', [_ligne_evenement()]))
        avant = self.env['souscription.chronologie.ligne'].search_count(
            [('souscription_id', '=', self.souscription_base.id)]
        )
        self.assertEqual(avant, 1)

        with self.assertRaises(UserError):
            self._cliquer_avec_client(
                client_flux_factice('chronologie', leve=chronologie_module.IngestionEnCours('verrou'))
            )

        apres = self.env['souscription.chronologie.ligne'].search_count(
            [('souscription_id', '=', self.souscription_base.id)]
        )
        self.assertEqual(apres, 1, "L'échec ne doit pas purger l'affichage précédent")
