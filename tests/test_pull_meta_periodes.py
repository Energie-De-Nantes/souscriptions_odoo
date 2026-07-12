"""
Tests du pull des méta-périodes (#77, ADR 0011/0019/0020 ; service extrait
#233, tranche 1 du PRD #231 ; pull unifié gardé par l'empreinte #235, tranche
2 du PRD #231 — ADR 0030 décision 1).

Quatre tranches :
- `_amorcer_depuis_meta` / `_releve_vals_depuis_objet` : mapping pur
  `PeriodeMeta`/`ObjetReleve` → `create()`, testé avec des stubs duck-typés
  (aucune dépendance à `electricore_client`, cf. la garde d'import de la
  fabrique).
- `_rafraichir_depuis_meta` : mapping pur `PeriodeMeta` → `write()` en bloc
  sur une Période déjà amorcée (#235), relevés remplacés en bloc seulement
  si non facturée.
- Le service `souscription.pull.meta.periodes.service` — propriétaire
  durable du pull (#233), gardé par l'empreinte (#235) : create-missing,
  écriture gardée par `source_hash`, skip-and-report, erreurs typées
  mappées, scope refresh — client mocké.
- Le wizard « Récupérer les périodes du mois », coquille mince (#233) :
  périmètre avec/sans RSC + formatage du résumé, délègue au service.

Fixtures RSC/PDL : identifiants factices (jamais des vrais échantillons).
"""

import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from odoo.addons.souscriptions_odoo.models.core import electricore_client_fabrique as fabrique_module
from odoo.addons.souscriptions_odoo.models.core import souscription_pull_meta_periodes_service as service_module
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase, client_flux_factice, flux_electricore, patcher_client_fabrique


def _objet_releve(**kwargs):
    """Stub duck-typé d'`ObjetReleve` (contrat v3) : mêmes attributs, valeurs
    par défaut à None pour les champs optionnels du contrat."""
    base = dict(
        releve_id='ELC-RELEVE-001',
        date_releve='2024-01-31',
        nature_index='reel',
        origine_releve='flux_R151',
        evenement=None,
        index_base_kwh=None,
        index_hp_kwh=None,
        index_hc_kwh=None,
        index_hph_kwh=None,
        index_hch_kwh=None,
        index_hpb_kwh=None,
        index_hcb_kwh=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _periode_meta(**kwargs):
    """Stub duck-typé de `PeriodeMeta` (contrat v3) : mêmes attributs que le
    modèle pydantic réel, mêmes noms — le mapping ne fait aucune traduction."""
    base = dict(
        ref_situation_contractuelle='RSC-00000000000001',
        pdl='14000000000001',
        mois_annee='2024-01',
        debut='2024-01-01',
        fin='2024-02-01',
        nb_jours=31,
        puissance_moyenne_kva=6.0,
        formule_tarifaire_acheminement='CU4',
        energie_base_kwh=280.0,
        energie_hp_kwh=None,
        energie_hc_kwh=None,
        turpe_fixe_eur=8.5,
        turpe_variable_eur=4.2,
        cta_eur=1.1,
        taux_accise_eur_mwh=21.0,
        has_changement=False,
        qualite='réelle',
        statut_communication='communicante',
        releves_utilises=[],
        source_hash='hash-abc123',
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@tagged('souscriptions', 'souscriptions_pull_meta', 'post_install', '-at_install')
class TestAmorcerDepuisMeta(SouscriptionsTestCase):
    """Mapping pur `PeriodeMeta` → `create()` (aucun client requis)."""

    def test_mappe_les_champs_du_contrat_sans_traduction(self):
        meta = _periode_meta()
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)

        self.assertEqual(periode.date_debut, date(2024, 1, 1))
        self.assertEqual(periode.date_fin, date(2024, 2, 1))
        self.assertEqual(periode.puissance_moyenne_kva, 6.0)
        self.assertEqual(periode.energie_base_kwh, 280.0)
        self.assertEqual(periode.turpe_fixe, 8.5)
        self.assertEqual(periode.turpe_variable, 4.2)
        self.assertEqual(periode.cta_eur, 1.1)
        self.assertEqual(periode.taux_accise_eur_mwh, 21.0)
        self.assertEqual(periode.qualite, 'réelle')
        self.assertEqual(periode.statut_communication, 'communicante')
        self.assertEqual(periode.source_hash, 'hash-abc123')
        self.assertFalse(periode.has_changement)

    def test_qualite_incalculable_creee_quand_meme(self):
        """Une période incalculable est créée, énergies nulles (brouillon
        facturable, CONTEXT.md / ADR 0020 §4)."""
        meta = _periode_meta(
            qualite='incalculable',
            statut_communication=None,
            energie_base_kwh=None,
            energie_hp_kwh=None,
            energie_hc_kwh=None,
        )
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)

        self.assertEqual(periode.qualite, 'incalculable')
        self.assertEqual(periode.energie_base_kwh, 0.0)

    def test_releves_utilises_deviennent_des_enfants_avec_provenance(self):
        """`releves_utilises` -> relevés enfants, provenance conservée
        (releve_externe_id, origine) — ADR 0020 §6."""
        meta = _periode_meta(
            releves_utilises=[
                _objet_releve(
                    releve_id='ELC-RELEVE-100',
                    date_releve='2024-01-01',
                    nature_index='reel',
                    origine_releve='flux_R151',
                    index_base_kwh=1000,
                ),
                _objet_releve(
                    releve_id='ELC-RELEVE-101',
                    date_releve='2024-01-31',
                    nature_index='estime',
                    origine_releve='estimation_electricore',
                    index_base_kwh=1280,
                ),
            ]
        )
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)

        self.assertEqual(len(periode.releve_ids), 2)
        premier, second = periode.releve_ids.sorted('date')
        self.assertEqual(premier.releve_externe_id, 'ELC-RELEVE-100')
        self.assertEqual(premier.origine, 'flux_R151')
        self.assertEqual(premier.nature, 'reel')
        self.assertEqual(premier.index_base, 1000.0)
        self.assertEqual(second.nature, 'estime')

    def test_index_kwh_absent_devient_zero_entier(self):
        """`index_*_kwh=None` (registre non transmis) → défaut `0` (int, #132),
        pas `0.0` : les index sont des `fields.Integer` côté Odoo."""
        meta = _periode_meta(releves_utilises=[_objet_releve(index_base_kwh=None)])
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)

        self.assertEqual(periode.releve_ids.index_base, 0)
        self.assertIsInstance(periode.releve_ids.index_base, int)

    def test_nature_corrige_devient_reel(self):
        """`nature_index='corrige'` (réel révisé) atterrit en `reel` (ADR 0020 §6)."""
        meta = _periode_meta(
            releves_utilises=[_objet_releve(nature_index='corrige')],
        )
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)
        self.assertEqual(periode.releve_ids.nature, 'reel')

    def test_evenement_prime_sur_origine_releve_pour_lorigine(self):
        """Un relevé d'événement C15 documente son origine par `evenement`
        (précision), sinon on retombe sur `origine_releve` (ADR 0020 §6)."""
        meta = _periode_meta(
            releves_utilises=[
                _objet_releve(origine_releve='flux_C15', evenement='CHGCPT'),
            ],
        )
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)
        self.assertEqual(periode.releve_ids.origine, 'CHGCPT')

    def test_create_missing_only_ne_reecrit_jamais_lexistant(self):
        """Un `(souscription, mois)` déjà amorcé n'est jamais réécrit
        automatiquement (ADR 0011) : garde vérifiée au niveau wizard, pas ici —
        ce test verrouille la clé (contrainte unique mensuelle, ADR 0020 §2)."""
        self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, _periode_meta())
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, _periode_meta())


# === `_rafraichir_depuis_meta` : mapping pur PeriodeMeta -> write() en bloc
# sur une Période déjà amorcée (#235, ADR 0030 décision 1). Appelée par le
# service une fois l'empreinte/le verdict jugés fiables — la garde vit chez
# l'appelant (cf. TestPullMetaPeriodesService plus bas) ; ici on vérifie que
# la méthode écrit inconditionnellement, en bloc, et respecte le facturé gelé.


@tagged('souscriptions', 'souscriptions_pull_meta', 'post_install', '-at_install')
class TestRafraichirDepuisMeta(SouscriptionsTestCase):
    def test_ecrase_latterrissage_v3_en_bloc(self):
        """L'énergie, le TURPE, la CTA, l'accise, la puissance moyenne, les
        verdicts et l'empreinte sont tous écrasés par un seul write()."""
        periode = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(source_hash='H1', energie_base_kwh=280.0, turpe_fixe_eur=8.5, cta_eur=1.1),
        )
        meta = _periode_meta(
            source_hash='H2',
            energie_base_kwh=310.0,
            turpe_fixe_eur=9.0,
            turpe_variable_eur=4.8,
            cta_eur=1.3,
            taux_accise_eur_mwh=22.0,
            puissance_moyenne_kva=7.0,
            qualite='estimée',
            statut_communication='non_communicante',
            has_changement=True,
        )

        periode._rafraichir_depuis_meta(meta)

        self.assertEqual(periode.energie_base_kwh, 310.0)
        self.assertEqual(periode.turpe_fixe, 9.0)
        self.assertEqual(periode.turpe_variable, 4.8)
        self.assertEqual(periode.cta_eur, 1.3)
        self.assertEqual(periode.taux_accise_eur_mwh, 22.0)
        self.assertEqual(periode.puissance_moyenne_kva, 7.0)
        self.assertEqual(periode.qualite, 'estimée')
        self.assertEqual(periode.statut_communication, 'non_communicante')
        self.assertTrue(periode.has_changement)
        self.assertEqual(periode.source_hash, 'H2')

    def test_remplace_les_releves_en_bloc_si_non_facturee(self):
        """AC3 : Période non facturée -> relevés remplacés en bloc (le
        re-pull promis par ADR 0015)."""
        periode = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(releves_utilises=[_objet_releve(releve_id='R1', index_base_kwh=1000)]),
        )
        self.assertEqual(periode.releve_ids.releve_externe_id, 'R1')

        periode._rafraichir_depuis_meta(
            _periode_meta(source_hash='H2', releves_utilises=[_objet_releve(releve_id='R2', index_base_kwh=1310)])
        )

        self.assertEqual(len(periode.releve_ids), 1)
        self.assertEqual(periode.releve_ids.releve_externe_id, 'R2')

    def test_provisions_et_releves_intacts_si_facturee(self):
        """AC2/AC5 : Période facturée -> le mesuré est rafraîchi mais la
        provision (facturé gelé) et le relevé-justificatif restent intacts —
        exemption chirurgicale du verrou (#14), jamais la provision."""
        periode = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(
                releves_utilises=[_objet_releve(releve_id='R1', index_base_kwh=1000)], energie_base_kwh=280.0
            ),
        )
        periode._creer_facture()  # facturée -> tampon provision := energie (#234)
        self.assertEqual(periode.provision_base_kwh, 280.0)

        periode._rafraichir_depuis_meta(
            _periode_meta(
                releves_utilises=[_objet_releve(releve_id='R2', index_base_kwh=1310)],
                energie_base_kwh=310.0,
                source_hash='H2',
                qualite='réelle',
            )
        )

        self.assertEqual(periode.energie_base_kwh, 310.0)  # mesuré rafraîchi
        self.assertEqual(periode.provision_base_kwh, 280.0)  # facturé gelé, intact
        self.assertEqual(periode.releve_ids.releve_externe_id, 'R1')  # relevé-justificatif intact


# === Service « propriétaire durable du pull », gardé par l'empreinte (#233,
# #235) : client mocké ===
#
# `souscription.pull.meta.periodes.service` porte désormais la politique
# gardée par l'empreinte (ADR 0030 décision 1, #235 — create-missing pour la
# création, source_hash/qualite pour l'écriture d'une Période existante) et
# skip-and-report (ADR 0011), et la méthode de transport nommée `_ouvrir_flux`
# (ADR 0024 §6). Les exceptions levées sont les vraies classes du module
# service (réelles si electricore_client est présent, stubs de la fabrique
# sinon, ADR 0024/#222) : aucun échange de symbole par patch, `except
# IngestionEnCours` du service attrape exactement ce qui est instancié ici.


@tagged('souscriptions', 'souscriptions_pull_meta', 'post_install', '-at_install')
class TestPullMetaPeriodesService(SouscriptionsTestCase):
    def _pull(self, client, souscriptions, mois=date(2024, 1, 1)):
        """Appelle le point d'entrée unique du scope facturation (#233 AC1),
        transport patché via la fabrique client (ADR 0024) — jamais de vrai
        client construit."""
        with patcher_client_fabrique(client):
            return self.env['souscription.pull.meta.periodes.service'].pull(souscriptions, mois)

    # --- Création (create-missing) ---

    def test_cree_les_periodes_manquantes_pour_les_souscriptions_a_rsc(self):
        """AC2 : le service crée les périodes manquantes du mois pour les
        souscriptions à RSC."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut='2024-01-01',
            fin='2024-02-01',
        )
        client = client_flux_factice('meta_periodes', [meta])

        creees, rafraichies, inchangees, conservees, erreurs = self._pull(client, self.souscription_base)

        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', date(2024, 1, 1))]
        )
        self.assertEqual(len(periode), 1)
        self.assertEqual(len(creees), 1)
        self.assertFalse(rafraichies)
        self.assertFalse(inchangees)
        self.assertFalse(conservees)
        self.assertFalse(erreurs)
        client.meta_periodes.assert_called_once_with(mois='2024-01-01', rsc=['RSC-00000000000001'])

    def test_releves_crees_avec_identifiant_externe_et_origine(self):
        """AC4 (#233) : relevés créés avec identifiant externe + origine."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut='2024-01-01',
            fin='2024-02-01',
            releves_utilises=[_objet_releve(releve_id='ELC-999', origine_releve='flux_R151')],
        )
        self._pull(client_flux_factice('meta_periodes', [meta]), self.souscription_base)

        releve = self.env['souscription.releve'].search([('releve_externe_id', '=', 'ELC-999')])
        self.assertEqual(len(releve), 1)
        self.assertEqual(releve.origine, 'flux_R151')

    def test_erreur_par_periode_ne_bloque_pas_le_lot(self):
        """Skip-and-report par élément : une erreur d'amorçage sur une RSC
        n'empêche pas les autres d'être traitées, et apparaît dans le résumé."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        meta_invalide = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut=None,  # déclenche une erreur de mapping (Date invalide)
            fin='2024-02-01',
        )
        creees, rafraichies, inchangees, conservees, erreurs = self._pull(
            client_flux_factice('meta_periodes', [meta_invalide]), self.souscription_base
        )
        self.assertEqual(len(erreurs), 1)

    # --- Politique d'écriture gardée par l'empreinte (ADR 0030 décision 1, #235) ---

    def test_empreinte_inchangee_naboutit_a_aucune_ecriture(self):
        """AC1 : `source_hash` inchangé -> rien n'est touché — une correction
        manuelle du·de la facturiste survit à la relecture de données
        inchangées."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        existante = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(ref_situation_contractuelle='RSC-00000000000001', source_hash='H1', cta_eur=1.1),
        )
        existante.cta_eur = 1.99  # correction manuelle du·de la facturiste

        meta = _periode_meta(ref_situation_contractuelle='RSC-00000000000001', source_hash='H1', cta_eur=999.0)
        creees, rafraichies, inchangees, conservees, erreurs = self._pull(
            client_flux_factice('meta_periodes', [meta]), self.souscription_base
        )

        self.assertEqual(existante.cta_eur, 1.99)  # correction manuelle intacte
        self.assertEqual(len(inchangees), 1)
        self.assertFalse(creees)
        self.assertFalse(rafraichies)
        self.assertFalse(conservees)
        self.assertFalse(erreurs)

    def test_empreinte_nouvelle_verdict_fiable_rafraichit_le_mesure_en_bloc(self):
        """AC2/AC3 : empreinte nouvelle + verdict réelle/estimée -> le mesuré
        v3 est rafraîchi en bloc sur une Période non facturée."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        existante = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(ref_situation_contractuelle='RSC-00000000000001', source_hash='H1', energie_base_kwh=280.0),
        )
        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            source_hash='H2',
            energie_base_kwh=310.0,
            qualite='réelle',
        )
        creees, rafraichies, inchangees, conservees, erreurs = self._pull(
            client_flux_factice('meta_periodes', [meta]), self.souscription_base
        )

        self.assertEqual(existante.energie_base_kwh, 310.0)
        self.assertEqual(existante.source_hash, 'H2')
        self.assertEqual(len(rafraichies), 1)
        self.assertFalse(creees)
        self.assertFalse(inchangees)
        self.assertFalse(conservees)
        self.assertFalse(erreurs)

    def test_empreinte_nouvelle_periode_facturee_provisions_et_releves_intacts(self):
        """AC2 : sur une Période facturée, le mesuré est rafraîchi mais les
        provisions et les relevés-justificatifs restent intacts — exemption
        chirurgicale du verrou (#14), jamais la provision."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        existante = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(
                ref_situation_contractuelle='RSC-00000000000001',
                source_hash='H1',
                energie_base_kwh=280.0,
                releves_utilises=[_objet_releve(releve_id='R1', index_base_kwh=1000)],
            ),
        )
        existante._creer_facture()  # facturée -> provision tamponnée (#234)
        self.assertEqual(existante.provision_base_kwh, 280.0)

        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            source_hash='H2',
            energie_base_kwh=310.0,
            qualite='réelle',
            releves_utilises=[_objet_releve(releve_id='R2', index_base_kwh=1310)],
        )
        creees, rafraichies, inchangees, conservees, erreurs = self._pull(
            client_flux_factice('meta_periodes', [meta]), self.souscription_base
        )

        self.assertEqual(existante.energie_base_kwh, 310.0)  # mesuré rafraîchi
        self.assertEqual(existante.provision_base_kwh, 280.0)  # facturé gelé
        self.assertEqual(existante.releve_ids.releve_externe_id, 'R1')  # relevé-justificatif intact
        self.assertEqual(len(rafraichies), 1)

    def test_empreinte_nouvelle_periode_non_facturee_remplace_les_releves_en_bloc(self):
        """AC3 : sur une Période non facturée, les relevés sont remplacés en
        bloc — le re-pull promis par ADR 0015, enfin réalisé."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        existante = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(
                ref_situation_contractuelle='RSC-00000000000001',
                source_hash='H1',
                releves_utilises=[_objet_releve(releve_id='R1', index_base_kwh=1000)],
            ),
        )
        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            source_hash='H2',
            qualite='réelle',
            releves_utilises=[_objet_releve(releve_id='R2', index_base_kwh=1310)],
        )
        self._pull(client_flux_factice('meta_periodes', [meta]), self.souscription_base)

        self.assertEqual(len(existante.releve_ids), 1)
        self.assertEqual(existante.releve_ids.releve_externe_id, 'R2')

    def test_qualite_incalculable_conserve_et_signale(self):
        """AC4 : verdict incalculable -> valeur stockée conservée, signalée
        au rapport — « je ne sais pas » n'écrase pas « je savais »."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        existante = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(ref_situation_contractuelle='RSC-00000000000001', source_hash='H1', energie_base_kwh=280.0),
        )
        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            source_hash='H2',
            qualite='incalculable',
            energie_base_kwh=0.0,
        )
        creees, rafraichies, inchangees, conservees, erreurs = self._pull(
            client_flux_factice('meta_periodes', [meta]), self.souscription_base
        )

        self.assertEqual(existante.energie_base_kwh, 280.0)  # conservée
        self.assertEqual(existante.source_hash, 'H1')  # empreinte pas mise à jour non plus
        self.assertEqual(len(conservees), 1)
        self.assertFalse(rafraichies)

    def test_mois_absent_du_flux_conserve_et_signale(self):
        """AC4 : une Période déjà amorcée dont la RSC n'est pas revenue dans
        le lot est conservée, signalée."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        existante = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(ref_situation_contractuelle='RSC-00000000000001', source_hash='H1', energie_base_kwh=280.0),
        )
        creees, rafraichies, inchangees, conservees, erreurs = self._pull(
            client_flux_factice('meta_periodes', []), self.souscription_base
        )

        self.assertEqual(existante.energie_base_kwh, 280.0)
        self.assertEqual(len(conservees), 1)
        self.assertIn('mois absent', conservees[0])

    def test_ingestion_en_cours_mappee_en_userror_reessayable(self):
        """AC5 : IngestionEnCours -> message « réessayer plus tard »."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_flux_factice('meta_periodes', leve=service_module.IngestionEnCours('verrou'))
        with self.assertRaises(UserError) as cm:
            self._pull(client, self.souscription_base)
        self.assertIn('plus tard', str(cm.exception))

    def test_precondition_non_remplie_mappee_en_userror_actionnable(self):
        """AC5 : PreconditionNonRemplie -> message actionnable du serveur conservé."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_flux_factice(
            'meta_periodes', leve=service_module.PreconditionNonRemplie('réconciliez les RSC avant de facturer')
        )
        with self.assertRaises(UserError) as cm:
            self._pull(client, self.souscription_base)
        self.assertIn('réconciliez les RSC', str(cm.exception))

    def test_contract_version_error_mappee_en_erreur_dure(self):
        """AC5 : ContractVersionError -> erreur dure (UserError, pas de retry implicite)."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_flux_factice(
            'meta_periodes', leve=service_module.ContractVersionError('serveur v2 < attendu v3')
        )
        with self.assertRaises(UserError) as cm:
            self._pull(client, self.souscription_base)
        self.assertIn('v2', str(cm.exception))

    def test_aucune_souscription_a_rsc_naboutit_pas_a_un_appel_de_flux(self):
        """Aucune RSC facturable -> aucun flux n'est ouvert (pas de round-trip
        réseau inutile), même si le client est acquis en tête (fast-fail,
        ADR 0024 §5 : la construction elle-même n'ouvre aucune socket)."""
        self.assertFalse(self.souscription_hphc.ref_situation_contractuelle)
        client = client_flux_factice('meta_periodes', [])
        creees, rafraichies, inchangees, conservees, erreurs = self._pull(client, self.souscription_hphc)
        client.meta_periodes.assert_not_called()
        self.assertFalse(creees)
        self.assertFalse(rafraichies)
        self.assertFalse(inchangees)
        self.assertFalse(conservees)
        self.assertFalse(erreurs)


# === Scope refresh (#235 AC6) : plage de mois, création désactivée — testé à
# la couture transport (un appel de flux par mois, mêmes arguments que
# pull()). Consommé par la Régularisation à la tranche 4 du PRD #231.


@tagged('souscriptions', 'souscriptions_pull_meta', 'post_install', '-at_install')
class TestPullMetaPeriodesServiceRefresh(SouscriptionsTestCase):
    def test_appelle_le_flux_une_fois_par_mois_et_ne_cree_rien(self):
        """AC6 : un appel de flux par mois de la plage ; aucune création même
        si le flux renvoie une méta pour un (RSC, mois) sans Période
        existante — la création reste l'apanage du scope facturation."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        meta_janvier = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001', debut='2024-01-01', fin='2024-02-01'
        )
        meta_fevrier = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001', debut='2024-02-01', fin='2024-03-01'
        )
        client = MagicMock()
        client.meta_periodes.side_effect = [flux_electricore([meta_janvier]), flux_electricore([meta_fevrier])]

        with patcher_client_fabrique(client):
            creees, rafraichies, inchangees, conservees, erreurs = self.env[
                'souscription.pull.meta.periodes.service'
            ].refresh(self.souscription_base, date(2024, 1, 1), date(2024, 2, 15))

        self.assertEqual(client.meta_periodes.call_count, 2)
        client.meta_periodes.assert_any_call(mois='2024-01-01', rsc=['RSC-00000000000001'])
        client.meta_periodes.assert_any_call(mois='2024-02-01', rsc=['RSC-00000000000001'])
        self.assertFalse(creees)  # scope refresh : jamais de création
        periodes = self.env['souscription.periode'].search([('souscription_id', '=', self.souscription_base.id)])
        self.assertFalse(periodes)

    def test_rafraichit_une_periode_existante_sur_la_plage(self):
        """AC6 : le scope refresh applique la même politique gardée par
        l'empreinte que pull() aux Périodes déjà amorcées de la plage."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        existante = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(
                ref_situation_contractuelle='RSC-00000000000001',
                debut='2024-01-01',
                fin='2024-02-01',
                source_hash='H1',
                energie_base_kwh=280.0,
            ),
        )
        meta_rafraichie = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut='2024-01-01',
            fin='2024-02-01',
            source_hash='H2',
            energie_base_kwh=310.0,
            qualite='réelle',
        )
        client = MagicMock()
        client.meta_periodes.side_effect = [flux_electricore([meta_rafraichie])]

        with patcher_client_fabrique(client):
            creees, rafraichies, inchangees, conservees, erreurs = self.env[
                'souscription.pull.meta.periodes.service'
            ].refresh(self.souscription_base, date(2024, 1, 1), date(2024, 1, 31))

        self.assertEqual(existante.energie_base_kwh, 310.0)
        self.assertEqual(existante.source_hash, 'H2')
        self.assertEqual(len(rafraichies), 1)
        self.assertFalse(creees)

    def test_aucune_souscription_a_rsc_naboutit_pas_a_un_appel_de_flux(self):
        """Même garde fast-fail que pull() : aucune RSC facturable -> aucun
        flux n'est ouvert, même sur une plage de plusieurs mois."""
        client = MagicMock()
        with patcher_client_fabrique(client):
            self.env['souscription.pull.meta.periodes.service'].refresh(
                self.souscription_hphc, date(2024, 1, 1), date(2024, 3, 1)
            )
        client.meta_periodes.assert_not_called()


# === Wizard « Récupérer les périodes du mois » : coquille mince (#233) ===
#
# La politique de pull (create-missing-only, skip-and-report, mapping des
# exceptions) est couverte par `TestPullMetaPeriodesService` ci-dessus. Ce qui
# reste propre au wizard : construire le périmètre (avec/sans RSC), déléguer
# et formater le résumé — vérifié ici, client mocké.


@tagged('souscriptions', 'souscriptions_pull_meta', 'post_install', '-at_install')
class TestWizardPullMetaPeriodes(SouscriptionsTestCase):
    def _wizard(self, mois=date(2024, 1, 1)):
        return self.env['souscription.pull.meta.periodes.wizard'].create({'mois': mois})

    def _lancer_avec_client(self, client, mois=date(2024, 1, 1)):
        """Lance le wizard avec un client factice fourni directement par la
        fabrique (ADR 0024) : la garde paquet/config de la fabrique est
        testée une fois dans test_electricore_client_fabrique.py, pas ici."""
        wizard = self._wizard(mois)
        with patcher_client_fabrique(client):
            wizard.action_lancer()
        return wizard

    def test_delegue_au_service_et_formate_le_resultat(self):
        """AC2 : le wizard délègue au service et formate le résumé (créées /
        rafraîchies / inchangées / conservées / erreurs)."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut='2024-01-01',
            fin='2024-02-01',
        )
        client = client_flux_factice('meta_periodes', [meta])

        wizard = self._lancer_avec_client(client)

        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', date(2024, 1, 1))]
        )
        self.assertEqual(len(periode), 1)
        self.assertIn('Créées : 1', wizard.resultat)
        self.assertEqual(wizard.state, 'done')
        client.meta_periodes.assert_called_once_with(mois='2024-01-01', rsc=['RSC-00000000000001'])

    def test_empreinte_inchangee_delegue_correctement(self):
        """AC1 : empreinte inchangée -> aucune écriture, bout en bout via le
        wizard — preuve que le wizard ne ré-implémente pas la garde, il la
        délègue au service (même politique que TestPullMetaPeriodesService)."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        existante = self.env['souscription.periode']._amorcer_depuis_meta(
            self.souscription_base,
            _periode_meta(
                ref_situation_contractuelle='RSC-00000000000001',
                debut='2024-01-01',
                fin='2024-02-01',
                source_hash='H1',
                cta_eur=1.23,
            ),
        )

        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut='2024-01-01',
            fin='2024-02-01',
            source_hash='H1',
            cta_eur=999.0,
        )
        wizard = self._lancer_avec_client(client_flux_factice('meta_periodes', [meta]))

        self.assertEqual(existante.cta_eur, 1.23)
        self.assertIn('Inchangées : 1', wizard.resultat)
        self.assertIn('Créées : 0', wizard.resultat)

    def test_resume_les_souscriptions_sans_rsc(self):
        """AC3 : résumé skip-and-report — souscriptions sans RSC comptées à
        part (périmètre construit par le wizard, hors du service)."""
        self.assertFalse(self.souscription_hphc.ref_situation_contractuelle)
        wizard = self._lancer_avec_client(client_flux_factice('meta_periodes', []))
        self.assertIn('Sans RSC (ignorées) :', wizard.resultat)
        self.assertNotIn('Sans RSC (ignorées) : 0', wizard.resultat)

    def test_souscription_en_instance_nee_du_raccordement_hors_pull(self):
        """#101 AC5 : une Souscription *en instance* (née à l'acceptation,
        sans RSC) reste hors du pull — comportement du pull clé RSC/mois
        (AC3 ci-dessus), asserté ici sur une Souscription née du
        Raccordement plutôt que sur une fixture directe."""
        demande = self.env['raccordement.demande'].create(
            {
                'pdl': 'PDL_RACC_HORS_PULL',
                'date_debut_souhaitee': date.today() + timedelta(days=30),
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'provision_mensuelle_kwh': 250.0,
                'contact_nom': 'Test',
                'contact_email': 'racc-hors-pull@example.com',
                'contact_street': 'Test Street',
                'contact_zip': '12345',
                'contact_city': 'Test City',
                'mode_paiement': 'virement',
            }
        )
        demande.stage_id = self.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')
        souscription = demande.souscription_id
        self.assertTrue(souscription, "La Souscription devrait naître à l'acceptation")
        self.assertEqual(souscription.etat, 'en_instance')

        wizard = self._lancer_avec_client(client_flux_factice('meta_periodes', []))

        self.assertIn(souscription.name, wizard.resultat)
        periode = self.env['souscription.periode'].search([('souscription_id', '=', souscription.id)])
        self.assertFalse(periode, 'Aucune période ne doit être amorcée pour une Souscription en instance')

    def test_erreurs_du_service_apparaissent_dans_le_resume(self):
        """Non-régression : le wizard ne ré-implémente pas skip-and-report —
        il affiche tel quel ce que le service rend."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        meta_invalide = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut=None,  # déclenche une erreur de mapping (Date invalide)
            fin='2024-02-01',
        )
        wizard = self._lancer_avec_client(client_flux_factice('meta_periodes', [meta_invalide]))
        self.assertIn('Erreurs : 1', wizard.resultat)

    def test_erreur_de_service_propage_en_userror_par_le_wizard(self):
        """Le wizard ne capture rien : une UserError du service (ex.
        ingestion en cours) traverse `action_lancer` telle quelle — preuve de
        délégation réelle, pas de ré-implémentation locale."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_flux_factice('meta_periodes', leve=service_module.IngestionEnCours('verrou'))
        with self.assertRaises(UserError) as cm:
            self._lancer_avec_client(client)
        self.assertIn('plus tard', str(cm.exception))

    def test_aucune_souscription_a_rsc_naboutit_pas_a_un_appel_de_flux(self):
        """Aucune RSC facturable -> aucun flux n'est ouvert (pas de round-trip
        réseau inutile), même si le client est acquis en tête (fast-fail,
        ADR 0024 §5 : la construction elle-même n'ouvre aucune socket)."""
        client = client_flux_factice('meta_periodes', [])
        wizard = self._lancer_avec_client(client)
        client.meta_periodes.assert_not_called()
        self.assertIn('Sans RSC', wizard.resultat)


@unittest.skipIf(
    not fabrique_module.ELECTRICORE_CLIENT_DISPONIBLE,
    'electricore_client non installé : test exercé uniquement là où le paquet réel est présent (CI Docker).',
)
@tagged('souscriptions', 'souscriptions_pull_meta', 'post_install', '-at_install')
class TestAmorcerDepuisMetaAvecPaquetReel(SouscriptionsTestCase):
    """`_amorcer_depuis_meta` face aux vrais modèles pydantic `PeriodeMeta`/
    `ObjetReleve` (contrat v3) — pas seulement les stubs duck-typés ci-dessus.
    Vérifie que le mapping accepte le type réel que le client renverra en
    production, sans écart de champ (ADR 0019 : contrat single-source)."""

    def test_mappe_un_vrai_periode_meta_pydantic(self):
        from electricore_client import ObjetReleve, PeriodeMeta

        meta = PeriodeMeta(
            ref_situation_contractuelle='RSC-00000000000001',
            pdl='14000000000001',
            mois_annee='2024-01',
            debut='2024-01-01',
            fin='2024-02-01',
            nb_jours=31,
            puissance_moyenne_kva=6.0,
            energie_base_kwh=280.0,
            turpe_fixe_eur=8.5,
            turpe_variable_eur=4.2,
            cta_eur=1.1,
            taux_accise_eur_mwh=21.0,
            has_changement=False,
            qualite='réelle',
            statut_communication='communicante',
            releves_utilises=[
                ObjetReleve(
                    releve_id='ELC-RELEVE-100',
                    date_releve='2024-01-01',
                    nature_index='reel',
                    origine_releve='flux_R151',
                    index_base_kwh=1000,
                )
            ],
            source_hash='hash-abc123',
        )

        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)

        self.assertEqual(periode.date_debut, date(2024, 1, 1))
        self.assertEqual(periode.energie_base_kwh, 280.0)
        self.assertEqual(periode.qualite, 'réelle')
        self.assertEqual(len(periode.releve_ids), 1)
        self.assertEqual(periode.releve_ids.releve_externe_id, 'ELC-RELEVE-100')
        self.assertEqual(periode.releve_ids.index_base, 1000.0)
