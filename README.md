# Autonomous Multi-Agent Analytics Platform

[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-FF6F00?logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![LangChain](https://img.shields.io/badge/Framework-LangChain-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/)
[![Langfuse](https://img.shields.io/badge/Observability-Langfuse-000000?logo=langfuse&logoColor=white)](https://langfuse.com/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL_16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Containers-Docker_Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![React 19](https://img.shields.io/badge/Frontend-React_19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/Language-TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

An autonomous multi-agent platform for natural language analytics over relational databases, SQL query generation, automated statistical modeling, interactive visualizations, and sandboxed dataset ingestion.

## 1. System Architecture

The platform uses a distributed, modular architecture where agents are coordinated via **LangGraph**, and inter-agent tool execution is standardized over the **Model Context Protocol (MCP)**:

```mermaid
flowchart TD
    User([User]) <--> Frontend["Frontend"]
    Frontend <-->|REST API + SSE| Backend["Backend Gateway"]
    
    Backend <-->|RPC / MCP| AIService["AI Service"]
    Backend <-->|Session Schemas| Postgres[("PostgreSQL")]
    
    subgraph AI["AI Agents Service"]
        Orchestrator["Orchestrator Agent"]
        MCPTools["MCP Tools"]
        DBAgent["DB Agent"]
        MLAgent["ML Agent"]
        
        Orchestrator --> MCPTools
        MCPTools --> DBAgent
        MCPTools --> MLAgent
    end
    
    AIService --- AI
    AIService -.-> Langfuse[("Langfuse")]
    Backend -.-> Langfuse
```

## 2. Module Directory

Each subsystem includes dedicated documentation detailing its state graph, prompt policies, and tool specifications:

| Module | Scope & Responsibility | Documentation |
| :--- | :--- | :---: |
| **`agents/orchestrator`** | Central supervisor, intent routing, direct algorithmic reasoning, multi-agent synthesis | [README](agents/orchestrator/README.md) |
| **`agents/db_agent`** | Dynamic schema reflection, SQL query generation, table mutations, transactional rollbacks, file ingestion | [README](agents/db_agent/README.md) |
| **`agents/ml_agent`** | Statistical analysis, clustering, sandboxed Python code execution, interactive visualizations | [README](agents/ml_agent/README.md) |
| **`backend`** | FastAPI REST gateway, SSE streaming, multi-tenant session schemas (`session_<uuid>`), artifact management | [README](backend/README.md) |
| **`frontend`** | React 19 + TypeScript + Vite studio with split-view workspace (Data Table, Plotly Charts, Code Inspector) | [README](frontend/README.md) |
| **`shared`** | Unified LLM provider factory (Gemini), Langfuse tracing wrappers, domain metadata schemas, connection pool | [README](shared/README.md) |
| **`tests`** | Automated 6-scenario evaluation suite (Onboarding, SQL, ML, Mutations, Robustness, Ingestion) with Langfuse scoring | [README](tests/README.md) |

## 3. Quickstart (Docker Compose)

#### Step 1. Clone & Configure Environment
```bash
git clone https://github.com/your-username/multi-agent-system.git
cd multi-agent-system
cp .env.example .env
```

Set your Gemini API key in `.env`:
```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-flash-lite-latest
LLM_API_KEY=...
```

#### Step 2. Build and Start Services
```bash
docker compose up --build -d
```

#### Step 3. Access Endpoints
* **Web Studio**: [http://localhost:8080](http://localhost:8080)
* **Backend API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Langfuse Tracing Dashboard**: [http://localhost:3000](http://localhost:3000)

## 4. Automated Evaluation & Testing

Run the end-to-end evaluation suite across all benchmark scenarios:

#### Step 1. Run Complete Evaluation Suite
```bash
uv run pytest tests/eval/test_eval_suite.py -v
```

#### Step 2. Run Individual Scenario
```bash
uv run pytest tests/eval/test_eval_suite.py -k "sql_analytics" -v -s
```

Detailed scenario definitions and scoring policies are available in [tests/README.md](tests/README.md).
