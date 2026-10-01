# Écrire et configurer un pipeline

Un **pipeline** est une suite de traitements (« blocs ») enchaînés, déclenchée par un
ou plusieurs **triggers**, et partageant un **contexte** de données commun d'un bloc à
l'autre.

Cette documentation couvre :

1. [Le fichier de configuration](#1-le-fichier-de-configuration)
2. [L'utilisation du contexte](#2-lutilisation-du-contexte)
3. [Les triggers disponibles et leur configuration](#3-les-triggers-disponibles-et-leur-configuration)
4. [Les blocs disponibles et leur configuration](#4-les-blocs-disponibles-et-leur-configuration)
5. [Déclencher et suivre un pipeline](#5-déclencher-et-suivre-un-pipeline)
6. [Exemple complet commenté](#6-exemple-complet-commenté)

> Documentation générée à partir du code de `lib/pipelines/` et du schéma
> `lib/_references/pipeline.schema.json` (état au 2026-10-01, Lumi 1.6.0 Abyss).
> Vue d'ensemble de Lumi : [README.md](README.md).

---

## 1. Le fichier de configuration

### 1.1 Emplacement

Chaque pipeline vit dans son propre dossier sous le répertoire configuré par
`directories.custom_pipelines` (par défaut `config/pipelines`, cf. `config/config.json`) :

```
config/pipelines/
├── recap_mail/
│   └── pipeline.json
└── mon_pipeline/
    └── pipeline.json
```

* Le **nom du dossier** est l'identifiant du pipeline (`pipeline_uid`). C'est lui qui
  sera utilisé dans l'URL de déclenchement (`/pipeline/mon_pipeline/start`).
* Le dossier **doit** contenir un fichier `pipeline.json`. Sans ce fichier, le dossier
  est ignoré au chargement.
* Les pipelines sont chargés **une seule fois au démarrage** du service
  (`PipelineManager.init()`). Toute modification d'un `pipeline.json` nécessite un
  redémarrage.
* Au chargement, chaque `pipeline.json` est **validé** contre le JSON Schema
  `lib/_references/pipeline.schema.json` : clé inconnue, classe de bloc inexistante,
  paramètre mal typé ou obligatoire manquant → exception et le service ne démarre pas.
  Le schéma documente aussi, bloc par bloc, les paramètres acceptés : c'est la référence
  en cas de doute.

### 1.2 Structure globale

```json
{
    "name": "Libellé lisible du pipeline",
    "services": {
        "nexora": { "login": "robot@example.com", "password": "..." }
    },
    "trigger": [
        { "class": "Api", "config": { } }
    ],
    "blocks": {
        "_root": {
            "class": "...",
            "config": { },
            "on_success": "bloc_suivant",
            "on_error": "exit(0)"
        },
        "bloc_suivant": {
            "class": "...",
            "config": { },
            "on_success": "exit(1)",
            "on_error": "exit(0)"
        }
    }
}
```

| Clé        | Type   | Rôle                                                                    |
|------------|--------|-----------------------------------------------------------------------|
| `name`     | string | Libellé d'affichage. Purement informatif (optionnel).                 |
| `services` | object | Optionnel. Authentification du run auprès des services de `config.json` (voir [§1.7](#17-authentification-aux-services--services)). |
| `trigger`  | array  | Liste des déclencheurs. Voir [§3](#3-les-triggers-disponibles-et-leur-configuration). Au moins un est requis. |
| `blocks`   | object | Dictionnaire `identifiant_de_bloc → définition`. Doit contenir `_root`. |

### 1.3 Définition d'un bloc

```json
"mon_bloc": {
    "class": "Agent",
    "config": { "...": "..." },
    "on_success": "bloc_a",
    "on_error": "bloc_b"
}
```

| Clé          | Obligatoire | Rôle                                                                                   |
|--------------|-------------|--------------------------------------------------------------------------------------|
| `class`      | oui         | Nom de la classe du bloc (sensible à la casse), voir [§4](#4-les-blocs-disponibles-et-leur-configuration). |
| `config`     | oui         | Paramètres propres au bloc. Interprété via le contexte (voir [§2](#2-lutilisation-du-contexte)). |
| `on_success` | non         | Que faire si le bloc réussit (`execute` renvoie vrai).                                 |
| `on_error`   | non         | Que faire si le bloc échoue (`execute` renvoie faux ou lève une exception).            |

Le résolveur de classe (`DynamicImport`) transforme `class` en
`lib.pipelines.blocks.<class en minuscules>` et y cherche la classe nommée exactement
`<class>`. Ainsi `"class": "ApiPost"` charge `lib/pipelines/blocks/apipost.py` → classe
`ApiPost`. Les blocs héritent de `Block` (`lib/pipelines/_abstract.py`). Un nouveau bloc
doit aussi être ajouté à l'énumération `block.class` (et à `$defs/config`) du schéma
`pipeline.schema.json`, sans quoi les pipelines qui l'utilisent sont refusés au chargement.

Les identifiants de bloc ne peuvent contenir que lettres, chiffres, `_` et `-`.

### 1.4 Le bloc `_root`

* L'exécution démarre **toujours** par le bloc dont l'identifiant est `_root`.
* Un pipeline sans bloc `_root` lève une exception au démarrage.

### 1.5 Enchaînement : `on_success`, `on_error`, `exit(...)`

La valeur de `on_success` / `on_error` est :

* **l'identifiant d'un autre bloc** → ce bloc est exécuté ensuite, avec le même contexte ;
* **`"exit(1)"`** → le pipeline s'arrête immédiatement avec le statut **succès** ;
* **`"exit(0)"`** → le pipeline s'arrête immédiatement avec le statut **échec** ;
* **absente** :
  * `on_success` absent → fin du pipeline avec le statut **succès** ;
  * `on_error` absent → fin du pipeline avec le statut **échec**.

> ⚠️ **Attention à la convention `exit`** : contrairement à un code retour shell,
> `exit(1)` = succès et `exit(0)` = échec. Le statut final est consultable via l'API
> de suivi (`is_success`).

Il n'y a **pas** de garde contre les cycles : `on_success`/`on_error` peut pointer vers
un bloc déjà exécuté (l'appel est récursif). C'est ce mécanisme qu'utilise le bloc
`Loop` ([§4.11 bis](#411-bis-loop)) ; en dehors de ce cas, à utiliser avec prudence.

### 1.6 Cycle de vie d'un run

1. Un trigger correspond → un `PipelineRunner` est créé avec un `process_uid` unique et lancé dans un thread dédié.
2. Un process `<process_uid>` est ouvert : il porte le wallet (authentifications aux services du pipeline) et les fichiers temporaires du run (voir [§4.16](#416-fichiers-temporaires)).
3. Le run s'authentifie auprès de chaque service déclaré sous `services` (voir [§1.7](#17-authentification-aux-services--services)).
4. Les données du trigger sont injectées dans le contexte sous `trigger` (voir [§2.1](#21-les-données-du-trigger)).
5. `_root` est exécuté, puis la chaîne `on_success` / `on_error` est suivie.
6. Chaque bloc est journalisé (statut + logs) : consultable via l'API de suivi.
7. En fin de run (succès **ou** échec), le process est fermé et tous les fichiers temporaires du run sont purgés.

### 1.7 Authentification aux services : `services`

La clé `services` associe un **nom de service** (clé de `services` dans `config.json`, pas
le `handler`) aux données d'authentification à lui transmettre :

```json
"services": {
    "nexora": { "login": "robot@example.com", "password": "..." },
    "autre_api": { "token": "..." }
}
```

* Au démarrage de chaque run, `Service.authenticate()` est appelé pour chaque entrée. La
  config d'un pipeline étant une source de confiance, l'échange **login / mot de passe**
  y est autorisé (contrairement à `POST /auth`, qui n'accepte que des jetons existants).
* Le secret obtenu (ex. `{"token": "..."}`) est rangé dans le **wallet** du run. Il est
  utilisé par les outils MCP appelés pendant un bloc `Agent`, et par les méthodes appelées
  via `ServiceMethod` (`self.getAuth()`).
* Un échec d'authentification est **journalisé mais n'arrête pas le run** : les blocs qui
  dépendent du service échoueront ensuite.
* Les données ne sont pas interpolées : ce sont des valeurs statiques du fichier.

---

## 2. L'utilisation du contexte

Le **contexte** (`PipelineContext`) est un espace de clés/valeurs partagé par tous les
blocs d'un run. Un bloc **lit** des valeurs produites par les blocs précédents et
**écrit** son résultat, généralement sous une clé paramétrable `output`.

### 2.1 Les données du trigger

Quand le pipeline est déclenché par un événement, le contexte est pré-rempli avec :

| Variable            | Contenu                                                                 |
|---------------------|----------------------------------------------------------------------|
| `trigger.type`      | Type numérique de l'événement (ex. `1` pour un appel API).           |
| `trigger.data`      | Charge utile de l'événement. Pour un déclenchement API, c'est le contenu du champ `payload` du corps JSON. |
| `trigger.data.<clé>`| Accès à un champ précis de la charge utile.                          |

Exemple : un `POST /pipeline/mon_pipeline/start` avec le corps
`{"payload": {"client_id": 42}}` rend `{trigger.data.client_id}` → `42`.

### 2.2 Interpolation dans la configuration

Toutes les **chaînes** de la `config` d'un bloc sont interprétées comme des templates au
moment où le bloc s'exécute, y compris les chaînes imbriquées dans des objets ou des
tableaux. La résolution est **paresseuse** : elle a lieu à la lecture, une fois le
contexte peuplé par les blocs précédents.

> Exception : la clé `template` d'une opération `add_column` du bloc `DataView` n'est
> **pas** interpolée avec le contexte (ses `{colonne}` sont résolus ligne par ligne).

### 2.3 Variables : `{chemin}`

```
{result}                     → la valeur de la clé "result"
{auth.body.data.token}       → navigation dans des dicts imbriqués
{mails[0].subject}           → indexation de liste
{trigger.data.client_id}     → donnée portée par le trigger
```

* Séparateur de niveau : `.`
* Indexation : `[n]` (entier positif), chaînable : `{a.b[0].c[2]}`
* Une clé absente lève une erreur et fait échouer le bloc.
* La valeur est convertie en chaîne (`str`) lors de l'insertion dans un texte.

### 2.4 Boucles : `{% for %}`

```
{% for mail in mails %}- {mail.subject} ({mail.from})
{% endfor %}
```

* `{% for <var> in <chemin> %} ... {% endfor %}`
* `<chemin>` doit résoudre vers une liste (ou une valeur nulle → 0 itération).
* À l'intérieur, `<var>` désigne l'élément courant ; les variables extérieures restent accessibles.

### 2.5 Conditions : `{% if %}`

```
{% if trigger.data.mode == "complet" %}Rapport complet
{% elif trigger.data.mode == "court" %}Rapport court
{% else %}Rapport par défaut
{% endif %}
```

Opérateurs supportés dans la condition :

| Opérateur          | Sens                              |
|--------------------|-----------------------------------|
| `==` `!=`          | égalité / différence              |
| `>` `<` `>=` `<=`  | comparaison d'ordre               |
| `IN` / `NOT IN`    | appartenance (insensible à la casse) |

Opérandes admis de part et d'autre de l'opérateur :

* littéral chaîne : `"texte"` ou `'texte'`
* nombre : `42`, `-3.5`
* booléen : `true` / `false`
* nul : `none` / `null`
* liste : `["a", "b", "c"]` (utile avec `IN`)
* chemin de variable : `trigger.data.role`

### 2.6 Config vs. contexte, et la clé `output`

* La `config` d'un bloc est **statique** (écrite dans le JSON) mais ses chaînes sont
  interpolées avec le **contexte dynamique** au moment de l'exécution.
* La plupart des blocs exposent une clé `output` (parfois `files_output`) : c'est le
  **nom de la variable de contexte** dans laquelle le bloc écrit son résultat, à
  réutiliser dans les blocs suivants via `{ce_nom}`.
* Le bloc `Context` ([§4.1](#41-context)) sert à **injecter des valeurs statiques** ou
  calculées dans le contexte sans appeler de service externe.

---

## 3. Les triggers disponibles et leur configuration

Un trigger est décrit par un objet `{ "class": "...", "config": { ... } }` dans le
tableau `trigger`. Un pipeline se déclenche dès qu'**au moins un** de ses triggers
reconnaît l'événement reçu.

Résolution de classe : `class` → `lib.pipelines.triggers.<class en minuscules>` →
classe `<class>`.

### 3.1 `Api`

Déclenche le pipeline sur un appel HTTP à `POST /pipeline/{pipeline_uid}/start`.

```json
"trigger": [
    { "class": "Api", "config": { } }
]
```

* `config` : **aucun paramètre**. Tout événement de type « appel API » est accepté.
* La charge utile éventuelle (`payload` du corps JSON) est déposée dans le contexte
  sous `trigger.data` (voir [§2.1](#21-les-données-du-trigger)).

### 3.2 Autres triggers

`Api` est le **seul** trigger disponible à ce jour : toute autre valeur de `class` est
refusée par la validation du `pipeline.json`. Les triggers héritent de `Trigger`
(`lib/pipelines/_abstract.py`) et reçoivent un `TriggerEvent` (`lib/pipelines/triggerevent.py`).

---

## 4. Les blocs disponibles et leur configuration

Tous les blocs partagent :

* `class` — voir tableau ci-dessous ;
* `config` — objet de paramètres (interpolé via le contexte) ;
* `on_success` / `on_error` — enchaînement (voir [§1.5](#15-enchaînement--on_success-on_error-exit)).

| `class`        | Rôle                                                        |
|----------------|-----------------------------------------------------------|
| `Context`      | Injecter des valeurs dans le contexte                     |
| `Agent`        | Faire réfléchir un agent LLM sur un prompt                |
| `JsonFormat`   | Parser / valider du JSON présent dans le contexte         |
| `XmlFormat`    | Parser / valider du XML présent dans le contexte          |
| `ApiGet`       | Requête HTTP `GET`                                        |
| `ApiPost`      | Requête HTTP `POST`                                       |
| `ApiPut`       | Requête HTTP `PUT`                                        |
| `ApiDelete`    | Requête HTTP `DELETE`                                     |
| `Mail`         | Envoyer un email (SMTP) ou lire une boîte (IMAP)          |
| `Webex`        | Envoyer une notification Webex (espace ou message direct) |
| `DataView`     | Transformer une table de données (filtre, tri, colonnes…) |
| `DataViewFile` | Sérialiser une liste de lignes dans un fichier (CSV/JSON) |
| `TxtReader`    | Lire un fichier texte / Markdown                          |
| `CsvReader`    | Lire un fichier CSV en table (compatible `DataView`)      |
| `ExcelReader`  | Lire un classeur Excel `.xlsx` / `.xlsm` / `.xls` en table |
| `FileDelete`   | Supprimer un ou plusieurs fichiers                        |
| `FileMove`     | Déplacer / renommer un ou plusieurs fichiers              |
| `FileWriter`   | Écrire sur le disque une copie d'un fichier temporaire    |
| `FileExists`   | Tester la présence d'un fichier                           |
| `Condition`    | Évaluer une expression booléenne et brancher le pipeline  |
| `Loop`         | Parcourir une liste du contexte, ligne par ligne          |
| `Sleep`        | Mettre le run en pause pendant N secondes                 |
| `MicroRag`     | Préparer des fichiers pour le micro-RAG d'un bloc `Agent` |
| `PythonScript` | Exécuter un script Python du dossier du pipeline         |
| `ServiceMethod`| Appeler une méthode d'un service (ex : `LumePackAPI`)     |

### 4.1 `Context`

Fusionne l'intégralité de sa `config` dans le contexte. Chaque paire clé/valeur devient
une variable réutilisable par les blocs suivants. Les chaînes sont interpolées au
passage (on peut donc composer une valeur à partir de variables déjà présentes).

```json
"prepare": {
    "class": "Context",
    "config": {
        "destinataire": "equipe@example.com",
        "sujet": "Rapport du {trigger.data.jour}",
        "seuil": 10
    },
    "on_success": "suite"
}
```

Toujours en succès.

### 4.2 `Agent`

Déclenche une réflexion LLM (`agent.reflect`) à partir d'un prompt et écrit la réponse
dans le contexte. La réflexion s'exécute dans un process enfant du run, qui hérite de son
wallet : les outils MCP appelés par l'agent utilisent les authentifications déclarées
sous `services` ([§1.7](#17-authentification-aux-services--services)).

| Paramètre       | Type   | Défaut                    | Rôle                                                                              |
|-----------------|--------|---------------------------|--------------------------------------------------------------------------------|
| `profile`       | string | —                         | **Obligatoire.** Nom du profil (`profiles.<nom>` de `config.json`) : modèle LLM, outils MCP, réglages des pièces jointes. |
| `prompt`        | string | `""`                      | Prompt transmis à l'agent. Interpolé avec le contexte.                         |
| `auto_confirm`  | bool   | `false`                   | `true` → les outils MCP à confirmation (`@confirmation_tool`) s'exécutent sans validation ; `false` → ils sont refusés. À réserver aux pipelines de confiance (envoi de mail, suppression, écritures externes…). |
| `language`      | string | `app.default_language`    | Code langue de la session.                                                     |
| `output`        | string | `"result"`                | Clé de contexte où stocker la réponse de l'agent.                              |
| `files_output`  | string | `"files"`                 | Clé de contexte où stocker les fichiers produits par les outils MCP pendant la réflexion (liste de `{key, filename, path}`). |
| `micro_rag`     | string \| array | —              | Fichiers préparés par un ou plusieurs blocs `MicroRag` : référence `"{var}"` ou liste de références. Voir [§4.13](#413-microrag). |
| `micro_rag_mode` | string | profil (`attachments.mode`), sinon `"auto"` | `"rag"` : extraits les plus pertinents ; `"full"` : texte complet ; `"auto"` : texte complet s'il tient dans `micro_rag_max_tokens`, extraits sinon. |
| `micro_rag_max_tokens` | int | profil (`attachments.full_text_max_tokens`), sinon `20000` | Seuil du mode `"auto"` (total estimé des fichiers joints, ≈ 4 caractères par token). |
| `micro_rag_query` | string | le `prompt`             | Requête de recherche des extraits (modes `rag` / `auto` sur un contenu trop long), si le prompt (souvent une consigne) ne décrit pas l'information à retrouver. |
| `micro_rag_top_k` | int  | profil (`attachments.file_context_top_k`), sinon `8` | Nombre d'extraits ajoutés au prompt. |

Échoue si le profil est introuvable, si une référence `micro_rag` est invalide ou si la
réflexion lève une erreur.

> Depuis la 1.6.0, le paramètre `authorization` du bloc n'existe plus : les
> authentifications se déclarent une fois pour tout le run, sous `services`.

```json
"analyse": {
    "class": "Agent",
    "config": {
        "profile": "agent-base",
        "prompt": "Résume ces emails et signale ceux qui demandent une action : {mails}",
        "output": "analyse"
    },
    "on_success": "send_mail",
    "on_error": "exit(0)"
}
```

### 4.3 `JsonFormat`

Parse une chaîne JSON présente dans le contexte, la valide optionnellement contre un
JSON Schema, et écrit la structure obtenue.

| Paramètre | Type            | Défaut  | Rôle                                                                        |
|-----------|-----------------|---------|--------------------------------------------------------------------------|
| `input`   | string          | —       | **Obligatoire.** Clé de contexte contenant la chaîne JSON sérialisée. La valeur **doit** être une chaîne. |
| `format`  | object \| `false` | `false` | JSON Schema de validation. `false` → aucune validation.                   |
| `output`  | string          | —       | **Obligatoire.** Clé de contexte où stocker la structure désérialisée.    |

Échoue si l'entrée n'est pas une chaîne, si le JSON est invalide, ou si la validation de
schéma échoue.

```json
"parse": {
    "class": "JsonFormat",
    "config": {
        "input": "reponse_agent",
        "format": {
            "type": "object",
            "required": ["titre", "points"],
            "properties": {
                "titre":  { "type": "string" },
                "points": { "type": "array", "items": { "type": "string" } }
            }
        },
        "output": "rapport"
    },
    "on_success": "suite",
    "on_error": "exit(0)"
}
```

### 4.4 `XmlFormat`

Équivalent XML de `JsonFormat` : parse une chaîne XML présente dans le contexte, la valide
optionnellement contre un XML Schema (XSD), et écrit la structure obtenue.

| Paramètre | Type              | Défaut  | Rôle                                                                        |
|-----------|-------------------|---------|--------------------------------------------------------------------------|
| `input`   | string            | —       | **Obligatoire.** Clé de contexte contenant la chaîne XML sérialisée. La valeur **doit** être une chaîne. |
| `format`  | string \| `false` | `false` | XML Schema (XSD) de validation, sous forme de chaîne. `false` → aucune validation. |
| `output`  | string            | —       | **Obligatoire.** Clé de contexte où stocker la structure désérialisée.    |

La structure produite est `{ "<racine>": <contenu> }`, où le contenu d'un élément est :

* sa valeur texte s'il n'a ni attribut ni enfant (`null` s'il est vide) ;
* sinon un objet : attributs préfixés par `@`, enfants par nom (sans namespace), **liste**
  si l'élément est répété, texte éventuel sous `#text`.

Toutes les valeurs restent des chaînes (pas de conversion de type). Le parser ignore les
commentaires, les DTD et ne résout pas les entités externes (protection XXE).

Échoue si l'entrée n'est pas une chaîne, si le XML est invalide, si le XSD est invalide,
ou si la validation de schéma échoue.

```json
"parse": {
    "class": "XmlFormat",
    "config": {
        "input": "reponse_agent",
        "format": "<xs:schema xmlns:xs=\"http://www.w3.org/2001/XMLSchema\"><xs:element name=\"rapport\"><xs:complexType><xs:sequence><xs:element name=\"titre\" type=\"xs:string\"/><xs:element name=\"point\" type=\"xs:string\" maxOccurs=\"unbounded\"/></xs:sequence></xs:complexType></xs:element></xs:schema>",
        "output": "rapport"
    },
    "on_success": "suite",
    "on_error": "exit(0)"
}
```

Avec `<rapport><titre>T</titre><point>a</point><point>b</point></rapport>` en entrée,
`rapport` vaut `{"rapport": {"titre": "T", "point": ["a", "b"]}}`.

### 4.5 Blocs HTTP : `ApiGet` / `ApiPost` / `ApiPut` / `ApiDelete`

Effectuent une requête REST et écrivent la réponse dans le contexte. La méthode HTTP est
imposée par la classe.

| Paramètre         | Type              | Défaut     | Rôle                                                                             |
|-------------------|-------------------|------------|-------------------------------------------------------------------------------|
| `url`             | string            | —          | **Obligatoire.** URL complète de l'endpoint. Interpolée.                       |
| `headers`         | object            | `{}`       | En-têtes HTTP. Valeurs interpolées.                                            |
| `params`          | object            | `{}`       | Paramètres de query string. Valeurs interpolées.                              |
| `body`            | object/array/string | `null`   | Corps de requête (POST/PUT surtout ; optionnel en DELETE ; ignoré en GET). Chaînes interpolées récursivement. |
| `send_json`       | bool              | `true`     | `true` → corps sérialisé en JSON + `Accept: application/json` + réponse parsée en JSON. `false` → corps envoyé tel quel (form/raw), réponse en texte brut. |
| `multipart`       | bool              | `false`    | `true` → corps envoyé en `multipart/form-data` (un champ par clé de `body`). Implicite si `files` est renseigné. (POST/PUT) |
| `files`           | object            | `{}`       | Fichiers joints en multipart. `{"champ": "/chemin"}` ou `{"champ": {"path": "...", "filename": "...", "content_type": "..."}}`. (POST/PUT) |
| `auth`            | object            | `{}`       | `{"type": "basic", "username": "...", "password": "..."}` ou `{"type": "bearer", "token": "..."}`. |
| `timeout`         | number            | `30`       | Délai d'attente en secondes.                                                  |
| `verify_ssl`      | bool              | `true`     | Vérification du certificat TLS.                                               |
| `allow_redirects` | bool              | `true`     | Suivi des redirections HTTP.                                                  |
| `fail_on_error`   | bool              | `true`     | Un statut HTTP ≥ 400 fait échouer le bloc (la réponse est tout de même écrite dans le contexte). |
| `output`          | string            | `"result"` | Clé de contexte où stocker le résultat.                                       |

**Résultat écrit dans le contexte** :

```json
{
    "status":  200,
    "ok":      true,
    "headers": { "...": "..." },
    "body":    "objet JSON parsé, ou texte brut"
}
```

Exemple (authentification puis réutilisation du jeton) :

```json
"_root": {
    "class": "ApiPost",
    "config": {
        "url": "https://api.example.com/auth/login",
        "body": { "login": "robot@example.com", "password": "..." },
        "output": "auth"
    },
    "on_success": "fetch",
    "on_error": "exit(0)"
},
"fetch": {
    "class": "ApiGet",
    "config": {
        "url": "https://api.example.com/clients/{trigger.data.client_id}",
        "auth": { "type": "bearer", "token": "{auth.body.data.token}" },
        "output": "client"
    },
    "on_success": "exit(1)",
    "on_error": "exit(0)"
}
```

### 4.6 `Mail`

Envoie un email (SMTP) ou lit une boîte de réception (IMAP).

**Paramètres communs**

| Paramètre  | Type   | Défaut   | Rôle                                                     |
|------------|--------|----------|-------------------------------------------------------|
| `action`   | string | `"send"` | `"send"`, `"list"` ou `"read"`.                       |
| `username` | string | —        | **Obligatoire.** Identifiant du compte ; sert aussi d'adresse d'expéditeur. |
| `password` | string | —        | **Obligatoire.** Mot de passe / mot de passe d'application. |
| `output`   | string | `"content"` | Clé de contexte où écrire le résultat. (Le code utilise `content` par défaut ; pour `send`, le résultat est un booléen.) |

**SMTP — `action: "send"`**

| Paramètre      | Type              | Défaut  | Rôle                                             |
|----------------|-------------------|---------|-----------------------------------------------|
| `smtp_host`    | string            | —       | **Obligatoire** en `send`. Serveur SMTP.      |
| `smtp_port`    | int               | `587`   | Port SMTP.                                    |
| `smtp_use_ssl` | bool              | `false` | Connexion SSL directe (`SMTP_SSL`).          |
| `smtp_use_tls` | bool              | `true`  | `STARTTLS` après connexion (ignoré si `smtp_use_ssl`). |
| `to`           | string \| string[] | —       | **Obligatoire** en `send`. Destinataire(s). Interpolé. |
| `subject`      | string            | `""`    | Sujet. Interpolé.                             |
| `body`         | string            | `""`    | Corps texte brut. Interpolé.                  |
| `attachments`  | array             | `[]`    | Pièces jointes. Chaque entrée : chemin local (interpolé), référence `"{var}"` vers un fichier ou une liste de fichiers (ex. `"{files}"` d'un bloc `Agent`, sortie d'un `DataViewFile`), dict `{"path", "filename"}`, ou liste imbriquée de ces formes. Le nom présenté au destinataire est `filename`. Les fichiers introuvables sont ignorés. |

**IMAP — `action: "list"` et `action: "read"`**

| Paramètre      | Type   | Défaut        | Rôle                                            |
|----------------|--------|---------------|----------------------------------------------|
| `imap_host`    | string | (`smtp_host`) | Serveur IMAP.                                |
| `imap_port`    | int    | `993`         | Port IMAP.                                   |
| `imap_use_ssl` | bool   | `true`        | Connexion SSL (`IMAP4_SSL`).                 |
| `folder`       | string | `"INBOX"`     | Dossier ciblé.                               |
| `limit`        | int    | `20`          | Nombre max d'emails retournés (`list`).      |
| `email_id`     | string | —             | **Obligatoire** en `read`. Identifiant IMAP de l'email à lire. |

* `action: "list"` → écrit une liste de `{id, subject, from, date}` (du plus récent au plus ancien).
* `action: "read"` → écrit `{id, subject, from, to, date, body, attachments[]}`.

```json
"lire_boite": {
    "class": "Mail",
    "config": {
        "action": "list",
        "limit": 20,
        "imap_host": "imap.example.com",
        "imap_port": 993,
        "imap_use_ssl": true,
        "username": "robot@example.com",
        "password": "...",
        "output": "mails"
    },
    "on_success": "analyse",
    "on_error": "exit(0)"
}
```

### 4.6 bis `Webex`

Envoie une notification Webex (message Markdown, avec une pièce jointe optionnelle) via un bot.
Le jeton du bot peut être repris d'un profil (`profiles.<profil>.connectors.webex`, le connecteur
n'a pas besoin d'être activé) ou fourni directement.

| Paramètre         | Type             | Défaut      | Rôle                                                              |
|-------------------|------------------|-------------|-------------------------------------------------------------------|
| `profile`         | string           | —           | Profil dont on réutilise `bot_token` et `webex_api`.              |
| `bot_token`       | string           | —           | Jeton du bot ; prioritaire sur celui du profil.                   |
| `webex_api`       | string           | profil ou `https://webexapis.com/v1` | URL de base de l'API Webex.              |
| `room_id`         | string           | —           | Espace destinataire.                                              |
| `to_person_email` | string           | —           | Email du destinataire (message direct).                           |
| `to_person_id`    | string           | —           | Identifiant Webex du destinataire (message direct).               |
| `message`         | string           | `""`        | Texte Markdown. Interpolé.                                        |
| `attachment`      | string \| object | —           | Fichier joint : chemin, `"{var}"` vers une structure `{path, filename}` (une liste → seul le premier est envoyé, Webex n'accepte qu'un fichier par message). |
| `timeout`         | int              | `30`        | Délai d'attente HTTP (s).                                         |
| `output`          | string           | `"webex"`   | Clé de contexte où écrire `{id, room_id}` du message créé.        |

Exactement un destinataire parmi `room_id`, `to_person_email` et `to_person_id`. Il faut au moins
un `message` ou un `attachment`. Le bot doit être membre de l'espace ciblé par `room_id`.

```json
"notifier": {
    "class": "Webex",
    "config": {
        "profile": "default",
        "to_person_email": "{trigger.data.demandeur}",
        "message": "Le rapport du **{trigger.data.jour}** est prêt.",
        "attachment": "{report}"
    },
    "on_success": "exit(0)",
    "on_error": "exit(1)"
}
```

### 4.7 `DataView`

Construit une vue tabulaire à partir d'un dict ou d'une liste du contexte, lui applique
une suite ordonnée d'opérations, puis réécrit le résultat dans le contexte.

| Paramètre      | Type   | Défaut     | Rôle                                                                     |
|----------------|--------|------------|----------------------------------------------------------------------|
| `input`        | string | —          | **Obligatoire.** Clé de contexte contenant le dict ou la liste source. |
| `key_column`   | string | `"key"`    | Nom de colonne recevant la clé quand la source est un dict.           |
| `value_column` | string | `"value"`  | Nom de colonne recevant la valeur pour une source de scalaires.       |
| `operations`   | array  | `[]`       | Opérations appliquées **dans l'ordre** (voir ci-dessous).             |
| `as`           | string | `"list"`   | `"list"` → liste de lignes ; `"dict"` → voir `key`.                   |
| `key`          | string | `null`     | Si `as: "dict"` + `key` → `{ligne[key]: ligne}`. Si `as: "dict"` sans `key` → forme colonnaire `{colonne: [valeurs]}`. |
| `flatten`      | bool   | `false`    | Si `as: "list"` et une seule colonne → liste de scalaires.            |
| `output`       | string | `"result"` | Clé de contexte où stocker le résultat.                              |

**Opérations** (chaque entrée de `operations` est un objet avec une clé `op`) :

| Opération                                                             | Effet                                            |
|----------------------------------------------------------------------|-----------------------------------------------|
| `{"op": "filter", "where": [[champ, op, val], …], "match": "all"\|"any"}` | Conserve les lignes qui valident.        |
| `{"op": "drop_rows", "where": […], "match": …}`                     | Supprime les lignes qui valident.            |
| `{"op": "drop_rows", "indices": [0, -1]}`                           | Supprime des lignes par position.            |
| `{"op": "add_rows", "rows": [{…}, …]}`                              | Ajoute des lignes.                           |
| `{"op": "order", "by": "champ"\|["a","b"], "desc": false}`          | Trie (alias `sort`).                         |
| `{"op": "drop_columns", "columns": ["a", "b"]}`                     | Supprime des colonnes.                       |
| `{"op": "select", "columns": ["a", "b"]}`                           | Ne conserve que ces colonnes (ordre inclus). |
| `{"op": "rename_column", "from": "a", "to": "b"}`                   | Renomme une colonne.                         |
| `{"op": "add_column", "name": "x", "value": <const>}`               | Ajoute une colonne constante.               |
| `{"op": "add_column", "name": "label", "template": "{nom} ({age})"}` | Ajoute une colonne calculée par ligne.      |

Opérateurs de `where` : `==` `!=` `>` `<` `>=` `<=` `in` `"not in"` `contains`
`startswith` `endswith`.

> Les chaînes de `operations` sont interpolées avec le contexte au moment de
> l'application, **sauf** la clé `template` d'un `add_column` (ses `{colonne}` sont
> résolus ligne par ligne ; une colonne absente donne une chaîne vide).

```json
"tri": {
    "class": "DataView",
    "config": {
        "input": "mails",
        "operations": [
            { "op": "filter", "where": [["from", "contains", "@client.com"]] },
            { "op": "order", "by": "date", "desc": true },
            { "op": "select", "columns": ["date", "from", "subject"] }
        ],
        "as": "list",
        "output": "mails_clients"
    },
    "on_success": "export",
    "on_error": "exit(0)"
}
```

### 4.8 `DataViewFile`

Sérialise une liste de lignes (typiquement la sortie d'un `DataView` en `as: "list"`)
dans un fichier temporaire rattaché au run.

| Paramètre   | Type   | Défaut               | Rôle                                                    |
|-------------|--------|----------------------|-----------------------------------------------------|
| `input`     | string | —                    | **Obligatoire.** Clé de contexte contenant la `list[dict]`. |
| `format`    | string | `"csv"`              | `"csv"`, `"json"` ou `"jsonl"`.                     |
| `filename`  | string | `"dataview.<format>"`| Nom du fichier proposé au téléchargement.           |
| `delimiter` | string | `","`                | Séparateur CSV (format `csv` uniquement).           |
| `output`    | string | `"file"`             | Clé de contexte où stocker `{key, filename, path, url}`. |

Le fichier est servi par `GET /files/...` via l'`url` renvoyée **le temps du run**, puis
purgé automatiquement à la fin.

```json
"export": {
    "class": "DataViewFile",
    "config": {
        "input": "mails_clients",
        "format": "csv",
        "filename": "mails_clients.csv",
        "output": "fichier_csv"
    },
    "on_success": "envoi",
    "on_error": "exit(0)"
}
```

Puis, par exemple, joindre le fichier dans un `Mail` : `"attachments": ["{fichier_csv}"]`
(le nom `mails_clients.csv` est alors conservé pour le destinataire).

### 4.9 Blocs lecteurs de fichier : `TxtReader` / `CsvReader` / `ExcelReader`

Ces trois blocs lisent un fichier et déposent son contenu dans le contexte. Ils partagent le
paramètre **`source`**, qui accepte indifféremment :

| Forme de `source`                              | Cas d'usage                                                            |
|------------------------------------------------|----------------------------------------------------------------------|
| `"/chemin/sur/le/serveur/data.csv"`            | Fichier déjà présent sur le serveur. Interpolé (`"/data/{jour}/x.csv"`). |
| `"{ma_var}"` (jeton unique)                    | Une variable de contexte pointant vers un fichier produit dans le run : sortie d'un `DataViewFile` (`{key, filename, path, url}`), ou un élément de la liste `files` d'un bloc `Agent`. Si la variable est une liste, le premier élément est pris. |
| `"http://.../files/<key>/<nom>?t=..."` ou `"<key>"` (32 hexa) | Référence directe à un fichier du `FileStore` rattaché au run ou à la session. |
| `{ "path": "...", "filename": "..." }`         | Structure de fichier fournie telle quelle dans la config.             |

> Un fichier de run n'est lisible que **pendant** le run qui l'a produit (voir
> [§4.16](#416-fichiers-temporaires)).

#### `TxtReader`

Lit un fichier texte brut (`.txt`, `.md`, `.log`, …) et écrit son contenu.

| Paramètre  | Type       | Défaut     | Rôle                                                          |
|------------|------------|------------|-------------------------------------------------------------|
| `source`   | string/obj | —          | **Obligatoire.** Voir ci-dessus.                            |
| `encoding` | string     | `"utf-8"`  | Encodage de décodage.                                       |
| `errors`   | string     | `"strict"` | Politique de décodage : `"strict"`, `"replace"`, `"ignore"`. |
| `strip`    | bool       | `false`    | Retire les espaces / sauts de ligne de début et de fin.     |
| `as`       | string     | `"text"`   | `"text"` → chaîne ; `"lines"` → liste de lignes.            |
| `keepends` | bool       | `false`    | Conserve le `\n` en fin de ligne (`as: "lines"` uniquement). |
| `output`   | string     | `"result"` | Clé de contexte où stocker le résultat.                     |

```json
"lire_note": {
    "class": "TxtReader",
    "config": { "source": "/srv/exports/{trigger.data.ref}.md", "strip": true, "output": "note" },
    "on_success": "suite",
    "on_error": "exit(0)"
}
```

#### `CsvReader`

Lit un fichier CSV et écrit une table directement exploitable par un bloc `DataView`
(`list[dict]`, ou forme colonnaire).

| Paramètre     | Type       | Défaut     | Rôle                                                                    |
|---------------|------------|------------|----------------------------------------------------------------------|
| `source`      | string/obj | —          | **Obligatoire.** Voir ci-dessus.                                     |
| `encoding`    | string     | `"utf-8"`  | Encodage de décodage.                                                |
| `delimiter`   | string     | `","`      | Séparateur de colonnes ; `"auto"` → détection automatique.           |
| `quotechar`   | string     | `"\""`     | Caractère de citation.                                               |
| `has_header`  | bool       | `true`     | La première ligne porte les noms de colonnes.                        |
| `columns`     | array      | `[]`       | Noms de colonnes imposés. Avec `has_header`, la 1re ligne est alors sautée. Sans `has_header` ni `columns` → `col_1`, `col_2`, … |
| `skip_rows`   | int        | `0`        | Lignes ignorées en tête du fichier (avant l'en-tête).               |
| `skip_empty`  | bool       | `true`     | Ignore les lignes entièrement vides.                                 |
| `trim`        | bool       | `true`     | Retire les espaces de début / fin des cellules.                     |
| `infer_types` | bool       | `false`    | Convertit les cellules en `int` puis `float` si possible.           |
| `limit`       | int        | `0`        | Nombre maximum de lignes de données (`0` = pas de limite).          |
| `as`          | string     | `"list"`   | `"list"` → `list[dict]` ; `"dict"` → `{colonne: [valeurs]}`.        |
| `output`      | string     | `"result"` | Clé de contexte où stocker le résultat.                             |

```json
"charger_csv": {
    "class": "CsvReader",
    "config": { "source": "{fichier_csv}", "delimiter": ";", "infer_types": true, "output": "lignes" },
    "on_success": "filtrer",
    "on_error": "exit(0)"
}
```

#### `ExcelReader`

Lit un classeur Excel (`.xlsx` / `.xlsm` via `openpyxl`, `.xls` via `xlrd`) et écrit une table
exploitable par un bloc `DataView`. Les dates / heures des cellules sont normalisées en chaîne
ISO 8601.

| Paramètre    | Type            | Défaut     | Rôle                                                                     |
|--------------|-----------------|------------|----------------------------------------------------------------------|
| `source`     | string/obj      | —          | **Obligatoire.** Voir ci-dessus.                                     |
| `format`     | string          | *(auto)*   | `"xlsx"` / `"xlsm"` / `"xls"` ; sinon déduit de l'extension du nom, repli sur `"xlsx"`. |
| `sheet`      | string/int/array | `null`     | Feuille(s) : nom, index `0`-based, ou `"*"` / liste → le résultat est `{nom_feuille: table}`. `null` → 1re feuille. |
| `has_header` | bool            | `true`     | La première ligne porte les noms de colonnes.                        |
| `columns`    | array           | `[]`       | Noms de colonnes imposés (mêmes règles que `CsvReader`).             |
| `skip_rows`  | int             | `0`        | Lignes ignorées en tête de feuille (avant l'en-tête).              |
| `skip_empty` | bool            | `true`     | Ignore les lignes entièrement vides.                                 |
| `trim`       | bool            | `true`     | Retire les espaces de début / fin des cellules chaîne.              |
| `limit`      | int             | `0`        | Nombre maximum de lignes de données par feuille (`0` = pas de limite). |
| `as`         | string          | `"list"`   | `"list"` → `list[dict]` ; `"dict"` → `{colonne: [valeurs]}`.        |
| `output`     | string          | `"result"` | Clé de contexte où stocker le résultat.                             |

```json
"charger_xlsx": {
    "class": "ExcelReader",
    "config": { "source": "/srv/imports/ventes.xlsx", "sheet": "Janvier", "output": "ventes" },
    "on_success": "agreger",
    "on_error": "exit(0)"
}
```

### 4.10 Blocs de gestion de fichier : `FileDelete` / `FileMove` / `FileWriter` / `FileExists`

Ces blocs agissent sur le fichier lui-même (et non sur son contenu). Ils acceptent le même
paramètre `source` que les blocs lecteurs ([§4.9](#49-blocs-lecteurs-de-fichier--txtreader--csvreader--excelreader)) :
chemin serveur, `"{var}"` (dict / liste de fichier de pipeline), URL `"/files/..."`, ou clé
`FileStore`.

#### `FileDelete`

Supprime un ou plusieurs fichiers. Un fichier du run est retiré du `FileStore` (suppression du
fichier temporaire) ; un fichier du serveur est supprimé du disque.

| Paramètre    | Type            | Défaut     | Rôle                                                                    |
|--------------|-----------------|------------|----------------------------------------------------------------------|
| `source`     | string/obj/array | —          | **Obligatoire.** Fichier(s) à supprimer. Une entrée `"{var}"` pointant vers une liste (ex. `"{files}"` d'un bloc `Agent`) supprime tous ses fichiers. |
| `missing_ok` | bool            | `true`     | Ne pas faire échouer le bloc si un fichier est déjà absent.           |
| `output`     | string          | `"result"` | Clé de contexte → `{"deleted": [noms…], "missing": [noms…]}`.         |

```json
"nettoyer": {
    "class": "FileDelete",
    "config": { "source": "{fichier_temp}" },
    "on_success": "exit(1)",
    "on_error": "exit(0)"
}
```

#### `FileMove`

Déplace (ou renomme) un ou plusieurs fichiers vers un emplacement du serveur. **Déplacer un fichier
produit pendant le run vers un chemin durable est le moyen de le conserver au-delà de la fin du
run** (le stockage temporaire est purgé — voir [§4.16](#416-fichiers-temporaires)).

| Paramètre     | Type            | Défaut     | Rôle                                                                     |
|---------------|-----------------|------------|----------------------------------------------------------------------|
| `source`      | string/obj/array | —          | **Obligatoire.** Fichier(s) à déplacer.                              |
| `destination` | string          | —          | **Obligatoire.** Chemin cible. Dossier existant ou terminé par `/` → le fichier y est déplacé sous son nom d'origine ; sinon chemin complet (renommage, une seule source). Plusieurs sources → `destination` doit être un dossier. |
| `overwrite`   | bool            | `false`    | Autorise l'écrasement d'un fichier cible existant.                   |
| `create_dirs` | bool            | `true`     | Crée les dossiers parents manquants.                                 |
| `output`      | string          | `"result"` | Clé de contexte → `{"path", "filename"}` (ou une liste si plusieurs sources). |

```json
"archiver": {
    "class": "FileMove",
    "config": { "source": "{rapport_csv}", "destination": "/srv/archives/{trigger.data.jour}/", "output": "archive" },
    "on_success": "exit(1)",
    "on_error": "exit(0)"
}
```

#### `FileWriter`

Écrit sur le disque du serveur une **copie** d'un ou plusieurs fichiers du stockage temporaire
(fichiers générés pendant le run : sortie d'un bloc `DataViewFile` / `Agent`, URL `"/files/..."`,
clé `FileStore`). Contrairement à `FileMove`, le fichier temporaire est conservé : son URL de
téléchargement reste utilisable par les blocs suivants (ex. pièce jointe d'un `Mail`) jusqu'à la
fin du run. Une `source` désignant un chemin serveur est refusée (utiliser `FileMove`).

| Paramètre     | Type            | Défaut     | Rôle                                                                     |
|---------------|-----------------|------------|----------------------------------------------------------------------|
| `source`      | string/obj/array | —          | **Obligatoire.** Fichier(s) temporaire(s) à écrire.                  |
| `destination` | string          | —          | **Obligatoire.** Chemin cible. Dossier existant ou terminé par `/` → le fichier y est écrit sous son nom d'origine ; sinon chemin complet (renommage, une seule source). Plusieurs sources → `destination` doit être un dossier. |
| `overwrite`   | bool            | `false`    | Autorise l'écrasement d'un fichier cible existant.                   |
| `create_dirs` | bool            | `true`     | Crée les dossiers parents manquants.                                 |
| `output`      | string          | `"result"` | Clé de contexte → `{"path", "filename", "size"}` (ou une liste si plusieurs sources). |

```json
"sauvegarder": {
    "class": "FileWriter",
    "config": { "source": "{rapport_csv}", "destination": "/srv/exports/{trigger.data.jour}/", "output": "export" },
    "on_success": "envoyer_mail",
    "on_error": "exit(0)"
}
```

#### `FileExists`

Teste la présence d'un fichier. Par défaut le bloc **échoue** quand le fichier est absent : on
branche alors le pipeline via `on_success` (présent) / `on_error` (absent).

| Paramètre         | Type       | Défaut     | Rôle                                                                    |
|-------------------|------------|------------|----------------------------------------------------------------------|
| `source`          | string/obj | —          | **Obligatoire.** Fichier à tester. Une entrée `"{var}"` pointant vers une liste teste le 1er élément. |
| `fail_on_missing` | bool       | `true`     | `true` → le bloc échoue si le fichier est absent (branchement immédiat via `on_error`) ; `false` → le bloc réussit toujours, le test se lit dans `{<output>.exists}`. |
| `output`          | string     | `"result"` | Clé de contexte → `{"exists": bool, "path", "filename", "size": int\|null}`. |

Une `source` structurellement invalide (variable de contexte absente, dict mal formé, source vide)
fait toujours échouer le bloc, quel que soit `fail_on_missing`.

```json
"verifier": {
    "class": "FileExists",
    "config": { "source": "/srv/imports/{trigger.data.ref}.xlsx" },
    "on_success": "traiter",
    "on_error": "notifier_absence"
}
```

### 4.11 `Condition`

Évalue une **expression booléenne** portant sur des variables de contexte et branche le pipeline
selon le résultat : `on_success` si l'expression est vraie, `on_error` si elle est fausse. Le
booléen est aussi écrit dans le contexte (`output`) pour être réutilisé plus loin (ex. dans un
`{% if %}`).

> L'expression n'est **pas** interpolée. On y référence une variable par son **chemin nu**
> (`trigger.data.role`) ou entre accolades (`{trigger.data.role}`), et les **chaînes littérales
> sont entre guillemets**. C'est le même langage que le `{% if %}` des templates, étendu à `AND` /
> `OR` / `NOT` et aux parenthèses.

**Opérateurs**

| Catégorie   | Opérateurs                                             |
|-------------|-------------------------------------------------------|
| Comparaison | `=` `==` &nbsp; `!=` `<>` &nbsp; `<` `>` `<=` `>=` &nbsp; `IN` &nbsp; `NOT IN` |
| Logique     | `AND` &nbsp; `OR` &nbsp; `NOT` &nbsp; + groupements `( … )` |

Priorité (de la plus faible à la plus forte) : `OR` < `AND` < `NOT` < comparaison. Les mots-clés
sont insensibles à la casse.

**Opérandes** : `"chaîne"` / `'chaîne'`, nombre (`42`, `-3.5`), `true` / `false`, `none` / `null`,
liste `["a", "b", 3]` (pour `IN` / `NOT IN`), ou un chemin de variable de contexte (indexation de
liste supportée : `mails[0].subject`). Un opérande seul est évalué par sa valeur de vérité Python
(chaîne non vide = vrai) : préférez une comparaison explicite pour tester un drapeau textuel.

| Paramètre         | Type   | Défaut     | Rôle                                                                       |
|-------------------|--------|------------|-------------------------------------------------------------------------|
| `expression`      | string | —          | **Obligatoire.** L'expression à évaluer.                                |
| `missing_as_null` | bool   | `false`    | `true` → une variable de contexte absente vaut `none` ; `false` → une variable absente fait échouer le bloc. |
| `fail_on_false`   | bool   | `true`     | `true` → le bloc échoue quand l'expression est fausse (branchement via `on_error`) ; `false` → le bloc réussit toujours, le résultat se lit dans `{<output>}`. |
| `output`          | string | `"result"` | Clé de contexte où stocker le booléen résultat.                         |

Détails d'évaluation : les comparaisons d'ordre (`<` `>` `<=` `>=`) renvoient **faux** si un membre
vaut `none` (pas d'erreur), et comparent en nombre lorsque les deux membres sont numériques (nombre
ou chaîne numérique) — pratique pour les données de `trigger.data`, souvent des chaînes. `IN` /
`NOT IN` font un test d'appartenance direct, sensible à la casse.

```json
"aiguillage": {
    "class": "Condition",
    "config": {
        "expression": "trigger.data.age >= 18 AND (trigger.data.role == 'admin' OR trigger.data.statut IN ['actif', 'essai'])"
    },
    "on_success": "traitement_complet",
    "on_error": "traitement_restreint"
}
```

### 4.11 bis `Loop`

Parcourt une liste du contexte (typiquement la sortie d'un `DataView` en `as: "list"`, ou
d'un `CsvReader`) ligne par ligne. À chaque passage, le bloc écrit la ligne courante et son
index dans le contexte, puis sort par `on_success` : c'est le **corps de boucle**, dont le
dernier bloc doit **reboucler vers ce même bloc `Loop`**. Une fois toutes les lignes
parcourues, le bloc sort par `on_error` : c'est la **sortie normale de fin de boucle**, pas
une erreur d'exécution.

| Paramètre | Type   | Défaut    | Rôle                                                                   |
|-----------|--------|-----------|----------------------------------------------------------------------|
| `input`   | string | —         | **Obligatoire.** Clé de contexte contenant la liste à parcourir.      |
| `item`    | string | `"item"`  | Clé de contexte recevant la ligne courante.                           |
| `index`   | string | `"index"` | Clé de contexte recevant l'index courant (à partir de `0`).           |

* L'avancement est stocké dans le contexte du run (pas sur le bloc) : plusieurs runs
  simultanés du même pipeline ne se perturbent pas.
* En fin de boucle, l'avancement est remis à zéro : le même bloc `Loop` peut être rejoué
  plus loin dans le run.
* Échoue aussi (donc sort par `on_error`) si `input` est absent ou ne désigne pas une liste :
  consultez les logs de l'étape pour distinguer ce cas d'une fin de boucle normale.
* Chaque itération est un appel récursif : réservez `Loop` à des listes de taille raisonnable.

```json
"boucle": {
    "class": "Loop",
    "config": { "input": "clients", "item": "client" },
    "on_success": "notifier_client",
    "on_error": "exit(1)"
},
"notifier_client": {
    "class": "Webex",
    "config": {
        "profile": "default",
        "to_person_email": "{client.email}",
        "message": "Bonjour {client.nom}, votre rapport est disponible."
    },
    "on_success": "boucle",
    "on_error": "boucle"
}
```

### 4.12 `Sleep`

Met le run en pause pendant `seconds` secondes, puis passe au bloc `on_success`. Chaque run
s'exécute dans son propre thread : la pause ne bloque ni le serveur ni les autres runs.

| Paramètre | Type                    | Défaut | Rôle                                                                          |
|-----------|-------------------------|--------|-----------------------------------------------------------------------------|
| `seconds` | number \| string        | `0`    | Durée de la pause en secondes (décimales acceptées). Une chaîne est convertie, ce qui permet une durée issue du contexte. |

Échoue si la durée n'est pas un nombre fini positif ou nul.

```json
"attente": {
    "class": "Sleep",
    "config": {
        "seconds": "{trigger.data.delai}"
    },
    "on_success": "relance"
}
```

### 4.13 `MicroRag`

Équivalent pipeline des fichiers joints à une conversation websocket : prépare un ou
plusieurs fichiers pour qu'un bloc `Agent` puisse raisonner dessus. Le texte est extrait dans
ce bloc (page par page pour un PDF). Le découpage en chunks et le calcul des embeddings n'ont
lieu que si un bloc `Agent` en a besoin (mode `rag`, ou `auto` sur un contenu trop long), et
**une seule fois** : les blocs `Agent` suivants réutilisent le résultat.
Rien n'est écrit en base vectorielle : tout reste dans le contexte du run.

| Paramètre            | Type                   | Défaut        | Rôle                                                                    |
|----------------------|------------------------|---------------|-----------------------------------------------------------------------|
| `source`             | string \| object \| array | —      | **Obligatoire.** Fichier(s) à intégrer, même syntaxe que `TxtReader` (chemin serveur, `"{var}"`, URL `/files/...`, clé FileStore). Une liste, ou un `"{var}"` qui pointe vers une liste, intègre tous les fichiers. |
| `allowed_extensions` | array                  | formats des pièces jointes (`.pdf`, `.docx`, `.xlsx`, `.pptx`, `.md`, `.txt`, `.csv`, `.html`…) | Extensions acceptées. |
| `max_file_size_mb`   | int                    | `20`          | Taille maximale d'un fichier.                                          |
| `append`             | bool                   | `false`       | Ajoute les fichiers à ceux déjà présents sous `output` au lieu de les remplacer (enchaînement de plusieurs blocs `MicroRag`). |
| `output`             | string                 | `"micro_rag"` | Clé de contexte où stocker les fichiers préparés.                      |

Échoue si un fichier est introuvable, vide, trop volumineux, d'une extension non autorisée
ou si l'extraction du texte échoue.

Côté bloc `Agent`, la clé `micro_rag` joint ces fichiers à la réflexion. Leur contenu est
placé en tête du prompt avant l'appel au LLM, selon `micro_rag_mode` :

* **`full`** : le texte complet de tous les fichiers (page par page, avec numéro, pour un PDF).
  Indispensable pour les demandes qui portent sur **tout** le document : lister les
  articles, résumer, comparer, vérifier une absence…
* **`rag`** : une recherche par similarité est lancée sur `micro_rag_query` (à défaut sur
  le `prompt`), et seuls les `micro_rag_top_k` extraits les plus pertinents sont envoyés.
  Adapté aux documents volumineux et aux questions ciblées (« que dit le contrat sur X ? »),
  mais le LLM ne voit pas le reste du document.
* **`auto`** (défaut) : `full` si le total estimé des fichiers tient dans
  `micro_rag_max_tokens`, `rag` sinon.

Si le profil autorise l'outil `files.search_attached_files`, l'agent peut aussi lancer
d'autres recherches dans ces fichiers pendant sa réflexion.

> La valeur de `micro_rag` doit être une référence **seule** (`"{docs}"`), pas un texte
> contenant une variable : la structure préparée est transmise telle quelle au bloc `Agent`.

```json
"prepare_docs": {
    "class": "MicroRag",
    "config": {
        "source": "{trigger.data.contrat}",
        "output": "docs"
    },
    "on_success": "analyse",
    "on_error": "exit(0)"
},
"analyse": {
    "class": "Agent",
    "config": {
        "profile": "agent-base",
        "prompt": "Liste les clauses de résiliation du contrat joint et leurs délais de préavis.",
        "micro_rag": "{docs}",
        "micro_rag_mode": "auto",
        "micro_rag_query": "résiliation, préavis, durée du contrat",
        "micro_rag_top_k": 10,
        "output": "analyse"
    },
    "on_success": "exit(1)",
    "on_error": "exit(0)"
}
```

### 4.14 `PythonScript`

Exécute un script Python placé dans le **dossier du pipeline**, à côté de `pipeline.json` :

```
config/pipelines/mon_pipeline/
├── pipeline.json
└── scripts/
    └── calcul.py
```

Le script définit une fonction (par défaut `run`) appelée avec deux arguments :

* `context` — le contexte du run (`PipelineContext`), en lecture **et** en écriture :
  * `context.get("cle")` : valeur d'une clé de premier niveau (une chaîne est interpolée) ;
  * `context.resolve("a.b[0].c")` : valeur typée d'un chemin, sans conversion en chaîne ;
  * `context.set("cle", valeur)` : crée ou remplace une variable ;
  * `context.merge({...})` : fusionne plusieurs variables (chaînes interpolées au passage) ;
  * `context.transform("Bonjour {nom}")` : interpole un template.
* `params` — le dict `params` de la config du bloc, déjà interpolé avec le contexte.

La fonction réussit par défaut : le bloc échoue uniquement si elle renvoie `False` ou lève
une exception (le message est alors journalisé dans les logs du bloc).

| Paramètre  | Type   | Défaut  | Rôle                                                                     |
|------------|--------|---------|------------------------------------------------------------------------|
| `script`   | string | —       | **Obligatoire.** Chemin du script, relatif au dossier du pipeline. Doit finir par `.py` et rester dans ce dossier. **Non interpolé** : une donnée du contexte ne peut pas choisir le code exécuté. |
| `function` | string | `"run"` | Fonction du script à appeler.                                           |
| `params`   | object | `{}`    | Paramètres transmis à la fonction (interpolés).                          |

* Le script est rechargé à **chaque exécution** : une modification est prise en compte sans
  redémarrage (contrairement à `pipeline.json`).
* Il s'exécute **sans bac à sable**, avec les droits du serveur (il peut importer `lib.*`,
  accéder au réseau, au disque…). Il a le même niveau de confiance que `pipeline.json`.
* Pour journaliser, utiliser `Logger.write(...)` (`from lib.log.logger import Logger`) :
  contrairement à `print`, ses messages sont rattachés aux logs du bloc.

```python
# config/pipelines/mon_pipeline/scripts/calcul.py
def run(context, params):
    lignes = context.resolve("commandes")
    total = sum(l["montant"] for l in lignes if l["pays"] == params["pays"])
    if total == 0:
        return False            # -> on_error
    context.set("total", total * params["taux"])
```

```json
"calcul": {
    "class": "PythonScript",
    "config": {
        "script": "scripts/calcul.py",
        "params": {
            "pays": "{trigger.data.pays}",
            "taux": 1.2
        }
    },
    "on_success": "envoi",
    "on_error": "exit(0)"
}
```

### 4.15 `ServiceMethod`

Appelle une méthode d'un **service** déclaré dans la clé `services` de la configuration
(ex : le service `nexora` de handler `LumePackAPI`). Même convention que `PythonScript` : la
méthode reçoit `context` (lecture et écriture) et `params` (le dict `params` de la config du
bloc, interpolé), et doit donc avoir la signature :

```python
# lib/services/lumepackapi.py
class LumePackAPI(Service):
    def test(self, context, params):
        context.set("test", "OUI")
```

La méthode réussit par défaut : le bloc échoue uniquement si elle renvoie `False` ou lève une
exception. Pour appeler l'API de manière authentifiée, elle utilise `self.getAuth()` (secret du
wallet du run, obtenu via la clé `services` du pipeline — [§1.7](#17-authentification-aux-services--services)) :
le service est une instance partagée, il ne doit porter aucun état propre au run.

| Paramètre | Type   | Défaut | Rôle                                                                                   |
|-----------|--------|--------|--------------------------------------------------------------------------------------|
| `service` | string | —      | **Obligatoire.** Nom du service (clé dans `services`, pas le `handler`). **Non interpolé.** |
| `method`  | string | —      | **Obligatoire.** Méthode publique à appeler (les noms commençant par `_` sont refusés). **Non interpolé.** |
| `params`  | object | `{}`   | Paramètres transmis à la méthode (interpolés).                                        |

```json
"test_nexora": {
    "class": "ServiceMethod",
    "config": {
        "service": "nexora",
        "method": "test",
        "params": {
            "id": "{trigger.data.id}"
        }
    },
    "on_success": "suite",
    "on_error": "exit(1)"
}
```

### 4.16 Fichiers temporaires

* Tout fichier écrit via `FileStore` pendant un run (bloc `DataViewFile`, ou outil MCP
  appelé pendant un bloc `Agent`) est **rattaché au run** (`process_uid`).
* Il est accessible via `GET /files/{key}/{filename}?t=<token du run>` **pendant** le run.
* En fin de run (quelle que soit l'issue), l'ensemble de ces fichiers est **purgé**.
* Pour transmettre un fichier à l'extérieur de façon durable, il faut donc l'envoyer
  pendant le run (email, upload vers une API…).

---

## 5. Déclencher et suivre un pipeline

Toutes les routes ci-dessous sont authentifiées en **Basic (admin)**.

### 5.1 Démarrer un pipeline

```
POST /pipeline/{pipeline_uid}/start
Content-Type: application/json

{ "payload": { "client_id": 42, "jour": "2026-09-09" } }
```

* Le corps est **optionnel**. `payload` (objet) est déposé dans le contexte sous
  `trigger.data`.
* Le pipeline ne démarre que si l'un de ses triggers accepte l'événement (pour `Api`,
  toujours).
* `400` si aucun dossier `<custom_pipelines>/{pipeline_uid}/pipeline.json` n'existe.
* Le lancement est asynchrone : la réponse est renvoyée dès la création du run.

Réponse :

```json
{ "pipelines": [ { "pipeline_uid": "mon_pipeline", "process_uid": "..." } ] }
```

### 5.2 Suivre un run

```
GET /pipeline/process/{process_uid}
```

Renvoie `{ pipeline_uid, process_uid, created_at, started_at, ended_at, is_ended,
is_success, steps[] }`. Chaque `step` : `{ id, name, created_at, is_success }` (sans les
logs).

### 5.3 Détail d'une étape (avec logs)

```
GET /pipeline/process/{process_uid}/{id}
```

Renvoie `{ id, process_uid, pipeline_uid, name, created_at, is_success, logs }`.

---

## 6. Exemple complet commenté

Pipeline `recap_mail` : lit les 20 derniers emails d'une boîte, demande à un agent un
récapitulatif, puis envoie ce récapitulatif par email.

`config/pipelines/recap_mail/pipeline.json` :

```json
{
    "name": "Recap mail",
    "services": {
        "nexora": { "token": "<jeton de service>" }
    },
    "trigger": [
        { "class": "Api", "config": { } }
    ],
    "blocks": {
        "_root": {
            "class": "Mail",
            "config": {
                "action": "list",
                "limit": 20,
                "imap_host": "imap.example.fr",
                "imap_port": 993,
                "imap_use_ssl": true,
                "username": "demo@example.fr",
                "password": "...",
                "output": "mails"
            },
            "on_success": "analyse",
            "on_error": "exit(0)"
        },
        "analyse": {
            "class": "Agent",
            "config": {
                "profile": "agent-base",
                "prompt": "Fais un récapitulatif de ces mails, uniquement ceux du jour, en indiquant les plus importants et ceux qui demandent une action de ma part : {mails}",
                "output": "analyse"
            },
            "on_success": "send_mail",
            "on_error": "exit(0)"
        },
        "send_mail": {
            "class": "Mail",
            "config": {
                "smtp_host": "smtp.example.fr",
                "smtp_port": 587,
                "smtp_use_ssl": false,
                "smtp_use_tls": true,
                "username": "demo@example.fr",
                "password": "...",
                "to": "moi@example.fr",
                "subject": "Analyse de vos mails",
                "body": "{analyse}"
            },
            "on_success": "exit(1)",
            "on_error": "exit(0)"
        }
    }
}
```

Déroulé :

0. Au démarrage du run, le service `nexora` est authentifié avec le jeton déclaré sous
   `services` ; les outils MCP appelés par l'agent l'utiliseront.
1. **`_root`** (`Mail` / `list`) écrit la liste des emails sous `mails`.
   Sur échec → `exit(0)` (fin en échec).
2. **`analyse`** (`Agent`) interpole `{mails}` dans le prompt, appelle le LLM, écrit la
   réponse sous `analyse`.
3. **`send_mail`** (`Mail` / `send`) envoie un email dont le corps est `{analyse}`.
   Sur succès → `exit(1)` (fin en succès).

Déclenchement :

```
POST /pipeline/recap_mail/start
```

Puis suivi via `GET /pipeline/process/{process_uid}` avec le `process_uid` renvoyé.
