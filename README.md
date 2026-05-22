# AI Driven App Test Platform MVP

A deployable MVP for AI-assisted mobile app testing. It uses Maestro as the first automation executor while keeping an internal Test Case DSL, so Appium, Playwright, or device-cloud executors can be added later.

## Display

<img width="1715" height="980" alt="image" src="https://github.com/user-attachments/assets/ef5e5dc7-7b90-4765-b950-9a8b23164bab" />
<img width="1715" height="980" alt="image" src="https://github.com/user-attachments/assets/dd9417c5-6214-4f71-be01-a5129a2e7cff" />
<img width="1715" height="980" alt="image" src="https://github.com/user-attachments/assets/c5d69ddb-0f98-446d-a838-ec0a4dce4ec0" />




## Capabilities

- Upload Figma MCP context and Figma design images
- Retrieve related context with the built-in lightweight RAG layer
- Generate structured test cases and persist them in SQLite
- Convert internal Test Case DSL into Maestro YAML flows
- Select regression cases from changed features, screens, and change summaries
- Run in dry-run mode or call the local Maestro CLI
- Generate HTML test reports
- Provide a built-in Web UI and REST API

## Quick Start

Recommended npm entrypoint:

```bash
npm run setup
npm run dev
```

Open:

```text
http://127.0.0.1:8080
```

You can also run the Python server directly:

```bash
python3 -m ai_test_platform.server
```

Default database file:

```text
./data/app.db
```

## Design

See [DESIGN.md](./DESIGN.md) for the current workflow, architecture, data model, RAG approach, Maestro execution path, and project memory design.

## Docker

```bash
docker build -t ai-app-test-platform .
docker run --rm -p 8080:8080 -v "$PWD/data:/app/data" ai-app-test-platform
```

## Maestro Execution

The default execution mode is dry-run, so the platform can run even without a device or Maestro CLI.

If Maestro is installed locally and you want real execution:

```bash
npm run dev:maestro
```

The runner writes flows to:

```text
./data/maestro_flows
```

Then it attempts to run:

```bash
maestro test <flow-file>
```

Maestro CLI is an optional dependency. Official installation options include:

```bash
curl -fsSL "https://get.maestro.mobile.dev" | bash
```

On macOS, Homebrew is also available:

```bash
brew tap mobile-dev-inc/tap
brew install mobile-dev-inc/tap/maestro
```

Real Maestro execution also requires Java 17+ and a running Android Emulator, iOS Simulator, or connected device.

## Dependencies

This MVP has no third-party Python dependency. The HTTP server, SQLite storage, lightweight RAG layer, and OpenAI API calls are implemented with the Python standard library, so `npm install` does not download any runtime packages.

## Figma-Only MVP Mode

The current MVP intentionally focuses on Figma-driven testing. PRD ingestion is hidden from the UI and the generator no longer creates PRD/Figma alignment cases.

Recommended flow:

1. Use Cursor or another MCP-capable tool to connect to Figma MCP.
2. Export one or more Figma design screens as PNG/JPG/WebP.
3. Upload all design images in the Web UI.
4. If `OPENAI_API_KEY` is set, uploaded Figma images are parsed by OpenAI vision into source models.
5. Generate test cases from the Figma design context.
6. Generate Maestro flows and run them with `npm run dev:maestro`.

Without `OPENAI_API_KEY`, uploaded images are stored as AI-ready artifacts and the system falls back to rule-based generation.

`LlamaIndex`, `pgvector`, and `LangGraph` are production-upgrade recommendations, not required by the current MVP. For a production version, a likely stack is:

```text
FastAPI + LlamaIndex + PostgreSQL/pgvector + LangGraph/Temporal
```

## AI Configuration

The platform uses real AI only when `OPENAI_API_KEY` is set. Without it, test case generation falls back to the deterministic rule-based generator.

```bash
export OPENAI_API_KEY=...
export AI_MODEL=gpt-4.1-mini
npm run dev
```

Current AI usage:

- OpenAI Responses API
- Structured Outputs with JSON Schema
- RAG context + Figma/design context -> structured Test Case DSL

Status endpoint:

```text
GET /api/ai/status
```

## API Summary

- `GET /api/health`
- `GET /api/ai/status`
- `POST /api/documents`
- `GET /api/documents`
- `POST /api/source-files`
- `GET /api/source-files`
- `POST /api/figma/mcp-context`
- `GET /api/figma/artifacts`
- `POST /api/generate-cases`
- `GET /api/test-cases`
- `GET /api/memory`
- `GET /api/memory/context`
- `POST /api/source-models`
- `GET /api/source-models`
- `POST /api/change-sets`
- `POST /api/case-suggestions`
- `POST /api/test-cases/{id}/approve`
- `POST /api/test-cases/{id}/maestro`
- `POST /api/regression/select`
- `POST /api/runs`
- `GET /api/runs/{id}`
- `GET /api/reports/{run_id}.html`

## Thanks

[Maestro](https://github.com/mobile-dev-inc/maestro)

[Codex](https://openai.com/codex/)
