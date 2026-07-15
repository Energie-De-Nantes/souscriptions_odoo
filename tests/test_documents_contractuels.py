"""Documents contractuels & Journal des actes (#63, ADR 0027).

Couvre la chaîne « capter au *Raccordement* → journaliser sur la *Souscription*
→ projeter dans les rapports » (ADR 0016/0027) : les déclarations/consentements
et les actes d'adhésion (acceptation CGV, renonciation au délai de
rétractation) sont saisis sur la demande de raccordement, journalisés (Journal
des actes, append-only) à la création de la Souscription — jamais recopiés en
champs plats —, puis rendus par les *Conditions particulières* et
l'*Attestation de fourniture*.
"""

import os
from datetime import date, timedelta

from lxml import etree
from odoo import fields
from odoo.tests.common import HttpCase, TransactionCase, tagged

from .common import SouscriptionsTestMixin, build_grille_lignes


@tagged('souscriptions', 'souscriptions_documents', 'post_install', '-at_install')
class TestCaptureConsentement(SouscriptionsTestMixin, TransactionCase):
    """Les déclarations captées au Raccordement sont journalisées sur la
    Souscription (ADR 0027) : cotitulaires recopiés, actes d'adhésion écrits au
    Journal des actes, jamais recopiés en champs plats."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.stage_final = cls.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')

    def _demande(self, **kwargs):
        defaults = {
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'provision_mensuelle_kwh': 250.0,
            'contact_nom': 'Titulaire',
            'contact_prenom': 'Test',
            'contact_email': 'titulaire@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'mode_paiement': 'prelevement',
            'bank_iban': 'FR1420041010050500013M02606',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    def test_actes_adhesion_journalises_sur_souscription(self):
        """Signature + renonciation saisies sur la demande produisent des lignes
        de Journal des actes sur la Souscription créée à la clôture du
        Raccordement — horodatage = la date de signature, plus de recopie de
        champs plats (ADR 0027)."""
        cotitulaire = self.env['res.partner'].create({'name': 'Cotitulaire Test'})
        signature = date.today()

        demande = self._demande(
            date_validation=signature,
            renonce_retractation=True,
            cotitulaires=[(6, 0, cotitulaire.ids)],
        )
        demande.stage_id = self.stage_final

        souscription = demande.souscription_id
        self.assertTrue(souscription, 'Souscription devrait être créée')
        self.assertEqual(souscription.cotitulaires, cotitulaire)

        acceptation = souscription._dernier_acte('acceptation_cgv')
        renonciation = souscription._dernier_acte('renonciation_retractation')
        self.assertTrue(acceptation, "L'acceptation CGV devrait être journalisée")
        self.assertTrue(renonciation, 'La renonciation devrait être journalisée')
        self.assertEqual(acceptation.date_consentement.date(), signature)
        self.assertEqual(renonciation.date_consentement.date(), signature)
        self.assertIn(demande.name, acceptation.source)

        # Plus de champs plats sur la Souscription (ADR 0027).
        self.assertNotIn('date_validation', souscription._fields)
        self.assertNotIn('renonce_retractation', souscription._fields)

    def test_declarations_par_defaut_vides(self):
        """Sans capture, la Souscription naît sans acte d'adhésion journalisé ni
        cotitulaire : une demande peut être close avant que la rétractation soit
        tranchée. Absence de ligne = pas de mention (ADR 0027)."""
        demande = self._demande()
        demande.stage_id = self.stage_final

        souscription = demande.souscription_id
        self.assertFalse(souscription._dernier_acte('acceptation_cgv'))
        self.assertFalse(souscription._dernier_acte('renonciation_retractation'))
        self.assertFalse(souscription.cotitulaires)

    def test_renonciation_seule_sans_signature_non_journalisee(self):
        """La renonciation n'a de sens qu'ancrée à une date de signature : sans
        date_validation, aucun acte n'est journalisé même si renonce_retractation
        est coché (pas d'horodatage fiable, pas de preuve, ADR 0027)."""
        demande = self._demande(renonce_retractation=True)
        demande.stage_id = self.stage_final

        souscription = demande.souscription_id
        self.assertFalse(souscription._dernier_acte('acceptation_cgv'))
        self.assertFalse(souscription._dernier_acte('renonciation_retractation'))


CP_URL = '/report/html/souscriptions_odoo.souscription_conditions_particulieres_document/%s'


@tagged('post_install', '-at_install', 'souscriptions_documents')
class TestConditionsParticulieres(SouscriptionsTestMixin, HttpCase):
    """Les Conditions particulières projettent la Souscription (ADR 0016) :
    titulaire, lieu, prix résolus depuis la Grille, déclarations, signature."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

        # TVA 20 % posée sur l'énergie Base pour exercer le chemin TTC/HT : le
        # particulier voit le prix taxé, la société le HT brut de la grille.
        cls.tva20 = cls.env['account.tax'].create(
            {
                'name': 'TVA 20% test',
                'amount': 20.0,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
            }
        )
        cls.env.ref('souscriptions_odoo.souscriptions_product_energie_base').taxes_id = [(6, 0, cls.tva20.ids)]

        cls.cotitulaire = cls.env['res.partner'].create({'name': 'Marie Cotitulaire'})

        # Particulier·ère, lissé, prélèvement, signé, renonce au délai, cotitulaire.
        cls.cp_particulier = cls.env['souscription.souscription'].create(
            {
                'partner_id': cls.partner_test.id,
                'cotitulaires': [(6, 0, cls.cotitulaire.ids)],
                'pdl': 'PDL_CP_PART',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'date_debut': date(2024, 1, 1),
                'lisse': True,
                'provision_mensuelle_kwh': 300.0,
                'mode_paiement': 'prelevement',
            }
        )
        # Actes d'adhésion journalisés (ADR 0027) : plus de champs plats sur la
        # Souscription — la CP les lit depuis le Journal des actes.
        signature = fields.Datetime.to_datetime('2025-03-14 09:00:00')
        cls.cp_particulier.enregistrer_consentement('acceptation_cgv', source='test', date_consentement=signature)
        cls.cp_particulier.enregistrer_consentement(
            'renonciation_retractation', source='test', date_consentement=signature
        )
        # Société : prix affichés HT.
        cls.cp_societe = cls.env['souscription.souscription'].create(
            {
                'partner_id': cls.partner_company.id,
                'pdl': 'PDL_CP_SOC',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'date_debut': date(2024, 1, 1),
                'mode_paiement': 'virement',
            }
        )

    def _html(self, souscription):
        self.authenticate('admin', 'admin')
        response = self.url_open(CP_URL % souscription.id)
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_rend_titulaire_lieu_et_cotitulaire(self):
        html = self._html(self.cp_particulier)
        self.assertIn('Conditions particulières', html)
        self.assertIn('Client Test Standard', html)  # titulaire
        self.assertIn('Marie Cotitulaire', html)  # cotitulaire
        self.assertIn('PDL_CP_PART', html)  # lieu de consommation

    def test_prix_energie_ht_pour_societe(self):
        """Société → prix de l'énergie Base affiché HT (0.1500 de la grille)."""
        html = self._html(self.cp_societe)
        self.assertIn('0.1500', html)
        self.assertIn('HT', html)

    def test_prix_energie_ttc_pour_particulier(self):
        """Particulier → même prix grille mais TTC (0.15 × 1.20 = 0.1800)."""
        html = self._html(self.cp_particulier)
        self.assertIn('0.1800', html)
        self.assertIn('TTC', html)

    def test_declarations_signature_et_support_durable(self):
        html = self._html(self.cp_particulier)
        # Renonciation au délai de rétractation journalisée.
        self.assertIn('rétractation', html.lower())
        # Lissage et mode de paiement déclarés.
        self.assertIn('Prélèvement', html)
        # Signature : l'année de la ligne acceptation_cgv (2025), distincte de
        # date_debut (2024).
        self.assertIn('2025', html)
        # Mention de la confirmation sur support durable.
        self.assertIn('support durable', html.lower())

    def test_sans_acte_journalise_aucune_mention(self):
        """Une Souscription sans ligne de journal n'imprime aucune mention
        d'adhésion ni de renonciation : absence de ligne = pas de preuve, donc
        pas de mention (ADR 0027) — la société de test n'a aucun acte journalisé."""
        html = self._html(self.cp_societe)
        self.assertIn('en attente', html.lower())
        self.assertNotIn('Adhésion validée le', html)
        self.assertNotIn('rétractation', html.lower())

    def test_mensualite_affichee_si_lisse(self):
        """Contrat lissé → une mensualité estimée figure sur la CP."""
        html = self._html(self.cp_particulier)
        self.assertIn('Mensualité', html)

    def test_ligne_consentement_lue_depuis_le_journal(self):
        """La CP affiche l'état du consentement « données de consommation » lu
        depuis le journal append-only (ADR 0017)."""
        self.cp_particulier.enregistrer_consentement('courbe_charge', source='test')
        html = self._html(self.cp_particulier)
        self.assertIn('données de consommation', html.lower())
        self.assertIn('Courbe de charge', html)
        # La finalité consentie est marquée « Donné » ; l'autre « Non renseigné ».
        self.assertIn('Donné', html)
        self.assertIn('Non renseigné', html)

    def test_projection_energie_majoree_pro(self):
        """PRO → l'énergie projetée porte la majoration (1 + coeff_pro/100),
        comme sur la facture (#67) : la CP et la facture montrent le même prix.
        Société (HT) pour comparer directement au prix grille brut (0.15)."""
        pro = self.cp_societe.copy({'coeff_pro': 10.0, 'pdl': 'PDL_CP_PRO'})
        base = next(e for e in pro._prix_documents()['energies'] if e['code'] == 'base')
        # 0.15 (grille) × 1.10 = 0.165, HT pour une société.
        self.assertAlmostEqual(base['prix_kwh'], 0.15 * 1.10, places=6)

    def test_projection_energie_sans_pro_egale_grille(self):
        """Non-PRO → l'énergie projetée est le prix grille brut, sans majoration
        (pas de régression). Société (HT) → 0.15 tel quel."""
        self.assertEqual(self.cp_societe.coeff_pro, 0.0)
        base = next(e for e in self.cp_societe._prix_documents()['energies'] if e['code'] == 'base')
        self.assertAlmostEqual(base['prix_kwh'], 0.15, places=6)

    def test_projection_prix_regime_moulin(self):
        """Régime Moulin (#105) : les Conditions particulières projettent le
        prix de la grille Moulin, pas celui du standard — même produit, prix
        différent (aucun produit dédié Moulin, CONTEXT.md)."""
        grille_moulin = self.env['grille.prix'].create(
            {
                'name': 'Grille Moulin CP',
                'date_debut': date(2024, 1, 1),
                'regime_prix': 'moulin',
            }
        )
        build_grille_lignes(self.env, grille_moulin, prix_base=0.30, prix_hp=0.35, prix_hc=0.25)

        moulin = self.cp_societe.copy({'regime_prix': 'moulin', 'pdl': 'PDL_CP_MOULIN'})
        base = next(e for e in moulin._prix_documents()['energies'] if e['code'] == 'base')
        self.assertAlmostEqual(base['prix_kwh'], 0.30, places=6)


ATTESTATION_URL = '/report/html/souscriptions_odoo.souscription_attestation_document/%s'


@tagged('post_install', '-at_install', 'souscriptions_documents')
class TestAttestationFourniture(SouscriptionsTestMixin, HttpCase):
    """L'attestation de fourniture est une preuve courte pour les tiers : ni prix,
    ni consentement, ni signature (CONTEXT.md / ADR 0016)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

    def _html(self, souscription):
        self.authenticate('admin', 'admin')
        response = self.url_open(ATTESTATION_URL % souscription.id)
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_rend_preuve_courte(self):
        html = self._html(self.souscription_base)
        self.assertIn('Attestation de fourniture', html)
        self.assertIn('Client Test Standard', html)  # titulaire
        self.assertIn('PDL_TEST_STANDARD', html)  # PDL
        self.assertIn('6', html)  # puissance souscrite
        self.assertIn('2024', html)  # actif depuis date_debut

    def test_pas_de_prix_consentement_ni_signature(self):
        """L'attestation ne porte aucune donnée tarifaire, ni consentement, ni
        signature — c'est ce qui la distingue des Conditions particulières."""
        html = self._html(self.souscription_base)
        self.assertNotIn('€/kWh', html)
        self.assertNotIn('Mensualité', html)
        self.assertNotIn('rétractation', html.lower())
        self.assertNotIn('support durable', html.lower())
        self.assertNotIn('Signature', html)
        self.assertNotIn('Conditions particulières', html)


@tagged('souscriptions', 'souscriptions_documents', 'post_install', '-at_install')
class TestJournalConsentement(SouscriptionsTestMixin, TransactionCase):
    """Journal des actes append-only possédé par la Souscription (ADR 0017/0027) :
    consentements RGPD (révocables) et actes d'adhésion contractuels
    (irrévocables), au sein du même journal (`souscription.consentement`)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

    def _ligne(self, souscription, **kwargs):
        vals = {
            'souscription_id': souscription.id,
            'finalite': 'courbe_charge',
            'etat': 'donne',
            'version_texte': '2026-06-v1',
            'source': 'test',
        }
        vals.update(kwargs)
        return self.env['souscription.consentement'].create(vals)

    def test_journal_est_append_only_en_ecriture(self):
        """Une ligne passée ne se réécrit pas : write lève (ADR 0017)."""
        from odoo.exceptions import UserError

        ligne = self._ligne(self.souscription_base)
        with self.assertRaises(UserError):
            ligne.etat = 'retire'

    def test_journal_est_append_only_en_suppression(self):
        """Une ligne passée ne se supprime pas : unlink lève (ADR 0017)."""
        from odoo.exceptions import UserError

        ligne = self._ligne(self.souscription_base)
        with self.assertRaises(UserError):
            ligne.unlink()

    def test_etat_courant_est_la_derniere_ligne(self):
        """L'état courant d'une finalité = sa dernière ligne ; le retrait crée une
        ligne et n'écrase pas la précédente (qui reste 'donne')."""
        donne = self._ligne(self.souscription_base, finalite='courbe_charge', etat='donne')
        retire = self._ligne(self.souscription_base, finalite='courbe_charge', etat='retire')

        self.assertEqual(self.souscription_base.etat_consentement('courbe_charge'), 'retire')
        # Append-only : la première ligne est intacte.
        self.assertEqual(donne.etat, 'donne')
        self.assertEqual(retire.etat, 'retire')

    def test_etat_courant_par_finalite(self):
        """Finalités granulaires : pas de consentement groupé (ADR 0017)."""
        self._ligne(self.souscription_base, finalite='courbe_charge', etat='donne')

        self.assertEqual(self.souscription_base.etat_consentement('courbe_charge'), 'donne')
        self.assertFalse(self.souscription_base.etat_consentement('conso_quotidienne'))

    def test_capture_a_la_creation_depuis_raccordement(self):
        """À la clôture du Raccordement, les finalités cochées créent des lignes de
        journal sur la Souscription ; les non cochées n'en créent pas."""
        demande = self.env['raccordement.demande'].create(
            {
                'pdl': 'TEST_CONSENT',
                'date_debut_souhaitee': date.today() + timedelta(days=10),
                'puissance_souscrite': '6',
                'contact_nom': 'Consent',
                'contact_email': 'consent@example.com',
                'contact_street': 'rue',
                'contact_zip': '44000',
                'contact_city': 'Nantes',
                'mode_paiement': 'virement',
                'consent_courbe_charge': True,
                'consent_conso_quotidienne': False,
            }
        )
        demande.stage_id = self.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')

        souscription = demande.souscription_id
        self.assertEqual(souscription.etat_consentement('courbe_charge'), 'donne')
        self.assertFalse(souscription.etat_consentement('conso_quotidienne'))

    def test_retrait_refuse_sur_acceptation_cgv(self):
        """Le journal refuse un retrait sur une finalité contractuelle
        irrévocable (ADR 0027) : on ne « retire » pas une signature."""
        from odoo.exceptions import UserError

        with self.assertRaises(UserError):
            self._ligne(self.souscription_base, finalite='acceptation_cgv', etat='retire')

    def test_retrait_refuse_sur_renonciation_retractation(self):
        """Même garde pour la renonciation au délai de rétractation."""
        from odoo.exceptions import UserError

        with self.assertRaises(UserError):
            self._ligne(self.souscription_base, finalite='renonciation_retractation', etat='retire')

    def test_retrait_rgpd_fonctionne_inchange(self):
        """Le garde d'irrévocabilité ne s'applique qu'aux deux finalités
        contractuelles : les retraits RGPD existants continuent de fonctionner."""
        ligne = self._ligne(self.souscription_base, finalite='courbe_charge', etat='retire')
        self.assertEqual(ligne.etat, 'retire')

    def test_don_accepte_sur_acte_irrevocable(self):
        """Un acte irrévocable peut être *donné* (c'est la signature elle-même) :
        seul le retrait est refusé."""
        ligne = self._ligne(self.souscription_base, finalite='acceptation_cgv', etat='donne')
        self.assertEqual(ligne.etat, 'donne')

    def test_dernier_acte_retourne_la_derniere_ligne(self):
        """`_dernier_acte` retourne l'enregistrement (pas seulement l'état) de la
        dernière ligne par finalité, vide si aucun acte."""
        self._ligne(self.souscription_base, finalite='acceptation_cgv', etat='donne')
        acte = self.souscription_base._dernier_acte('acceptation_cgv')
        self.assertTrue(acte)
        self.assertEqual(acte.finalite, 'acceptation_cgv')
        self.assertFalse(self.souscription_base._dernier_acte('renonciation_retractation'))

    def test_enregistrer_consentement_accepte_horodatage_explicite(self):
        """`enregistrer_consentement` accepte un horodatage explicite (date de
        signature) au lieu du défaut « maintenant » — nécessaire pour journaliser
        un acte d'adhésion à la date réelle de signature (ADR 0027)."""
        signature = fields.Datetime.to_datetime('2025-03-14 09:00:00')
        ligne = self.souscription_base.enregistrer_consentement(
            'acceptation_cgv', source='test', date_consentement=signature
        )
        self.assertEqual(ligne.date_consentement, signature)


@tagged('souscriptions', 'souscriptions_documents', 'post_install', '-at_install')
class TestConsentementDemoStructure(TransactionCase):
    """Garde structurel : le journal étant append-only (write interdit), sa démo
    DOIT être noupdate=1 — sinon un -u tenterait de réécrire les lignes et ferait
    échouer la mise à jour. Test structurel (lit le XML, n'a pas besoin que la
    démo soit chargée), cf. test_releve_demo.TestReleveDemoOrdre."""

    def test_demo_consentement_est_noupdate(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'demo', 'consentement_demo.xml')
        root = etree.parse(path).getroot()
        data = root.find('data')
        noupdate = root.get('noupdate') or (data is not None and data.get('noupdate'))
        self.assertEqual(noupdate, '1', 'demo/consentement_demo.xml doit être noupdate=1 (modèle append-only).')
        # Toutes les lignes ciblent bien le journal de consentement.
        models = {rec.get('model') for rec in root.iter('record')}
        self.assertEqual(models, {'souscription.consentement'})
