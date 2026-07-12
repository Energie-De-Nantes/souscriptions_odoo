"""Backfill `provision := energie` sur les non-lissées déjà facturées (#234,
ADR 0030 décision 2 — Énergie facturée universelle).

Avant cette version, `_quantite_facturee` facturait le mesuré (`energie_*`)
directement pour un contrat non lissé, sans jamais écrire `provision_*` : ce
champ restait à 0 (défaut), jamais réécrit par le pull create-missing-only
(ADR-0011) ni par `create()` (qui ne peuple la provision que pour un contrat
lissé, `souscription_periode.py::create`). Sûr, donc, d'écraser `provision_*`
par `energie_*` sur les Périodes non lissées déjà facturées : aucune donnée
utile n'y est perdue, et leur écart mesuré − facturé (`ecart_*_kwh`, calculé)
retombe à zéro juste après — comme si elles avaient toujours été tamponnées
à la facturation.

SQL direct : `provision_*` est un champ verrouillé (#14) dès qu'une facture
référence la Période — la voie ORM (`write()`) lèverait une UserError sur
exactement les lignes visées ici. Idempotent : la clause `IS DISTINCT FROM`
ne touche que les lignes où `provision_*` diverge encore de `energie_*` ;
rejouer ce script est un no-op.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE souscription_periode p
        SET provision_hp_kwh = p.energie_hp_kwh,
            provision_hc_kwh = p.energie_hc_kwh,
            provision_base_kwh = p.energie_base_kwh
        WHERE p.lisse_periode = false
          AND EXISTS (
              SELECT 1 FROM account_move m
              WHERE m.periode_id = p.id AND m.move_type = 'out_invoice'
          )
          AND (
              p.provision_hp_kwh IS DISTINCT FROM p.energie_hp_kwh
              OR p.provision_hc_kwh IS DISTINCT FROM p.energie_hc_kwh
              OR p.provision_base_kwh IS DISTINCT FROM p.energie_base_kwh
          )
        """
    )
