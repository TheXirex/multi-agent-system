# Multi-Agent System

A modular multi-agent platform featuring shared LLM integrations and domain-specific agents.

## Architecture

- **`pyproject.toml`**: Root-level project configuration and dependency management.
- **`shared/`**: Common package containing the LLM interface and factory (`LLMFactory`, `GeminiLLM`, `BaseLLM`).
- **`agents/orchestrator/`**: Central Orchestrator Agent acting as an **MCP Client**. Directly answers conversational requests and coordinates specialized tool execution across domain agents via MCP, preserving structured metadata (CSV tables and SQL queries).
- **`agents/db_agent/`**: Database agent built on **LangChain** and **LangGraph** (`StateGraph`) that inspects PostgreSQL schema, generates SQL queries, executes them, and exports results to CSV via an extensible tool registry. Exposes tools through MCP via `mcp_server.py`.
- **`docker/postgres/init.sql`**: PostgreSQL initialization script with sample e-commerce data.
- **`docker-compose.yml`**: Compose configuration orchestrating PostgreSQL (`postgres-db`), AI Orchestrator service (`ai-service`), and NiceGUI split-view UI (`frontend`).
- **`output/`**: Directory where generated CSV files are saved.

## Environment & Dependency Management (`uv`)

Create the virtual environment and install all packages in editable mode:

```bash
# Create venv
uv venv .venv

# Activate venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies and project in editable mode
uv pip install -e .
```

## Quickstart

### 1. Configure Environment

Copy `.env.example` to `.env` and set your LLM configuration:

```bash
cp .env.example .env
```

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash-lite
LLM_API_KEY=your_actual_api_key
```

### 2. Run with Docker Compose

Start all services (`postgres`, `ai` backend with all agents, and `ui` frontend):

```bash
# Using make.bat (Windows):
make up

# Or directly with Docker Compose:
docker compose up --build
```

Services:
- **`postgres`**: Database on `localhost:5432`
- **`ai`**: Central AI service (FastAPI) on `localhost:8000` (`http://localhost:8000/api/query`, `http://localhost:8000/health`)
- **`ui`**: Frontend Web UI on `http://localhost:8080`

### 3. Run AI Service (FastAPI)

Run the backend AI service exposing the Orchestrator over HTTP:

```bash
python -m agents.api
```

Or query the endpoint directly:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Find top 3 customers by total order amount"}'
```

### 5. Run as MCP Server

To expose the agent and its tools via the Model Context Protocol (STDIO transport):

```bash
python -m agents.db_agent.mcp_server
```

Registered MCP Tools:
- `query_and_analyze_database(user_input: str)`: Analyzes database, executes generated SQL, exports CSV, and returns structured response (`response`, `metadata.table`, `metadata.code`).
- `execute_sql_to_csv(query: str, filename: str)`: Executes raw SQL and exports to CSV.
- `get_database_schema()`: Returns tables and full schema summary.

### 5. Run Web UI (NiceGUI)

Launch the interactive split-view UI featuring natural language chat and real-time query result table widget:

```bash
# Run as Compose service
docker compose up frontend

# Or in detached mode in background
docker compose up -d frontend

# Or run locally (virtual environment)
python -m ui.app
```

Then open `http://localhost:8080` in your web browser.