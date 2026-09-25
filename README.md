# Multi-Agent System

A modular multi-agent platform featuring shared LLM integrations and domain-specific agents.

## Architecture

- **`pyproject.toml`**: Root-level project configuration and dependency management.
- **`shared/`**: Common package containing the LLM interface and factory (`LLMFactory`, `GeminiLLM`, `BaseLLM`).
- **`agents/db_agent/`**: Database agent built on **LangChain** and **LangGraph** (`StateGraph`) that inspects PostgreSQL schema, generates SQL queries, executes them, and exports results to CSV via an extensible tool registry.
- **`docker/postgres/init.sql`**: PostgreSQL initialization script with sample e-commerce data.
- **`docker-compose.yml`**: Compose configuration orchestrating the PostgreSQL database and `db-agent`.
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

```bash
# Start Postgres in background
docker compose up -d postgres

# Build DB Agent image
docker compose build db-agent

# Run DB Agent interactively
docker compose run --rm db-agent

# Or run a single query directly
docker compose run --rm db-agent python -m agents.db_agent.main --query "Find top 3 customers by total order amount"
```

### 3. Local Run (CLI)

```bash
python -m agents.db_agent.main --query "Show all completed orders"
```

### 4. Run as MCP Server

To expose the agent and its tools via the Model Context Protocol (STDIO transport):

```bash
python -m agents.db_agent.mcp_server
```

Registered MCP Tools:
- `query_and_analyze_database(user_input: str)`: Analyzes database, executes generated SQL, exports CSV, and returns structured response (`response`, `metadata.table`, `metadata.code`).
- `execute_sql_to_csv(query: str, filename: str)`: Executes raw SQL and exports to CSV.
- `get_database_schema()`: Returns tables and full schema summary.