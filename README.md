![alt text](https://raw.githubusercontent.com/gerard-loic/lumi/refs/heads/master/public/lumi-abyss.jpg?raw=true)

# Lumi

Lumi version 1.6.0 (Abyss — beta)

Lumi is an open-source AI chatbot backend built on top of **FastAPI** and the **Model Context Protocol (MCP)**. It exposes a WebSocket chat API that connects a Large Language Model to a set of custom tools and a **RAG knowledge base**, enabling the agent to answer questions grounded in real data rather than hallucinated knowledge.

## Features

- **WebSocket chat endpoint** — answers are streamed token by token over a persistent WebSocket connection. The client receives typed JSON events (`token`, `tool_call`, `rag`, `file`, `followup`, `end`, …).
- **MCP tool integration** — tools are registered as MCP tools, optionally grouped into subfolders. The agent calls them automatically when it needs real data to answer a question.
- **RAG (Retrieval-Augmented Generation)** — a built-in knowledge base lets the agent search indexed documents before answering. The agent triggers searches automatically via the `search_knowledge_base` MCP tool.
- **Document generation** — native tools for generating PDF, Word, and Excel files, including embedded charts (bar, pie, line). Word documents follow a customizable company **template (gabarit)**, with a cover page, header/footer, auto-generated table of contents, and table styles.
- **Follow-up suggestions** — after each reply, the agent can propose short follow-up questions to help guide the conversation.
- **Configurable LLM backend** — pick a connector per profile: `LiteLLM` (any LiteLLM-compatible model: OpenAI, Azure, local models, etc.), or the OpenAI-compatible `Cerebras`, `DigitalOcean`, and `Llama` connectors — see [`profiles.<name>.llm`](#profilesnamellm).
- **Pipelines** — declarative, JSON-defined workflows chaining blocks (LLM agent, HTTP calls, mail, Webex, file reading/writing, data transformation, conditions, loops, Python scripts…) that share a common context, started and monitored through the HTTP API — see [Pipelines](#pipelines) and the dedicated guide [README-PIPELINES.md](README-PIPELINES.md).
- **External MCP servers** — remote MCP servers (HTTP or SSE) can be plugged in as services, their tools being exposed to the agent alongside the built-in ones — see [External MCP servers](#external-mcp-servers).
- **Configuration profiles** — a single Lumi instance can serve several independent agents (different LLM model, tools, attachment policy, RAG collection, connectors) side by side, selected per session via [profiles](#profiles).
- **Multilingual conversations** — each profile declares which languages it supports; a session picks one at authentication time, and the agent's system prompt, tool descriptions, confirmation prompts, and error messages are all translated accordingly — see [Localization](#localization).
- **Session info endpoint** — `GET /auth` returns the calling session's profile-derived configuration (follow-up questions, language, attachment policy) so a client can adapt its UI without hardcoding per-profile behavior — see [HTTP API](#http-api).
- **File attachments** — users can attach files to a conversation; the agent reasons over their content through an ephemeral, per-session RAG index — see [File attachments](#file-attachments).
- **Source citations** — replies built from the knowledge base or from attached files come with `rag` events pointing back to the originating document, page, and (for the persistent RAG) a secure download URL.
- **Authentication** — a JWT-based `/auth` endpoint protects the chat API and temporary file downloads. A session can authenticate to several services at once; the resulting secrets are kept in a per-session **wallet** that tools and services read from. Admin endpoints use HTTP Basic Auth.
- **Temporary file serving** — tools can produce files that are made available for download through a secure, time-limited URL.
- **Webex connector** — the agent can be deployed as a Webex bot, receiving and answering messages from Webex spaces via webhooks.
- **Scheduled CRON tasks** — a built-in scheduler runs background maintenance tasks (log retention/shredding, RAG folder indexing) on a configurable minute/hour schedule.
- **Usage statistics** — a `/usage` endpoint returns token and request consumption for the current month.
- **Docker-friendly layout** — everything deployment-specific (config, custom tools/services, prompts, templates, secrets) lives under `config/`, and everything Lumi writes at runtime (temp files, logs, local DB, RAG storage) lives under `storage/`. The rest of the tree is the application itself, so a container image only needs those two directories mounted as volumes — see [`config/` directory layout](#config-directory-layout).
- **Validated configuration** — `config/config.json` and every `pipeline.json` are checked against a JSON Schema at startup (`lib/_references/`), so a typo or misplaced key fails fast with an explicit error.
- **Extensible by design** — add custom tools, services, LLM filters, and CRON tasks by dropping files into their respective directories, without touching the built-in `lib/` code. Which MCP tools are exposed is finely controlled via `mcp.tools_enabled` (exact names, whole-group wildcards, or single-tool overrides).

## What's new in v1.6.0 — Abyss

Lumi 1.6.x (Abyss) is a major release built around a brand-new **pipeline engine**, along with new LLM providers, a reworked authentication model, and a hardened configuration and security layer.

### Pipeline engine

- **Pipeline management** — declarative workflows defined in JSON (`config/pipelines/<pipeline_uid>/pipeline.json`), chaining blocks that share a common templated context. See [Pipelines](#pipelines) and the dedicated guide [README-PIPELINES.md](README-PIPELINES.md).
- **API trigger** — pipelines are started through the HTTP API (`POST /pipeline/{pipeline_uid}/start`).
- **Pipeline monitoring API** — each run can be tracked step by step (status and logs) via `GET /pipeline/process/...`.
- **25 built-in blocks** to build pipelines:

| Category | Blocks |
|----------|--------|
| API operations (GET, POST, PUT, DELETE) | `ApiGet`, `ApiPost`, `ApiPut`, `ApiDelete` |
| LLM agent | `Agent` |
| Conditions | `Condition` |
| Processing loops | `Loop` |
| File management (read, write, move, delete, existence check) | `FileWriter`, `FileMove`, `FileDelete`, `FileExists` |
| Data tables | `DataView`, `DataViewFile` |
| Excel, TXT and CSV files | `ExcelReader`, `TxtReader`, `CsvReader` |
| Format checking | `JsonFormat`, `XmlFormat` |
| Sending / reading e-mails | `Mail` |
| Lightweight RAG | `MicroRag` |
| Python script execution | `PythonScript` |
| Service method execution | `ServiceMethod` |
| Webex notifications | `Webex` |
| Utilities | `Context`, `Sleep` |

### LLM & embedding

- **New LLM connectors** — `Llama`, `DigitalOcean`, and `Cerebras` (OpenAI-compatible APIs) join `LiteLLM` — see [`profiles.<name>.llm`](#profilesnamellm).
- **Reworked embedding providers** — the embedder is now chosen per RAG collection (`LiteLLMEmbedder`, `DigitalOceanEmbedder`, `LlamaEmbedder`).

### Authentication wallet

- **Authentication wallet** — `POST /auth` now takes one authorization payload per service (`{"<service>": {...}}`); the secrets returned by each service are stored in the session's wallet and read by services through `Service.getAuth()`. Pipelines declare their own service credentials the same way. Services implement `authenticate()` (replacing `checkAuthentication()`).

### Configuration & security

- **Configuration validation at startup** — `config.json` and every `pipeline.json` are checked against JSON Schemas (`lib/_references/config.schema.json`, `lib/_references/pipeline.schema.json`); the server refuses to start on an invalid file, with an explicit error.
- **Security fixes** — new [`security`](#security) section (sandbox process cap, minimum JWT secret length, auth rate-limiter window and tracking bound, multipart overhead), together with several security hardening fixes. `extraction.max_concurrent` moved to `security.sandbox_max_process`.

### Other changes

- **External MCP servers** — the `MCPExternalService` handler connects remote MCP servers (HTTP/SSE), with either a static connection shared by all sessions or a per-session connection using the user's token — see [External MCP servers](#external-mcp-servers).
- **Refactored base classes** — every extensible type now has its abstract base in a `_abstract.py` module next to its implementations (`lib/services/_abstract.py`, `lib/cron/tasks/_abstract.py`, `lib/agent/filters/_abstract.py`, `lib/connectors/_abstract.py`, `lib/pipelines/_abstract.py`, …), and managers live in their own modules (`lib/services/servicemanager.py`, `lib/connectors/connectormanager.py`).

## Getting started

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and edit the config
cp config/config.default.json config/config.json
# → set your LLM credentials, database connection, JWT secret, etc.

# 3. Start the service
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

The interactive API docs are available at `http://localhost:8001/docs`.

Everything Lumi reads or writes outside its own code lives under two directories, both entirely excluded from version control (`.gitignore`) except for a tracked `config/config.default.json` template:

- **`config/`** — deployment configuration and any deployment-specific code/assets: `config.json`, system prompt file(s), custom MCP tools, custom services, custom language overrides, Word template, RAG source documents, etc. See [`config/` directory layout](#config-directory-layout) for the full list.
- **`storage/`** — everything Lumi produces at runtime: temporary files, logs, the local SQLite database, and retained RAG source files. Ships with empty, git-ignored `temp/`, `data/`, `logs/`, and `rag/` subfolders (kept via `.gitkeep`).

This split is what makes the service easy to containerize: the application image itself is stateless, and a deployment only needs to mount `config/` (read-only) and `storage/` (read-write) as volumes.

---

## `config/` directory layout

`config/` is the only directory a deployment needs to populate. It's entirely git-ignored except for the tracked `config.default.json` template (copy it to `config.json` — see [Getting started](#getting-started)). Depending on which features are enabled, it can contain:

| Path | Required | Purpose |
|------|----------|---------|
| `config.json` | Yes | The active configuration file (see [Configuration reference](#configuration-reference) below). |
| `systemprompt.md` (or whatever `llm.system_prompt_file` points to) | Yes per profile, unless `llm.system_prompt` is set inline instead | Agent system prompt(s) — see [`profiles.<name>.llm`](#profilesnamellm). |
| `languages/<code>/*.json` | No | Custom/override translation files — see [Localization](#localization). Path configurable via [`directories.custom_languages_dir`](#directories). |
| `services/*.py` | No | Custom service handler classes not shipped in `lib/services/` — see [Adding services](#adding-services). Path configurable via [`directories.custom_services_dir`](#directories). |
| `tools/**/*.py` | No | Custom MCP tools not shipped in `lib/mcp/tools/` — see [Adding tools](#adding-tools). Path configurable via [`directories.custom_mcp_tools_dir`](#directories). May itself contain further subfolders (e.g. `models/`) for shared code imported by those tools. |
| `pipelines/<pipeline_uid>/pipeline.json` | No | Pipeline definitions (plus any script used by a `PythonScript` block) — see [Pipelines](#pipelines). Path configurable via [`directories.custom_pipelines`](#directories). |
| `templates/*.docx` | No | Word template(s) (gabarit) referenced by [`word.template`](#word) — see [Word document templates](#word-document-templates-gabarits). |
| any folder referenced by a `Ragindexer` CRON task's `config.folders` (e.g. `source-rag/`) | No | Source documents to automatically (re)index into the RAG knowledge base — see [`cron`](#cron). The folder name/location is an arbitrary config value, not a fixed convention. |

Other than `config.json` itself — loaded directly by `Config.init()` — none of these paths are hardcoded: each is a configuration value with the default shown above, so a deployment is free to relocate them as long as the config is updated to match. Runtime data (temp files, logs, local DB, RAG storage), by contrast, lives entirely under `storage/` — see [`directories`](#directories).

---

## Configuration reference

Lumi is configured through a single JSON file: `config/config.json`. The `config/config.default.json` file serves as a template.

The file is validated at startup against the JSON Schema `lib/_references/config.schema.json`: unknown keys are rejected (`additionalProperties: false`), and the service refuses to start if the file doesn't match. A free-form top-level `custom` object is allowed for deployment-specific settings that Lumi itself doesn't read (e.g. front-end parameters).

### `app`

General application settings.

| Key | Type | Description |
|-----|------|-------------|
| `name` | string | Display name of the service. |
| `description` | string | Short description of the service. |
| `url` | string | Public URL of the service (used to register Webex webhooks, etc.). |
| `allowed_cors_ips` | array | Allowed CORS origins (use `["*"]` to allow all). |
| `allowed_cors_methods` | array | Allowed CORS methods. |
| `allowed_cors_headers` | array | Allowed CORS headers. |
| `ws_inactivity_timeout` | int | WebSocket inactivity timeout in seconds (default: 300). |
| `max_request_body_mb` | number | Maximum HTTP request body size in MB (default: 100), answered with `413` beyond. `POST /files/upload` is instead capped at the largest `attachments.max_file_size_mb` of the profiles. |
| `admin_users` | array | List of `{ username, password }` objects for HTTP Basic Auth on admin endpoints. |
| `default_language` | string | Language code used when `POST /auth` doesn't specify one — see [Localization](#localization). |

### `authentication`

Controls how users authenticate to obtain a WebSocket token.

| Key | Type | Description |
|-----|------|-------------|
| `service` | string | Name of the main authentication service (must match a key in `services`). Authenticating to it is mandatory for every `POST /auth` — see [HTTP API → Authentication](#authentication-1). |
| `jwt_secret` | string | Secret used to sign and verify JWT tokens. |
| `jwt_algorithm` | string | JWT signing algorithm (e.g. `HS256`). |
| `session_duration` | int | Session validity duration in seconds. |
| `max_auth_requests_minute` | int | Maximum `POST /auth` requests per client IP per minute (default `10`, `-1` to disable). Answers `429` beyond. Behind a reverse proxy, start uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy IP>` so the real client IP is used. |

### `services`

Declares external services available to the tools. Each key is the logical name of the service; each value contains a `handler` field pointing to the Python class that implements the service, plus the class-specific configuration.

```json
"services": {
  "myservice": {
    "handler": "LumePackAPI",
    "url": "https://api.example.com",
    "timeout": 60
  },
  "bdd": {
    "handler": "PostgreSQL",
    "host": "localhost",
    "port": 5432,
    "database": "dbname",
    "username": "",
    "password": ""
  },
  "my_mcp_server": {
    "handler": "MCPExternalService",
    "transport": "http",
    "url": "https://mcp.example.com/mcp",
    "headers": { "Authorization": "Bearer <token>" }
  }
}
```

Built-in handlers: `LumePackAPI` (HTTP API client), `PostgreSQL` (database, also used by the pgvector RAG store and pipeline logs), and `MCPExternalService` (remote MCP server — see [External MCP servers](#external-mcp-servers)).

Built-in handlers live in `lib/services/`. Deployment-specific handlers go in `directories.custom_services_dir` (default `config/services`) instead, without touching `lib/`. See [Adding services](#adding-services) to create custom ones.

### `logger`

| Key | Type | Description |
|-----|------|-------------|
| `output.enabled` | bool | Print logs to stdout. |
| `file.enabled` | bool | Write logs to a file. |
| `file.path` | string | Directory where log files are written. |

### `profiles`

Lumi can serve several independent agent configurations from a single running instance. Each key under `profiles` is a profile name — `default` must always be defined — bundling its own `llm`, `mcp`, `attachments`, `rag`, and `connectors` settings.

A client selects a profile when opening a session, via the `profile` field of `POST /auth` (see [HTTP API → Authentication](#authentication-1)). If the requested profile doesn't exist, Lumi falls back to `default`. Admin endpoints that list or filter tools (`GET /tools`) also accept a `profile` query parameter.

```json
"profiles": {
  "default": {
    "llm": { "...": "..." },
    "mcp": { "...": "..." },
    "attachments": { "...": "..." },
    "rag": { "collection": "demo", "top_k": 5 },
    "connectors": { "...": "..." }
  },
  "another_profile": {
    "...": "..."
  }
}
```

Everything below (`llm`, `languages`, `mcp`, `attachments`, `rag`, `connectors`) is scoped under `profiles.<name>`.

#### `profiles.<name>.languages`

Array of language codes (e.g. `["fr", "en"]`) a session on this profile is allowed to select via `POST /auth`. Optional — if omitted, only `app.default_language` is allowed for that profile. See [Localization](#localization).

#### `profiles.<name>.llm`

LLM and agent settings.

| Key | Type | Description |
|-----|------|-------------|
| `system_prompt_file` | string | Path to the system prompt Markdown file. May contain the `%language%` placeholder, replaced at call time with the session's language name (e.g. `français`) — see [Localization](#localization). |
| `system_prompt` | string | Inline system prompt, used instead of `system_prompt_file` if set. Also supports `%language%`. |
| `connector` | string | LLM connector to use: `LiteLLM`, `Cerebras`, `DigitalOcean`, or `Llama` (classes of `lib/agent/llmconnector/`). The connector's settings go in a block named after it (see `<connector>.*` below). |
| `memory_messages` | int | Number of past exchanges kept in context. |
| `empty_llm_response_max_retry` | int | Max retries when the LLM returns an empty response. |
| `followup_questions.enabled` | bool | Generate follow-up question suggestions after each reply. |
| `followup_questions.count` | int | Number of follow-up questions to generate. |
| `filters` | object | Active output filters. Currently supports `CodeFilter` (strips markdown code fences). |
| `<connector>.model` | string | Model identifier for the connector named in `connector` (e.g. `LiteLLM.model`). |
| `<connector>.api_base` | string | Base URL of the LLM provider API. |
| `<connector>.api_key` | string | API key for the LLM provider (optional for `Llama`). |

Embedding models are not configured here: each RAG collection carries its own embedder (see [`rag`](#rag)).

#### `profiles.<name>.mcp`

MCP tool settings.

| Key | Type | Description |
|-----|------|-------------|
| `max_tool_iterations` | int | Maximum number of consecutive tool calls per agent turn. |
| `tools_enabled` | array | Patterns controlling which tools are exposed to this profile's agent. A tool not covered by this list is not registered. Accepts: exact tool function names (e.g. `search_knowledge_base`); `namespace.*` to enable every tool of a module or subfolder, matched against the tool's module path relative to `tools.` (e.g. `word.*` enables all tools in `tools/word/`, `datetime.*` enables all tools in `tools/datetime.py`); `namespace/tool_name` to enable a single tool from a group (e.g. `pdf/generer_fichier_pdf`); and general glob patterns (`*`, `?`) matched against the module path. Tools of an [external MCP server](#external-mcp-servers) use the namespace `ext.<service>` (e.g. `ext.my_mcp_server.*`). |

#### `profiles.<name>.attachments`

Controls the [file attachment](#file-attachments) feature for this profile.

| Key | Type | Description |
|-----|------|-------------|
| `enabled` | bool | Allow users to attach files to a conversation via `POST /files/upload`. |
| `max_files` | int | Maximum number of files attached at once per session. |
| `max_file_size_mb` | int | Maximum size, in MB, of a single attached file. |
| `allowed_extensions` | array | File extensions accepted for upload (e.g. `.pdf`, `.docx`, `.xlsx`, `.md`, `.txt`, `.csv`, ...). |
| `mode` | string | What is injected into the prompt: `rag` (most relevant chunks only), `full` (complete text of every attached file) or `auto` (default: full text if it fits in `full_text_max_tokens`, chunks otherwise). |
| `full_text_max_tokens` | int | Threshold of the `auto` mode, on the estimated total size of attached files (≈ 4 characters per token). Default `20000`. |
| `file_context_top_k` | int | Number of attachment chunks retrieved (and injected into context, or returned by `search_attached_files`) per query. |

#### `profiles.<name>.rag`

| Key | Type | Description |
|-----|------|-------------|
| `collection` | string | RAG collection searched by `search_knowledge_base` for sessions on this profile (the only one they can access; without it, RAG search is unavailable). Must be declared in [`rag.collections`](#rag). Its embedder and chunking settings are also used for session-attachment search. |
| `top_k` | int | Number of chunks returned per `search_knowledge_base` search. Defaults to `5`. |

#### `profiles.<name>.connectors`

Connectors extend this profile's agent to additional communication channels. Each profile can enable its own connectors independently — see [Webex connector](#webex-connector).

##### `profiles.<name>.connectors.webex`

| Key | Type | Description |
|-----|------|-------------|
| `enabled` | bool | Enable or disable the Webex connector for this profile. |
| `bot_token` | string | Webex bot access token. |
| `webhook_secret` | string | Secret used to verify incoming webhook signatures. |
| `webex_api` | string | Webex API base URL (`https://webexapis.com/v1`). |
| `api_key` | string | Optional API key passed to the authentication service for Webex users of this profile. |
| `allow_group_messages` | bool | If `true`, the bot responds in group spaces; if `false`, only in 1-to-1 spaces. |

### `usage`

Global usage limits, shared across all profiles.

| Key | Type | Description |
|-----|------|-------------|
| `max_tokens_month` | int | Monthly token budget (`-1` = unlimited). |
| `max_requests_month` | int | Monthly request budget (`-1` = unlimited). |
| `max_requests_minute` | int | Per-minute rate limit per session. |

### `security`

| Key | Type | Description |
|-----|------|-------------|
| `sandbox_max_process` | int | Maximum number of simultaneous sandbox subprocesses (file extraction, cf. `extraction`); further executions wait (default: `4`). |
| `min_secret_length` | int | Minimum length of `authentication.jwt_secret`, checked at startup (default: `32`, i.e. 256 bits for HS256). |
| `auth_rate_window` | int | Sliding window, in seconds, over which `authentication.max_auth_requests_minute` is counted (default: `60`). |
| `auth_rate_max_tracked_ips` | int | Number of client IPs tracked by the auth rate limiter beyond which inactive IPs are purged, to bound memory (default: `10000`). |
| `multipart_overhead_mb` | number | Margin, in MB, added to the largest `attachments.max_file_size_mb` to size the `POST /files/upload` body limit, covering the multipart envelope (boundaries, part headers) (default: `1`). |

### `extraction`

Text extraction of uploaded or indexed files (PDF, Office, HTML...) runs in an isolated subprocess with resource limits, so that a malicious file (decompression bomb, pathological PDF) cannot exhaust the server. Linux only (`forkserver` multiprocessing context).

| Key | Type | Description |
|-----|------|-------------|
| `timeout` | int | Maximum duration of one extraction, in seconds (default: `120`). Also used as CPU time limit. |
| `max_memory_mb` | int | Maximum memory (address space) of the extraction subprocess, in MB (default: `2048`). |
| `max_uncompressed_mb` | int | Archives (docx, xlsx, pptx, zip...) whose entries exceed this total uncompressed size are rejected before extraction (default: `500`). |
| `max_archive_entries` | int | Archives with more entries are rejected before extraction (default: `10000`). |

### `directories`

Filesystem paths used across Lumi. Built-in ones default to locations under `storage/` (runtime data) or `static/` (built-in language files); the `custom_*` override directories default to locations under `config/` — see [`config/` directory layout](#config-directory-layout).

| Key | Type | Description |
|-----|------|-------------|
| `temp_dir` | string | Directory for temporary files produced by tools and user uploads (e.g. generated PDFs). Default: `storage/temp`. |
| `local_storage_dir` | string | Directory for persistent local data (the usage-statistics SQLite database). Default: `storage/data`. |
| `languages_dir` | string | Directory of built-in translation files, one subfolder per language code (`<languages_dir>/<code>/*.json`). Default: `static/languages`. |
| `rag_storage_dir` | string | Directory where indexed RAG source files are kept, per collection (see [source file retention](#rag-knowledge-base)). Default: `storage/rag`. |
| `custom_languages_dir` | string | Directory of deployment-specific translation overrides/additions, same layout as `languages_dir`, merged on top of it. Default: `config/languages`. |
| `custom_services_dir` | string | Fallback directory scanned for service handler classes not found in `lib/services/` — see [Adding services](#adding-services). Default: `config/services`. |
| `custom_mcp_tools_dir` | string | Additional directory scanned for MCP tools alongside `lib/mcp/tools/` — see [Adding tools](#adding-tools). Default: `config/tools`. |
| `custom_pipelines` | string | Directory containing one subfolder per pipeline (`<custom_pipelines>/<pipeline_uid>/pipeline.json`) — see [Pipelines](#pipelines). Default: `config/pipelines`. |

### `word`

Settings for the Word document template (gabarit) used by the `word.*` MCP tools. See [Word document templates](#word-document-templates-gabarits).

| Key | Type | Description |
|-----|------|-------------|
| `template` | string | Path to the `.docx` template file, typically under `config/templates/` (see [`config/` directory layout](#config-directory-layout)). Auto-generated on first use if it doesn't exist. |
| `template_placeholder` | string | Placeholder replaced by the generated body content. |
| `template_summary_placeholder` | string | Placeholder replaced by the auto-generated table of contents. |
| `template_title_placeholder` | string | Placeholder replaced by the document title (cover page and header). |
| `template_date_placeholder` | string | Placeholder replaced by the generation date. |
| `template_array_style` | string | Name of the table style (defined in the template) applied to generated tables. |
| `page_break_before_heading1` | bool | Insert a page break before every top-level (`#`) heading. |
| `heading_style_1` | string | Name of the paragraph style (defined in the template) applied to `#` headings. Defaults to `Heading 1`. |
| `heading_style_2` | string | Name of the paragraph style (defined in the template) applied to `##` headings. Defaults to `Heading 2`. |
| `heading_style_3` | string | Name of the paragraph style (defined in the template) applied to `###` headings. Defaults to `Heading 3`. |

### `pdf`

Settings for the PDF template used by the `generer_fichier_pdf` MCP tool. All keys are optional.

| Key | Type | Description |
|-----|------|-------------|
| `template_color` | string | Accent color as a 6-digit hex code without `#` (default: `1F4E79`). |
| `template_logo` | string \| null | Path to a logo image (relative to the project root, or absolute). Ignored if the file doesn't exist. |
| `template_footer_text` | string \| null | Text displayed in the page footer. |

### `rag`

Persistent RAG knowledge base settings. `rag.collections` declares each collection by name. A profile references one of them (see [`profiles.<name>.rag`](#profilesnamerag)).

```json
"rag": {
  "collections": {
    "demo": {
      "embedding_dim": 1024,
      "chunk_size": 500,
      "chunk_overlap": 50,
      "connector": "PgVector",
      "pgvector": { "table": "rag_documents" },
      "embedder": {
        "class": "LiteLLMEmbedder",
        "model": "openai/Qwen/Qwen3-Embedding-0.6B",
        "api_base": "https://provider.fr/v1",
        "api_key": ""
      }
    }
  }
}
```

A collection's vectors are only comparable with vectors from the same model, so indexing (cron, API) and search (`search_knowledge_base`) of a collection always use that collection's `embedder`. Changing it requires a full reindex of the collection. Using a collection that is not declared raises an error.

| Key (`rag.collections.<name>.`) | Type | Description |
|-----|------|-------------|
| `embedding_dim` | int | Embedding vector dimension (must match the embedder's model). |
| `chunk_size` | int | Target chunk size in tokens. |
| `chunk_overlap` | int | Overlap between consecutive chunks. |
| `connector` | string | Vector store backend (`PgVector`). |
| `pgvector.table` | string | PostgreSQL table used to store vectors. Collections with the same `embedding_dim` can share a table. |
| `embedder.class` | string | Embedder class from `lib/agent/llmembedder` (`LiteLLMEmbedder`, `DigitalOceanEmbedder`, `LlamaEmbedder`). |
| `embedder.model` | string | Embedding model identifier. |
| `embedder.api_base` | string | Base URL of the embedding API. |
| `embedder.api_key` | string | API key for the embedding API. |

Indexed source files are kept for citation/download purposes under `directories.rag_storage_dir` (see [`directories`](#directories) and [source file retention](#rag-knowledge-base)).

### `cron`

An array of scheduled background tasks, executed once a minute by `CronManager`. See [Adding CRON tasks](#adding-cron-tasks).

```json
"cron": [
  {
    "task": "Shredding",
    "time": { "minute": "/5", "hour": "*" },
    "config": { "log_max_days": 30 }
  },
  {
    "task": "Ragindexer",
    "time": { "minute": "/10", "hour": "*" },
    "config": { "folders": ["/data/docs"], "profile": "default" }
  }
]
```

| Key | Type | Description |
|-----|------|-------------|
| `task` | string | Name of the `CronTask` subclass to run (must exist in `lib/cron/tasks/`). |
| `time` | object | Schedule, matched against the current minute/hour. Each field (`minute`, `hour`) accepts `"*"` (always), `"/N"` (every N units), or a fixed integer (exact match). Omitted fields always match. |
| `config` | object | Task-specific configuration, passed to the task instance. |

Built-in tasks live in `lib/cron/tasks/`:
- `Shredding` deletes log files older than `config.log_max_days` days (log delestage/retention).
- `Ragindexer` walks each folder in `config.folders`, and indexes (or re-indexes) into the RAG knowledge base any file that isn't already indexed or whose on-disk modification time is newer than its indexed version. The RAG collection used is `profiles.<config.profile>.rag.collection` (`config.profile` defaults to `default`).

---

## HTTP API

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/auth` | — | Authenticate and open a session. Returns a JWT token. |
| `DELETE` | `/auth` | Bearer | Close the current session. |
| `GET` | `/auth` | Bearer | Return the current session's effective, profile-derived configuration — see [Localization](#localization). |

**POST /auth** — body:

```json
{
  "authorization": {
    "<authentication.service>": { "token": "<user-token>" },
    "<other-service>": { "token": "<other-token>" }
  },
  "profile": "default",
  "language": "fr"
}
```

`authorization` holds one entry per service, keyed by service name. The entry for the main service (`authentication.service`) is mandatory: if that service rejects it, the request fails with `403`. Entries for other configured services are optional and authenticated in parallel; a failure there is only logged and the service is skipped for the session. Each service's `authenticate()` returns a secret (e.g. `{"token": "..."}`) that is stored in the session's **wallet**, from which tools and services read it later (`Service.getAuth()`). Over HTTP, only existing tokens are accepted — login/password credentials are reserved for trusted callers (pipeline configuration).

Only one session per authorization payload is kept: a new `POST /auth` with the same payload replaces the previous session, unless that one has an open WebSocket connection, in which case the request fails with `409`. Requests are rate-limited per client IP (`authentication.max_auth_requests_minute`, `429` beyond).

`profile` selects which [profile](#profiles) the session runs on (its LLM, tools, attachment policy, RAG collection, connectors); falls back to `default` if the name doesn't match a configured profile.

`language` (optional) selects the session's language among the codes allowed by `profiles.<profile>.languages` (see [Localization](#localization)); returns `400` if the code doesn't exist or isn't allowed for the profile. Falls back to `app.default_language` if omitted.

Response:

```json
{ "token": "<jwt>" }
```

**DELETE /auth** — requires `Authorization: Bearer <jwt>` header. Returns `{ "detail": "Session closed" }`.

**GET /auth** — requires `Authorization: Bearer <jwt>` header. Returns the calling session's effective configuration, derived from its profile:

```json
{
  "followup_questions": true,
  "language": "fr",
  "attachements": true,
  "attachements_max_file_size_mb": 20,
  "attachements_max_files": 5,
  "attachements_allowed_extensions": [".pdf", ".docx", ".md", "..."]
}
```

Lets a client adapt its UI (e.g. show/hide the attachment button, enforce size limits, display follow-up suggestions) directly from the session's own configuration instead of duplicating each profile's settings client-side.

### Usage

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/usage` | Bearer or Basic admin | Returns token and request statistics for the current month. |

Response:

```json
{ "year": 2026, "month": 6, "token_used": 45000, "request_count": 120 }
```

### Administration

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/health` | Basic admin | Service health and active WebSocket connections. |
| `GET` | `/tools` | Basic admin | List of active MCP tools. Accepts an optional `?profile=<name>` query param to filter down to the tools enabled for that profile (`profiles.<name>.mcp.tools_enabled`); without it, returns the union of tools registered across all profiles. |

### Pipeline runs

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/pipeline/{pipeline_uid}/start` | Basic admin | Start a pipeline asynchronously. Optional JSON body `{ "payload": { ... } }`, exposed to the pipeline as `trigger.data`. Returns `{ "pipelines": [ { "pipeline_uid", "process_uid" } ] }`; `400` if the pipeline doesn't exist. |
| `GET` | `/pipeline/process/{process_uid}` | Basic admin | Run status (`is_ended`, `is_success`, timestamps) and list of executed steps. |
| `GET` | `/pipeline/process/{process_uid}/{id}` | Basic admin | Detail of one step, including its logs. |

See [Pipelines](#pipelines) and [README-PIPELINES.md](README-PIPELINES.md).

### File upload

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/files/upload` | Bearer | Attach a file to the current session's conversation — see [File attachments](#file-attachments). |

**POST /files/upload** — `multipart/form-data` with a single `file` field. Response:

```json
{ "key": "...", "filename": "report.pdf", "tokens": 1520 }
```

### File download

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/files/{key}/{filename}` | Bearer or `?t=` hash | Download a temporary file generated by a tool. |
| `GET` | `/files/rag/{collection}/{key}/{filename}` | Bearer (session whose profile's `rag.collection` is `{collection}`), `?t=` per-file signature, or Basic admin | Download a source document retained by the RAG knowledge base (see [source file retention](#rag-knowledge-base)). |

---

## Localization

Conversations, MCP tool metadata (display names, confirmation prompts), and system error messages can all be served in the language chosen by the session.

### Selecting a language

A profile declares which languages it supports via [`profiles.<name>.languages`](#profilesnamelanguages) (e.g. `["fr", "en"]`). A client selects one when opening a session, via the `language` field of `POST /auth` (see [HTTP API → Authentication](#authentication-1)); if omitted, the session falls back to [`app.default_language`](#app). `POST /auth` returns `400` if the requested language doesn't exist or isn't in the profile's `languages` list. The session's language is also reported back by [`GET /auth`](#authentication-1).

### Translation files

Translations are plain JSON dictionaries of `"dotted.key": "text"` pairs, one file per topic, under one subfolder per language code:

- `directories.languages_dir` (default `static/languages/<code>/*.json`) — built-in translations shipped with Lumi (MCP tool names/confirmations in `mcp.json`, system error messages in `errors.json`).
- `directories.custom_languages_dir` (default `config/languages/<code>/*.json`) — deployment-specific translations, loaded on top of the built-in ones (same key overwrites, new keys are added). Use this to translate your own custom tools' descriptions and confirmation prompts, or to add a language Lumi doesn't ship translations for yet.

```json
// config/languages/fr/mcp.json
{
  "nexora.orders.list": "Liste les commandes",
  "nexora.orders.list.confirmation": "Je vais lister les commandes. Dois-je continuer ?"
}
```

A missing key resolves to `[the.key]` (the bracketed code itself) rather than raising, so an untranslated string is easy to spot without breaking the conversation.

### Where translations are applied

- **System prompt** — the `%language%` placeholder in `llm.system_prompt` / `llm.system_prompt_file` is replaced with the session's language name (e.g. `français`), so the LLM knows which language to answer in.
- **Tool display names and confirmation prompts** — an MCP tool's `@tool_description` name and, for `@confirmation_tool`, its question and options, are looked up as translation keys (falling back to the raw tool name / text if no matching key exists) and sent to the client already translated.
- **System error messages** — WebSocket-level errors such as rate limiting (`agent.rate_limit_exceeded.*`) or an in-progress response (`agent.response_in_progress`) are resolved through the same mechanism (`errors.json`).

---

## WebSocket protocol

Connect to `ws://host:8001/ws?token=<jwt>`.

**Incoming messages (client → server):**

```json
{ "type": "message",      "message": "..." }
{ "type": "confirmation", "option": 0 }
```

Files attached via `POST /files/upload` (see [File attachments](#file-attachments)) don't need to be referenced in the message — the agent automatically searches them for every message once at least one is attached.

**Outgoing events (server → client):**

```json
{ "type": "token",               "content": "..." }
{ "type": "tool_call",           "tools": "...", "status": "PENDING|OK|ERROR" }
{ "type": "rag",                 "source": "...", "locations": [...], "url": "..." }
{ "type": "file",                "name": "...", "url": "..." }
{ "type": "url",                 "name": "...", "url": "..." }
{ "type": "followup",            "questions": [...] }
{ "type": "confirmation",        "question": "...", "options": [...] }
{ "type": "confirmation_refused" }
{ "type": "error",               "error_code": "...", "message": "...", "details": "..." }
{ "type": "end" }
```

---

## RAG knowledge base

The RAG layer indexes documents into a **PostgreSQL / pgvector** vector store. The agent queries it automatically via the `search_knowledge_base` tool, which is strictly scoped to the RAG collection configured on the session's [profile](#profilesnamerag) (`profiles.<name>.rag.collection`): the LLM cannot target another collection, and a profile without `rag.collection` has no RAG search.

Documents can be indexed manually via the [document management API](#document-management-api), or automatically from folders on disk via the [`Ragindexer` CRON task](#cron).

### PostgreSQL / pgvector setup

Lumi automatically creates the pgvector table and its indexes on first use (`CREATE TABLE IF NOT EXISTS ...`), and also issues `CREATE EXTENSION IF NOT EXISTS vector` — but the **pgvector extension binaries must already be installed on the PostgreSQL server**, since Lumi can enable the extension but not install it.

- Use a PostgreSQL image/package that ships pgvector, e.g. the [`pgvector/pgvector`](https://github.com/pgvector/pgvector) Docker image (`pgvector/pgvector:pg16` or similar) instead of the plain `postgres` image, or install the `postgresql-<version>-pgvector` package on a self-managed server.
- The `services.bdd` user configured in `config.json` (see [`services`](#services)) needs privileges to run `CREATE EXTENSION` on the target database (superuser, or a role granted rights to create pre-authorized extensions).
- If the extension isn't installed or hasn't been created yet, RAG operations (indexing, search) fail with `vector type not found in the database`. Fix it by connecting to the target database and running:
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  ```
  If that command itself fails (e.g. `could not open extension control file`), the server is missing the pgvector binaries — switch to a PostgreSQL image/package that includes them.

### Supported document formats

PDF, Word (`.docx`/`.doc`), PowerPoint (`.pptx`/`.ppt`), Excel (`.xlsx`/`.xls`), Markdown, HTML, plain text, CSV, and source code files (`.py`, `.js`, `.ts`).

PDF pages are extracted individually (with a `page` metadata field). All other formats are converted to Markdown via [MarkItDown](https://github.com/microsoft/markitdown) before chunking.

### Source file retention & citations

Whenever a file is indexed (via the document management API or `Ragindexer`), a copy of the original source file is kept in `directories.rag_storage_dir` (`RagStore`), alongside its vector chunks. When `search_knowledge_base` uses chunks from that file to answer a question, the agent emits a `rag` WebSocket event carrying the source name, the pages used, and a **signed, time-limited download URL** (`GET /files/rag/{collection}/{key}/{filename}`, see [File download](#file-download)) pointing back to that retained file. Re-indexing or deleting a document also deletes its retained copy.

### Document management API

All RAG endpoints require HTTP Basic Auth (admin credentials).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/rag/documents` | Index a new document (text or file upload). Returns `409` if the source already exists. |
| `PUT` | `/rag/documents` | Re-index an existing document (deletes old chunks then indexes the new content). |
| `DELETE` | `/rag/collections/{collection}/documents/{source}` | Delete all chunks for a given source. |
| `DELETE` | `/rag/collections/{collection}` | Delete an entire collection. |
| `GET` | `/rag/stats` | Return chunk counts per collection. |

Both `POST` and `PUT` accept `multipart/form-data` with the fields:

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | Document to index (mutually exclusive with `text`). |
| `text` | string | Raw text to index (mutually exclusive with `file`). |
| `source` | string | Identifier for the document (defaults to the filename). |
| `collection` | string | Target collection, declared in `rag.collections` (defaults to the `default` profile's `rag.collection`). |

---

## File attachments

Users can attach files directly to a conversation, so the agent can reason over their content without indexing them into the shared knowledge base.

### Uploading a file

```
POST /files/upload
Authorization: Bearer <jwt>
Content-Type: multipart/form-data

file=<binary>
```

Requires `profiles.<name>.attachments.enabled` to be `true` for the session's profile. The upload is rejected (`400`) if it exceeds `attachments.max_files` already attached, `attachments.max_file_size_mb`, or if the extension isn't in `attachments.allowed_extensions` — see [`profiles.<name>.attachments`](#profilesnameattachments). Text is extracted the same way as for the [RAG knowledge base](#supported-document-formats) (PDFs page by page, other formats via MarkItDown). Response:

```json
{ "key": "...", "filename": "report.pdf", "tokens": 1520 }
```

### Per-session RAG

Attached files are never written to the persistent pgvector store. On every user message, Lumi automatically injects their content into the prompt, according to `attachments.mode`:

- `full`: the complete text of every attached file (page by page for PDFs). Required for requests about the whole document (list, summarize, compare...).
- `rag`: files are chunked and embedded on the fly into an **ephemeral, in-memory index** scoped to the session (cached for its lifetime, discarded when it ends), and only the most relevant chunks (`attachments.file_context_top_k`) for the message are injected Chunking and embeddings use the settings of the **session's profile's RAG collection** (`profiles.<name>.rag.collection`, or the `default` profile's collection if unset). Nothing is written to that collection.
- `auto` (default): `full` while the attached files fit in `attachments.full_text_max_tokens`, `rag` beyond.

The `search_attached_files` MCP tool remains available for the LLM to run additional, more targeted searches.

### Citations

Like `search_knowledge_base`, using attached-file content triggers a `rag` WebSocket event per source file (`{ "type": "rag", "source": "report.pdf", "locations": [2, 5] }`) so the client can show which file (and page, for paginated files) an answer drew from. When the full text is injected, `locations` is empty (the whole file was used). Since attachments aren't persisted, these events carry no download `url`.

---

## Built-in tools

Lumi ships with the following generic MCP tool groups in `lib/mcp/tools/`. Enable a group (or a single tool within it) via [`mcp.tools_enabled`](#profilesnamemcp).

| Group | Module | Tools | Description |
|-------|--------|-------|-------------|
| `datetime` | `lib/mcp/tools/context/datetime.py` | `get_business_days`, `next_business_day`, `get_public_holidays` | Date arithmetic and French public-holiday / business-day calculations. |
| `excel` | `lib/mcp/tools/excel/excel.py` | `generer_fichier_excel` | Generates Excel (`.xlsx`) files, including embedded charts. |
| `files` | `lib/mcp/tools/files/files.py` | `search_attached_files` | Searches files attached to the conversation — see [File attachments](#file-attachments). |
| `pdf` | `lib/mcp/tools/pdf/pdf.py` | `generer_fichier_pdf` | Generates templated PDF documents (cover page, header/footer, tables, charts). |
| `rag` | `lib/mcp/tools/rag/rag.py` | `search_knowledge_base` | Searches the RAG knowledge base — see [RAG knowledge base](#rag-knowledge-base). |
| `web` | `lib/mcp/tools/web/web.py` | `rechercher_sur_internet`, `lire_page_web` | Web search and web page reading. |
| `word` | `lib/mcp/tools/word/word.py` | 8 tools | Word document generation and editing on top of a company template — see [Word document templates](#word-document-templates-gabarits). |



---

## Pipelines

A **pipeline** is a server-side workflow, declared in JSON, that chains processing **blocks** sharing a common **context**. Each pipeline lives in its own folder under [`directories.custom_pipelines`](#directories) (default `config/pipelines/<pipeline_uid>/pipeline.json`); pipelines are loaded and validated (`lib/_references/pipeline.schema.json`) once at startup.

```json
{
  "name": "Recap mail",
  "services": { "nexora": { "login": "robot@example.com", "password": "..." } },
  "trigger": [ { "class": "Api", "config": {} } ],
  "blocks": {
    "_root":   { "class": "Mail",  "config": { "action": "list", "...": "...", "output": "mails" }, "on_success": "analyse", "on_error": "exit(0)" },
    "analyse": { "class": "Agent", "config": { "profile": "default", "prompt": "Summarize: {mails}", "output": "summary" }, "on_success": "exit(1)" }
  }
}
```

- Execution starts at the `_root` block and follows each block's `on_success` / `on_error` (another block id, `exit(1)` = success, `exit(0)` = failure).
- Block configuration strings are templates over the context: `{var.path[0]}`, `{% for %}`, `{% if %}`.
- `services` authenticates the run to configured services (credentials allowed here, since the pipeline file is trusted); secrets go into the run's wallet, shared with the `Agent` blocks' MCP tools.
- Each run executes in its own thread with its own process id; files produced during the run are purged at the end.
- The only trigger implemented so far is `Api` (`POST /pipeline/{pipeline_uid}/start`, see [HTTP API → Pipeline runs](#pipeline-runs)).

The full guide — configuration file, context and templating, every block and its parameters, run monitoring, and a commented example — is in **[README-PIPELINES.md](README-PIPELINES.md)** (in French).

---

## External MCP servers

A remote MCP server is declared as a service with the `MCPExternalService` handler:

| Key | Type | Description |
|-----|------|-------------|
| `transport` | string | `http` (streamable HTTP) or `sse`. |
| `url` | string | URL of the MCP endpoint. |
| `headers` | object | Optional static HTTP headers sent on connection. |
| `auth` | string | `static` (default): connected once at startup, shared by every session. `session`: connected per conversation turn, with the session's own token (`Authorization: Bearer <token>`), taken from the wallet — the client provides it in `POST /auth` under the service's name. |

Its tools are exposed to the LLM as `ext__<service>__<tool>` and enabled per profile in `mcp.tools_enabled` with the `ext.<service>` namespace (e.g. `ext.my_mcp_server.*`). A server unreachable at startup is logged and skipped.

---

## Adding tools

Built-in tools live in `lib/mcp/tools/` (optionally grouped in subfolders, e.g. `lib/mcp/tools/word/`). Deployment-specific tools go in `directories.custom_mcp_tools_dir` (default `config/tools`) instead, following the exact same layout — that way custom tools ship with the deployment's config, not with the application code. Both directories are scanned the same way at startup: each `.py` file is auto-discovered, files and folders starting with `_` are ignored (still importable as regular Python modules, e.g. for shared helpers — see below), and a tool method is only exposed to a given profile if it matches an entry in that profile's `mcp.tools_enabled` (see [`profiles.<name>.mcp`](#profilesnamemcp) above).

Since the project root is on the Python path, a custom tool file can import shared code from anywhere under `config/` as a regular package — e.g. `config/models/` for Pydantic models shared across several custom tool files, imported as `from config.models.mymodels import ...`.

### Creating a tool class

Create a file in `lib/mcp/tools/` (or your `custom_mcp_tools_dir`) and define a class that extends `MCPTool`:

```python
from lib.mcp.toolloader import MCPTool, tool_description, slow_tool, confirmation_tool, restricted_tool
from typing import Annotated
from pydantic import Field

class MyTools(MCPTool):
    name = "mytools"
    description = "Short description of this tool group"

    def my_tool_function(
        self,
        param: Annotated[str, Field(description="Description of the parameter")],
    ) -> str:
        """
        Full description of what the tool does — shown to the LLM to decide when to use it.
        """
        return "result"
```

Each public method of the class becomes an MCP tool. The method docstring is used as the tool description for the LLM.

### Decorators

Decorators are imported from `lib.mcp.toolloader` and applied to individual tool methods.

#### `@tool_description(name: str)`

Sets a human-readable display name for the tool, shown in the UI when the tool is called.

```python
@tool_description(name="My tool display name")
def my_tool(self, ...):
    ...
```

#### `@slow_tool`

Marks the tool as potentially slow. The UI can use this flag to show a loading indicator.

```python
@slow_tool
def my_slow_tool(self, ...):
    ...
```

#### `@confirmation_tool(question, options, validation_option)`

Prompts the user for confirmation before executing the tool. The tool only runs if the user selects the option at index `validation_option`.

```python
@confirmation_tool(
    question="Are you sure you want to proceed?",
    options=["Yes", "No"],
    validation_option=0,
)
def my_destructive_tool(self, ...):
    ...
```

#### `@restricted_tool`

Marks the tool as unavailable for non-chatbot agents (e.g. connectors that do not support interactive flows).

```python
@restricted_tool
def my_restricted_tool(self, ...):
    ...
```

### Emitting events

Tools can emit side-channel events (files, URLs) that are forwarded to the client alongside the tool result:

```python
from lib.agent.events import FileEvent, UrlEvent
from lib.files.filestore import FileStore

def my_tool(self, ...):
    url = FileStore.save(filename="result.pdf", content=pdf_bytes)
    self.emit(FileEvent.get(name="result.pdf", url=url))
    return {"url": url}
```

---

## Word document templates (gabarits)

The `word.*` MCP tools (`lib/mcp/tools/word/word.py`) generate and edit `.docx` files on top of a company **template (gabarit)** configured under [`word`](#word), rather than plain documents. If the configured `word.template` file doesn't exist yet, Lumi builds a default one automatically on first use (cover page, header/footer, table of contents area, heading and table styles).

The template contains placeholders (`word.template_placeholder`, `word.template_title_placeholder`, `word.template_summary_placeholder`, `word.template_date_placeholder`) that tools fill in with the generated content, title, table of contents, and date, plus a named table style (`word.template_array_style`) applied to generated tables.

Markdown headings (`#`/`##`/`###`) are rendered using the paragraph styles named in `word.heading_style_1`/`2`/`3`, so a custom template can define its own heading styles instead of Word's built-in `Heading 1`/`2`/`3`. If a configured style name isn't found in the template, Lumi falls back to the built-in `Heading N` style for that level.

### Markdown → Word rendering

Document content is authored in Markdown, enriched with layout directives placed on their own line:

| Directive | Effect |
|-----------|--------|
| `:::center` / `:::right` / `:::justify` / `:::left` | Aligns the following blocks. |
| `:::pagebreak` | Inserts a page break. |
| `:::chart:N` | Inserts the chart at index `N` from the `graphiques` parameter (bar, line, or pie). |
| `:::image:URL` | Inserts an image fetched from a URL. |

Standard Markdown is also supported: headings (`#`/`##`/`###`, auto-collected into the table of contents), bold/italic/strikethrough/underline, inline code, links, tables (6 columns max), lists, and fenced code blocks.

### Available tools

| Tool | Purpose |
|------|---------|
| `generer_fichier_word` | Generate a new Word document from Markdown content, following the template. |
| `lire_document_word` | Read back a generated document's title, outline, and full text. |
| `extraire_tableaux_word` | Extract all tables from a document, with their index and preceding section. |
| `remplacer_texte_word` | Find-and-replace text anywhere in a document (body, headers/footers, tables). |
| `ajouter_contenu_word` | Append Markdown content to a document, or insert it after a given section. |
| `mettre_a_jour_tableau_word` | Replace the data of an existing table, identified by index. |
| `fusionner_documents_word` | Merge several Word documents into one, each keeping its own cover page and table of contents. |
| `convertir_word_en_pdf` | Convert a Word document to PDF (requires LibreOffice/`soffice` on the server). |

---

## Adding services

Services are reusable HTTP or database clients made available to tools via `ServiceManager`. Built-in handlers live in `lib/services/`; deployment-specific ones go in `directories.custom_services_dir` (default `config/services`) instead. For each configured service, `ServiceManager` looks for `<handler>.py` in `lib/services/` first, then falls back to the custom directory if not found there.

### Creating a service

Create a file named after your handler (lowercased) in `lib/services/` or your `custom_services_dir`, and define a class that extends `Service`:

```python
from lib.services._abstract import Service

class MyService(Service):

    def __init__(self, name: str, data: dict):
        service_format = {
            "url": "str",
            "timeout": "int",
        }
        super().__init__(name=name, data=data, serviceDataFormat=service_format)
        self.timeout = data.get("timeout", 10)
```

`name` is the service's key in `services`. The `serviceDataFormat` dict declares the expected keys in the service's configuration block (`handler` excluded). The `Service` base class validates the config structure at startup and raises a clear error if a key is missing or unexpected.

A service is a single instance shared by all sessions and pipeline runs: it must not hold any per-user state. Per-user authentication goes through the wallet (see [Authentication](#authentication-2) below).

### Registering a service

Add the service to `services` in `config.json`. The `handler` key must match the class name exactly:

```json
"services": {
  "myservice": {
    "handler": "MyService",
    "url": "https://api.example.com",
    "timeout": 30
  }
}
```

### Using a service from a tool

```python
from lib.services.servicemanager import ServiceManager

class MyTools(MCPTool):
    def my_tool(self, ...):
        svc = ServiceManager.get("myservice")
        return svc.get("some/endpoint")
```

### Authentication

Services can override `authenticate(authorization: dict, allow_credentials: bool = False) -> dict | bool` to verify user credentials. `authorization` is the entry for this service in the `POST /auth` payload (or in a pipeline's `services` block). The method returns the secret to keep in the wallet (e.g. `{"token": "..."}`), or `False` on failure. `allow_credentials` is `True` only for trusted callers (pipelines), allowing a login/password exchange; over HTTP only existing tokens should be accepted. The default implementation returns `{}` (no per-user authentication).

Inside the service, `self.getAuth()` returns the current session's (or pipeline run's) secret for this service.

A public method with the signature `method(self, context, params)` can also be called from a pipeline through the `ServiceMethod` block — see [README-PIPELINES.md](README-PIPELINES.md).

### Dynamic class loading

LLM filters, LLM connectors, embedders, connectors (e.g. Webex), CRON tasks, and pipeline triggers and blocks are all instantiated through a single mechanism, `DynamicImport.getInstance` (`lib/utils/dynamicimport.py`). It only imports classes from a fixed allow-list of module paths (`lib.cron.tasks`, `lib.agent.filters`, `lib.agent.llmconnector`, `lib.agent.llmembedder`, `lib.connectors.webex`, `lib.pipelines.triggers`, `lib.pipelines.blocks`), so configuration values can never trigger the loading of arbitrary code — dropping a new class in one of these packages is enough to make it loadable, but the package itself must be explicitly allow-listed.

Services follow a separate, path-based loading mechanism instead (`ServiceManager`, see [Adding services](#adding-services) above): the `handler` name in a service's config is resolved to a `.py` file in `lib/services/`, falling back to `directories.custom_services_dir`, rather than going through `DynamicImport`'s allow-list.

---

## Adding CRON tasks

CRON tasks run periodically in the background (see [`cron`](#cron) for scheduling). They live in `lib/cron/tasks/`.

### Creating a CRON task

Create a file in `lib/cron/tasks/` and define a class that extends `CronTask`, with a class name matching the file name (case-insensitive) and the `task` value used in the `cron` config entry. Also add the task name to the `cronTask.task` enum of `lib/_references/config.schema.json`, otherwise the configuration is rejected at startup:

```python
from lib.cron.tasks._abstract import CronTask

class MyTask(CronTask):
    def __init__(self, config: dict):
        super().__init__(className="MyTask", config=config)

    async def run(self):
        await super().run()
        # self.config holds the task-specific "config" block from the cron entry
        ...
```

`CronManager` calls `testExecution(timestamp)` once a minute for every configured task, and awaits `run()` when the current minute/hour match the task's `time` schedule.

---

## Webex connector

The Webex connector turns Lumi into a Webex bot that receives messages from Webex spaces and replies via the agent. Since v1.4.0, `webex` is configured per [profile](#profiles) (`profiles.<name>.connectors.webex`) rather than globally — each profile with `enabled: true` gets its own bot, its own webhook route, and talks to its own agent, so a single Lumi instance can run several Webex bots side by side.

### Step 1 — Create a Webex bot

1. Go to [developer.webex.com](https://developer.webex.com) and sign in.
2. Open **My Webex Apps** → **Create a New App** → **Create a Bot**.
3. Fill in the bot name, username, and icon, then click **Add Bot**.
4. Copy the **Bot Access Token** — this is the value of `connectors.webex.bot_token` for the profile in your config. The token is shown only once; store it securely.

### Step 2 — Configure the connector

In `config/config.json`, under the target profile:

```json
"profiles": {
  "default": {
    "connectors": {
      "webex": {
        "enabled": true,
        "bot_token": "<bot-access-token>",
        "webhook_secret": "<a-random-secret-string>",
        "webex_api": "https://webexapis.com/v1",
        "api_key": "",
        "allow_group_messages": false
      }
    }
  }
}
```

- `webhook_secret`: choose any random string. Lumi uses it to verify that incoming webhook requests genuinely come from Webex.
- `allow_group_messages`: set to `true` if the bot should respond in group spaces. When `false`, the bot only processes direct (1-to-1) messages.
- `api_key`: passed to the authentication service (see [How it works](#how-it-works)) when authenticating a Webex user for this profile.
- `app.url` must point to the public URL of the Lumi server (e.g. `https://lumi.example.com`). Lumi registers the webhook at `<app.url>/webex/webhook/<profile>` on startup, where `<profile>` is the profile's name.

### Step 3 — Expose the server

The Webex platform must be able to reach your server over HTTPS. If you are running locally, use a tool such as [ngrok](https://ngrok.com) to expose the server:

```bash
ngrok http 8001
# Copy the https://... URL into config.json → app.url
```

### Step 4 — Start Lumi

On startup, for every profile with `connectors.webex.enabled: true`, the connector:
1. Authenticates the bot with the Webex API to retrieve its identity.
2. Registers (or updates) a webhook named `lumi-webhook` on that bot's Webex account, pointing to `<app.url>/webex/webhook/<profile>`.

### How it works

- When a user sends a message to a bot, Webex calls `POST /webex/webhook/<profile>` for the corresponding profile.
- Lumi verifies the `X-Spark-Signature` header using that profile's `webhook_secret`.
- The message is dispatched to that profile's agent, and the reply is sent back to the Webex space.
- User authentication is handled transparently: the bot identifies the sender by their Webex email and calls the profile's `connectors.webex.api_key` + the configured authentication service to obtain a session token.

---

## Changelog



### v1.6.x — Abyss (beta)

See [What's new in v1.6.0](#whats-new-in-v160--abyss).

### v1.5.x — Waves

- **Multilingual LLM conversations** — profiles now declare an allowed `languages` list; a session selects one via `POST /auth`, and the agent substitutes it into the system prompt (`%language%`) so replies are generated in that language.
- **Translation manager** — a new `LanguageManager` / `Language` / `Traduction` layer loads per-language JSON dictionaries from `static/languages/<code>/` (built-in) and merges in overrides from `config/languages/<code>/` (deployment-specific), keyed by dotted translation codes (e.g. `[word.generer_fichier_word.confirmation]`).
- **Translated MCP tool helpers, confirmations, and errors** — tool display names, confirmation questions/options, and system error messages (rate limiting, response-in-progress, …) are now resolved through the session's language instead of being hardcoded.
- **`GET /auth` session info endpoint** — returns the current session's effective configuration (follow-up questions enabled, language, attachment policy) derived from its profile, so the client can adapt the agent's UI directly instead of duplicating profile settings.
- **Reorganized directory layout for Docker** — built-in code moved under `lib/` (`lib/mcp/tools/`, `lib/services/`), and everything deployment-specific was consolidated under two directories: `config/` (configuration, custom tools/services/languages, prompts, templates, secrets) and `storage/` (temp files, logs, local DB, RAG storage). See [`config/` directory layout](#config-directory-layout).

### v1.4.x - Phosphor

- **File attachments** — users can attach files to a conversation via `POST /files/upload`. The agent can then search their content through the `search_attached_files` MCP tool, with the most relevant excerpts also injected directly into context automatically.
- **Attachment limits & restrictions** — attached files are governed by a configurable `attachments` block (enable/disable, max number of files, max file size, allowed extensions), enforced per profile.
- **Per-session RAG** — attached files are chunked and embedded on the fly into an ephemeral, in-memory vector index (never written to the persistent RAG store), giving the LLM the same retrieval-based reasoning over conversation attachments as over the main knowledge base.
- **Source citations** — replies that relied on the RAG knowledge base or on attached files now come with `rag` events pointing back to the source document (and page, when applicable), so the origin of an answer can be traced and, for the persistent RAG, opened via a secure URL.
- **RAG folder indexing CRON task** — a new `Ragindexer` task scans one or more source folders and automatically (re)indexes new or modified documents into the RAG vector store on a schedule.
- **Configuration profiles** — the `llm`, `mcp`, `attachments`, `rag`, and `connectors` settings are now grouped under named `profiles`, so a single Lumi instance can run several agents with different models, tools, and behaviors, selected at authentication time.
- **Persistent RAG source files with secure URLs** — indexed documents are kept alongside their vector chunks and served back through a time-limited, signed URL when cited in a reply, instead of being discarded after indexing.

### v1.3.x — Aurora

- **Reorganized MCP tool structure** — tools can now be grouped into subfolders (e.g. `tools/word/`), and `mcp.tools_enabled` gained flexible matching patterns: exact tool names, `namespace.*` wildcards to enable a whole group at once, and `namespace/tool_name` to enable a single tool from a group (see [Adding tools](#adding-tools)).
- **Advanced Word MCP tools** — Word generation now builds on a customizable company **template (gabarit)**: cover page, header/footer, auto-generated table of contents, table styles, chart embedding, targeted section insertion, table updates, document merging, and Word → PDF conversion (see [Word document templates](#word-document-templates-gabarits)).
- **CRON task engine** — a new scheduler (`CronManager`) runs background tasks on a configurable minute/hour schedule, defined in the `cron` config section (see [`cron`](#cron)).
- **Log shredding CRON task** — a built-in `Shredding` task automatically deletes old log files past a configurable retention period.
- **Refactored, secured dynamic import system** — services, LLM filters, connectors, and CRON tasks are now all instantiated through a single, allow-listed dynamic import mechanism, preventing arbitrary class loading from configuration.
- **Follow-up question suggestions** — the agent can generate short, relevant follow-up questions after each reply, configurable via `llm.followup_questions`.
- **New `followup` client event** — a `FollowUpEvent` delivers the generated follow-up questions to the WebSocket client (see [WebSocket protocol](#websocket-protocol)).

### v1.2.x — Spark

- **Webex connector** — the agent can be deployed as a Webex bot (see [Webex connector](#webex-connector)).
- **PDF and Word tools** — new native tools for generating richly formatted PDF and Word documents.
- **Chart support** — bar charts, pie charts, and line charts can be embedded in generated PDFs and Word documents.
- **Date and business-day calculations** — new `datetime` tool handles date arithmetic and French public holidays.
- **Usage statistics endpoint** — `GET /usage` returns monthly token and request consumption.
- **Session close endpoint** — `DELETE /auth` allows a client to explicitly close its session.
- **System prompt refactoring** — the system prompt is now fully driven by a Markdown file (`config/systemprompt.md`).
- Various LumePackAPI service fixes.

### v1.1.x — Sense

- Initial public release.
- WebSocket chat, MCP tool integration, RAG / pgvector knowledge base, JWT authentication, Excel file generation.

---

## License

This project is released under the **MIT License** — free to use, modify, and distribute, for personal or commercial purposes, with attribution.

```
MIT License

Copyright (c) 2025 Loic Gerard

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
