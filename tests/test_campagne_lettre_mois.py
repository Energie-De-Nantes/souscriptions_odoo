"""Tests de la Lettre du mois portée par la Campagne (#313, ADR 0034) : champ
Html historisé, reporté de M-1 à M à la création — même idiome que les notes
de campagne (`_reporter_notes_precedentes`, test_campagne_notes.py), chaîné
N -> N+1 -> N+2…
"""

from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneLettreMois(SouscriptionsTestCase):
    def _campagne(self, mois, **vals):
        base = {'mois': mois}
        base.update(vals)
        return self.env['souscription.campagne.facturation'].create(base)

    def test_campagne_porte_un_champ_html_lettre_mois(self):
        """AC : un champ Html, un par mois — pas écrasé d'un mois sur l'autre."""
        campagne = self._campagne(date(2024, 5, 1), lettre_mois='<p>Bonjour à tous·tes !</p>')
        self.assertIn('Bonjour à tous·tes', campagne.lettre_mois)

    def test_lettre_de_m_moins_1_prefile_le_mois_m(self):
        """AC : la lettre de M-1 est pré-remplie à la création de la
        campagne de M."""
        self._campagne(date(2024, 5, 1), lettre_mois='<p>Tarif solidaire : 30% des foyers.</p>')

        juin = self._campagne(date(2024, 6, 1))

        self.assertIn('Tarif solidaire', juin.lettre_mois)

    def test_lettre_passee_a_la_creation_prime_sur_le_report(self):
        """Le report ne fait que PRÉ-remplir : une lettre écrite à la création
        est la volonté du·de la Facturiste et n'est pas écrasée par celle de
        M-1. Contrairement aux notes (des enfants qu'on ajoute), la lettre est
        un champ scalaire — sans garde, le report l'écraserait."""
        self._campagne(date(2024, 5, 1), lettre_mois='<p>Lettre de mai.</p>')

        juin = self._campagne(date(2024, 6, 1), lettre_mois='<p>Lettre de juin.</p>')

        self.assertIn('Lettre de juin', juin.lettre_mois)
        self.assertNotIn('Lettre de mai', juin.lettre_mois)

    def test_lettre_videe_dans_lediteur_a_la_creation_se_prefile_quand_meme(self):
        """`<p><br></p>` est ce que l'éditeur HTML envoie pour un champ vidé :
        c'est une absence de lettre, donc le report doit s'appliquer — d'où
        `is_html_empty` plutôt qu'un simple `not`."""
        self._campagne(date(2024, 5, 1), lettre_mois='<p>Permanences le mardi.</p>')

        juin = self._campagne(date(2024, 6, 1), lettre_mois='<p><br></p>')

        self.assertIn('Permanences le mardi', juin.lettre_mois)

    def test_chainage_m_moins_1_vers_m_vers_m_plus_1(self):
        """AC : le chaînage M-1 -> M -> M+1 tient — la lettre copiée devient
        elle-même la source du report suivant."""
        self._campagne(date(2024, 5, 1), lettre_mois='<p>Permanences le mardi.</p>')
        juin = self._campagne(date(2024, 6, 1))
        self.assertIn('Permanences le mardi', juin.lettre_mois)

        juillet = self._campagne(date(2024, 7, 1))

        self.assertIn('Permanences le mardi', juillet.lettre_mois)

    def test_absence_de_campagne_precedente_ne_reporte_rien(self):
        """AC : chaîne rompue (pas de campagne pour le mois précédent) —
        rien à reporter, aucune erreur, même contrat que les notes."""
        campagne = self._campagne(date(2024, 8, 1))

        self.assertFalse(campagne.lettre_mois)

    def test_lettre_vide_se_reporte_vide_sans_erreur(self):
        """Une campagne sans lettre écrite ne casse pas le report du mois
        suivant."""
        self._campagne(date(2024, 5, 1))

        juin = self._campagne(date(2024, 6, 1))

        self.assertFalse(juin.lettre_mois)

    def test_editer_la_lettre_du_mois_suivant_ne_modifie_pas_le_mois_precedent(self):
        """Le report est une COPIE, pas une référence partagée : réécrire M
        après coup laisse M-1 intact."""
        mai = self._campagne(date(2024, 5, 1), lettre_mois='<p>Version mai.</p>')
        juin = self._campagne(date(2024, 6, 1))

        juin.lettre_mois = '<p>Version juin, mise à jour.</p>'

        self.assertIn('Version mai', mai.lettre_mois)
        self.assertIn('Version juin', juin.lettre_mois)
