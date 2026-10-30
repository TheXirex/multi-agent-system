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
  layout.paper_bgcolor = '#212529';
  layout.plot_bgcolor = '#212529';
  layout.font = { color: '#f8f9fa', family: 'inherit', ...(layout.font || {}) };

  if (layout.template && typeof layout.template === 'object') {
    const tLayout = layout.template.layout || {};
    tLayout.paper_bgcolor = '#212529';
    tLayout.plot_bgcolor = '#212529';
    tLayout.font = { color: '#f8f9fa', ...(tLayout.font || {}) };
  }

  if (layout.title) {
    layout.title = typeof layout.title === 'object' ? { ...layout.title, text: '' } : '';
  }

  if (!layout.margin) {
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
        <div ref={containerRef} style={{ width: '100%', minHeight: '380px' }} />
      </div>
    </div>
  );
};
