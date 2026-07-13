"""Tests des notes de campagne et du report au mois suivant (#159, ADR 0025).

Une note « à reporter » non traitée renaît comme prérequis repris (rappel
doux, non bloquant) dans la campagne suivante — jamais câblée au DAG (aucune
étape ne lit note_ids/reprise).
"""

from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCampagneNotes(SouscriptionsTestCase):
    def _campagne(self, mois):
        return self.env['souscription.campagne.facturation'].create({'mois': mois})

    def _note(self, campagne, **vals):
        base = {'campagne_id': campagne.id, 'texte': 'Une note'}
        base.update(vals)
        return self.env['souscription.campagne.note'].create(base)

    def test_campagne_porte_texte_a_reporter_traite(self):
        """AC : la campagne porte des notes (texte, à reporter, traité)."""
        campagne = self._campagne(date(2026, 5, 1))
        note = self._note(campagne, texte='Relancer le client X', a_reporter=True, traite=False)
        self.assertIn(note, campagne.note_ids)
        self.assertEqual(note.texte, 'Relancer le client X')
        self.assertTrue(note.a_reporter)
        self.assertFalse(note.traite)

    def test_note_a_reporter_non_traitee_apparait_dans_le_mois_suivant(self):
        """AC : créer N+1 recopie les notes de N où à_reporter=vrai &
        traité=faux, comme prérequis repris."""
        mai = self._campagne(date(2026, 5, 1))
        self._note(mai, texte='Relancer le client X', a_reporter=True, traite=False)

        juin = self._campagne(date(2026, 6, 1))

        reprises = juin.note_ids.filtered('reprise')
        self.assertEqual(len(reprises), 1)
        self.assertEqual(reprises.texte, 'Relancer le client X')
        self.assertTrue(reprises.a_reporter)
        self.assertFalse(reprises.traite)

    def test_note_sans_a_reporter_ne_se_reporte_pas(self):
        """AC : une note non flaguée à_reporter ne se reporte pas."""
        mai = self._campagne(date(2026, 5, 1))
        self._note(mai, texte='Note ponctuelle', a_reporter=False)

        juin = self._campagne(date(2026, 6, 1))

        self.assertFalse(juin.note_ids)

    def test_note_traitee_ne_se_reporte_pas_meme_si_a_reporter(self):
        mai = self._campagne(date(2026, 5, 1))
        self._note(mai, texte='Déjà réglée', a_reporter=True, traite=True)

        juin = self._campagne(date(2026, 6, 1))

        self.assertFalse(juin.note_ids)

    def test_chainage_note_reprise_non_traitee_se_reporte_encore(self):
        """AC : chaînage N→N+1→N+2 — une note reprise, toujours non traitée,
        se re-reporte au mois d'après."""
        mai = self._campagne(date(2026, 5, 1))
        self._note(mai, texte='Relancer', a_reporter=True, traite=False)
        juin = self._campagne(date(2026, 6, 1))
        self.assertEqual(len(juin.note_ids), 1)

        juillet = self._campagne(date(2026, 7, 1))

        reprises = juillet.note_ids.filtered('reprise')
        self.assertEqual(len(reprises), 1)
        self.assertEqual(reprises.texte, 'Relancer')
        self.assertEqual(reprises.origine_note_id, juin.note_ids)

    def test_marquer_traite_stoppe_le_chainage(self):
        """AC : marquer un prérequis repris traité le retire des rappels —
        il ne se reporte plus."""
        mai = self._campagne(date(2026, 5, 1))
        self._note(mai, texte='Relancer', a_reporter=True, traite=False)
        juin = self._campagne(date(2026, 6, 1))
        juin.note_ids.write({'traite': True})

        juillet = self._campagne(date(2026, 7, 1))

        self.assertFalse(juillet.note_ids, 'note traitée : ne se reporte plus')

    def test_absence_de_campagne_precedente_ne_reporte_rien(self):
        """Chaîne rompue (pas de campagne pour le mois précédent) : rien à
        reporter, aucune erreur."""
        campagne = self._campagne(date(2026, 8, 1))
        self.assertFalse(campagne.note_ids)

    def test_note_reprise_najamais_bloquante_pour_le_dag(self):
        """AC : les prérequis repris sont mis en avant mais ne bloquent
        jamais une étape — aucune étape ne référence note_ids/reprise."""
        mai = self._campagne(date(2026, 5, 1))
        self._note(mai, texte='Relancer', a_reporter=True, traite=False)
        juin = self._campagne(date(2026, 6, 1))
        self.assertTrue(juin.note_ids.filtered('reprise'), 'précondition : une note reprise existe bien')

        # Racines du DAG depuis #248 (pull_sorties_c15 + sync_f15) — même
        # rattrapage que test_racines_du_dag_toujours_pretes.
        racines = juin.etape_ids.filtered(lambda e: e.code in ('pull_sorties_c15', 'sync_f15'))
        self.assertTrue(racines)
        self.assertTrue(all(e.etat_prerequis == 'prete' for e in racines))
