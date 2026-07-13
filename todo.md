AURORA
- [x] Deplacer _charts.py de tools/
- [x] Reorganier les dossiers d'outils
- [x] Outils MCP Word avancés
- [x] Pb des fichiers, envoyés avant la génération ??
- [x] Tache de delestage
- [x] Implémentation d'un mécanisme de tâches CRON
- [x] Refonte et sécurisation du système d'import dynamique
- [ ] Refactor version Aurora
- [x] MAJ README
- [x] Follow-up 
- [x] Modification version
- [x] Ajout FollowUpEvent Event
----------------------------
BACKLOG
- [ ] Implémentation des traductions
- [ ] RAG local sur un fichier
- [ ] Envoi de fichiers à l'agent
- [ ] Limiter la sortie ?
- [ ] Support OCR / modèle de compréhension d'image
- [ ] option pour retourner les infos des documents
- [ ] Confirmations : prévoir des options plus riches (objets)
- [ ] Limitation des résultats
- [ ] Détermination auto du modèle le mieux adapté pour répondre à une question ?
- [ ] Critique de la réponse par un modèle
- [ ] Possibilité d'arreter une conversation proprement
- [ ] Indexation RAG Word, Excel
- [ ] Cron Indexer RAG
- [ ] Sources de stockage RAG
- [ ] Création de pipelines
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
------------
Versions à venir : 

Phosphor
Focalisé sur les fonctionnalités RAG

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