# Documents contractuels : projections de la Souscription, consentements captés au raccordement

Les documents contractuels remis au·à la *souscripteur·rice* — **conditions particulières**
(l'acte d'adhésion complet : coordonnées, lieu de consommation, options, tarifs engagés,
déclarations/consentements, signature électronique) et **attestation de fourniture** (preuve
courte sans prix ni consentements) — sont des **rapports QWeb projetés de la *Souscription***, pas
un modèle de données distinct. La *Souscription* reste le système de référence ; elle est enrichie
des **consentements** (autorisation courbe de charge, renonciation au délai de rétractation) et de
la **date de signature électronique**, qui sont **captés au *raccordement*** (équivalent du *LSD*
de prod) puis **recopiés** sur la *Souscription* à sa création (`_create_souscription`), laquelle
en devient **propriétaire**.

## Options considérées

- **Copier les consentements sur la Souscription** (retenu) — cohérent avec le snapshot typé des
  *Périodes* (même geste « capter à l'entrée, puis posséder ») ; la *Souscription* reste
  auto-portante ; une *Souscription* née hors raccordement (migration prod, saisie manuelle) peut
  porter ses consentements.
- **Lire en transparence depuis la demande de raccordement** (rejeté) — la *Souscription* ne serait
  plus auto-portante, les rapports seraient couplés à l'intake, et toute *Souscription* sans
  demande associée n'aurait aucun consentement à afficher.

## Conséquences

- Les champs de consentement / signature existent en double : sur `raccordement.demande` (capture)
  et sur `souscription.souscription` (référence lue par les rapports), avec mapping dans
  `_create_souscription`.
- Les tarifs des documents sont rendus **depuis la *Grille de prix*** (data-driven, TTC pour les
  particuliers / HT pour les sociétés via `is_company`), jamais une image figée comme en prod.
- La CP supersède les deux rapports prod (« Contrat V1 » à image, « Attestation de contrat »
  data-driven) ; le rapport prod nommé « Attestation de contrat » n'est **pas** l'*attestation de
  fourniture* définie ici.
