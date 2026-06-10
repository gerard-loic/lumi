![alt text](https://raw.githubusercontent.com/gerard-loic/lumi/refs/heads/master/public/cover.jpg?raw=true)

# Lumi

Lumi version 1.1.0 (Sense)

Lumi is an open-source AI chatbot backend built on top of **FastAPI** and the **Model Context Protocol (MCP)**. It exposes a WebSocket chat API that connects a Large Language Model to a set of custom tools and a **RAG knowledge base**, enabling the agent to answer questions grounded in real data rather than hallucinated knowledge.

## What it does

- **WebSocket chat endpoint** — answers are streamed token by token over a persistent WebSocket connection. The client receives typed JSON events (`token`, `tool_call`, `rag`, `file`, `end`, …).
- **MCP tool integration** — tools are registered as MCP tools. The agent calls them automatically when it needs real data to answer a question.
- **RAG (Retrieval-Augmented Generation)** — a built-in knowledge base lets the agent search indexed documents before answering. The agent triggers searches automatically via the `search_knowledge_base` MCP tool.
- **Configurable LLM backend** — uses LiteLLM under the hood, so you can point it at any compatible model (OpenAI, Azure, local models, etc.) by changing a config value.
- **Authentication** — a JWT-based `/auth` endpoint protects the chat API and temporary file downloads. Admin endpoints use HTTP Basic Auth.
- **Temporary file serving** — tools can produce files (e.g. Excel exports) that are made available for download through a secure, time-limited URL.

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

### RAG configuration

```json
"rag": {
  "collection":    "demo",
  "embedding_dim": 1024,
  "top_k":         5,
  "chunk_size":    500,
  "chunk_overlap": 50,
  "connector":     "PgVector",
  "pgvector": {
    "table": "rag_documents"
  }
}
```

The embedding model is configured under `llm.litellm.embedding_model`. The pgvector table and its HNSW index are created automatically on first use.

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
{ "type": "confirmation",        "question": "...", "options": [...] }
{ "type": "confirmation_refused" }
{ "type": "error",               "error_code": "...", "message": "...", "details": "..." }
{ "type": "end" }
```

## Adding tools

Drop a new `.py` file in the `tools/` directory and register your functions as MCP tools in `lib/mcp/server.py`. The agent will automatically discover and use them on the next startup.

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
