# Consentement aux données de consommation : formulaire Odoo public + journal append-only, EDN seul responsable

EDN **internalise la capture du consentement** RGPD (collecte auprès d'*Enedis* des données de
consommation plus fines que l'index : consommations quotidiennes transmises au fournisseur, courbe
de charge) dans un **formulaire public du module *raccordement*** (Odoo), au lieu du chaînage prod
*formulaire externe → LSD → abonnement*. Le consentement est tracé dans un **journal append-only**
(`souscription.consentement` : finalité, horodatage, version du texte affiché, source/IP, état
donné|retiré, date de retrait), **possédé par la *Souscription***.

Motif : co-localiser la **preuve** (accountability, RGPD art. 7-1) avec le système de référence,
sous un **responsable de traitement unique** (EDN), supprimer le maillon de capture externe, et
garantir l'**intégrité entre le texte affiché et la preuve**. EDN **déclare à Enedis** détenir le
consentement (mécanisme admis par Enedis pour la courbe de charge) et doit pouvoir le **démontrer** ;
un booléen coché en back-office par un·e *facturiste* ne vaut **pas** consentement — l'acte positif
du·de la *souscripteur·rice* est requis, d'où le **formulaire public**.

## Options considérées

- **Formulaire externe → LSD** (prod) — la preuve vit hors du système de référence ; le PDF
  re-affiche les consentements en texte statique, rendu par un *autre* système que la capture →
  intégrité texte↔preuve fragile ; maillon supplémentaire. Rejeté.
- **Booléen + preuve archivée** (`ir.attachment`) — insuffisant pour l'**historique de retrait** et
  la **version du texte** ; un booléen mutable perd l'histoire. Rejeté.

## Conséquences

- Nouveau modèle `souscription.consentement` (append-only) ; l'état courant d'une finalité = sa
  dernière ligne ; le retrait crée une ligne, n'écrase rien.
- **Finalités granulaires** (consommations quotidiennes ≠ courbe de charge) : pas de consentement
  groupé (exigence de spécificité, art. 4-11).
- **Index de facturation** = exécution du contrat (art. 6-1-b), **hors** consentement.
- Restent des chantiers **distincts** : le formulaire public lui-même, l'activation/désactivation de
  la collecte chez Enedis (via *electricore* / SGE), et l'UI de **retrait** au *portail*.
- Conservation de la preuve : durée du contrat + délai de prescription (cf. doc dédié).
