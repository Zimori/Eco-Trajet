# Notes de Conception & Journal de Bord — EcoTrajet

## 1. Autopsie de la V1 (Projet Scolaire MIF10 et illusions)

On part d'un projet universitaire en équipe (UE MIF10 à Lyon 1). Une interface web Next.js affichait une carte et faisait des calculs... ok bien mais trop simpliste:

- Les trains et les bus empruntaient l'API routière automobile d'OSRM (le train roulait littéralement sur l'autoroute avec des temps et des distances bien évidemment faussés).
- L'empreinte carbone n'était calculée par aucun pipeline: 5 constantes codées en dur dans un script JavaScript (distance * 2.93 pour le train, etc.).
- Le backend n'existait pas: aucune API Python, aucun conteneur runnable, une pipeline timde.

Le projet ne faisait pas de l'ingénierie, il faisait du show. On pouvait cliquer, visualiser, et c'était suffisant pour choper une bonne note mais on ne pouvait pas produire un service fiable ni un moteur de décision crédible.

## 2. Pivot Architectural Solo

J'ai repris le projet seul et je l'ai refait pour qu'il ressemble à un vrai service, pas à une démo.

- Le frontend Next.js reste un simple dashboard. Le vrai métier a été déplacé dans un backend FastAPI en Python 3.11, avec un conteneur propre.
- J'ai nettoyé la dette technique: suppression de la fausse base PostgreSQL `bd/co2_app.sql`, suppression de la route zombie `pages/api/test.js`, nettoyage des scripts JS et déplacement des assets dans `public/icons/`.
- J'ai aussi ajouté un mode dégradé propre: si les datasets manquent, le backend répond `503` sur `/health` au lieu de tomber en silence.

Le prototype de TP devient une vraie base de mobilité exploitable par des agents IA.

## 3. Choix d'Ingénierie & Compromis

- Réseau ferré:
  On n'a pas chargé tout le réseau ferré national brut. Ce serait trop lourd, trop fragile et ça ferait probablement exploser la RAM au démarrage. Donc on a un graphe sur les lignes principales TGV/Intercités avec 9 gros hubs. Ça suffit pour faire des trajets réalistes comme Paris-Lyon, sans perdre en vitesse.
- Données ADEME:
  ADEME ne donne pas un Parquet prêt à l'emploi. Le script de seed récupère les facteurs officiels, puis les transforme en `ademe_base_empreinte.parquet` avec PyArrow. Ça rend les requêtes rapides et évite de dépendre d'un appel réseau à chaque fois.
- Trouver la gare la plus proche:
  Les coordonnées sont projetées en Lambert-93 pour calculer des distances propres. C'est plus précis que de faire un simple calcul de distance euclidienne sur des coordonnées GPS.

## 4. Débogage

- `jq` se cassait sur le JSON de `/health` alors que le serveur n'était pas vraiment en cause. En réalité, un proxy interne interceptait les appels locaux, réécrivait `localhost` ou le redirigeait vers une route inaccessible, et renvoyait du HTML d'erreur à la place d'une réponse API. Le parseur JSON se cassait systèmatiquement. Solution: forcer `--noproxy "*"` et appeler explicitement `127.0.0.1` pour sortir du chemin du proxy.
- L'exécution de `sudo make run` verrouillait le dossier hôte `backend/data/` sous l'utilisateur root, empêchant l'utilisateur non-root sécurisé du conteneur (`appuser`) d'y écrire le Parquet (`PermissionError: [Errno 13]`). Solution: ajustement des droits et exécution du seed dans l'environnement conteneurisé.
- Blocage (bug CORS Preflight OPTIONS 405) des requêtes du dashboard Next.js résolu par l'adjonction explicite de `CORSMiddleware` sur l'ensemble des routes FastAPI.

## 5. Roadmap

- Ingestion d'un flux GTFS national pour le calcul fin des liaisons régionales TER.
- Intégration d'un vector store (Qdrant) pour le matching sémantique des noms de gares et d'arrêts mal orthographiés par les utilisateurs ou les LLMs. (Exemple: "Gare de Lyon" → "Gare de Lyon Part-Dieu" ou "Gare de Lyon Perrache" ou "Gare de Lyon" simplement?).

Le système est bon, mais il n'est pas fini. La vraie production commence quand le service peut évoluer sans doute, sans patchs improvisés et sans promesses de "ça devrait marcher".
