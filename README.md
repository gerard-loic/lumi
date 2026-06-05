![alt text](https://raw.githubusercontent.com/gerard-loic/lumi/refs/heads/master/public/cover.jpg?raw=true)

# Lumi

Lumi is an open-source AI chatbot backend built on top of **FastAPI** and the **Model Context Protocol (MCP)**. It exposes a streaming chat API that connects a Large Language Model to a set of custom tools, enabling the agent to answer questions grounded in real data rather than hallucinated knowledge.

## What it does

- **Streaming chat endpoint** — answers are delivered as Server-Sent Events (SSE) so the client can display tokens as they arrive.
- **MCP tool integration** — tools are registered as MCP tools. The agent calls them automatically when it needs real data to answer a question.
- **Configurable LLM backend** — uses LiteLLM under the hood, so you can point it at any compatible model (OpenAI, Azure, local models, etc.) by changing a config value.
- **Authentication** — a JWT-based `/auth` endpoint protects the chat API and temporary file downloads.
- **Temporary file serving** — tools can produce files (e.g. Excel exports) that are made available for download through a secure, time-limited URL.

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
