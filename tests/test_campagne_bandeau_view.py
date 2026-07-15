"""Tests XML des vues de la Campagne de facturation (#301) : bandeau de stat
buttons natif, décorations de la matrice des étapes, liste enrichie.
Restructuration XML pure — assertions structurelles sur l'arch résolu
(lxml), pas de comportement métier nouveau (déjà couvert par
test_campagne_bandeau_stats.py)."""

from lxml import etree
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneBandeauButtonBox(SouscriptionsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        view = cls.env['souscription.campagne.facturation'].get_view(view_type='form')
        cls.arch = etree.fromstring(view['arch'])

    _BOUTONS_ATTENDUS = {
        'action_drill_down_perimetre': 'nb_perimetre',
        'action_drill_down_a_tirer': 'nb_a_tirer',
        'action_drill_down_a_facturer': 'nb_a_facturer',
        'action_drill_down_facturees': 'nb_facturees_brouillon',
        'action_drill_down_emises': 'nb_emises_bucket',
        'action_drill_down_total_emis': 'total_emis_ttc',
    }

    def test_bandeau_de_stat_buttons_natif_en_tete_de_fiche(self):
        """AC #301 : le formulaire affiche le bandeau natif — button_box avec
        une tuile cliquable par statistique (Périmètre, entonnoir, total TTC)."""
        button_box = self.arch.find(".//div[@name='button_box']")
        self.assertIsNotNone(button_box)
        self.assertIn('oe_button_box', button_box.get('class', ''))

        boutons = button_box.findall("./button[@type='object']")
        noms = {b.get('name') for b in boutons}
        self.assertEqual(noms, set(self._BOUTONS_ATTENDUS), 'une tuile par statistique du bandeau, ni plus ni moins')

        for bouton in boutons:
            self.assertIn('oe_stat_button', bouton.get('class', ''))
            champ_attendu = self._BOUTONS_ATTENDUS[bouton.get('name')]
            champs = bouton.findall(f".//field[@name='{champ_attendu}']")
            self.assertEqual(len(champs), 1, f'la tuile {bouton.get("name")} doit afficher {champ_attendu}')

    def test_groupe_factures_du_mois_a_disparu(self):
        """AC #301 : le groupe « Factures du mois » disparaît, remplacé par
        le bandeau — les champs sous-jacents (nb_factures_creees/emises)
        restent sur le modèle (#157), juste plus affichés ici."""
        groupes = self.arch.findall(".//group[@string='Factures du mois']")
        self.assertFalse(groupes)
