# Déploiement : sécuriser les factures émises avec le hash de séquence

Consigne de déploiement (pas du code) — tranche 4 du chantier « Brouillon gouverné, gel
à l'émission » (PRD #264, #268). À appliquer sur **chaque base** qui facture réellement,
`souscriptions_prodlocal` comprise.

## Pourquoi

[ADR 0032](adr/0032-brouillon-gouverne-gel-a-lemission.md) (décision 4) pose que
l'émission (`action_post`) est l'unique événement de gel : une fois postée, une facture
d'énergie est censée être **définitive**. Le module ne réimplémente aucun verrou
applicatif dur pour ça (même raisonnement qu'[ADR 0014](adr/0014-pas-de-verrou-lignes-facture-confiance-facturiste.md)
décision 2 : éviter de combattre les recomputes ORM sur le cœur comptable) — il s'appuie
sur le mécanisme **natif** que la loi française anti-fraude (art. 286-I-3° bis du CGI)
prévoit pour ça : le **hash de séquence** (chaînage cryptographique des écritures
postées, qui rend toute modification a posteriori détectable).

Techniquement, tant que ce réglage n'est pas activé, `button_draft()` reste possible sur
une facture postée — la correction *documentée* d'une facture émise passe par un avoir ou
une Régularisation (jamais par une réouverture en brouillon), mais rien ne l'empêche
applicativement. Le hash de production est ce qui rend cette discipline **non
contournable**.

**`l10n_fr` ne l'active pas tout seul.** Vérifié dans le source Odoo 19
(`odoo/addons/account/models/account_journal.py`, champ `restrict_mode_hash_table`) :
aucun module `l10n_fr*` (`l10n_fr`, `l10n_fr_account`…) ne pose ce champ à `True` en
donnée — c'est un booléen à cocher **à la main**, journal par journal, à l'installation
de chaque base.

## Le geste

**Comptabilité → Configuration → Journaux** → ouvrir le **journal de ventes** →
onglet **Réglages avancés** → cocher **« Sécuriser les écritures comptabilisées avec une
empreinte »** (`restrict_mode_hash_table`, libellé anglais *Secure Posted Entries with
Hash*).

## Irréversible dès la première écriture postée

Ce n'est pas qu'une discipline documentée : Odoo l'**impose** techniquement. Dès qu'une
facture est postée sur le journal avec ce réglage actif, elle porte un `inalterable_hash`
— et `account.journal.write()` refuse alors de décocher `restrict_mode_hash_table` sur ce
journal (`You cannot modify the field … of a journal that already has accounting
entries.`, vérifié dans le même fichier source). Autrement dit : le geste se fait
**avant** la première facture réellement émise sur ce journal, ou pas du tout.

## Portée

Un geste **par base**, pas un artefact de code du module — à refaire à chaque nouvelle
base qui facture réellement (dont `souscriptions_prodlocal`, cf. `COOKBOOK.md`
`bring-up`). Les bases de test/démo n'ont pas besoin de l'activer (aucune facture émise
n'y est réellement définitive) ; c'est d'ailleurs volontaire pour laisser tourner la
suite de tests (button_draft y reste possible, cf. ADR 0032 décision 4).
