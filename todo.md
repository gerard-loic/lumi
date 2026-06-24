
----------------------------
BACKLOG
- [ ] Implémentation des traductions
- [ ] RAG local sur un fichier
- [ ] Envoi de fichiers à l'agent
- [ ] Limiter la sortie ?
- [ ] Support OCR / modèle de compréhension d'image
- [ ] option pour retourner les infos des documents
- [ ] Confirmations : prévoir des options plus riches (objets)
- [ ] Follow-up 
- [ ] Limitation des résultats
- [ ] Détermination auto du modèle le mieux adapté pour répondre à une question ?
- [ ] Critique de la réponse par un modèle
- [ ] Tache de delestage
- [ ] Possibilité d'arreter une conversation proprement
- [ ] Indexation RAG Word, Excel
- [ ] Cron Indexer RAG
- [ ] Sources de stockage RAG
------------
Versions à venir : 



Ocean (1.3.0)
- Envoi de fichiers à l'agent
- Outils de lectures de PDF/Excel/Word
- Micro RAG sur les outils envoyés

Vision (1.4.0)
- Implémentation de modèles de vision
- Implémentation de modèles d'audio
- Envoi de la demande en audio au modèle

------------

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