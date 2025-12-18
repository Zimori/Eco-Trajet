# EcoTrajet - Calculateur d'Empreinte Carbone pour Trajets

## Description

EcoTrajet est une application web permettant aux utilisateurs de calculer et comparer l'empreinte carbone de leurs déplacements en fonction du mode de transport choisi. L'application offre une interface intuitive avec autocomplétion des adresses, calcul d'itinéraire et visualisation cartographique.

## Technologies Utilisées

### Frontend
- **Next.js** : Framework React pour le rendu côté serveur et le routage
- **React** : Bibliothèque JavaScript pour construire l'interface utilisateur
- **TypeScript** : Superset de JavaScript ajoutant le typage statique
- **CSS Modules** : Pour le styling avec isolation des styles

### Cartographie
- **Leaflet** : Bibliothèque JavaScript open-source pour les cartes interactives
- **React Leaflet** : Composants React pour Leaflet
- **Leaflet-GeoSearch** : Composant pour l'autocomplétion des adresses dans Leaflet

### APIs Externes
- **OpenStreetMap** : Fournit les données cartographiques de base
- **Nominatim** : Service de géocodage pour convertir les adresses en coordonnées géographiques
- **OSRM** (Open Source Routing Machine) : API pour le calcul d'itinéraires entre deux points

## Dépendances Principales

```json
{
  "dependencies": {
    "axios": "^x.x.x",               // Client HTTP pour les requêtes API
    "leaflet": "^1.x.x",             // Bibliothèque de cartographie
    "leaflet-geosearch": "^3.x.x",   // Autocomplétion d'adresses
    "next": "^14.x.x",               // Framework Next.js
    "react": "^18.x.x",              // Bibliothèque React
    "react-dom": "^18.x.x",          // Rendu React dans le DOM
    "react-leaflet": "^4.x.x"        // Composants React pour Leaflet
  }
}
```

## Structure de l'Application

- `/src/app` : Pages et composants de l'application
  - `/calculate` : Page de calcul d'itinéraire et d'empreinte carbone
- `/src/components` : Composants réutilisables
  - `MapComponent.tsx` : Composant de carte pour afficher les itinéraires
  - `Header.tsx` : En-tête de l'application
- `/src/lib` : Services et utilitaires
  - `routeService.js` : Service pour le calcul d'itinéraires et d'émissions CO2
  - `db.js` : Service pour la connexion à la base de données
- `/public` : Ressources statiques, images

## APIs Utilisées

### 1. API Nominatim
- **Fournisseur** : OpenStreetMap
- **Utilisation** : Convertit les noms de lieux en coordonnées géographiques (latitude/longitude)
- **Endpoint** : `https://nominatim.openstreetmap.org/search`
- **Limites** : Max 1 requête par seconde, nécessite un User-Agent personnalisé

### 2. API OSRM
- **Fournisseur** : Project OSRM
- **Utilisation** : Calcule les itinéraires entre deux points avec distance et durée
- **Endpoint** : `https://router.project-osrm.org/route/v1/{profile}/{coordinates}`
- **Formats supportés** : Formats GeoJSON pour la géométrie des itinéraires

## Calcul des Émissions CO2

L'application utilise des facteurs d'émission basés sur les données de l'ADEME (Agence de l'environnement et de la maîtrise de l'énergie) :

- **Voiture** : 218 g CO2/km (thermique)
- **Bus** : 113 g CO2/km (thermique)
- **Train** : 2.93 g CO2/km (TGV)
- **Avion** : 259 g CO2/km (court courrier)
- **Vélo/Marche** : 0 g CO2/km (émissions directes)

## Installation et Démarrage

1. **Cloner le dépôt** :
   ```bash
   git clone <url-du-repository>
   cd mif10-g04-2024
   ```

2. **Installer les dépendances** :
   ```bash
   npm install
   ```

3. **Lancer le serveur de développement** :
   ```bash
   npm run dev
   ```

4. **Construire pour la production** :
   ```bash
   npm run build
   npm start
   ```

## Fonctionnalités

- Autocomplétion des adresses de départ et d'arrivée
- Calcul d'itinéraire entre deux points
- Affichage de la distance et la durée du trajet
- Calcul des émissions CO2 selon le mode de transport
- Visualisation de l'itinéraire sur une carte interactive
- Interface réactive et intuitive

## Limitations

- Les facteurs d'émission sont des moyennes et ne prennent pas en compte des variables comme le modèle de véhicule ou le taux d'occupation
- L'itinéraire pour les bus et les trains utilise le même calcul que pour les voitures (limitation de l'API OSRM)
- La précision des données dépend de la qualité des données OpenStreetMap

## Contributeurs

- Équipe MIF10-G04-2024
