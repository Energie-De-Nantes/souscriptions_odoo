"""
Tests du `mois` canonique de la Période (#76, ADR 0020 §2) et de son unicité
(#239, ADR 0030 décision 3).

`mois` est un `Date` au 1er du mois, dérivé stocké de `date_debut` — support
local de la clé d'idempotence `(RSC, mois)` du pull electricore (ADR 0011).
La Période est **purement mensuelle** : `type_periode` ne porte plus que
`mensuelle` (la Régularisation est un modèle propre depuis la tranche 4,
#236) — l'unicité `(souscription, mois)` est donc **pleine**, portée par un
`models.Constraint` UNIQUE ordinaire (plus d'index partiel scopé au type).
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
        """AC2 : deux mensuelles de la même souscription sur le même mois
        canonique sont toujours rejetées — unicité **pleine** (clé
        d'idempotence (RSC, mois), ADR 0020 §2 amendé par ADR 0030 décision 3,
        #239)."""
        self._periode(self.souscription_base)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self._periode(self.souscription_base)
            self.env.flush_all()

    def test_unicite_mensuelle_mois_differents_acceptee(self):
        """Deux périodes mensuelles de mois canoniques différents cohabitent."""
        p1 = self._periode(self.souscription_base, date_debut=date(2024, 3, 1), date_fin=date(2024, 4, 1))
        p2 = self._periode(self.souscription_base, date_debut=date(2024, 4, 1), date_fin=date(2024, 5, 1))
        self.assertNotEqual(p1.mois, p2.mois)

    # `test_regularisations_libres_meme_mois` et
    # `test_ajustement_ne_bloque_pas_la_mensuelle_du_meme_mois` (unicité
    # scopée aux seules mensuelles) sont retirés : sans objet depuis que
    # `type_periode` ne porte plus que `mensuelle` (#239) — on ne peut plus
    # créer de période 'regularisation'/'ajustement' via l'ORM (Selection).
