"""
Tests du `mois` canonique de la Période (#76, ADR 0020 §2).

`mois` est un `Date` au 1er du mois, dérivé stocké de `date_debut` — support
local de la clé d'idempotence `(RSC, mois)` du pull electricore (ADR 0011).
Unicité `(souscription, mois)` scopée aux périodes **mensuelles** :
régularisations et ajustements restent libres.
"""

from datetime import date

from odoo.tests.common import tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_mois', 'post_install', '-at_install')
class TestPeriodeMoisCanonique(SouscriptionsTestCase):
    def _periode(self, souscription, **vals):
        base = {
            'souscription_id': souscription.id,
            'date_debut': date(2024, 3, 1),
            'date_fin': date(2024, 4, 1),
            'type_periode': 'mensuelle',
        }
        base.update(vals)
        return self.env['souscription.periode'].create(base)

    def test_mois_derive_au_premier_du_mois(self):
        """`mois` est dérivé de `date_debut`, tronqué au 1er du mois."""
        periode = self._periode(self.souscription_base, date_debut=date(2024, 3, 15), date_fin=date(2024, 4, 15))
        self.assertEqual(periode.mois, date(2024, 3, 1))

    def test_mois_deja_au_premier_du_mois(self):
        """`date_debut` déjà au 1er du mois : `mois` lui est égal."""
        periode = self._periode(self.souscription_base, date_debut=date(2024, 3, 1), date_fin=date(2024, 4, 1))
        self.assertEqual(periode.mois, date(2024, 3, 1))

    def test_unicite_mensuelle_meme_mois_rejetee(self):
        """Deux périodes mensuelles de la même souscription sur le même mois
        canonique sont rejetées (clé d'idempotence (RSC, mois), ADR 0020 §2)."""
        self._periode(self.souscription_base)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self._periode(self.souscription_base)
            self.env.flush_all()

    def test_unicite_mensuelle_mois_differents_acceptee(self):
        """Deux périodes mensuelles de mois canoniques différents cohabitent."""
        p1 = self._periode(self.souscription_base, date_debut=date(2024, 3, 1), date_fin=date(2024, 4, 1))
        p2 = self._periode(self.souscription_base, date_debut=date(2024, 4, 1), date_fin=date(2024, 5, 1))
        self.assertNotEqual(p1.mois, p2.mois)

    def test_regularisations_libres_meme_mois(self):
        """Les régularisations/ajustements restent libres : plusieurs par mois
        possibles, hors du scope de l'unicité (ADR 0020 §2)."""
        self._periode(self.souscription_base, type_periode='regularisation')
        # Ne lève rien : les périodes non-mensuelles ne sont pas contraintes.
        self._periode(self.souscription_base, type_periode='regularisation')

    def test_ajustement_ne_bloque_pas_la_mensuelle_du_meme_mois(self):
        """Une régularisation/ajustement sur un mois n'empêche pas la période
        mensuelle correspondante (le scope est bien restreint au type mensuel)."""
        self._periode(self.souscription_base, type_periode='ajustement')
        # La mensuelle du même mois reste créable.
        self._periode(self.souscription_base, type_periode='mensuelle')
