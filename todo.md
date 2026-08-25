Version ABYSS : 
- [x] Gestion d'un fallback de font pour les PDF
- [ ] Création de pipelines [EN COURS]
- [ ] API statistiques détaillées
- [ ] Suivi des pipelines
- [ ] API info profil
- [x] Support connecteur LLM DigitalOcean 
- [x] Support connecteur LLM Cerebras
- [ ] Dans Embedder liaison dynamique / gestion différentiée des prividers
- [ ] Documentation spécifique sur l'écriture des fichiers de configuration avec options
- [ ] Vérifier le service d'auth Webex nécessaire ?
- [ ] Revue des logs
- [ ] File format checker
- [ ] Vérificateur de format des fichiers de configuration
- [ ] Gestionnaire de droits d'API Basic

BACKLOG
- [ ] Gérer d'autres sources de données ?
- [ ] Limiter la sortie ?
- [ ] Support OCR / modèle de compréhension d'image
- [ ] Confirmations : prévoir des options plus riches (objets)
- [ ] Limitation des résultats
- [ ] Détermination auto du modèle le mieux adapté pour répondre à une question ?
- [ ] Critique de la réponse par un modèle
- [ ] Possibilité d'arreter une conversation proprement
- [ ] Loop
- [ ] MCP externes
- [ ] MCP contextuel ?
- [ ] Support Audio
- [ ] Image to text
- [ ] Génération d'images
- [ ] Passer le delestage sessions en tache CRON ?
- [ ] Outils excel et graphiques avancés
- [ ] Refondre l'orchestrateur
- [ ] Outils PDF avancés [ABANDON PREMIERE IMPLEMENTATION]
- [ ] Securiser encore davantage l'import dynamique
- [ ] Audit sécurité
- [ ] Revoir les limites d'appels d'outils
- [ ] problèmes des retours LLM vides
- [ ] Gestion de profils LLM
- [ ] Simplification et refactor des classes pour le RAG
- [ ] Refactor AuthSessionManager
- [ ] Gestionnaire de codes d'erreur
- [ ] Conservation d'historique de conversations / pouvoir les continuer
- [ ] Gestion téléchargement fichiers CSV
- [ ] Pb des logs non enregistrés ?? (le démarrage)
- [ ] Outils MCP recherche WEB : préciser la recherche effectuée
- [ ] sourcer la réponse
- [ ] Event de redirection
- [ ] Supprimer un fichier du micro RAG
- [ ] Suppression des messages du context : résumer dabord
- [ ] modifier l'evenement rag en source plus globale
- [ ] Avoir les affichages de sources dans les contenus
- [ ] Sur les appels MCP avec un UID d'appel d'outil





------------
Versions à venir : 

Abyss
Focalisé sur les pipelines

Nova
Focalisé sur les capacités d'analyse d'images

Vortex
Focalisé sur les capacités de l'agent à se controler et vérifier la réalisation de sa tâche

Pulse
Focalisé sur l'optimisation de l'orchestrateur

Nimbus 
Focalisé sur les capacités audio

Focalisé sur les capacités à créer des schémas


- [x] Events des appels d'outils (2 états)
- [x] Gestion des erreurs sur l'appel des outils
- [x] Gestion de l'authentification
- [x] Gestion des erreir sur l'agent
- [x] Gestion des erreurs sur le http
- [x] Refactor
- [x] Delestage du cache
- [x] Liaison des fichiers avec le cache
- [x] Meilleure gestion des sessions et données en cache (dans Agent)
- [x] revoir fichier de configuration
- [x] Gestion du traitement long
- [x] Gestion de la confirmation avant action
- [x] Implémenter RAG
- [x] Implémenter pré-traitement RAG
- [x] Implémenter version
- [x] Authentification gestion RAG
- [x] Simplifier l'écriture d'un service
- [x] Citer ou nom les sources
- [x] Stats d'utilisation de la base RAG
- [x] Mise à jour document RAG
- [x] Refactor RAG
- [x] Activer ou nom certains outils MCP de base
- [x] Limiter l'histo envoyé à N messages
- [x] modifier readme
- [x] Sur les outils, retourner le nom de l'outil dans le message
- [x] Modification socket : ne pas kill à la fin mais au bout de N minutes
- [x] Sécurité : limites
- [x] ne pas pouvoir envoyer une question si un échange est déjà en cours
- [x] ne pas pouvoir envoyer une question si un échange est déjà en cours
- [x] bug botcore
- [x] Problème de non réponse du LLM (réponse vide)
- [x] Filtres de contenus
- [x] Retour des urls et des fichiers 
- [x] Bug sur les retours de confirmations (message refusé après sélection d'un oui ? ou pas de validation du tout)
- [x] chat.html : pb des fichiers
- [x] Fonction "instruction" dans le tool MCP
- [x] Pb confirmation avec l'abandon de l'action [EN COURS]
- [x] Pbs de l'affichage du retour des liens
- [x] Connecteur Webex [EN COURS]
- [x] Outil génération PDF [EN COURS]
- [x] pb pbVector sur prod
- [x] Gestion des liens directs, modification authentification
- [x] Connecteur Webex : avoir des retours sur les actions en cours

Version SPARK : 
- [x] Revoir le fichier de configuration pour le prompt
- [x] Critique du code
- [x] Fermer une session proprement
- [x] Outil génération fichier Word
- [x] Refactoring pour la version Spark
- [x] Outils de date/heure
- [x] Gestion du system prompt dans un fichier séparé
- [x] Webex : mise en forme des tableaux
- [x] Statistiques d'usages : en authentification Session
- [x] Sécurisation bot : accessibilité ? 
- [x] Webex bot : Accès en mode pingé ?
- [x] Mise à jour fichier conf
- [x] Mise à jour README.md
- [x] Vérifier le fonctionnement multithread

Version AURORA :
- [x] Deplacer _charts.py de tools/
- [x] Reorganier les dossiers d'outils
- [x] Outils MCP Word avancés
- [x] Pb des fichiers, envoyés avant la génération ??
- [x] Tache de delestage
- [x] Implémentation d'un mécanisme de tâches CRON
- [x] Refonte et sécurisation du système d'import dynamique
- [x] Refactor version Aurora
- [x] MAJ README
- [x] Follow-up 
- [x] Modification version
- [x] Ajout FollowUpEvent Event

Version PHOSPHOR :
- [x] RAG local sur un fichier 
- [x] Envoi de fichiers à l'agent
- [x] RAG local ou dans le prompt en fonction de la taille
- [x] Limitations des envois de fichiers
- [x] option pour retourner les infos des documents
- [x] Indexation RAG Word, Excel 
- [x] Cron Indexer RAG
- [x] Sources de stockage RAG
- [x] Cache pour l'indexer
- [x] Versions
- [x] Profils
- [x] RAG par profil
- [x] MCP par profil
- [x] Retester toutes les fonctionnalités
- [x] Supprimer les anciennes libs
- [x] Refactor
- [x] Modification readme
- [x] Garder les fichiers sources du RAG
- [x] Evenement Rag, intégrer une Url pour accéder au fichier
- [x] Dans route auth, profile par défaut

Version WAVE :
- [x] Implémentation des traductions LLM
- [x] Traduction des codes d'erreur
- [x] Gestion des noms d'outils MCP en multilingue
- [x] Gestionnaire de traduction
- [x] API pour avoir la configuration d'un profil
- [x] Réorganiser les fichiers / dossiers
- [x] Refactor
- [x] Fichiers dans les autres langues
- [x] Version
- [x] Readme
- [x] Optimisation pour déploiement Docker
------------

Installer cloudflared

curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
rm cloudflared.deb

Lancer le tunnel
cloudflared tunnel --url http://localhost:8001


----------------------------------------
Implémentation Webex sur LumePack :
Fichiers : 
app/Http/Middleware/WebexBasicAuth.php
app/Http/Controllers/Webex/WebexAuthController.php
config/webex.php
Modifié : bootstrap/app.php
Modifié : routes/api.php
Modifié : .env.example et .env

----------------------------------------
Implémentation

Docker compose up -d
docker compose up --build -d (pour réinstaller les libs)
docker compose down
docker compose -f docker-compose.prod.yml up --build -dAUROR
----------------------------------------
Installer libreoffice

sudo apt install -y libreoffice-writer