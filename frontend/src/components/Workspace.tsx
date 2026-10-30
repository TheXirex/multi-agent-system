import React, { useState, useRef } from 'react';
import type { TurnArtifacts } from '../types';
import {
  Table as TableIcon,
  BarChart2,
  Code as CodeIcon,
  ChevronLeft,
  ChevronRight,
  Search,
  Database,
  Terminal,
} from 'lucide-react';
import { useScrollGutter } from '../utils/scrollAutoHide';
import { PlotlyChart } from './PlotlyChart';
import { CodeViewer } from './CodeViewer';

interface WorkspaceProps {
  turns: TurnArtifacts[];
  currentTurnIndex: number;
  onSelectTurn: (index: number) => void;
  onScrollToMessage: (turnIndex: number) => void;
}

type TabType = 'table' | 'plots' | 'code';

interface EmptyTabStateProps {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
}

const EmptyTabState: React.FC<EmptyTabStateProps> = ({ icon, title, subtitle }) => (
  <div className="empty-state">
    {icon}
    <span className="empty-state-title">{title}</span>
    <span className="empty-state-subtitle">{subtitle}</span>
  </div>
);

function resolvePreferredTab(
  currentTab: TabType,
  hasTable: boolean,
  hasPlots: boolean,
  hasCode: boolean
): TabType {
  if (currentTab === 'table' && hasTable) return 'table';
  if (currentTab === 'plots' && hasPlots) return 'plots';
  if (currentTab === 'code' && hasCode) return 'code';
  if (hasPlots) return 'plots';
  if (hasTable) return 'table';
  if (hasCode) return 'code';
  return currentTab;
}

export const Workspace: React.FC<WorkspaceProps> = ({
  turns,
  currentTurnIndex,
  onSelectTurn,
  onScrollToMessage,
}) => {
  const [tabState, setTabState] = useState<{ tab: TabType; turnIndex: number }>({
    tab: 'table',
    turnIndex: currentTurnIndex,
  });
  const [searchState, setSearchState] = useState<{ query: string; page: number; turnIndex: number }>({
    query: '',
    page: 1,
    turnIndex: currentTurnIndex,
  });
  const [rowsPerPage, setRowsPerPage] = useState(15);

  const totalTurns = turns.length;
  const activeTurn: TurnArtifacts | undefined =
    currentTurnIndex > 0 && currentTurnIndex <= totalTurns
      ? turns[currentTurnIndex - 1]
      : undefined;

  const hasTable = Boolean(activeTurn?.datasetData?.rows && activeTurn.datasetData.rows.length > 0);
  const hasPlots = Boolean(activeTurn?.chartsData && activeTurn.chartsData.length > 0);
  const hasCode = Boolean(
    (activeTurn?.pythonScript && activeTurn.pythonScript.trim()) ||
      (activeTurn?.sqlQuery && activeTurn.sqlQuery.trim())
  );

  const activeTab: TabType =
    tabState.turnIndex === currentTurnIndex
      ? tabState.tab
      : resolvePreferredTab(tabState.tab, hasTable, hasPlots, hasCode);

  const setActiveTab = (tab: TabType) => {
    setTabState({ tab, turnIndex: currentTurnIndex });
  };

  const tableSearch = searchState.turnIndex === currentTurnIndex ? searchState.query : '';
  const rawTablePage = searchState.turnIndex === currentTurnIndex ? searchState.page : 1;

  const handlePrevTurn = () => {
    if (currentTurnIndex > 1) {
      const nextIdx = currentTurnIndex - 1;
      onSelectTurn(nextIdx);
      onScrollToMessage(nextIdx);
    }
  };

  const handleNextTurn = () => {
    if (currentTurnIndex < totalTurns) {
      const nextIdx = currentTurnIndex + 1;
      onSelectTurn(nextIdx);
      onScrollToMessage(nextIdx);
    }
  };

  const allRows = activeTurn?.datasetData?.rows || [];
  const columns = activeTurn?.datasetData?.columns || [];

  const filteredRows = tableSearch.trim()
    ? allRows.filter((r) =>
        Object.values(r).some((val) =>
          String(val).toLowerCase().includes(tableSearch.toLowerCase())
        )
      )
    : allRows;

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / rowsPerPage));
  const tablePage = Math.min(rawTablePage, totalPages);
  const paginatedRows = filteredRows.slice(
    (tablePage - 1) * rowsPerPage,
    tablePage * rowsPerPage
  );

  const bodyScrollRef = useRef<HTMLDivElement>(null);
  const scrollGutter = useScrollGutter(bodyScrollRef, `${activeTab}-${currentTurnIndex}`, 0);

  return (
    <div className="panel-card">
      <div className="workspace-header">
        <div className="workspace-tabs">
          <button
            onClick={() => setActiveTab('table')}
            className={`tab-btn ${activeTab === 'table' ? 'active' : ''}`}
          >
            <TableIcon size={14} />
            <span>Table Data</span>
          </button>

          <button
            onClick={() => setActiveTab('plots')}
            className={`tab-btn ${activeTab === 'plots' ? 'active' : ''}`}
          >
            <BarChart2 size={14} />
            <span>Visualizations</span>
          </button>

          <button
            onClick={() => setActiveTab('code')}
            className={`tab-btn ${activeTab === 'code' ? 'active' : ''}`}
          >
            <CodeIcon size={14} />
            <span>Code & Scripts</span>
          </button>
        </div>

        <div className="turn-nav">
          <button
            onClick={handlePrevTurn}
            disabled={currentTurnIndex <= 1}
            title="Previous message artifacts"
            className="turn-nav-btn"
          >
            <ChevronLeft size={16} />
          </button>

          <span className="turn-nav-counter">
            {totalTurns > 0 ? `${currentTurnIndex} / ${totalTurns}` : '0 / 0'}
          </span>

          <button
            onClick={handleNextTurn}
            disabled={currentTurnIndex >= totalTurns}
            title="Next message artifacts"
            className="turn-nav-btn"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      <div
        ref={bodyScrollRef}
        className="scroll-auto-hide workspace-body"
        style={{ paddingRight: `${Math.max(0, 12 - scrollGutter)}px` }}
      >
        {activeTab === 'table' && (
          <div className="tab-pane">
            {!hasTable ? (
              <EmptyTabState
                icon={<Database size={36} color="#6c757d" />}
                title="No tabular dataset for this message"
                subtitle="Ask a question to query database records, inspect tables, or upload a dataset."
              />
            ) : (
              <div className="table-card">
                <div className="table-toolbar">
                  <div className="session-item-main">
                    <span className="agent-label">
                      {activeTurn?.datasetData?.name || 'Dataset'}
                    </span>
                    <span className="badge">
                      {filteredRows.length} {filteredRows.length === 1 ? 'row' : 'rows'}
                    </span>
                  </div>

                  <div className="table-search-box">
                    <Search size={12} color="#adb5bd" style={{ flexShrink: 0 }} />
                    <input
                      type="text"
                      placeholder="Search records..."
                      value={tableSearch}
                      onChange={(e) =>
                        setSearchState({
                          query: e.target.value,
                          page: 1,
                          turnIndex: currentTurnIndex,
                        })
                      }
                      className="table-search-input"
                    />
                  </div>
                </div>

                <div className="scroll-auto-hide" style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        {columns.map((col, idx) => (
                          <th key={idx} title={col.label || col.name}>
                            {col.label || col.name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedRows.map((row, rIdx) => (
                        <tr key={rIdx}>
                          {columns.map((col, cIdx) => {
                            const rawVal = row[col.name];
                            const strVal =
                              rawVal !== undefined && rawVal !== null ? String(rawVal) : null;
                            return (
                              <td key={cIdx} title={strVal !== null ? strVal : undefined}>
                                {strVal !== null ? strVal : <span style={{ color: '#6c757d' }}>null</span>}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="table-pagination">
                  <div className="chat-input-row" style={{ gap: '6px' }}>
                    <span>Rows per page:</span>
                    <select
                      value={rowsPerPage}
                      onChange={(e) => {
                        setRowsPerPage(Number(e.target.value));
                        setSearchState({
                          query: tableSearch,
                          page: 1,
                          turnIndex: currentTurnIndex,
                        });
                      }}
                      className="page-select"
                    >
                      <option value={10}>10</option>
                      <option value={15}>15</option>
                      <option value={25}>25</option>
                      <option value={50}>50</option>
                    </select>
                  </div>

                  <div className="chat-input-row">
                    <span>
                      Page {tablePage} of {totalPages}
                    </span>
                    <button
                      onClick={() =>
                        setSearchState({
                          query: tableSearch,
                          page: Math.max(1, tablePage - 1),
                          turnIndex: currentTurnIndex,
                        })
                      }
                      disabled={tablePage <= 1}
                      className="page-btn"
                    >
                      Prev
                    </button>
                    <button
                      onClick={() =>
                        setSearchState({
                          query: tableSearch,
                          page: Math.min(totalPages, tablePage + 1),
                          turnIndex: currentTurnIndex,
                        })
                      }
                      disabled={tablePage >= totalPages}
                      className="page-btn"
                    >
                      Next
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'plots' && (
          <div className="tab-pane">
            {!hasPlots ? (
              <EmptyTabState
                icon={<BarChart2 size={36} color="#6c757d" />}
                title="No interactive charts for this message"
                subtitle="Ask for an interactive visualization, distribution, correlation, or clustering model plot."
              />
            ) : (
              <div className="tab-stack">
                {activeTurn?.chartsData.map((ch, idx) => (
                  <PlotlyChart
                    key={idx}
                    spec={ch.spec}
                    title={ch.title}
                    chartType={ch.chart_type}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'code' && (
          <div className="tab-pane">
            {!hasCode ? (
              <EmptyTabState
                icon={<Terminal size={36} color="#6c757d" />}
                title="No scripts or queries for this message"
                subtitle="Code and SQL statements generated by agents appear here."
              />
            ) : (
              <div className="tab-stack">
                {activeTurn?.pythonScript && (
                  <CodeViewer
                    code={activeTurn.pythonScript}
                    language="python"
                    title={
                      activeTurn.metadata?.code_title ||
                      activeTurn.metadata?.task_description ||
                      'Machine Learning Python Script'
                    }
                  />
                )}
                {activeTurn?.sqlQuery && (
                  <CodeViewer
                    code={activeTurn.sqlQuery}
                    language="sql"
                    title={
                      activeTurn.metadata?.sql_description ||
                      activeTurn.datasetData?.name ||
                      'PostgreSQL Query Statement'
                    }
                  />
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
