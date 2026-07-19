"""Tests du socle « champs du passé » (issue #208, PRD #207, ADR 0023 §3
amendé).

Deux champs, deux modèles :

- `souscription.periode.legacy_regularisee` (« état régularisée ») : déjà
  posé par le second auteur clôture (ADR 0031 décision 4, #248) et déjà lu
  par la sélection des candidats de la Régularisation
  (`souscription_regularisation.py::_recalculer`, couvert par
  `test_regularisation.py::test_ac3_mois_legacy_regularisee_exclu_silencieusement`).
  Ce fichier couvre ce qui restait sans test dédié pour #208 : le champ est
  posable au `create()` — y compris sur une Période déjà verrouillée par
  `facture_legacy_ref` — sans passer par le verrou de facturation (#14), et il
  est visible en vue liste ET formulaire.
- `account.move.origine_legacy` : nouveau champ, booléen d'affichage
  filtrable en vue liste factures, distinct de la clé technique
  (`__migration__`, external id, hors de ce module).
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_champs_passe', 'post_install', '-at_install')
class TestLegacyRegulariseePosableAuCreate(SouscriptionsTestCase):
    def test_posable_au_create_sur_une_periode_deja_verrouillee(self):
        """AC1 : `legacy_regularisee` se pose AU CREATE, même sur une Période
        d'ouverture (`facture_legacy_ref`, ADR 0023 décision 3) qui naît déjà
        verrouillée (`_est_facturee_emise` renvoie True dès que
        `facture_legacy_ref` est posé) — la Période historique naît complète
        et figée, le verrou de facturation (#14) n'est pas modifié."""
        periode = self.env['souscription.periode'].create(
            {
                'souscription_id': self.souscription_base.id,
                'date_debut': date(2023, 6, 1),
                'date_fin': date(2023, 7, 1),
                'type_periode': 'mensuelle',
                'facture_legacy_ref': 'FACT-PROD-2023-0999',
                'provision_base_kwh': 280.0,
                'legacy_regularisee': True,
            }
        )

        self.assertTrue(periode.legacy_regularisee)
        self.assertTrue(periode._est_facturee_emise(), 'Une Période legacy naît déjà verrouillée')

    def test_write_ulterieur_ne_passe_pas_par_le_verrou(self):
        """`legacy_regularisee` est volontairement absent de `_LOCKED_FIELDS`
        (cf. son commentaire dans `souscription_periode.py`) : un `write()`
        ultérieur sur une Période déjà ÉMISE (facture postée) réussit — le
        champ n'a pas besoin du contexte `regularisation_tampon` — alors
        qu'un champ facturable comme `provision_base_kwh` lève une
        UserError dans les mêmes conditions (contrôle négatif)."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()
        facture.action_post()
        self.assertTrue(periode._est_facturee_emise())

        periode.write({'legacy_regularisee': True})
        self.assertTrue(periode.legacy_regularisee)

        with self.assertRaises(UserError):
            periode.write({'provision_base_kwh': 999.0})


@tagged('souscriptions', 'souscriptions_champs_passe', 'post_install', '-at_install')
class TestLegacyRegulariseeVue(SouscriptionsTestCase):
    def test_visible_en_vue_liste_et_formulaire(self):
        """AC1 : le champ est exposé sur les vues liste ET formulaire de la
        Période — même convention que `facture_legacy_ref`
        (`test_periode_ouverture.py::test_identifiable_en_liste_et_formulaire`)."""
        list_view = self.env['souscription.periode'].get_view(view_type='list')
        self.assertIn('legacy_regularisee', list_view['arch'])

        form_view = self.env['souscription.periode'].get_view(view_type='form')
        self.assertIn('legacy_regularisee', form_view['arch'])


@tagged('souscriptions', 'souscriptions_champs_passe', 'post_install', '-at_install')
class TestOrigineLegacy(SouscriptionsTestCase):
    def _facture(self, **vals):
        base = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_test.id,
            'invoice_date': date(2024, 1, 31),
        }
        base.update(vals)
        return self.env['account.move'].create(base)

    def test_default_false_et_settable(self):
        """AC3 : booléen d'affichage, défaut False, posable comme n'importe
        quel champ — l'ETL de migration le pose au backfill."""
        native = self._facture()
        self.assertFalse(native.origine_legacy)

        legacy = self._facture(origine_legacy=True)
        self.assertTrue(legacy.origine_legacy)

    def test_filtrable_en_liste(self):
        """AC3 : filtrable en vue liste factures — le domaine ORM fonctionne
        (le filtre de recherche natif s'appuie dessus) ET le champ est
        exposé, comme colonne et comme filtre, sur les vues natives des
        factures client (`account.view_invoice_tree` / `..._filter`)."""
        legacy = self._facture(origine_legacy=True)
        native = self._facture()

        trouvees = self.env['account.move'].search([('origine_legacy', '=', True), ('id', 'in', (legacy | native).ids)])
        self.assertEqual(trouvees, legacy)

        list_view = self.env['account.move'].get_view(view_id=self.env.ref('account.view_out_invoice_tree').id)
        self.assertIn('origine_legacy', list_view['arch'])

        search_view = self.env['account.move'].get_view(view_id=self.env.ref('account.view_account_invoice_filter').id)
        self.assertIn('origine_legacy', search_view['arch'])
