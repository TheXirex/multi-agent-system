import React, { useState, useEffect, useRef } from 'react';
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
import { PlotlyChart } from './PlotlyChart';
import { CodeViewer } from './CodeViewer';

interface WorkspaceProps {
  turns: TurnArtifacts[];
  currentTurnIndex: number;
  onSelectTurn: (index: number) => void;
  onScrollToMessage: (turnIndex: number) => void;
}

type TabType = 'table' | 'plots' | 'code';

export const Workspace: React.FC<WorkspaceProps> = ({
  turns,
  currentTurnIndex,
  onSelectTurn,
  onScrollToMessage,
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('table');
  const [tableSearch, setTableSearch] = useState('');
  const [tablePage, setTablePage] = useState(1);
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

  // Smart auto-tab switching when changing turns
  useEffect(() => {
    if (!activeTurn) return;
    if (activeTab === 'table' && hasTable) return;
    if (activeTab === 'plots' && hasPlots) return;
    if (activeTab === 'code' && hasCode) return;

    if (hasPlots) setActiveTab('plots');
    else if (hasTable) setActiveTab('table');
    else if (hasCode) setActiveTab('code');
  }, [currentTurnIndex, hasTable, hasPlots, hasCode]);

  // Reset table pagination when turn or dataset changes
  useEffect(() => {
    setTablePage(1);
    setTableSearch('');
  }, [currentTurnIndex, activeTurn?.datasetData?.id]);

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

  // Filtered rows for dataset table
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
  const paginatedRows = filteredRows.slice(
    (tablePage - 1) * rowsPerPage,
    tablePage * rowsPerPage
  );

  const bodyScrollRef = useRef<HTMLDivElement>(null);
  const [scrollGutter, setScrollGutter] = useState<number>(0);

  useEffect(() => {
    const el = bodyScrollRef.current;
    if (!el) return;

    const updateGutter = () => {
      const sw = Math.max(0, el.offsetWidth - el.clientWidth);
      setScrollGutter(sw);
    };

    updateGutter();
    const rafId = requestAnimationFrame(updateGutter);

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(updateGutter);
      resizeObserver.observe(el);
    }

    window.addEventListener('resize', updateGutter);

    return () => {
      cancelAnimationFrame(rafId);
      if (resizeObserver) resizeObserver.disconnect();
      window.removeEventListener('resize', updateGutter);
    };
  }, [activeTab, activeTurn]);

  return (
    <div className="panel-card">
      {/* 1. Header Row: Tabs + Badges + Turn Navigator */}
      <div
        style={{
          width: '100%',
          padding: '6px 10px',
          borderBottom: '1px solid rgba(73, 80, 87, 0.6)',
          backgroundColor: '#212529',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          flexShrink: 0,
        }}
      >
        {/* Left: Tab Switcher */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flex: 1 }}>
          <button
            onClick={() => setActiveTab('table')}
            style={{
              padding: '6px 12px',
              fontSize: '12px',
              fontWeight: 600,
              gap: '6px',
              color: activeTab === 'table' ? '#f8f9fa' : '#adb5bd',
              backgroundColor: activeTab === 'table' ? '#343a40' : 'transparent',
              border: activeTab === 'table' ? '1px solid #495057' : '1px solid transparent',
            }}
          >
            <TableIcon size={14} />
            <span>Table Data</span>
          </button>

          <button
            onClick={() => setActiveTab('plots')}
            style={{
              padding: '6px 12px',
              fontSize: '12px',
              fontWeight: 600,
              gap: '6px',
              color: activeTab === 'plots' ? '#f8f9fa' : '#adb5bd',
              backgroundColor: activeTab === 'plots' ? '#343a40' : 'transparent',
              border: activeTab === 'plots' ? '1px solid #495057' : '1px solid transparent',
            }}
          >
            <BarChart2 size={14} />
            <span>Visualizations</span>
          </button>

          <button
            onClick={() => setActiveTab('code')}
            style={{
              padding: '6px 12px',
              fontSize: '12px',
              fontWeight: 600,
              gap: '6px',
              color: activeTab === 'code' ? '#f8f9fa' : '#adb5bd',
              backgroundColor: activeTab === 'code' ? '#343a40' : 'transparent',
              border: activeTab === 'code' ? '1px solid #495057' : '1px solid transparent',
            }}
          >
            <CodeIcon size={14} />
            <span>Code & Scripts</span>
          </button>
        </div>

        {/* Turn Navigator controls */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '2px',
            backgroundColor: '#343a40',
            border: '1px solid #495057',
            padding: '2px 4px',
            borderRadius: 'var(--app-radius)',
            flexShrink: 0,
          }}
        >
          <button
            onClick={handlePrevTurn}
            disabled={currentTurnIndex <= 1}
            title="Previous message artifacts"
            style={{
              padding: '4px',
              color: currentTurnIndex > 1 ? '#f8f9fa' : '#6c757d',
            }}
          >
            <ChevronLeft size={16} />
          </button>

          <span
            style={{
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              fontWeight: 600,
              color: '#f8f9fa',
              padding: '0 6px',
              minWidth: '45px',
              textAlign: 'center',
              userSelect: 'none',
            }}
          >
            {totalTurns > 0 ? `${currentTurnIndex} / ${totalTurns}` : '0 / 0'}
          </span>

          <button
            onClick={handleNextTurn}
            disabled={currentTurnIndex >= totalTurns}
            title="Next message artifacts"
            style={{
              padding: '4px',
              color: currentTurnIndex < totalTurns ? '#f8f9fa' : '#6c757d',
            }}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {/* 2. Main Tab Body */}
      <div
        ref={bodyScrollRef}
        className="scroll-auto-hide"
        style={{
          flex: 1,
          overflowY: 'auto',
          paddingTop: '12px',
          paddingBottom: '12px',
          paddingLeft: '12px',
          paddingRight: `${Math.max(0, 12 - scrollGutter)}px`,
          minHeight: 0,
        }}
      >
        {/* ========================================================= */}
        {/* TAB 1: TABLE DATA */}
        {/* ========================================================= */}
        {activeTab === 'table' && (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            {!hasTable ? (
              <div
                style={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: '1px dashed rgba(73, 80, 87, 0.7)',
                  borderRadius: 'var(--app-radius)',
                  padding: '32px',
                  color: '#adb5bd',
                  textAlign: 'center',
                }}
              >
                <Database size={36} color="#6c757d" style={{ marginBottom: '8px' }} />
                <span style={{ fontSize: '14px', fontWeight: 600, color: '#ced4da' }}>
                  No tabular dataset for this message
                </span>
                <span style={{ fontSize: '12px', color: '#6c757d', marginTop: '4px' }}>
                  Ask a question to query database records, inspect tables, or upload a dataset.
                </span>
              </div>
            ) : (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  height: '100%',
                  backgroundColor: '#212529',
                  border: '1px solid rgba(73, 80, 87, 0.6)',
                  borderRadius: 'var(--app-radius)',
                  overflow: 'hidden',
                }}
              >
                {/* Table sub-toolbar: search & count */}
                <div
                  style={{
                    padding: '8px 12px',
                    borderBottom: '1px solid rgba(73, 80, 87, 0.6)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '12px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                    <span style={{ fontSize: '12px', fontWeight: 600, color: '#f8f9fa' }}>
                      {activeTurn?.datasetData?.name || 'Dataset'}
                    </span>
                    <span className="badge">
                      {filteredRows.length} {filteredRows.length === 1 ? 'row' : 'rows'}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '5px',
                        backgroundColor: '#343a40',
                        border: '1px solid #495057',
                        borderRadius: 'var(--app-radius)',
                        padding: '2px 6px',
                        maxWidth: '125px',
                      }}
                    >
                      <Search size={12} color="#adb5bd" style={{ flexShrink: 0 }} />
                      <input
                        type="text"
                        placeholder="Search records..."
                        value={tableSearch}
                        onChange={(e) => {
                          setTableSearch(e.target.value);
                          setTablePage(1);
                        }}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          boxShadow: 'none',
                          outline: 'none',
                          fontSize: '11px',
                          color: '#f8f9fa',
                          width: '95px',
                          padding: '1px 0',
                        }}
                      />
                    </div>
                  </div>
                </div>

                {/* Table Grid */}
                <div className="scroll-auto-hide" style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
                  <table
                    style={{
                      width: '100%',
                      borderCollapse: 'collapse',
                      fontSize: '12px',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    <thead>
                      <tr style={{ backgroundColor: '#1c1f23', position: 'sticky', top: 0, zIndex: 10 }}>
                        {columns.map((col, idx) => (
                          <th
                            key={idx}
                            title={col.label || col.name}
                            style={{
                              padding: '8px 12px',
                              textAlign: 'left',
                              color: '#ced4da',
                              fontWeight: 600,
                              borderBottom: '1px solid #495057',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {col.label || col.name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedRows.map((row, rIdx) => (
                        <tr
                          key={rIdx}
                          style={{
                            borderBottom: '1px solid rgba(73, 80, 87, 0.4)',
                            backgroundColor: rIdx % 2 === 0 ? 'rgba(52, 58, 64, 0.2)' : 'transparent',
                          }}
                        >
                          {columns.map((col, cIdx) => {
                            const rawVal = row[col.name];
                            const strVal = rawVal !== undefined && rawVal !== null ? String(rawVal) : null;
                            return (
                              <td
                                key={cIdx}
                                title={strVal !== null ? strVal : undefined}
                                style={{
                                  padding: '6px 12px',
                                  color: '#dee2e6',
                                  whiteSpace: 'nowrap',
                                  maxWidth: '240px',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                }}
                              >
                                {strVal !== null ? strVal : <span style={{ color: '#6c757d' }}>null</span>}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Table Pagination Bar */}
                <div
                  style={{
                    padding: '6px 12px',
                    borderTop: '1px solid rgba(73, 80, 87, 0.6)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontSize: '11px',
                    color: '#adb5bd',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span>Rows per page:</span>
                    <select
                      value={rowsPerPage}
                      onChange={(e) => {
                        setRowsPerPage(Number(e.target.value));
                        setTablePage(1);
                      }}
                      style={{
                        padding: '1px 4px',
                        fontSize: '11px',
                        background: '#343a40',
                        color: '#f8f9fa',
                        border: '1px solid #495057',
                      }}
                    >
                      <option value={10}>10</option>
                      <option value={15}>15</option>
                      <option value={25}>25</option>
                      <option value={50}>50</option>
                    </select>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>
                      Page {tablePage} of {totalPages}
                    </span>
                    <button
                      onClick={() => setTablePage((p) => Math.max(1, p - 1))}
                      disabled={tablePage <= 1}
                      style={{ padding: '2px 6px', background: '#343a40', border: '1px solid #495057' }}
                    >
                      Prev
                    </button>
                    <button
                      onClick={() => setTablePage((p) => Math.min(totalPages, p + 1))}
                      disabled={tablePage >= totalPages}
                      style={{ padding: '2px 6px', background: '#343a40', border: '1px solid #495057' }}
                    >
                      Next
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ========================================================= */}
        {/* TAB 2: VISUALIZATIONS */}
        {/* ========================================================= */}
        {activeTab === 'plots' && (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            {!hasPlots ? (
              <div
                style={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: '1px dashed rgba(73, 80, 87, 0.7)',
                  borderRadius: 'var(--app-radius)',
                  padding: '32px',
                  color: '#adb5bd',
                  textAlign: 'center',
                }}
              >
                <BarChart2 size={36} color="#6c757d" style={{ marginBottom: '8px' }} />
                <span style={{ fontSize: '14px', fontWeight: 600, color: '#ced4da' }}>
                  No interactive charts for this message
                </span>
                <span style={{ fontSize: '12px', color: '#6c757d', marginTop: '4px' }}>
                  Ask for an interactive visualization, distribution, correlation, or clustering model plot.
                </span>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
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

        {/* ========================================================= */}
        {/* TAB 3: CODE & SCRIPTS */}
        {/* ========================================================= */}
        {activeTab === 'code' && (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            {!hasCode ? (
              <div
                style={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: '1px dashed rgba(73, 80, 87, 0.7)',
                  borderRadius: 'var(--app-radius)',
                  padding: '32px',
                  color: '#adb5bd',
                  textAlign: 'center',
                }}
              >
                <Terminal size={36} color="#6c757d" style={{ marginBottom: '8px' }} />
                <span style={{ fontSize: '14px', fontWeight: 600, color: '#ced4da' }}>
                  No scripts or queries for this message
                </span>
                <span style={{ fontSize: '12px', color: '#6c757d', marginTop: '4px' }}>
                  Code and SQL statements generated by agents appear here.
                </span>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {activeTurn?.pythonScript && (
                  <CodeViewer
                    code={activeTurn.pythonScript}
                    language="python"
                    title={
                      activeTurn.metadata?.code_title ||
                      activeTurn.metadata?.task_description ||
                      "Machine Learning Python Script"
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
                      "PostgreSQL Query Statement"
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
