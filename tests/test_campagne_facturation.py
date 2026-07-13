"""Tests de la Campagne de facturation — spine (#156, ADR 0025).

Le DAG déclaré par `ETAPES_CAMPAGNE` : `pull_meta_periodes`/`sync_f15` sont les
deux racines (les deux « vrais pulls ») ; chacun gate sa porte de vérif —
`verif_periodes` (prereq : pull méta-périodes) et `verif_refacturations`
(prereq : sync F15) ; `creer_factures` (prereq : les deux vérifs) et
`emettre_factures` (prereq : créer) sont des étapes à signal dérivé. Les
relevés d'index ne sont pas une étape : ils arrivent avec le pull des périodes.

Dans cette tranche, les étapes à signal dérivé (pull, créer, émettre) sont
volontairement toujours « non faites » (leur signal arrive en #157, cf.
ETAPES_CAMPAGNE) : seul le sous-DAG des portes manuelles est démontrable ici
(AC #156 : "here they can be treated as not-yet-done").
"""

from datetime import date

from odoo.addons.souscriptions_odoo.models.core import souscription_campagne as campagne_module
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneFacturationSpine(SouscriptionsTestCase):
    def _campagne(self, mois=date(2026, 7, 1)):
        return self.env['souscription.campagne.facturation'].create({'mois': mois})

    def _etape(self, campagne, code):
        return campagne.etape_ids.filtered(lambda e: e.code == code)

    def test_creation_seme_toutes_les_etapes_du_catalogue(self):
        """AC : créer une campagne amorce toutes les étapes du catalogue."""
        campagne = self._campagne()
        self.assertEqual(len(campagne.etape_ids), len(campagne_module.ETAPES_CAMPAGNE))
        self.assertEqual(set(campagne.etape_ids.mapped('code')), set(campagne_module.ETAPES_CAMPAGNE))

    def test_unicite_par_mois(self):
        """AC : une seconde campagne pour le même mois est rejetée — même à
        un autre jour du mois (unicité sur le mois, pas la date exacte)."""
        self._campagne(date(2026, 7, 1))
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._campagne(date(2026, 7, 15))

    def test_mois_normalise_au_premier_du_mois(self):
        campagne = self._campagne(date(2026, 7, 15))
        self.assertEqual(campagne.mois, date(2026, 7, 1))

    def test_racines_du_dag_toujours_pretes(self):
        """Les racines du DAG (pull sorties C15 + sync F15) sont toujours
        « prête » : aucune dépendance à satisfaire. `pull_meta_periodes`
        gagne un prérequis sur `pull_sorties_c15` (#248, ADR 0031 décision 4 —
        l'ordre de campagne « pull des sorties -> date_fin -> périmètre ->
        pull des méta-périodes ») : ce n'est donc plus une racine."""
        campagne = self._campagne()
        racines = campagne.etape_ids.filtered(lambda e: e.code in ('pull_sorties_c15', 'sync_f15'))
        self.assertEqual(len(racines), 2)
        self.assertTrue(all(e.etat_prerequis == 'prete' for e in racines))

    def test_etape_avec_prerequis_bloquee_tant_que_non_satisfaits(self):
        """`verif_refacturations` (prereq : sync F15) reste bloquée tant que le
        pull F15 n'a pas été lancé pour la campagne (`lance` = False)."""
        campagne = self._campagne()
        self.assertEqual(self._etape(campagne, 'verif_refacturations').etat_prerequis, 'bloquee')

    def test_valider_porte_persiste_valide_par_et_valide_le(self):
        """AC : valider une porte manuelle persiste validé_par/validé_le et la
        rend « faite » (la validation manuelle vaut override du prérequis)."""
        campagne = self._campagne()
        verif = self._etape(campagne, 'verif_periodes')
        self.assertFalse(verif.valide_par_id)
        self.assertFalse(verif.valide_le)
        self.assertFalse(verif.fait)

        verif.write({'valide': True})

        self.assertEqual(verif.valide_par_id, self.env.user)
        self.assertTrue(verif.valide_le)
        self.assertTrue(verif.fait)

    def test_validation_des_deux_portes_amont_debloque_letape_avale(self):
        """AC : valider une porte flippe les étapes avales de bloquée à
        prête une fois TOUS leurs prérequis satisfaits. `creer_factures`
        (prereq : vérif périodes + vérif refacturations, deux portes
        manuelles) le démontre sans dépendre d'un signal dérivé (#157)."""
        campagne = self._campagne()
        verif_periodes = self._etape(campagne, 'verif_periodes')
        verif_refacturations = self._etape(campagne, 'verif_refacturations')
        creer_factures = self._etape(campagne, 'creer_factures')
        self.assertEqual(creer_factures.etat_prerequis, 'bloquee')

        verif_periodes.write({'valide': True})
        campagne.etape_ids.invalidate_recordset()
        self.assertEqual(creer_factures.etat_prerequis, 'bloquee', 'un seul des deux prérequis validé')

        verif_refacturations.write({'valide': True})
        campagne.etape_ids.invalidate_recordset()
        self.assertEqual(creer_factures.etat_prerequis, 'prete', 'les deux prérequis sont validés')

    def test_devalider_une_porte_reverrouille_letape_avale(self):
        """Symétrique : redescendre `valide` à False rebloque l'étape avale
        (le DAG reste une fonction pure de l'état courant, pas un cliquet)."""
        campagne = self._campagne()
        verif_periodes = self._etape(campagne, 'verif_periodes')
        verif_refacturations = self._etape(campagne, 'verif_refacturations')
        creer_factures = self._etape(campagne, 'creer_factures')
        (verif_periodes | verif_refacturations).write({'valide': True})
        campagne.etape_ids.invalidate_recordset()
        self.assertEqual(creer_factures.etat_prerequis, 'prete')

        verif_periodes.write({'valide': False})
        campagne.etape_ids.invalidate_recordset()
        self.assertEqual(creer_factures.etat_prerequis, 'bloquee')

    def test_aucun_champ_verification_ajoute_sur_periode_ou_refacturation(self):
        """AC (ADR 0025) : la porte de vérif reste à la maille campagne — 0
        champ de vérification sur souscription.periode / .refacturation."""
        for modele in ('souscription.periode', 'souscription.refacturation'):
            for nom_champ in self.env[modele]._fields:
                self.assertNotIn('verifi', nom_champ.lower(), f'{modele}.{nom_champ} : champ de vérif inattendu')

    def test_menu_cycle_facturation_sous_racine_souscriptions(self):
        """AC : le menu « Cycle de facturation » liste les campagnes."""
        menu = self.env.ref('souscriptions_odoo.menu_souscription_campagne_facturation')
        self.assertEqual(menu.name, 'Cycle de facturation')
        self.assertEqual(menu.parent_id, self.env.ref('souscriptions_odoo.menu_souscription_root'))
        action = self.env.ref('souscriptions_odoo.action_souscription_campagne_facturation')
        self.assertEqual(menu.action.id, action.id)
        self.assertEqual(action.res_model, 'souscription.campagne.facturation')

    def test_liste_triee_mois_decroissant(self):
        """AC : l'historique EST la liste des campagnes, mois décroissant."""
        c1 = self._campagne(date(2026, 5, 1))
        c2 = self._campagne(date(2026, 6, 1))
        c3 = self._campagne(date(2026, 7, 1))
        toutes = self.env['souscription.campagne.facturation'].search([('id', 'in', (c1 | c2 | c3).ids)])
        self.assertEqual(list(toutes), [c3, c2, c1])

    def test_nom_affiche_le_mois_en_toutes_lettres(self):
        campagne = self._campagne(date(2026, 7, 3))
        self.assertEqual(campagne.name, 'Juillet 2026')
