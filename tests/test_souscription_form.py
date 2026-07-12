"""Tests du formulaire souscription refondu (#199) : statusbar readonly dans
le header, button box (factures + aperçu portail), bloc oe_title, deux
colonnes, onglet Électricore. Restructuration XML pure : assertions
structurelles sur l'arch résolu (lxml), pas de comportement métier nouveau."""

from lxml import etree
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_form', 'post_install', '-at_install')
class TestSouscriptionFormRefonte(SouscriptionsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        view = cls.env['souscription.souscription'].get_view(view_type='form')
        cls.arch = etree.fromstring(view['arch'])

    def test_etat_en_statusbar_readonly_dans_le_header_seulement(self):
        header = self.arch.find('header')
        self.assertIsNotNone(header)
        etat_fields = header.findall(".//field[@name='etat']")
        self.assertEqual(len(etat_fields), 1, "L'état doit apparaître une seule fois, dans le header")
        self.assertEqual(etat_fields[0].get('widget'), 'statusbar')
        self.assertEqual(etat_fields[0].get('readonly'), '1')

        sheet = self.arch.find('sheet')
        self.assertIsNotNone(sheet)
        # Les listes embarquées (refacturations, journal des actes) portent leur
        # propre champ `etat` : on ne compte que ceux du modèle souscription,
        # hors sous-vues (non descendants d'un <field>).
        etat_souscription = [
            f for f in sheet.findall(".//field[@name='etat']") if not any(a.tag == 'field' for a in f.iterancestors())
        ]
        self.assertFalse(etat_souscription, 'etat ne doit plus figurer dans le corps de la fiche')

    def test_date_fin_readonly_dans_le_formulaire(self):
        """AC4 (#246, ADR 0031) : `date_fin` à auteur unique — le fait C15,
        jamais de saisie manuelle depuis les vues."""
        date_fin_fields = self.arch.findall(".//field[@name='date_fin']")
        self.assertEqual(len(date_fin_fields), 1)
        self.assertEqual(date_fin_fields[0].get('readonly'), '1')

    def test_header_ne_garde_que_resoudre_rsc(self):
        header = self.arch.find('header')
        noms = [b.get('name') for b in header.findall('button')]
        self.assertEqual(noms, ['action_resoudre_rsc_maintenant'])

        header_str = etree.tostring(header, encoding='unicode')
        self.assertNotIn('action_souscription_conditions_particulieres', header_str)
        self.assertNotIn('action_souscription_attestation', header_str)
        self.assertNotIn('action_apercu_portail', header_str)

    def test_button_box_montre_factures_et_apercu_portail(self):
        button_box = self.arch.find(".//div[@name='button_box']")
        self.assertIsNotNone(button_box)
        box_str = etree.tostring(button_box, encoding='unicode')
        self.assertIn('action_voir_factures', box_str)
        self.assertIn('facture_count', box_str)
        self.assertIn('action_apercu_portail', box_str)

    def test_oe_title_h1_souscripteur_cotitulaires(self):
        oe_title = self.arch.find(".//div[@class='oe_title']")
        self.assertIsNotNone(oe_title)
        self.assertIsNotNone(oe_title.find('h1'))
        title_str = etree.tostring(oe_title, encoding='unicode')
        self.assertIn('name="name"', title_str)
        self.assertIn('name="partner_id"', title_str)
        self.assertIn('name="cotitulaires"', title_str)

    def test_pdl_dans_le_groupe_point_de_livraison(self):
        groupe = self.arch.find(".//group[@string='Point de livraison']")
        self.assertIsNotNone(groupe, 'Groupe « Point de livraison » absent (renommage de « Infos »)')
        self.assertTrue(groupe.findall(".//field[@name='pdl']"))

    def test_majoration_pro_dans_caracteristiques_cachee_si_pas_pro(self):
        caracteristiques = self.arch.find(".//group[@string='Caractéristiques facturantes']")
        coeff = caracteristiques.find(".//field[@name='coeff_pro']")
        self.assertIsNotNone(coeff, 'coeff_pro doit être dans « Caractéristiques facturantes »')
        self.assertEqual(coeff.get('invisible'), 'not partner_is_company')
        paiement = self.arch.find(".//group[@string='Paiement']")
        self.assertIsNone(paiement.find(".//field[@name='coeff_pro']"))

    def test_cheques_energie_dans_leur_onglet(self):
        page = self.arch.find(".//page[@string='Chèques énergie']")
        self.assertIsNotNone(page)
        self.assertIsNotNone(page.find(".//field[@name='cheque_energie_ids']"))

    def test_onglet_electricore_porte_les_cinq_champs_identite(self):
        page = self.arch.find(".//page[@string='Électricore']")
        self.assertIsNotNone(page)
        page_str = etree.tostring(page, encoding='unicode')
        for champ in (
            'ref_situation_contractuelle',
            'id_affaire',
            'id_affaire_date_saisie',
            'motif_resolution_rsc',
            'date_derniere_resolution_rsc',
        ):
            self.assertIn(f'name="{champ}"', page_str, f'Champ {champ} absent de l’onglet Électricore')

    def test_plus_de_groupe_identite_electricore_hors_onglet(self):
        self.assertIsNone(self.arch.find(".//group[@string='Identité électricore']"))

    def test_onglet_electricore_quatrieme_apres_journal_des_actes(self):
        notebook = self.arch.find('.//notebook')
        self.assertIsNotNone(notebook)
        libelles = [p.get('string') for p in notebook.findall('page')]
        self.assertEqual(
            libelles,
            ['Périodes de facturation', 'Refacturations', 'Journal des actes', 'Électricore', 'Chèques énergie'],
        )

    def test_colonnes_periodes_masquees_par_defaut(self):
        periode_list = self.arch.find(".//field[@name='periode_ids']//list")
        self.assertIsNotNone(periode_list)
        for champ in ('type_tarif_periode', 'facture_legacy_ref'):
            field_el = periode_list.find(f".//field[@name='{champ}']")
            self.assertIsNotNone(field_el, f'Colonne {champ} absente de la liste des périodes')
            self.assertEqual(field_el.get('optional'), 'hide')
