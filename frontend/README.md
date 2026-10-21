# Multi-Agent Studio - Frontend

Modern, reactive web interface built with React 19, TypeScript, and Vite for autonomous agent orchestration, SQL data querying, interactive visualizations, and script inspection.

## Architecture

- **Framework**: Vite + React 19 (TypeScript)
- **Styling**: Vanilla CSS design system with strict monochrome grayscale palette (`src/index.css`)
- **Key Libraries**:
  - `lucide-react`: Lightweight iconography
  - `plotly.js-dist-min`: Interactive charts & plots
  - `marked`: Markdown rendering for LLM responses
  - `prismjs`: Syntax highlighting for Python and SQL

## Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── Header.tsx        # Studio brand, sidebar toggle, busy spinner
│   │   ├── Sidebar.tsx       # Session history, inline rename, delete confirmation modal
│   │   ├── Chat.tsx          # Message stream, query input, file attachments, turn restore
│   │   ├── Workspace.tsx     # Table data, visualizations, and code tabs with turn navigation
│   │   ├── PlotlyChart.tsx   # Responsive interactive chart renderer
│   │   └── CodeViewer.tsx    # Python and SQL syntax highlighted code viewer
│   ├── services/
│   │   └── api.ts            # REST API client for backend communication
│   ├── utils/
│   │   └── formatters.ts     # Title truncation & text formatting helpers
│   ├── types.ts              # TypeScript interfaces and data models
│   ├── index.css             # Monochrome dark theme tokens and utility classes
│   ├── App.tsx               # Main application controller and state orchestrator
│   └── main.tsx              # React DOM entry point
├── public/
│   └── favicon.svg           # Studio SVG icon
├── Dockerfile                # Containerized Vite dev server
└── vite.config.ts            # Vite config with backend proxy to :8000
```

## Running Locally

```bash
npm install
npm run dev
```

Build for production:
```bash
npm run build
```
