![alt text](https://raw.githubusercontent.com/gerard-loic/lumi/refs/heads/master/public/lumi-aurora.jpg?raw=true)

# Lumi

Lumi version 1.3.1 (Aurora)

Lumi is an open-source AI chatbot backend built on top of **FastAPI** and the **Model Context Protocol (MCP)**. It exposes a WebSocket chat API that connects a Large Language Model to a set of custom tools and a **RAG knowledge base**, enabling the agent to answer questions grounded in real data rather than hallucinated knowledge.

## Features

- **WebSocket chat endpoint** — answers are streamed token by token over a persistent WebSocket connection. The client receives typed JSON events (`token`, `tool_call`, `rag`, `file`, `followup`, `end`, …).
- **MCP tool integration** — tools are registered as MCP tools, optionally grouped into subfolders. The agent calls them automatically when it needs real data to answer a question.
- **RAG (Retrieval-Augmented Generation)** — a built-in knowledge base lets the agent search indexed documents before answering. The agent triggers searches automatically via the `search_knowledge_base` MCP tool.
- **Document generation** — native tools for generating PDF, Word, and Excel files, including embedded charts (bar, pie, line). Word documents follow a customizable company **template (gabarit)**, with a cover page, header/footer, auto-generated table of contents, and table styles.
- **Follow-up suggestions** — after each reply, the agent can propose short follow-up questions to help guide the conversation.
- **Configurable LLM backend** — uses LiteLLM under the hood, so you can point it at any compatible model (OpenAI, Azure, local models, etc.) by changing a config value.
- **Authentication** — a JWT-based `/auth` endpoint protects the chat API and temporary file downloads. Admin endpoints use HTTP Basic Auth.
- **Temporary file serving** — tools can produce files that are made available for download through a secure, time-limited URL.
- **Webex connector** — the agent can be deployed as a Webex bot, receiving and answering messages from Webex spaces via webhooks.
- **Scheduled CRON tasks** — a built-in scheduler runs background maintenance tasks (e.g. log retention/shredding) on a configurable minute/hour schedule.
- **Usage statistics** — a `/usage` endpoint returns token and request consumption for the current month.
- **Extensible by design** — add custom tools, services, LLM filters, and CRON tasks by dropping files into their respective directories. All dynamic class loading goes through a single, allow-listed mechanism for safety. Which MCP tools are exposed is finely controlled via `mcp.tools_enabled` (exact names, whole-group wildcards, or single-tool overrides).

## What's new in v1.3.0 — Aurora

- **Reorganized MCP tool structure** — tools can now be grouped into subfolders (e.g. `tools/word/`), and `mcp.tools_enabled` gained flexible matching patterns: exact tool names, `namespace.*` wildcards to enable a whole group at once, and `namespace/tool_name` to enable a single tool from a group (see [Adding tools](#adding-tools)).
- **Advanced Word MCP tools** — Word generation now builds on a customizable company **template (gabarit)**: cover page, header/footer, auto-generated table of contents, table styles, chart embedding, targeted section insertion, table updates, document merging, and Word → PDF conversion (see [Word document templates](#word-document-templates-gabarits)).
- **CRON task engine** — a new scheduler (`CronManager`) runs background tasks on a configurable minute/hour schedule, defined in the `cron` config section (see [`cron`](#cron)).
- **Log shredding CRON task** — a built-in `Shredding` task automatically deletes old log files past a configurable retention period.
- **Refactored, secured dynamic import system** — services, LLM filters, connectors, and CRON tasks are now all instantiated through a single, allow-listed dynamic import mechanism, preventing arbitrary class loading from configuration.
- **Follow-up question suggestions** — the agent can generate short, relevant follow-up questions after each reply, configurable via `llm.followup_questions`.
- **New `followup` client event** — a `FollowUpEvent` delivers the generated follow-up questions to the WebSocket client (see [WebSocket protocol](#websocket-protocol)).

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

---

## Configuration reference

Lumi is configured through a single JSON file: `config/config.json`. The `config/config.default.json` file serves as a template.

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
| `admin_users` | array | List of `{ username, password }` objects for HTTP Basic Auth on admin endpoints. |

### `authentication`

Controls how users authenticate to obtain a WebSocket token.

| Key | Type | Description |
|-----|------|-------------|
| `service` | string | Name of the service used to verify credentials (must match a key in `services`). |
| `jwt_secret` | string | Secret used to sign and verify JWT tokens. |
| `jwt_algorithm` | string | JWT signing algorithm (e.g. `HS256`). |
| `session_duration` | int | Session validity duration in seconds. |

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
  }
}
```

Built-in handlers live in the `services/` directory. See [Adding services](#adding-services) to create custom ones.

### `logger`

| Key | Type | Description |
|-----|------|-------------|
| `output.enabled` | bool | Print logs to stdout. |
| `file.enabled` | bool | Write logs to a file. |
| `file.path` | string | Directory where log files are written. |

### `llm`

LLM and agent settings.

| Key | Type | Description |
|-----|------|-------------|
| `system_prompt_file` | string | Path to the system prompt Markdown file. |
| `connector` | string | LLM connector to use (`LiteLLM`). |
| `memory_messages` | int | Number of past exchanges kept in context. |
| `empty_llm_response_max_retry` | int | Max retries when the LLM returns an empty response. |
| `max_tokens_month` | int | Monthly token budget (`-1` = unlimited). |
| `max_requests_month` | int | Monthly request budget (`-1` = unlimited). |
| `max_requests_minute` | int | Per-minute rate limit per session. |
| `followup_questions.enabled` | bool | Generate follow-up question suggestions after each reply. |
| `followup_questions.count` | int | Number of follow-up questions to generate. |
| `litellm.model` | string | LiteLLM model identifier. |
| `litellm.embedding_model` | string | LiteLLM model identifier used for RAG embeddings. |
| `litellm.api_base` | string | Base URL of the LLM provider API. |
| `litellm.api_key` | string | API key for the LLM provider. |
| `filters` | object | Active output filters. Currently supports `CodeFilter` (strips markdown code fences). |

### `mcp`

MCP tool settings.

| Key | Type | Description |
|-----|------|-------------|
| `max_tool_iterations` | int | Maximum number of consecutive tool calls per agent turn. |
| `tools_enabled` | array | Patterns controlling which tools are exposed. A tool not covered by this list is not registered. Accepts: exact tool function names (e.g. `search_knowledge_base`); `namespace.*` to enable every tool of a module or subfolder, matched against the tool's module path relative to `tools.` (e.g. `word.*` enables all tools in `tools/word/`, `datetime.*` enables all tools in `tools/datetime.py`); `namespace/tool_name` to enable a single tool from a group (e.g. `pdf/generer_fichier_pdf`); and general glob patterns (`*`, `?`) matched against the module path. |

### `files`

| Key | Type | Description |
|-----|------|-------------|
| `temp_dir` | string | Directory for temporary files produced by tools (e.g. generated PDFs). |
| `local_storage_dir` | string | Directory for persistent local data (e.g. usage statistics). |

### `word`

Settings for the Word document template (gabarit) used by the `word.*` MCP tools. See [Word document templates](#word-document-templates-gabarits).

| Key | Type | Description |
|-----|------|-------------|
| `template` | string | Path to the `.docx` template file. Auto-generated on first use if it doesn't exist. |
| `template_placeholder` | string | Placeholder replaced by the generated body content. |
| `template_summary_placeholder` | string | Placeholder replaced by the auto-generated table of contents. |
| `template_title_placeholder` | string | Placeholder replaced by the document title (cover page and header). |
| `template_date_placeholder` | string | Placeholder replaced by the generation date. |
| `template_array_style` | string | Name of the table style (defined in the template) applied to generated tables. |
| `page_break_before_heading1` | bool | Insert a page break before every top-level (`#`) heading. |

### `rag`

RAG knowledge base settings.

| Key | Type | Description |
|-----|------|-------------|
| `collection` | string | Default collection name. |
| `embedding_dim` | int | Embedding vector dimension (must match the embedding model). |
| `top_k` | int | Number of chunks returned per search. |
| `chunk_size` | int | Target chunk size in tokens. |
| `chunk_overlap` | int | Overlap between consecutive chunks. |
| `connector` | string | Vector store backend (`PgVector`). |
| `pgvector.table` | string | PostgreSQL table used to store vectors. |

### `cron`

An array of scheduled background tasks, executed once a minute by `CronManager`. See [Adding CRON tasks](#adding-cron-tasks).

```json
"cron": [
  {
    "task": "Shredding",
    "time": { "minute": "/5", "heure": "*" },
    "config": { "log_max_days": 30 }
  }
]
```

| Key | Type | Description |
|-----|------|-------------|
| `task` | string | Name of the `CronTask` subclass to run (must exist in `lib/cron/tasks/`). |
| `time` | object | Schedule, matched against the current minute/hour. Each field (`minute`, `heure`) accepts `"*"` (always), `"/N"` (every N units), or a fixed integer (exact match). Omitted fields always match. |
| `config` | object | Task-specific configuration, passed to the task instance. |

Built-in tasks live in `lib/cron/tasks/`. The bundled `Shredding` task deletes log files older than `config.log_max_days` days (log delestage/retention).

### `connectors`

Connectors extend the agent to additional communication channels.

#### `connectors.webex`

| Key | Type | Description |
|-----|------|-------------|
| `enabled` | bool | Enable or disable the Webex connector. |
| `bot_token` | string | Webex bot access token. |
| `webhook_secret` | string | Secret used to verify incoming webhook signatures. |
| `webex_api` | string | Webex API base URL (`https://webexapis.com/v1`). |
| `api_key` | string | Optional API key passed to the authentication service for Webex users. |
| `allow_group_messages` | bool | If `true`, the bot responds in group spaces; if `false`, only in 1-to-1 spaces. |

---

## HTTP API

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/auth` | — | Authenticate and open a session. Returns a JWT token. |
| `DELETE` | `/auth` | Bearer | Close the current session. |

**POST /auth** — body:

```json
{ "authorization": { "token": "<user-token>" } }
```

Response:

```json
{ "token": "<jwt>" }
```

**DELETE /auth** — requires `Authorization: Bearer <jwt>` header. Returns `{ "detail": "Session closed" }`.

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
| `GET` | `/tools` | Basic admin | List of active MCP tools. |

### File download

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/files/{key}/{filename}` | Bearer or `?t=` hash | Download a file generated by a tool. |

---

## WebSocket protocol

Connect to `ws://host:8001/ws?token=<jwt>`.

**Incoming messages (client → server):**

```json
{ "type": "message",      "message": "..." }
{ "type": "confirmation", "option": 0 }
```

**Outgoing events (server → client):**

```json
{ "type": "token",               "content": "..." }
{ "type": "tool_call",           "tools": "...", "status": "PENDING|OK|ERROR" }
{ "type": "rag",                 "source": "...", "locations": [...] }
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

The RAG layer indexes documents into a **PostgreSQL / pgvector** vector store. The agent queries it automatically via the `search_knowledge_base` tool.

### Supported document formats

PDF, Word (`.docx`/`.doc`), PowerPoint (`.pptx`/`.ppt`), Excel (`.xlsx`/`.xls`), Markdown, HTML, plain text, CSV, and source code files (`.py`, `.js`, `.ts`).

PDF pages are extracted individually (with a `page` metadata field). All other formats are converted to Markdown via [MarkItDown](https://github.com/microsoft/markitdown) before chunking.

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
| `collection` | string | Target collection (defaults to `rag.collection` in config). |

---

## Built-in tools

Lumi ships with the following generic MCP tool groups in `tools/`. Enable a group (or a single tool within it) via [`mcp.tools_enabled`](#mcp).

| Group | Module | Tools | Description |
|-------|--------|-------|-------------|
| `datetime` | `tools/context/datetime.py` | `get_business_days`, `next_business_day`, `get_public_holidays` | Date arithmetic and French public-holiday / business-day calculations. |
| `excel` | `tools/excel/excel.py` | `generer_fichier_excel` | Generates Excel (`.xlsx`) files, including embedded charts. |
| `pdf` | `tools/pdf/pdf.py` | `generer_fichier_pdf` | Generates templated PDF documents (cover page, header/footer, tables, charts). |
| `rag` | `tools/rag/rag.py` | `search_knowledge_base` | Searches the RAG knowledge base — see [RAG knowledge base](#rag-knowledge-base). |
| `web` | `tools/web/web.py` | `rechercher_sur_internet`, `lire_page_web` | Web search and web page reading. |
| `word` | `tools/word/word.py` | 8 tools | Word document generation and editing on top of a company template — see [Word document templates](#word-document-templates-gabarits). |



---

## Adding tools

Tools live in the `tools/` directory (optionally grouped in subfolders, e.g. `tools/word/`). Each file is auto-discovered at startup. Files and folders starting with `_` are ignored. A tool method is only exposed if it matches an entry in `mcp.tools_enabled` (see the `mcp` config section above).

### Creating a tool class

Create a file in `tools/` and define a class that extends `MCPTool`:

```python
from lib.mcp.tools import MCPTool, tool_description, slow_tool, confirmation_tool, restricted_tool
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

Decorators are imported from `lib.mcp.tools` and applied to individual tool methods.

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

The `word.*` MCP tools (`tools/word/word.py`) generate and edit `.docx` files on top of a company **template (gabarit)** configured under [`word`](#word), rather than plain documents. If the configured `word.template` file doesn't exist yet, Lumi builds a default one automatically on first use (cover page, header/footer, table of contents area, heading and table styles).

The template contains placeholders (`word.template_placeholder`, `word.template_title_placeholder`, `word.template_summary_placeholder`, `word.template_date_placeholder`) that tools fill in with the generated content, title, table of contents, and date, plus a named table style (`word.template_array_style`) applied to generated tables.

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

Services are reusable HTTP or database clients made available to tools via `ServiceManager`. They live in the `services/` directory.

### Creating a service

Create a file in `services/` and define a class that extends `Service`:

```python
from lib.mcp.services import Service

class MyService(Service):

    def __init__(self, data: dict):
        service_format = {
            "url": "str",
            "timeout": "int",
        }
        super().__init__(data=data, serviceDataFormat=service_format)
        self.timeout = data.get("timeout", 10)
```

The `serviceDataFormat` dict declares the expected keys in the service's configuration block. The `Service` base class validates the config structure at startup and raises a clear error if a key is missing or unexpected.

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
from lib.mcp.services import ServiceManager

class MyTools(MCPTool):
    def my_tool(self, ...):
        svc = ServiceManager.get("myservice")
        return svc.get("some/endpoint")
```

### Authentication

Services can implement the `checkAuthentication(authorization: dict)` method to verify user credentials at session open time. The `authorization` dict is the payload sent by the client in `POST /auth`.

### Dynamic class loading

Services, LLM filters, connectors, and CRON tasks are all instantiated through a single mechanism, `DynamicImport.getInstance` (`lib/utils/dynamicimport.py`). It only imports classes from a fixed allow-list of module paths (`lib.cron.tasks`, `lib.agent.filters`, `lib.agent.llmconnector`, `lib.connectors.webex`), so configuration values can never trigger the loading of arbitrary code — dropping a new class in one of these packages is enough to make it loadable, but the package itself must be explicitly allow-listed.

---

## Adding CRON tasks

CRON tasks run periodically in the background (see [`cron`](#cron) for scheduling). They live in `lib/cron/tasks/`.

### Creating a CRON task

Create a file in `lib/cron/tasks/` and define a class that extends `CronTask`, with a class name matching the file name (case-insensitive) and the `task` value used in the `cron` config entry:

```python
from lib.cron.tasks.crontask import CronTask

class MyTask(CronTask):
    def __init__(self, config: dict):
        super().__init__(className="MyTask", config=config)

    def run(self):
        super().run()
        # self.config holds the task-specific "config" block from the cron entry
        ...
```

`CronManager` calls `testExecution(timestamp)` once a minute for every configured task, and runs `run()` when the current minute/hour match the task's `time` schedule.

---

## Webex connector

The Webex connector turns Lumi into a Webex bot that receives messages from Webex spaces and replies via the agent.

### Step 1 — Create a Webex bot

1. Go to [developer.webex.com](https://developer.webex.com) and sign in.
2. Open **My Webex Apps** → **Create a New App** → **Create a Bot**.
3. Fill in the bot name, username, and icon, then click **Add Bot**.
4. Copy the **Bot Access Token** — this is the value of `connectors.webex.bot_token` in your config. The token is shown only once; store it securely.

### Step 2 — Configure the connector

In `config/config.json`:

```json
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
```

- `webhook_secret`: choose any random string. Lumi uses it to verify that incoming webhook requests genuinely come from Webex.
- `allow_group_messages`: set to `true` if the bot should respond in group spaces. When `false`, the bot only processes direct (1-to-1) messages.
- `app.url` must point to the public URL of the Lumi server (e.g. `https://lumi.example.com`). Lumi registers the webhook at `<app.url>/webex/webhook` on startup.

### Step 3 — Expose the server

The Webex platform must be able to reach your server over HTTPS. If you are running locally, use a tool such as [ngrok](https://ngrok.com) to expose the server:

```bash
ngrok http 8001
# Copy the https://... URL into config.json → app.url
```

### Step 4 — Start Lumi

On startup, the connector:
1. Authenticates the bot with the Webex API to retrieve its identity.
2. Registers (or updates) a webhook named `lumi-webhook` on your Webex account, pointing to `<app.url>/webex/webhook`.

### How it works

- When a user sends a message to the bot, Webex calls `POST /webex/webhook`.
- Lumi verifies the `X-Spark-Signature` header using the `webhook_secret`.
- The message is dispatched to the agent, and the reply is sent back to the Webex space.
- User authentication is handled transparently: the bot identifies the sender by their Webex email and calls `connectors.webex.api_key` + the configured authentication service to obtain a session token.

---

## Changelog

### v1.3.0 — Aurora

See [What's new in v1.3.0](#whats-new-in-v130--aurora).

### v1.2.0 — Spark

- **Webex connector** — the agent can be deployed as a Webex bot (see [Webex connector](#webex-connector)).
- **PDF and Word tools** — new native tools for generating richly formatted PDF and Word documents.
- **Chart support** — bar charts, pie charts, and line charts can be embedded in generated PDFs and Word documents.
- **Date and business-day calculations** — new `datetime` tool handles date arithmetic and French public holidays.
- **Usage statistics endpoint** — `GET /usage` returns monthly token and request consumption.
- **Session close endpoint** — `DELETE /auth` allows a client to explicitly close its session.
- **System prompt refactoring** — the system prompt is now fully driven by a Markdown file (`config/systemprompt.md`).
- Various LumePackAPI service fixes.

### v1.1.0 — Sense

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
Dynam