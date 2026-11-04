import React, { useEffect, useRef, useState } from 'react';
import Plotly from 'plotly.js-dist-min';
import { BarChart2, Check, ChevronDown, ChevronRight, Copy } from 'lucide-react';

interface PlotlyChartProps {
  spec: Record<string, any>;
  title?: string;
  chartType?: string;
  collapsible?: boolean;
  defaultExpanded?: boolean;
}

function applyDarkThemeLayout(spec: Record<string, any>): Record<string, any> {
  if (!spec || typeof spec !== 'object') return spec;
  const cloned = JSON.parse(JSON.stringify(spec));

  const layout = cloned.layout || {};
  layout.autosize = true;
  delete layout.width;
  layout.paper_bgcolor = 'rgba(0,0,0,0)';
  layout.plot_bgcolor = 'rgba(0,0,0,0)';
  layout.font = { color: '#f8f9fa', family: 'inherit', ...(layout.font || {}) };
  layout.colorway = ['#8b5cf6', '#f97316', '#06b6d4', '#10b981', '#f59e0b', '#ec4899', '#6366f1', '#14b8a6'];

  if (layout.template && typeof layout.template === 'object') {
    const tLayout = layout.template.layout || {};
    tLayout.paper_bgcolor = 'rgba(0,0,0,0)';
    tLayout.plot_bgcolor = 'rgba(0,0,0,0)';
    tLayout.font = { color: '#f8f9fa', ...(tLayout.font || {}) };
    tLayout.colorway = layout.colorway;
  }

  if (layout.title) {
    layout.title = typeof layout.title === 'object' ? { ...layout.title, text: '' } : '';
  }

  const is3D =
    Boolean(layout.scene) ||
    (Array.isArray(cloned.data) && cloned.data.some((d: any) => d && d.type === 'scatter3d'));

  if (is3D) {
    layout.margin = {
      l: Math.max(layout.margin?.l || 0, 30),
      r: Math.max(layout.margin?.r || 0, 30),
      t: Math.max(layout.margin?.t || 0, 30),
      b: Math.max(layout.margin?.b || 0, 20),
    };
  } else if (!layout.margin) {
    layout.margin = { t: 24, r: 20, b: 44, l: 48 };
  } else {
    layout.margin.t = Math.min(layout.margin.t || 24, 28);
  }

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

  if (layout.scene && typeof layout.scene === 'object') {
    const scene = layout.scene;
    ['xaxis', 'yaxis', 'zaxis'].forEach((k) => {
      const axis = scene[k] || {};
      axis.gridcolor = axis.gridcolor || '#343a40';
      axis.zerolinecolor = axis.zerolinecolor || '#495057';
      axis.linecolor = axis.linecolor || '#495057';
      axis.tickcolor = axis.tickcolor || '#6c757d';
      axis.tickfont = { size: 11, color: '#ced4da', ...(axis.tickfont || {}) };
      axis.backgroundcolor = axis.backgroundcolor || 'rgba(52, 58, 64, 0.4)';
      axis.showbackground = axis.showbackground !== undefined ? axis.showbackground : true;

      const rawTitle = axis.title;
      const titleObj =
        typeof rawTitle === 'string'
          ? { text: rawTitle }
          : typeof rawTitle === 'object' && rawTitle !== null
          ? rawTitle
          : {};
      const currentFontSize = titleObj.font?.size ? Number(titleObj.font.size) : 0;
      axis.title = {
        ...titleObj,
        text: titleObj.text ? String(titleObj.text).split('_').join(' ') : axis.title,
        font: {
          ...(titleObj.font || {}),
          size: Math.max(currentFontSize, 16),
          color: '#f8f9fa',
          weight: 600,
        },
      };
      scene[k] = axis;
    });

    if (!scene.camera || !scene.camera.eye) {
      scene.camera = { eye: { x: 1.35, y: 1.35, z: 1.15 } };
    }
    if (!scene.aspectmode) {
      scene.aspectmode = 'cube';
    }
  }

  if (Array.isArray(cloned.data)) {
    cloned.data.forEach((trace: any) => {
      if (trace && trace.type === 'scatter3d') {
        trace.type = 'scatter';
        delete trace.z;
        trace.marker = trace.marker || {};
        trace.marker.color = trace.marker.color || '#8b5cf6';
        delete trace.marker.line;
      } else if (trace && (trace.type === 'scatter' || trace.type === 'scattergl')) {
        const mode = String(trace.mode || '');
        const name = String(trace.name || '').toLowerCase();
        if (mode.includes('lines') || name.includes('trendline') || name.includes('ols')) {
          trace.line = { ...(trace.line || {}), color: '#f97316', width: 3.5, dash: 'solid' };
        }
        if (mode.includes('markers') || !mode) {
          if (!trace.marker?.color || trace.marker.color === '#636efa' || trace.marker.color === '#1f77b4') {
            trace.marker = { ...(trace.marker || {}), color: '#8b5cf6' };
          }
        }
      } else if (trace && trace.type === 'pie') {
        trace.hole = trace.hole !== undefined ? trace.hole : 0.4;
      }
    });
  }

  if (Array.isArray(layout.shapes)) {
    layout.shapes.forEach((s: any) => {
      if (s && s.line) {
        s.line.dash = 'solid';
        s.line.color = '#f97316';
      }
    });
  }

  delete layout.scene;
  cloned.layout = layout;
  return cloned;
}

export const PlotlyChart: React.FC<PlotlyChartProps> = ({
  spec,
  title,
  chartType,
  collapsible = true,
  defaultExpanded = true,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [copied, setCopied] = useState(false);
  const [isCopying, setIsCopying] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const themed = applyDarkThemeLayout(spec);
    const data = themed.data || [];
    const layout = themed.layout || {};
    const config = { responsive: true, displayModeBar: false, ...(themed.config || {}) };

    Plotly.newPlot(el, data, layout, config);

    const handleResize = () => {
      Plotly.Plots.resize(el);
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      Plotly.purge(el);
    };
  }, [spec]);

  useEffect(() => {
    if (isExpanded && containerRef.current) {
      Plotly.Plots.resize(containerRef.current);
    }
  }, [isExpanded]);

  const handleToggle = () => {
    if (!collapsible) return;
    setIsExpanded((prev) => !prev);
  };

  const layoutTitle = spec?.layout?.title;
  const specTitle =
    typeof layoutTitle === 'object'
      ? layoutTitle?.text
      : typeof layoutTitle === 'string'
      ? layoutTitle
      : null;
  const displayTitle = title || specTitle || 'Interactive Visualization';

  const is3D =
    Boolean(chartType?.toLowerCase().includes('3d')) ||
    Boolean(spec?.data?.some((d: any) => d && d.type === 'scatter3d')) ||
    Boolean(spec?.layout?.scene);

  const downloadFallbackSnapshot = () => {
    if (!containerRef.current) return;
    const safeName = (title || 'chart_snapshot').toLowerCase().split(' ').join('_');
    Plotly.downloadImage(containerRef.current, {
      format: 'png',
      width: 1000,
      height: 600,
      filename: safeName,
    });
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopySnapshot = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!containerRef.current || isCopying) return;
    setIsCopying(true);
    try {
      const dataUrl = await Plotly.toImage(containerRef.current, {
        format: 'png',
        width: 1000,
        height: 600,
      });
      const res = await fetch(dataUrl);
      const blob = await res.blob();

      if (navigator.clipboard && typeof ClipboardItem !== 'undefined' && navigator.clipboard.write) {
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } else {
        downloadFallbackSnapshot();
      }
    } catch (err) {
      console.error('Failed to copy chart snapshot to clipboard:', err);
      try {
        downloadFallbackSnapshot();
      } catch (dlErr) {
        console.error('Failed to download fallback chart image:', dlErr);
      }
    } finally {
      setIsCopying(false);
    }
  };

  const headerClasses = [
    'widget-header',
    isExpanded ? 'expanded' : '',
    collapsible ? 'collapsible' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="widget-card">
      <div onClick={collapsible ? handleToggle : undefined} className={headerClasses}>
        <div className="widget-title-group">
          <BarChart2 size={14} color="#adb5bd" style={{ flexShrink: 0 }} />
          <span className="widget-title" title={displayTitle}>
            {displayTitle}
          </span>
        </div>

        <div className="widget-actions">
          <span className="badge badge-light">
            {chartType ? chartType.toUpperCase() : 'CHART'}
          </span>

          <button
            type="button"
            onClick={handleCopySnapshot}
            disabled={isCopying}
            title={copied ? 'Snapshot copied to clipboard!' : 'Copy chart snapshot (PNG)'}
            className={`widget-copy-btn ${copied ? 'copied' : ''}`}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : isCopying ? 'Capturing...' : 'Copy'}</span>
          </button>

          {collapsible && (
            <span className="widget-chevron">
              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
          )}
        </div>
      </div>

      <div
        style={{
          padding: '8px 10px',
          width: '100%',
          display: isExpanded ? 'block' : 'none',
        }}
      >
        <div ref={containerRef} style={{ width: '100%', minHeight: is3D ? '520px' : '380px' }} />
      </div>
    </div>
  );
};
