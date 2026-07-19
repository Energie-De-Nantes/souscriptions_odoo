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
from odoo.addons.souscriptions_odoo.models.core import souscription_campagne as campagne_module
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
class TestCampagnePhaseChampsEtRecherche(SouscriptionsTestCase):
    """#374 : `phase` cherchable (colonne stockée, recherche SQL native) et
    les quatre one2many
    `etape_<phase>_ids` qui partitionnent `etape_ids` — le fix du bug de la
    vue en phases (le `domain` XML ne filtrait jamais l'affichage)."""

    def _campagne(self, mois=date(2024, 7, 1)):
        return self.env['souscription.campagne.facturation'].create({'mois': mois})

    def test_les_quatre_champs_partitionnent_etape_ids(self):
        campagne = self._campagne()
        par_phase = {
            'tirer': campagne.etape_tirer_ids,
            'verifier': campagne.etape_verifier_ids,
            'facturer': campagne.etape_facturer_ids,
            'solder': campagne.etape_solder_ids,
        }
        # Union complète : aucune étape du catalogue n'est perdue.
        union = campagne.env['souscription.campagne.etape']
        for etapes in par_phase.values():
            union |= etapes
        self.assertEqual(set(union.ids), set(campagne.etape_ids.ids))
        # Zéro recouvrement : chaque étape apparaît dans une seule phase.
        self.assertEqual(sum(len(etapes) for etapes in par_phase.values()), len(campagne.etape_ids))
        # Chaque champ ne contient que des étapes de sa propre phase.
        for phase, etapes in par_phase.items():
            self.assertTrue(etapes, f'aucune étape en phase {phase}')
            self.assertTrue(all(e.phase == phase for e in etapes))

    def test_search_phase_egalite_renvoie_les_bons_codes(self):
        campagne = self._campagne()
        trouvees = self.env['souscription.campagne.etape'].search(
            [('phase', '=', 'tirer'), ('campagne_id', '=', campagne.id)]
        )
        codes_tirer = {code for code, info in campagne_module.ETAPES_CAMPAGNE.items() if info['phase'] == 'tirer'}
        self.assertEqual(set(trouvees.mapped('code')), codes_tirer)

    def test_search_phase_in_renvoie_lunion_des_phases(self):
        campagne = self._campagne()
        trouvees = self.env['souscription.campagne.etape'].search(
            [('phase', 'in', ['tirer', 'solder']), ('campagne_id', '=', campagne.id)]
        )
        codes_attendus = {
            code for code, info in campagne_module.ETAPES_CAMPAGNE.items() if info['phase'] in ('tirer', 'solder')
        }
        self.assertEqual(set(trouvees.mapped('code')), codes_attendus)


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneVueEnPhases(SouscriptionsTestCase):
    """AC #344/#374 : le formulaire rend quatre sections titrées, une par
    champ etape_<phase>_ids — même motif que TestCampagneBandeauButtonBox/
    TestCampagneEtapesDecorations (tests/test_campagne_bandeau_view.py) :
    arch résolu, assertions lxml, aucune donnée requise. Depuis #374, chaque
    `<field>` est nu (le filtre vit côté Python sur le champ, pas dans un
    domain XML qui ne filtrerait pas l'affichage) et le contenu de liste
    (décorations, boutons, bloquee_par...) est résolu une seule fois, sur la
    vue liste partagée du comodèle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        view = cls.env['souscription.campagne.facturation'].get_view(view_type='form')
        cls.arch = etree.fromstring(view['arch'])
        vue_etape = cls.env['souscription.campagne.etape'].get_view(
            view_id=cls.env.ref('souscriptions_odoo.view_souscription_campagne_etape_list').id, view_type='list'
        )
        cls.arch_liste_etape = etree.fromstring(vue_etape['arch'])

    _PHASES_ATTENDUES = [
        ('tirer', 'Tirer'),
        ('verifier', 'Vérifier'),
        ('facturer', 'Facturer'),
        ('solder', 'Solder'),
    ]

    def test_quatre_sections_un_champ_nu_par_phase_dans_lordre(self):
        """AC #374 : un champ etape_<phase>_ids par phase, SANS enfants (pas
        de domain XML — le filtre vit dans la définition Python du champ),
        dans l'ordre Tirer/Vérifier/Facturer/Solder."""
        etape_page = self.arch.find(".//page[@name='etapes']")
        self.assertIsNotNone(etape_page)
        champs = [e for e in etape_page if e.tag == 'field']
        self.assertEqual(len(champs), 4, 'un champ par phase, plus de duplication')
        for (code, _label), champ in zip(self._PHASES_ATTENDUES, champs, strict=True):
            self.assertEqual(champ.get('name'), f'etape_{code}_ids')
            self.assertIsNone(champ.get('domain'), 'le filtre vit côté Python, plus en domain XML')
            self.assertEqual(list(champ), [], 'champ nu : la vue liste vient du comodèle')

    def test_chaque_section_est_precedee_dun_separateur_titre(self):
        """Un séparateur TITRÉ précède chaque section."""
        etape_page = self.arch.find(".//page[@name='etapes']")
        separateurs = [e for e in etape_page if e.tag == 'separator']
        titres = [s.get('string') for s in separateurs]
        self.assertEqual(titres, [label for _code, label in self._PHASES_ATTENDUES])

    def test_une_seule_definition_de_liste_garde_les_decorations_existantes(self):
        """AC #374 : une seule liste d'étapes dans le XML — les décorations
        grisé/gras de #301 (motif déjà couvert par test_campagne_bandeau_view.py)
        survivent à la déduplication."""
        self.assertEqual(self.arch_liste_etape.get('decoration-muted'), 'fait')
        # decoration-bf, pas « decoration-bold » (#374) : seul -bf existe en
        # Odoo — l'ancien attribut était ignoré en sous-liste inline et rejeté
        # par le RNG en vue autonome.
        self.assertEqual(self.arch_liste_etape.get('decoration-bf'), "etat_prerequis == 'prete' and not fait")

    def test_pas_de_poignee_de_tri_sur_les_lignes_detape(self):
        """AC #344 : le catalogue est fixe et topologique — drag-to-reorder
        est un mensonge d'affichage, la poignée disparaît."""
        poignees = self.arch_liste_etape.findall(".//field[@widget='handle']")
        self.assertFalse(poignees, "aucune poignée de réordonnancement sur les lignes d'étape")

    def test_boutons_lancer_et_voir_intacts(self):
        """AC #374 : boutons Lancer/Voir intacts après déduplication."""
        boutons = {b.get('string') for b in self.arch_liste_etape.findall('.//button')}
        self.assertEqual(boutons, {'Lancer', 'Voir'})

    def test_bloquee_par_present_une_seule_fois(self):
        """AC #374 : « Bloquée par : X » — visible seulement quand
        etat_prerequis == 'bloquee', une seule définition partagée par les
        quatre sections (au lieu d'une par section avant #374)."""
        champs = self.arch_liste_etape.findall(".//field[@name='bloquee_par']")
        self.assertEqual(len(champs), 1)
        self.assertEqual(champs[0].get('invisible'), "etat_prerequis != 'bloquee'")

    def test_toggle_valide_present_une_seule_fois(self):
        """AC #374 : le toggle de porte (valide) survit à la déduplication."""
        champs = self.arch_liste_etape.findall(".//field[@name='valide']")
        self.assertEqual(len(champs), 1)
        self.assertEqual(champs[0].get('widget'), 'boolean_toggle')
