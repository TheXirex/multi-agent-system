import React, { useEffect, useRef } from 'react';
import Plotly from 'plotly.js-dist-min';

interface PlotlyChartProps {
  spec: Record<string, any>;
  title?: string;
  chartType?: string;
}

function isRawColorTitle(val: unknown): boolean {
  if (typeof val !== 'string') return false;
  let s = val.trim().toLowerCase();
  if (s.startsWith('<b>') && s.endsWith('</b>')) {
    s = s.slice(3, -4).trim();
  }
  if (s.startsWith('<span>') && s.endsWith('</span>')) {
    s = s.slice(6, -7).trim();
  }
  return s === 'color' || s === 'colour' || s === 'color:' || s === 'colour:';
}

function cleanLegendLayout(targetLayout: Record<string, any>) {
  if (!targetLayout || typeof targetLayout !== 'object') return;

  if (targetLayout.legend && typeof targetLayout.legend === 'object') {
    const lTitle = targetLayout.legend.title;
    if (lTitle && typeof lTitle === 'object') {
      if (isRawColorTitle(lTitle.text)) {
        lTitle.text = '';
      }
    } else if (isRawColorTitle(lTitle)) {
      targetLayout.legend.title = '';
    }
  }

  if (isRawColorTitle(targetLayout.legend_title_text)) {
    targetLayout.legend_title_text = '';
  }

  if (targetLayout.legend_title && typeof targetLayout.legend_title === 'object') {
    if (isRawColorTitle(targetLayout.legend_title.text)) {
      targetLayout.legend_title.text = '';
    }
  } else if (isRawColorTitle(targetLayout.legend_title)) {
    targetLayout.legend_title = '';
  }
}

function sanitizePlotlyLayout(spec: Record<string, any>): Record<string, any> {
  if (!spec || typeof spec !== 'object') return spec;
  const cloned = JSON.parse(JSON.stringify(spec));

  const layout = cloned.layout || {};
  layout.autosize = true;
  delete layout.width;
  layout.paper_bgcolor = '#212529';
  layout.plot_bgcolor = '#212529';
  layout.font = { color: '#f8f9fa', family: 'inherit', ...(layout.font || {}) };

  cleanLegendLayout(layout);

  if (layout.template && typeof layout.template === 'object') {
    const tLayout = layout.template.layout || {};
    tLayout.paper_bgcolor = '#212529';
    tLayout.plot_bgcolor = '#212529';
    tLayout.font = { color: '#f8f9fa', ...(tLayout.font || {}) };
    cleanLegendLayout(tLayout);
  }

  // Clear uninformative colorbar titles and sanitize hover tooltips
  if (Array.isArray(cloned.data)) {
    cloned.data.forEach((trace: any) => {
      if (trace && typeof trace === 'object') {
        if (trace.marker && typeof trace.marker === 'object') {
          const colorbar = trace.marker.colorbar;
          if (colorbar && typeof colorbar === 'object') {
            if (colorbar.title && typeof colorbar.title === 'object') {
              if (isRawColorTitle(colorbar.title.text)) {
                colorbar.title.text = '';
              }
            } else if (isRawColorTitle(colorbar.title)) {
              colorbar.title = '';
            }
          }
        }

        // For box plots, ensure clean quartile statistics without legend clutter
        if (trace.type === 'box') {
          if (
            !trace.hovertemplate ||
            trace.hovertemplate.includes('%{max}') ||
            trace.hovertemplate.includes('%{q3}') ||
            trace.hovertemplate.includes('%{y}<extra></extra>')
          ) {
            delete trace.hovertemplate;
            const hasX = trace.x && (Array.isArray(trace.x) ? trace.x.length > 0 : true);
            trace.hoverinfo = hasX ? 'x+y' : 'y';
          }
        }

        // Strip secondary legend box from hovertemplate if present without <extra>
        if (typeof trace.hovertemplate === 'string') {
          if (!trace.hovertemplate.includes('<extra>')) {
            trace.hovertemplate = trace.hovertemplate + '<extra></extra>';
          } else if (
            trace.hovertemplate.includes('<extra>%{') ||
            (trace.name && trace.hovertemplate.includes('<extra>' + trace.name + '</extra>'))
          ) {
            trace.hovertemplate = trace.hovertemplate.split('<extra>')[0] + '<extra></extra>';
          }
        }

        // If hoverinfo includes 'name', remove 'name' so legend trace name does not appear in tooltip
        if (typeof trace.hoverinfo === 'string' && trace.hoverinfo.includes('name')) {
          const parts = trace.hoverinfo.split('+').filter((p: string) => p !== 'name');
          trace.hoverinfo = parts.length > 0 ? parts.join('+') : 'x+y';
        }
      }
    });
  }

  // Clear title inside Plotly canvas so it's only rendered above the chart in the UI
  if (layout.title) {
    if (typeof layout.title === 'object') {
      layout.title = { ...layout.title, text: '' };
    } else {
      layout.title = '';
    }
  }
  if (!layout.margin) {
    layout.margin = { t: 24, r: 20, b: 44, l: 48 };
  } else {
    layout.margin.t = Math.min(layout.margin.t || 24, 28);
  }

  // Adjust axes for dark theme readability
  Object.keys(layout).forEach((k) => {
    if (k.startsWith('xaxis') || k.startsWith('yaxis')) {
      const axis = layout[k];
      if (axis && typeof axis === 'object') {
        axis.gridcolor = axis.gridcolor || '#343a40';
        axis.zerolinecolor = axis.zerolinecolor || '#495057';
        axis.linecolor = axis.linecolor || '#495057';
        axis.tickcolor = axis.tickcolor || '#6c757d';
        axis.tickfont = { color: '#ced4da', ...(axis.tickfont || {}) };
        axis.titlefont = { color: '#f8f9fa', ...(axis.titlefont || {}) };
      }
    }
  });

  cloned.layout = layout;
  return cloned;
}

export const PlotlyChart: React.FC<PlotlyChartProps> = ({ spec, title }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const sanitized = sanitizePlotlyLayout(spec);
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

  const layoutTitle = spec?.layout?.title;
  const specTitle =
    typeof layoutTitle === 'object'
      ? layoutTitle?.text
      : typeof layoutTitle === 'string'
      ? layoutTitle
      : null;
  const displayTitle = title || specTitle || 'Interactive Visualization';

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
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <span
          style={{
            fontSize: '12px',
            fontWeight: 600,
            color: '#f8f9fa',
            fontFamily: 'var(--font-mono)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            maxWidth: '100%',
          }}
        >
          {displayTitle}
        </span>
      </div>
      <div ref={containerRef} style={{ width: '100%', minHeight: '380px' }} />
    </div>
  );
};
