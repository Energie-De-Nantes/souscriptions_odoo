"""Tests de la vue en phases de la Campagne de facturation (#344, PRD #339).

Deux couches, comme le motif de test_campagne_bandeau_view.py :
- le compute `bloquee_par` (modèle, `souscription.campagne.etape`) — TDD
  classique sur une campagne réelle ;
- la structure XML de la vue formulaire (arch résolu via `get_view`,
  assertions lxml) — quatre sections Tirer/Vérifier/Facturer/Solder, plus de
  poignée de tri. Restructuration + affichage purs, aucun comportement
  métier nouveau (boutons/portes/drill-downs inchangés, déjà couverts
  ailleurs)."""

from datetime import date

from lxml import etree
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneEtapeBloqueePar(SouscriptionsTestCase):
    def _campagne(self, mois=date(2024, 7, 1)):
        return self.env['souscription.campagne.facturation'].create({'mois': mois})

    def _etape(self, campagne, code):
        return campagne.etape_ids.filtered(lambda e: e.code == code)

    def test_etape_bloquee_affiche_les_libelles_des_prerequis_non_faits(self):
        """AC #344 : « Bloquée par : X » — les libellés, pas le badge muet."""
        campagne = self._campagne()
        creer_factures = self._etape(campagne, 'creer_factures')
        self.assertEqual(creer_factures.etat_prerequis, 'bloquee')
        self.assertEqual(creer_factures.bloquee_par, 'Vérif périodes, Vérif refacturations')

    def test_etape_prete_naffiche_rien(self):
        campagne = self._campagne()
        racine = self._etape(campagne, 'sync_f15')
        self.assertEqual(racine.etat_prerequis, 'prete')
        self.assertFalse(racine.bloquee_par)

    def test_etape_faite_naffiche_rien(self):
        campagne = self._campagne()
        verif = self._etape(campagne, 'verif_periodes')
        verif.write({'valide': True})
        self.assertTrue(verif.fait)
        self.assertFalse(verif.bloquee_par)

    def test_deblocage_partiel_ne_liste_que_le_prerequis_restant(self):
        """Une porte validée sur deux : bloquee_par se réduit au SEUL
        prérequis manquant, il ne fige pas la liste initiale."""
        campagne = self._campagne()
        verif_periodes = self._etape(campagne, 'verif_periodes')
        creer_factures = self._etape(campagne, 'creer_factures')
        verif_periodes.write({'valide': True})
        campagne.etape_ids.invalidate_recordset()
        self.assertEqual(creer_factures.etat_prerequis, 'bloquee')
        self.assertEqual(creer_factures.bloquee_par, 'Vérif refacturations')


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneVueEnPhases(SouscriptionsTestCase):
    """AC #344 : le formulaire rend `etape_ids` en quatre sections titrées —
    même motif que TestCampagneBandeauButtonBox/TestCampagneEtapesDecorations
    (tests/test_campagne_bandeau_view.py) : arch résolu, assertions lxml,
    aucune donnée requise."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        view = cls.env['souscription.campagne.facturation'].get_view(view_type='form')
        cls.arch = etree.fromstring(view['arch'])

    _PHASES_ATTENDUES = [
        ('tirer', 'Tirer'),
        ('verifier', 'Vérifier'),
        ('facturer', 'Facturer'),
        ('solder', 'Solder'),
    ]

    def test_quatre_sections_filtrees_par_phase_dans_lordre(self):
        """AC #344 : le même one2many rendu quatre fois, filtré par `phase`
        (#342) — une occurrence par phase, dans l'ordre Tirer/Vérifier/
        Facturer/Solder."""
        etape_page = self.arch.find(".//page[@name='etapes']")
        self.assertIsNotNone(etape_page)
        champs_etape_ids = etape_page.findall(".//field[@name='etape_ids']")
        self.assertEqual(len(champs_etape_ids), 4, 'le one2many est rendu une fois par phase')
        for (code, _label), champ in zip(self._PHASES_ATTENDUES, champs_etape_ids, strict=True):
            domaine = champ.get('domain') or ''
            self.assertIn(f"'{code}'", domaine, f"la section {code} doit filtrer etape_ids sur phase == '{code}'")

    def test_chaque_section_est_precedee_dun_separateur_titre(self):
        """« Même idiome que la ligne de séparation énergie/abonnement d'une
        facture » : un séparateur TITRÉ précède chaque section."""
        etape_page = self.arch.find(".//page[@name='etapes']")
        separateurs = [e for e in etape_page if e.tag == 'separator']
        titres = [s.get('string') for s in separateurs]
        self.assertEqual(titres, [label for _code, label in self._PHASES_ATTENDUES])

    def test_toutes_les_sections_gardent_les_decorations_existantes(self):
        """Restructuration pure : les décorations grisé/gras de #301 (motif
        déjà couvert par test_campagne_bandeau_view.py) survivent au
        découpage en quatre listes."""
        listes = self.arch.findall(".//field[@name='etape_ids']/list")
        self.assertEqual(len(listes), 4)
        for etape_list in listes:
            self.assertEqual(etape_list.get('decoration-muted'), 'fait')
            self.assertEqual(etape_list.get('decoration-bold'), "etat_prerequis == 'prete' and not fait")

    def test_pas_de_poignee_de_tri_sur_les_lignes_detape(self):
        """AC #344 : le catalogue est fixe et topologique — drag-to-reorder
        est un mensonge d'affichage, la poignée disparaît."""
        etape_page = self.arch.find(".//page[@name='etapes']")
        poignees = etape_page.findall(".//field[@widget='handle']")
        self.assertFalse(poignees, "aucune poignée de réordonnancement sur les lignes d'étape")

    def test_bloquee_par_affiche_une_fois_par_section(self):
        """AC #344 : « Bloquée par : X » — visible seulement quand
        etat_prerequis == 'bloquee', dans chacune des quatre sections."""
        champs = self.arch.findall(".//field[@name='etape_ids']//field[@name='bloquee_par']")
        self.assertEqual(len(champs), 4, 'une occurrence par section')
        for champ in champs:
            self.assertEqual(champ.get('invisible'), "etat_prerequis != 'bloquee'")
