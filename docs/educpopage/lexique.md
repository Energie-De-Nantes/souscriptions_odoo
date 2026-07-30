# Petit lexique

Les mots de la maison, regroupés par thème, en une ou deux phrases chacun.
C'est une version de poche : la référence complète reste le
[CONTEXT.md](https://github.com/Energie-De-Nantes/souscriptions_odoo/blob/main/CONTEXT.md)
du dépôt, dont chaque définition est tirée.

## Le contrat

**Souscription** — Le contrat de fourniture d'électricité lui-même :
l'enregistrement de référence côté fournisseur, identifié par sa référence
Enedis (la RSC). On évite « abonnement » et « commande » — l'abonnement, ici,
c'est seulement la part fixe du prix. Voir [contrat](contrat.md).

**Souscripteur·rice** — La personne ou l'organisation titulaire d'une
Souscription (« usager·ère » au portail). On évite « client ».

**En instance / En service / En attente de clôture / Résiliée** — Les quatre
états de vie du contrat, toujours déduits des faits (référence Enedis acquise,
sortie notifiée, clôture soldée), jamais choisis à la main.

**Conditions particulières** — Le PDF qui récapitule les conditions propres au
contrat (prix engagés, consentements, signature) : une projection régénérée de
la Souscription, qui complète les CGV.

**Raccordement** — Le workflow d'entrée (le tableau de l'accueilliste) qui
instruit une demande de fourniture, du formulaire à la validation de
l'abonnement, et donne naissance à la Souscription. Voir [raccordement](raccordement.md).

**Journal des actes** — Le registre où rien ne s'efface des actes du·de la
souscripteur·rice : consentements (révocables) et actes d'adhésion
(irrévocables), chaque ligne portant horodatage et version du texte montré.
Voir [consentement](consentement.md).

## La facturation

**Facturiste** — Le rôle qui conduit la facturation mensuelle et vérifie les
données avant émission ; la Campagne de facturation est son tableau de bord.

**Campagne de facturation** — Le tableau de bord mensuel (un par mois, créé
seulement sur mois révolu) qui orchestre rapatriements, vérifications, création
et émission en quatre phases — Tirer / Vérifier / Facturer / Solder — et
s'amorce seule à sa création. Voir [facturer](facturer.md).

**Période** — Le brouillon mensuel facturable d'un contrat : amorcé par les
données d'electricore, complété ou corrigé par le·la facturiste, et dont le
« facturé » gèle à l'émission de la facture. Voir [facture](facture.md).

**Énergie facturée** — La quantité d'énergie que les factures émises ont
réellement portée pour un mois ; elle n'évolue que par l'émission d'une facture
(mensuelle ou régularisation).

**Facture** — Le document comptable légal : brouillon librement retravaillable
(l'espace de travail du·de la facturiste), puis définitif à l'émission —
l'unique événement de gel. Toute correction ensuite passe par un avoir ou une
régularisation.

**Avoir** — Le document de correction d'une facture émise, écrit entièrement à
la main (jamais régénéré depuis la Période) et lié à sa facture source pour la
traçabilité.

**Régularisation (solde)** — Le document qui facture (ou rembourse en avoir)
les écarts entre mesuré et facturé, aux prix historiques de chaque mois.
Émise, elle est immuable et solde les mois qu'elle couvre. Voir [regulariser](regulariser.md).

**Geste commercial** — Ajustement volontaire du facturé : en quantités ou en
jours sur la Période (avant le gel), en euros comme ligne manuelle du brouillon
de facture — jamais en maquillant une ligne générée.

## Les prix

**Grille de prix** — Le barème fournisseur daté, tout-compris (coût du réseau
absorbé), unique moteur de calcul des prix. Sélectionnée par régime et date de
début du mois, elle change toujours un 1er du mois. Voir [prix](prix.md).

**Régime de prix** — L'axe qui dit quel barème s'applique à un contrat
(standard ou Moulin), chaque régime versionnant ses grilles indépendamment.

**Tarif solidaire** — Régime social qui impose une comptabilité entièrement
séparée du standard (exigence légale) — pas une simple remise.

**Majoration PRO** — Surcoût en % négocié contrat par contrat, appliqué à
l'abonnement et à l'énergie, jamais aux refacturations Enedis.

**Produit de facturation** — Le produit porté par une ligne de facture, qui
détermine le compte comptable et la TVA ; choisi par son rôle et par l'axe
solidaire, via un catalogue unique.

## L'argent

**Mode de paiement** — La façon dont le·la souscripteur·rice règle le solde
(prélèvement, Moneko, espèces, virement, chèque), portée par le contrat et
jamais devinée depuis un IBAN. Voir [encaisser](encaisser.md).

**Chèque énergie** — Aide d'État en tiers-payeur : la facture reste entière et
le chèque la paie en partie (« payé / reste à payer »). Imputé à l'émission,
consommé d'abord celui qui expire le plus tôt, après validation manuelle sur le
site étatique.

## Les données Enedis

**Relevé (d'index)** — L'événement daté de lecture du compteur (réel ou
estimé), justificatif légal affiché sur chaque facture et figé à son émission.

**Qualité (verdict)** — Le verdict d'electricore sur l'énergie d'un mois —
réelle, estimée ou incalculable — que le·la facturiste lit mais ne calcule ni
ne modifie.

**Refacturation (Enedis)** — En-cours Enedis (prestation taxée ou indemnité
hors TVA) refacturé à l'usager·ère et rassemblé sur sa prochaine facture. File
par défaut « à refacturer », mise « en attente » à la main en cas de doute.

**Consentement (données de consommation)** — L'autorisation RGPD de collecter
chez Enedis des données plus fines que l'index (conso quotidienne, courbe de
charge) ; l'index de facturation, lui, n'en requiert pas. Voir [consentement](consentement.md).

---

Un mot manque, ou une définition sonne faux à l'usage ? C'est exactement le
genre de retour que ce site attend : le lexique se corrige au fil des
relectures avec l'équipe, et c'est le CONTEXT.md du dépôt qui reçoit la
version amendée — cette page n'en est que le reflet.
