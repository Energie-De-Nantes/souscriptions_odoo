from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from .common import ABO_ANNUEL_SOL, build_grille_lignes


@tagged('souscriptions', 'post_install', '-at_install')
class TestIntegration(TransactionCase):
    """Tests d'intégration bout-en-bout : souscription -> période -> facture"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create(
            {
                'name': 'Client Intégration',
                'is_company': False,
            }
        )

        self.etat_actif = self.env['souscription.etat'].create(
            {
                'name': 'Actif',
                'sequence': 1,
            }
        )

        # Désactiver les grilles existantes et créer une grille de test
        self.env['grille.prix'].search([('is_current', '=', True)]).write({'is_current': False})

        # Grille de prix complète pour les tests (nouvelle structure)
        self.grille = self.env['grille.prix'].create(
            {
                'name': 'Grille Intégration',
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 12, 31),
                'active': True,
                'is_current': True,
            }
        )

        # Lignes de prix : abonnement par puissance (€/an) + énergies (€/kWh)
        build_grille_lignes(
            self.env,
            self.grille,
            prix_base=0.2276,
            prix_hp=0.2516,
            prix_hc=0.2032,
        )

    def test_workflow_complet_base(self):
        """Test workflow complet : souscription BASE -> période -> facture"""
        # 1. Créer souscription BASE
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_INTEG_BASE',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_actif.id,
                'date_debut': date(2024, 1, 1),
                'coeff_pro': 0.0,  # Particulier
            }
        )

        # 2. Créer période de facturation
        periode = self.env['souscription.periode'].create(
            {
                'souscription_id': souscription.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 1, 31),
                'type_periode': 'mensuelle',
                # Contrat non lissé : on facture le mesuré (energie_*), pas une provision.
                'energie_base_kwh': 280.0,
                'turpe_fixe': 8.50,
                'turpe_variable': 12.30,
            }
        )

        # 3. Générer facture
        souscription.creer_factures()

        # 4. Vérifications
        self.assertTrue(periode.facture_id)
        facture = periode.facture_id

        # Vérifier la facture
        self.assertEqual(facture.partner_id, self.partner)
        self.assertEqual(facture.move_type, 'out_invoice')

        # Vérifier les lignes de facture
        lignes = facture.invoice_line_ids
        self.assertGreater(len(lignes), 0)

        # Ligne abonnement
        ligne_abo = lignes.filtered(lambda l: l.product_id and 'Abonnement' in l.product_id.name)
        self.assertEqual(len(ligne_abo), 1)
        self.assertEqual(ligne_abo.quantity, 30)  # Jours du mois (correct)

        # Ligne énergie BASE
        ligne_energie = lignes.filtered(lambda l: l.product_id and 'Énergie Base' in l.product_id.name)
        self.assertEqual(len(ligne_energie), 1)
        self.assertEqual(ligne_energie.quantity, 280.0)

        # Notes TURPE (dans les lignes display_type='line_note')
        notes_turpe = lignes.filtered(lambda l: l.display_type == 'line_note' and 'turpe' in l.name.lower())
        self.assertGreaterEqual(len(notes_turpe), 1)  # Au moins une note TURPE

    def test_workflow_complet_hphc(self):
        """Test workflow complet : souscription HP/HC -> période -> facture"""
        # 1. Créer souscription HP/HC
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_INTEG_HPHC',
                'puissance_souscrite': '9',
                'type_tarif': 'hphc',
                'etat_facturation_id': self.etat_actif.id,
                'date_debut': date(2024, 2, 1),
                'coeff_pro': 15.0,  # PRO +15%
            }
        )

        # 2. Créer période HP/HC
        periode = self.env['souscription.periode'].create(
            {
                'souscription_id': souscription.id,
                'date_debut': date(2024, 2, 1),
                'date_fin': date(2024, 2, 29),
                'type_periode': 'mensuelle',
                # Contrat non lissé : on facture le mesuré. Calendrier 4 cadrans →
                # energie_hp = HPH+HPB (180), energie_hc = HCH+HCB (120).
                'energie_hph_kwh': 180.0,
                'energie_hch_kwh': 120.0,
            }
        )

        # 3. Générer facture
        souscription.creer_factures()

        # 4. Vérifications HP/HC
        facture = periode.facture_id
        lignes = facture.invoice_line_ids

        # Ligne abonnement avec majoration PRO
        ligne_abo = lignes.filtered(lambda l: l.product_id and 'Abonnement' in l.product_id.name and 'PRO' in l.name)
        self.assertEqual(len(ligne_abo), 1)

        # Lignes énergie HP et HC
        ligne_hp = lignes.filtered(lambda l: l.product_id and 'Énergie HP' in l.product_id.name)
        ligne_hc = lignes.filtered(lambda l: l.product_id and 'Énergie HC' in l.product_id.name)

        self.assertEqual(len(ligne_hp), 1)
        self.assertEqual(len(ligne_hc), 1)
        self.assertEqual(ligne_hp.quantity, 180.0)
        self.assertEqual(ligne_hc.quantity, 120.0)

    def test_workflow_solidaire(self):
        """Test workflow tarif solidaire"""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_SOLIDAIRE',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_actif.id,
                'tarif_solidaire': True,
            }
        )

        periode = self.env['souscription.periode'].create(
            {
                'souscription_id': souscription.id,
                'date_debut': date(2024, 3, 1),
                'date_fin': date(2024, 3, 31),
                'type_periode': 'mensuelle',
                'provision_base_kwh': 200.0,
            }
        )

        souscription.creer_factures()

        # Vérifier produit solidaire utilisé
        facture = periode.facture_id
        ligne_abo = facture.invoice_line_ids.filtered(lambda l: l.product_id and 'Abonnement' in l.product_id.name)

        # Le prix doit être celui du tarif solidaire 6 kVA, proratisé au jour
        # (prix annuel / 365).
        prix_journalier_attendu = ABO_ANNUEL_SOL['6'] / 365.0
        self.assertAlmostEqual(ligne_abo.price_unit, prix_journalier_attendu, places=4)

    def test_facturation_multiple_souscriptions(self):
        """Test facturation simultanée de plusieurs souscriptions"""
        # Créer 3 souscriptions différentes
        souscriptions = []
        for i in range(3):
            partner = self.env['res.partner'].create(
                {
                    'name': f'Client Multi {i + 1}',
                }
            )

            sous = self.env['souscription.souscription'].create(
                {
                    'partner_id': partner.id,
                    'pdl': f'PDL_MULTI_{i + 1}',
                    'puissance_souscrite': '6',
                    'type_tarif': 'base',
                    'etat_facturation_id': self.etat_actif.id,
                }
            )
            souscriptions.append(sous)

            # Période pour chaque souscription
            self.env['souscription.periode'].create(
                {
                    'souscription_id': sous.id,
                    'date_debut': date(2024, 4, 1),
                    'date_fin': date(2024, 4, 30),
                    'type_periode': 'mensuelle',
                    'provision_base_kwh': 250.0,
                }
            )

        # Facturation groupée
        souscriptions_recordset = self.env['souscription.souscription'].browse([s.id for s in souscriptions])
        souscriptions_recordset.creer_factures()

        # Vérifier que toutes les factures sont créées
        for sous in souscriptions:
            periode = sous.periode_ids[0]
            self.assertTrue(periode.facture_id)
            self.assertEqual(periode.facture_id.partner_id, sous.partner_id)

    def test_erreur_grille_manquante(self):
        """Test gestion erreur : aucune grille ne couvre la période facturée"""
        # Retirer la grille couvrant 2024 : la période ci-dessous tombe alors
        # dans un trou de couverture.
        self.grille.unlink()

        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_ERREUR',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_actif.id,
            }
        )

        self.env['souscription.periode'].create(
            {
                'souscription_id': souscription.id,
                'date_debut': date(2024, 5, 1),
                'date_fin': date(2024, 5, 31),
                'type_periode': 'mensuelle',
                'provision_base_kwh': 100.0,
            }
        )

        # Doit lever une erreur. creer_factures journalise l'échec en ERROR
        # avant de relancer : on attend cet échec, donc on coupe ce logger
        # pour ne pas polluer la sortie.
        from odoo.tools import mute_logger

        with self.assertRaises(UserError), mute_logger('odoo.addons.souscriptions_odoo.models.core.souscription'):
            souscription.creer_factures()
