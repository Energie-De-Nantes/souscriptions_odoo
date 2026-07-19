from datetime import date

from odoo.tests.common import TransactionCase, tagged

from .common import build_grille_lignes


@tagged('souscriptions', 'souscriptions_template', 'post_install', '-at_install')
class TestInvoiceTemplate(TransactionCase):
    """Tests du template de facture personnalisé d'électricité"""

    def setUp(self):
        super().setUp()

        # Créer un client de test
        self.partner = self.env['res.partner'].create(
            {
                'name': 'Marie Dupont Test',
                'is_company': False,
                'street': '15 rue des Tests',
                'city': 'Rennes',
                'zip': '35000',
                'country_id': self.env.ref('base.fr').id,
                'email': 'marie.test@email.fr',
            }
        )

        # Grille de prix avec lignes (ADR 0029 — grille.composants() lève
        # bruyamment sans ligne de prix), construite via le socle commun.
        self.grille_prix = self.env['grille.prix'].create(
            {
                'name': 'Grille Test Template',
                'date_debut': date(2024, 1, 1),
                'active': True,
            }
        )
        build_grille_lignes(self.env, self.grille_prix, prix_base=0.15, prix_hp=0.18, prix_hc=0.12)

        # Souscription Base
        self.souscription_base = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_TEMPLATE_BASE',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'date_debut': date(2024, 1, 1),
                'provision_mensuelle_kwh': 280.0,
                'ref_compteur': 'COMP123456',
                'tarif_solidaire': False,
            }
        )

        # Souscription HP/HC
        self.souscription_hphc = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_TEMPLATE_HPHC',
                'puissance_souscrite': '9',
                'type_tarif': 'hphc',
                'date_debut': date(2024, 1, 1),
                'provision_hp_kwh': 200.0,
                'provision_hc_kwh': 120.0,
                'ref_compteur': 'COMP789012',
                'tarif_solidaire': False,
            }
        )

        # Souscription solidaire
        self.souscription_solidaire = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_TEMPLATE_SOLIDAIRE',
                'puissance_souscrite': '3',
                'type_tarif': 'base',
                'date_debut': date(2024, 1, 1),
                'provision_mensuelle_kwh': 180.0,
                'ref_compteur': 'COMP345678',
                'tarif_solidaire': True,
            }
        )

    def _create_periode_and_invoice(self, souscription, date_debut, date_fin):
        """Helper pour créer une période et sa facture"""
        # Calculer les jours
        jours = (date_fin - date_debut).days + 1

        if souscription.type_tarif == 'base':
            base_kwh = 280.0
            periode_data = {
                'souscription_id': souscription.id,
                'date_debut': date_debut,
                'date_fin': date_fin,
                'type_periode': 'mensuelle',
                'jours': jours,
                'energie_hph_kwh': base_kwh * 0.5,
                'energie_hpb_kwh': base_kwh * 0.2,
                'energie_hch_kwh': base_kwh * 0.2,
                'energie_hcb_kwh': base_kwh * 0.1,
                'provision_base_kwh': base_kwh if souscription.lisse else 0,
                'turpe_fixe': 8.5,
                'turpe_variable': base_kwh * 0.015,
            }
        else:  # HP/HC
            hp_kwh = 200.0
            hc_kwh = 120.0
            periode_data = {
                'souscription_id': souscription.id,
                'date_debut': date_debut,
                'date_fin': date_fin,
                'type_periode': 'mensuelle',
                'jours': jours,
                'energie_hph_kwh': hp_kwh * 0.6,
                'energie_hpb_kwh': hp_kwh * 0.4,
                'energie_hch_kwh': hc_kwh * 0.6,
                'energie_hcb_kwh': hc_kwh * 0.4,
                'provision_hp_kwh': hp_kwh if souscription.lisse else 0,
                'provision_hc_kwh': hc_kwh if souscription.lisse else 0,
                'turpe_fixe': 12.8,
                'turpe_variable': (hp_kwh + hc_kwh) * 0.018,
            }

        periode = self.env['souscription.periode'].create(periode_data)
        facture = periode._creer_facture()

        return periode, facture

    def test_facture_energie_detection(self):
        """Test que les factures d'énergie sont correctement détectées"""
        periode, facture = self._create_periode_and_invoice(self.souscription_base, date(2024, 1, 1), date(2024, 1, 31))

        # Vérifier que c'est détecté comme facture d'énergie
        self.assertTrue(facture.is_facture_energie)
        self.assertEqual(facture.souscription_id, self.souscription_base)
        self.assertEqual(facture.periode_id, periode)

    def test_get_name_invoice_report_route_vers_le_document_energie(self):
        """#289 : le hook natif d'Odoo (`_get_name_invoice_report`) est la
        porte UNIQUE lue par `account.report_invoice` — portail, PDF email et
        Imprimer/Télécharger par défaut la traversent tous. Une facture
        d'énergie route vers le document dédié."""
        _periode, facture = self._create_periode_and_invoice(
            self.souscription_base, date(2024, 1, 1), date(2024, 1, 31)
        )
        self.assertEqual(facture._get_name_invoice_report(), 'souscriptions_odoo.report_facture_energie')

    def test_get_name_invoice_report_fallback_hors_energie(self):
        """Une facture hors énergie (`is_facture_energie = False`) retombe
        sur le gabarit standard d'Odoo via `super()` — automatiquement, sans
        liste d'exclusion à maintenir."""
        facture_normale = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner.id,
                'invoice_line_ids': [(0, 0, {'name': 'Produit test', 'quantity': 1, 'price_unit': 100.0})],
            }
        )
        self.assertFalse(facture_normale.is_facture_energie)
        self.assertEqual(facture_normale._get_name_invoice_report(), 'account.report_invoice_document')

    def test_template_rendering_base(self):
        """Test du rendu du template pour tarif Base"""
        periode, facture = self._create_periode_and_invoice(self.souscription_base, date(2024, 2, 1), date(2024, 2, 29))

        # Rendu au vrai chemin (#289) : account.account_invoices est l'action
        # Imprimer par défaut — portail/email/impression la traversent toutes.
        html_bytes, _dummy = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', facture.ids)
        html_content = html_bytes.decode()

        # Vérifications du contenu HTML (cartes Contrat / Point de livraison
        # du template EDN — reports/facture_energie_template.xml)
        self.assertIn('Contrat', html_content)
        self.assertIn('Point de livraison', html_content)
        self.assertIn('Marie Dupont Test', html_content)
        self.assertIn('PDL_TEMPLATE_BASE', html_content)
        self.assertIn('6 kVA', html_content)
        self.assertIn('Base', html_content)
        self.assertIn('COMP123456', html_content)

        # Vérifier les sections
        self.assertIn('Abonnement', html_content)
        self.assertIn('Énergie', html_content)

        # Vérifier les notes TURPE
        self.assertIn('Dont turpe fixe: 8.50€', html_content)
        self.assertIn('Dont turpe variable:', html_content)

        # Vérifier la mention réglementaire TURPE (callout, à titre informatif)
        self.assertIn('TURPE', html_content)

    def test_template_rendering_hphc(self):
        """Test du rendu du template pour tarif HP/HC"""
        periode, facture = self._create_periode_and_invoice(self.souscription_hphc, date(2024, 3, 1), date(2024, 3, 31))

        html_bytes, _dummy = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', facture.ids)
        html_content = html_bytes.decode()

        # Vérifications spécifiques HP/HC
        self.assertIn('HP/HC', html_content)
        self.assertIn('9 kVA', html_content)
        self.assertIn('PDL_TEMPLATE_HPHC', html_content)

        # Vérifier les notes TURPE pour HP/HC
        self.assertIn('Dont turpe fixe: 12.80€', html_content)

    def test_template_rendering_solidaire(self):
        """Test du rendu du template pour tarif solidaire"""
        periode, facture = self._create_periode_and_invoice(
            self.souscription_solidaire, date(2024, 4, 1), date(2024, 4, 30)
        )

        html_bytes, _dummy = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', facture.ids)
        html_content = html_bytes.decode()

        # Vérifier le badge tarif solidaire
        self.assertIn('Tarif solidaire', html_content)
        self.assertIn('3 kVA', html_content)

    def test_invoice_lines_structure(self):
        """Test de la structure des lignes de facture"""
        periode, facture = self._create_periode_and_invoice(self.souscription_base, date(2024, 5, 1), date(2024, 5, 31))

        # Vérifier la structure des lignes
        lines = facture.invoice_line_ids

        # Doit contenir des sections et des notes
        sections = lines.filtered(lambda l: l.display_type == 'line_section')
        notes = lines.filtered(lambda l: l.display_type == 'line_note')
        product_lines = lines.filtered(lambda l: l.display_type == 'product')

        # Vérifications
        self.assertTrue(len(sections) >= 2)  # Au moins Abonnement et Énergie
        self.assertTrue(len(notes) >= 2)  # Au moins 2 notes TURPE
        self.assertTrue(len(product_lines) >= 2)  # Au moins abonnement et énergie

        # Vérifier les noms des sections
        section_names = [s.name for s in sections]
        self.assertIn('Abonnement', section_names)
        self.assertIn('Énergie', section_names)

        # Vérifier les notes TURPE
        note_names = [n.name for n in notes]
        turpe_notes = [n for n in note_names if 'turpe' in n.lower()]
        self.assertTrue(len(turpe_notes) >= 2)

    def test_template_fallback_non_energie(self):
        """#289, vrai chemin : une facture hors énergie rend le gabarit
        standard d'Odoo sur account.account_invoices (l'action Imprimer par
        défaut, celle que portail/email/impression traversent toutes) — pas
        de fuite du design électricité."""
        # Créer une facture normale (non-énergie)
        facture_normale = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner.id,
                'invoice_line_ids': [
                    (
                        0,
                        0,
                        {
                            'name': 'Produit test',
                            'quantity': 1,
                            'price_unit': 100.0,
                        },
                    )
                ],
            }
        )

        # Vérifier que ce n'est pas une facture d'énergie
        self.assertFalse(facture_normale.is_facture_energie)

        html_bytes, _dummy = self.env['ir.actions.report']._render_qweb_html(
            'account.account_invoices', facture_normale.ids
        )
        html_content = html_bytes.decode()

        # Ne devrait pas contenir les éléments spécifiques à l'énergie
        self.assertNotIn('Point de livraison', html_content)
        self.assertNotIn('Tarif solidaire', html_content)

    def test_report_filename(self):
        """Test du nom de fichier personnalisé"""
        periode, facture = self._create_periode_and_invoice(self.souscription_base, date(2024, 6, 1), date(2024, 6, 30))

        filename = facture._get_report_base_filename()

        # Devrait contenir le nom de la souscription
        expected_pattern = f'Facture_Energie_{self.souscription_base.name}'
        self.assertIn(expected_pattern, filename)

    def test_paiement_prelevement_affiche_la_mention_sans_compte_bancaire(self):
        """#369 : le bloc Paiement lit `o.mode_paiement` (prélèvement) — la
        mention de prélèvement est présente, aucune mention agnostique
        n'est absente."""
        self.souscription_base.mode_paiement = 'prelevement'
        _periode, facture = self._create_periode_and_invoice(
            self.souscription_base, date(2024, 8, 1), date(2024, 8, 31)
        )

        html_bytes, _dummy = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', facture.ids)
        html_content = html_bytes.decode()

        self.assertIn('Prélèvement automatique déclenché le 10 du mois', html_content)
        self.assertIn("Pas d'escompte pour paiement anticipé", html_content)
        self.assertIn("Passée la date d'échéance", html_content)

    def test_paiement_avec_compte_bancaire_mais_mode_virement_naffiche_aucun_prelevement(self):
        """#369 : la régression corrigée — un partner porteur d'un
        `res.partner.bank` (donc de `bank_ids`) dont la souscription est en
        virement ne doit JAMAIS voir la mention de prélèvement (l'ancien
        gabarit la devinait depuis `bank_ids`, sans lire `mode_paiement`).
        Aucun bloc de mode pour virement ; les mentions agnostiques restent."""
        self.env['res.partner.bank'].create(
            {'partner_id': self.partner.id, 'acc_number': 'FR1420041010050500013M02606'}
        )
        self.souscription_base.mode_paiement = 'virement'
        _periode, facture = self._create_periode_and_invoice(
            self.souscription_base, date(2024, 9, 1), date(2024, 9, 30)
        )

        html_bytes, _dummy = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', facture.ids)
        html_content = html_bytes.decode()

        self.assertNotIn('Prélèvement automatique', html_content)
        self.assertNotIn('règlement manuel', html_content)
        self.assertIn("Pas d'escompte pour paiement anticipé", html_content)
        self.assertIn("Passée la date d'échéance", html_content)

    def test_paiement_monnaie_locale_affiche_la_marche_a_suivre_sans_qr(self):
        """#369 : Moneko affiche la marche à suivre vouvoyée, jamais de
        `<img>` de QR sur le PDF (immuable une fois émis — le QR ne vit que
        dans le mail, recomposé à chaque envoi)."""
        self.souscription_base.mode_paiement = 'monnaie_locale'
        _periode, facture = self._create_periode_and_invoice(
            self.souscription_base, date(2024, 10, 1), date(2024, 10, 31)
        )

        html_bytes, _dummy = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', facture.ids)
        html_content = html_bytes.decode()

        self.assertIn("d'ici le 10 de ce mois", html_content)
        self.assertIn('Opérations', html_content)
        self.assertNotIn('<img', html_content)
        self.assertNotIn('Prélèvement automatique', html_content)
        self.assertIn("Pas d'escompte pour paiement anticipé", html_content)
        self.assertIn("Passée la date d'échéance", html_content)

    def test_invoice_totals_calculation(self):
        """Test du calcul des totaux dans la facture"""
        periode, facture = self._create_periode_and_invoice(self.souscription_base, date(2024, 7, 1), date(2024, 7, 31))

        # Vérifier que la facture a un montant total
        self.assertGreater(facture.amount_total, 0)
        self.assertGreater(facture.amount_untaxed, 0)

        # Vérifier que le total correspond aux lignes
        product_lines = facture.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        calculated_total = sum(line.price_subtotal for line in product_lines)

        self.assertEqual(facture.amount_untaxed, calculated_total)
