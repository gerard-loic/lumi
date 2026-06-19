- [ ] Revoir le fichier de configuration pour le prompt
- [x] Retour des urls et des fichiers 
- [ ] Implémentation des traductions
- [ ] RAG local sur un fichier
- [ ] Envoi de fichiers à l'agent
- [ ] Limiter la sortie ?
- [ ] Critique du code
- [ ] Support OCR / modèle de compréhension d'image
- [ ] option pour retourner les infos des documents
- [ ] Confirmations : prévoir des options plus riches (objets)
- [ ] Bug sur les retours de confirmations (message refusé après sélection d'un oui ? ou pas de validation du tout)
- [x] chat.html : pb des fichiers
- [ ] Follow-up 
- [ ] Limitation des résultats
- [ ] Détermination auto du modèle le mieux adapté pour répondre à une question ?
- [ ] Critique de la réponse par un modèle
- [ ] Fonction "instruction" dans le tool MCP
- [ ] Pb confirmation avec l'abandon de l'action [EN COURS]
- [ ] Pbs de l'affichage du retour des liens
- [ ] Tache de delestage
- [ ] Possibilité d'arreter une conversation proprement
- [ ] Connecteur Webex [EN COURS]
- [x] Outil génération PDF [EN COURS]
- [ ] Outil génération fichier Word
- [x] pb pbVector sur prod
- [ ] Gestion des liens directs, modification authentification
- [ ] Refactoring pour la version Spark
- [ ] Outils de date/heure
- [ ] Gestion du system prompt dans un fichier séparé
- [ ] Connecteur Webex : avoir des retours sur les actions en cours

------------
Versions à venir : 

Spark (1.2.0)
- Connecteur Webex
- Outils MCP PDF/Date/Word

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