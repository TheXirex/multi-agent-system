import React, { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';

interface PlotlyChartProps {
  spec: Record<string, any>;
  title?: string;
  chartType?: string;
}

const MONO_PALETTE = [
  '#f8f9fa',
  '#ced4da',
  '#adb5bd',
  '#6c757d',
  '#dee2e6',
  '#e9ecef',
  '#495057',
];

function sanitizePlotlyMonochrome(spec: Record<string, any>): Record<string, any> {
  if (!spec || typeof spec !== 'object') return spec;
  const cloned = JSON.parse(JSON.stringify(spec));

  const layout = cloned.layout || {};
  layout.autosize = true;
  delete layout.width;
  layout.paper_bgcolor = '#212529';
  layout.plot_bgcolor = '#212529';
  layout.font = { color: '#f8f9fa', family: 'inherit' };
  layout.colorway = MONO_PALETTE;

  if (layout.template && typeof layout.template === 'object') {
    const tLayout = layout.template.layout || {};
    tLayout.colorway = MONO_PALETTE;
    tLayout.paper_bgcolor = '#212529';
    tLayout.plot_bgcolor = '#212529';
    tLayout.font = { color: '#f8f9fa' };
  } else {
    delete layout.template;
  }

  // Adjust axes
  Object.keys(layout).forEach((k) => {
    if (k.startsWith('xaxis') || k.startsWith('yaxis')) {
      const axis = layout[k];
      if (axis && typeof axis === 'object') {
        axis.gridcolor = '#343a40';
        axis.zerolinecolor = '#495057';
        axis.linecolor = '#495057';
        axis.tickcolor = '#6c757d';
        axis.tickfont = { color: '#ced4da' };
        axis.titlefont = { color: '#f8f9fa' };
      }
    }
  });

  // Adjust traces
  const traces = cloned.data || [];
  if (Array.isArray(traces)) {
    traces.forEach((tr, i) => {
      if (!tr || typeof tr !== 'object') return;
      const monoColor = MONO_PALETTE[i % MONO_PALETTE.length];

      if (tr.marker && typeof tr.marker === 'object') {
        const mc = tr.marker.color;
        if (!mc || (typeof mc === 'string' && /636efa|1976d2|1f77b4|blue|cyan|indigo|#0000ff/i.test(mc))) {
          tr.marker.color = monoColor;
        }
        if (tr.marker.colorscale) {
          tr.marker.colorscale = 'Greys';
        }
      } else if (!tr.marker && ['scatter', 'bar', 'pie'].includes(tr.type)) {
        tr.marker = { color: monoColor };
      }

      if (tr.line && typeof tr.line === 'object') {
        const lc = tr.line.color;
        if (!lc || (typeof lc === 'string' && /636efa|1976d2|1f77b4|blue|cyan|indigo|#0000ff/i.test(lc))) {
          tr.line.color = monoColor;
        }
      } else if (!tr.line && ['scatter', 'scattergl', 'line'].includes(tr.type)) {
        tr.line = { color: monoColor };
      }
    });
  }

  cloned.layout = layout;
  cloned.data = traces;
  return cloned;
}

export const PlotlyChart: React.FC<PlotlyChartProps> = ({ spec, title, chartType }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const sanitized = sanitizePlotlyMonochrome(spec);
    const data = sanitized.data || [];
    const layout = sanitized.layout || {};
    const config = { responsive: true, displayModeBar: false, ...(sanitized.config || {}) };

    Plotly.newPlot(containerRef.current, data, layout, config);

    const handleResize = () => {
      if (containerRef.current) {
        Plotly.Plots.resize(containerRef.current);
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (containerRef.current) {
        Plotly.purge(containerRef.current);
      }
    };
  }, [spec]);

  return (
    <div
      style={{
        width: '100%',
        maxWidth: '100%',
        backgroundColor: '#212529',
        border: '1px solid rgba(73, 80, 87, 0.7)',
        borderRadius: '6px',
        padding: '14px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span
          style={{
            fontSize: '12px',
            fontWeight: 600,
            color: '#f8f9fa',
            fontFamily: 'var(--font-mono)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            maxWidth: '75%',
          }}
        >
          {title || 'Interactive Visualization'}
        </span>
        <span className="badge">{(chartType || 'PLOTLY').toUpperCase()}</span>
      </div>
      <div ref={containerRef} style={{ width: '100%', minHeight: '380px' }} />
    </div>
  );
};
