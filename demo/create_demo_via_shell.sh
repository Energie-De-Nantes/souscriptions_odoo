#!/bin/bash

echo "🔧 Création des données de démo via Odoo shell..."

odoo shell -d souscriptions_demo --addons-path=/home/virgile/addons_odoo << 'EOF'

print("=== Création des données de démo ===")

# Clients de démo
clients_data = [
    {
        "name": "Marie Dupont",
        "is_company": False,
        "street": "15 rue des Énergies Vertes",
        "city": "Rennes",
        "zip": "35000",
        "country_id": env.ref("base.fr").id,
        "email": "marie.dupont@email.fr",
        "phone": "02.99.12.34.56",
    },
    {
        "name": "Jean Martin", 
        "is_company": False,
        "street": "8 avenue du Développement Durable",
        "city": "Nantes",
        "zip": "44000",
        "country_id": env.ref("base.fr").id,
        "email": "jean.martin@email.fr",
        "phone": "02.40.78.90.12",
    },
    {
        "name": "Boulangerie Bio du Coin",
        "is_company": True,
        "street": "3 place du Marché", 
        "city": "Saint-Malo",
        "zip": "35400",
        "country_id": env.ref("base.fr").id,
        "email": "contact@boulangerie-bio.fr",
        "phone": "02.99.56.78.90",
    },
    {
        "name": "Sophie Leroy",
        "is_company": False,
        "street": "12 rue de la Solidarité",
        "city": "Lorient", 
        "zip": "56100",
        "country_id": env.ref("base.fr").id,
        "email": "sophie.leroy@email.fr",
        "phone": "02.97.12.34.56",
    }
]

# Supprimer les clients existants
existing = env["res.partner"].search([("name", "in", [c["name"] for c in clients_data])])
if existing:
    existing.unlink()
    print(f"Supprimé {len(existing)} clients existants")
    
# Créer les clients
clients = env["res.partner"].create(clients_data)
print(f"✅ {len(clients)} clients créés")

# Test du modèle souscription.etat
print("\\nTest du modèle souscription.etat...")
try:
    # Récupérer l'état de facturation
    etat = env["souscription.etat"].search([], limit=1)
    if not etat:
        etat = env["souscription.etat"].create({"name": "Actif", "sequence": 1})
        print("État de facturation créé")
    else:
        print(f"État trouvé : {etat.name}")
        
    # Lister tous les états
    tous_etats = env["souscription.etat"].search([])
    print(f"Nombre total d'états : {len(tous_etats)}")
    for e in tous_etats:
        print(f"  - {e.name} (séquence: {e.sequence})")
        
except Exception as e:
    print(f"ERREUR avec souscription.etat : {e}")
    # Vérifier si le module souscriptions est bien installé
    modules = env["ir.module.module"].search([("name", "=", "souscriptions")])
    if modules:
        print(f"Module souscriptions : état = {modules[0].state}")
    else:
        print("Module souscriptions non trouvé !")

# Souscriptions de démo
souscriptions_data = [
    {
        "partner_id": clients[0].id,
        "pdl": "PDL22516914012345", 
        "puissance_souscrite": "6",
        "type_tarif": "base",
        "etat_facturation_id": etat.id,
        "date_debut": "2024-01-01",
        "tarif_solidaire": False,
        "lisse": True,
        "provision_mensuelle_kwh": 280.0,
        "ref_compteur": "85234567",
    },
    {
        "partner_id": clients[1].id,
        "pdl": "PDL22516914098765",
        "puissance_souscrite": "9", 
        "type_tarif": "hphc",
        "etat_facturation_id": etat.id,
        "date_debut": "2024-01-01",
        "tarif_solidaire": False,
        "lisse": True,
        "provision_mensuelle_kwh": 350.0,
        "ref_compteur": "85987654",
    },
    {
        "partner_id": clients[2].id,
        "pdl": "PDL22516914055555",
        "puissance_souscrite": "12",
        "type_tarif": "base", 
        "etat_facturation_id": etat.id,
        "date_debut": "2024-01-01",
        "tarif_solidaire": False,
        "lisse": False,
        "coeff_pro": 15.0,
        "ref_compteur": "85123456",
    },
    {
        "partner_id": clients[3].id,
        "pdl": "PDL22516914033333",
        "puissance_souscrite": "3",
        "type_tarif": "base",
        "etat_facturation_id": etat.id, 
        "date_debut": "2024-01-01",
        "tarif_solidaire": True,
        "lisse": False,
        "ref_compteur": "85456789",
    }
]

# Supprimer les souscriptions existantes
existing_sous = env["souscription.souscription"].search([("pdl", "in", [s["pdl"] for s in souscriptions_data])])
if existing_sous:
    existing_sous.unlink()
    print(f"Supprimé {len(existing_sous)} souscriptions existantes")

# Créer les souscriptions
souscriptions = env["souscription.souscription"].create(souscriptions_data)
print(f"✅ {len(souscriptions)} souscriptions créées")

# Créer des périodes de facturation pour chaque souscription
from datetime import date, timedelta
import calendar

print("Création des périodes de facturation...")

periodes_data = []
for i, souscription in enumerate(souscriptions):
    # Créer 3 mois de périodes (nov, déc 2024, jan 2025)
    mois_list = [
        (2024, 11),  # Novembre 2024
        (2024, 12),  # Décembre 2024
        (2025, 1),   # Janvier 2025
    ]
    
    for annee, mois in mois_list:
        # Dates de début et fin du mois
        debut_mois = date(annee, mois, 1)
        if mois == 12:
            fin_mois = date(annee + 1, 1, 1) - timedelta(days=1)
        else:
            fin_mois = date(annee, mois + 1, 1) - timedelta(days=1)
        
        jours = (fin_mois - debut_mois).days + 1
        
        # Consommations selon le type de souscription
        if souscription.type_tarif == "base":
            # BASE - Marie (280 kWh/mois) et PRO (350 kWh/mois) et Solidaire (180 kWh/mois)
            if souscription.tarif_solidaire:  # Sophie
                base_kwh = 180 + (mois * 10)  # Variation saisonnière
            elif souscription.coeff_pro > 0:  # Boulangerie
                base_kwh = 350 + (mois * 15)
            else:  # Marie
                base_kwh = 280 + (mois * 12)
            
            periode_data = {
                "souscription_id": souscription.id,
                "date_debut": debut_mois,
                "date_fin": fin_mois,
                "type_periode": "mensuelle",
                "jours": jours,
                # Pour BASE, on alimente les champs détaillés pour que les computed marchent
                "energie_hph_kwh": base_kwh * 0.5,  # 50% HPH
                "energie_hpb_kwh": base_kwh * 0.2,  # 20% HPB  
                "energie_hch_kwh": base_kwh * 0.2,  # 20% HCH
                "energie_hcb_kwh": base_kwh * 0.1,  # 10% HCB
                "provision_base_kwh": base_kwh if souscription.lisse else 0,
                # TURPE estimé (Base: ~0.15€/kWh)
                "turpe_fixe": 8.5,
                "turpe_variable": base_kwh * 0.015,
            }
        else:  # HP/HC - Jean
            hp_kwh = 220 + (mois * 8)  # 70% HP
            hc_kwh = 130 + (mois * 5)  # 30% HC
            
            periode_data = {
                "souscription_id": souscription.id,
                "date_debut": debut_mois,
                "date_fin": fin_mois,
                "type_periode": "mensuelle", 
                "jours": jours,
                # Pour HP/HC, on alimente les champs détaillés (HP = HPH + HPB, HC = HCH + HCB)
                "energie_hph_kwh": hp_kwh * 0.6,  # 60% du HP en HPH
                "energie_hpb_kwh": hp_kwh * 0.4,  # 40% du HP en HPB
                "energie_hch_kwh": hc_kwh * 0.6,  # 60% du HC en HCH
                "energie_hcb_kwh": hc_kwh * 0.4,  # 40% du HC en HCB
                "provision_hp_kwh": hp_kwh if souscription.lisse else 0,
                "provision_hc_kwh": hc_kwh if souscription.lisse else 0,
                # TURPE HP/HC
                "turpe_fixe": 12.8,
                "turpe_variable": (hp_kwh + hc_kwh) * 0.018,
            }
        
        periodes_data.append(periode_data)

# Supprimer les périodes existantes pour ces souscriptions
existing_periodes = env["souscription.periode"].search([("souscription_id", "in", souscriptions.ids)])
if existing_periodes:
    existing_periodes.unlink()
    print(f"Supprimé {len(existing_periodes)} périodes existantes")

# Créer les périodes
periodes = env["souscription.periode"].create(periodes_data)
print(f"✅ {len(periodes)} périodes créées")

# Valider les changements
env.cr.commit()
print("🎉 Données de démo créées avec succès !")

print("\n=== Vérification ===")
total_clients = env["res.partner"].search_count([("name", "in", [c["name"] for c in clients_data])])
total_souscriptions = env["souscription.souscription"].search_count([("pdl", "in", [s["pdl"] for s in souscriptions_data])])
total_periodes = env["souscription.periode"].search_count([("souscription_id", "in", souscriptions.ids)])
print(f"Clients dans la base: {total_clients}")
print(f"Souscriptions dans la base: {total_souscriptions}")
print(f"Périodes dans la base: {total_periodes}")

print("\n=== Résumé des données créées ===")
for sous in souscriptions:
    periodes_count = env["souscription.periode"].search_count([("souscription_id", "=", sous.id)])
    print(f"  {sous.partner_id.name}: {sous.type_tarif.upper()} {sous.puissance_souscrite}kVA - {periodes_count} périodes")

EOF

echo "✅ Script terminé !"