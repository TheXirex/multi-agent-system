import json
import logging
import os
from pathlib import Path
import sys
import time
import urllib.request
import urllib.error

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("showcase")

BACKEND_URL = "http://localhost:8000"

QUESTIONS = [
    {
        "category": "1. Categorical Ranking (Top-N)",
        "query": "Which top 10 categories have the highest number of products in the catalog?",
        "expected": "Horizontal Bar Chart (sorted ascending, Top 10)",
    },
    {
        "category": "2. Metric Distribution",
        "query": "How are discount percentages distributed across all products in our catalog?",
        "expected": "Histogram with bin borders",
    },
    {
        "category": "3. Correlation Between Two Variables",
        "query": "Does a higher discount percentage impact customer ratings? Show the relationship with a trendline.",
        "expected": "Scatter Plot with OLS trendline",
    },
    {
        "category": "4. Time Series Trend",
        "query": "How has total order revenue evolved month by month over the entire recorded timeline?",
        "expected": "Line Chart with markers",
    },
    {
        "category": "5. Multi-Feature Correlation Matrix",
        "query": "Explore the mutual correlation between all numeric metrics including prices, discounts, ratings, and review counts.",
        "expected": "Heatmap matrix",
    },
    {
        "category": "6. Composition / Proportions",
        "query": "What is the breakdown and structural share of orders across different order fulfillment statuses?",
        "expected": "Donut Chart",
    },
    {
        "category": "7. Clustering & Segmentation",
        "query": "Segment products based on prices, discounts, and ratings to uncover typical price and quality market tiers.",
        "expected": "Cluster Scatter Plot",
    },
]


def make_request(url: str, data: dict = None, method: str = "GET") -> dict:
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    logger.info("Initializing Showcase Session...")
    session_res = make_request(f"{BACKEND_URL}/api/sessions", {"title": "ML Charts Showcase"}, method="POST")
    session_id = session_res["id"]
    logger.info(f"Created chat session: id={session_id}, title='{session_res.get('title')}'")

    output_dir = Path("output")
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for idx, item in enumerate(QUESTIONS, start=1):
        cat = item["category"]
        q = item["query"]
        expected = item["expected"]

        logger.info(f"\n--- [{idx}/{len(QUESTIONS)}] {cat} ---")
        logger.info(f"Query: {q}")
        start_time = time.time()

        try:
            payload = {
                "query": q,
                "session_id": session_id,
            }
            res = make_request(f"{BACKEND_URL}/api/query", payload, method="POST")
            duration = round(time.time() - start_time, 2)
            meta = res.get("metadata", {})
            response_text = res.get("response", "")
            chart_ids = meta.get("chart_ids", [])

            logger.info(f"Completed in {duration}s. Returned chart_ids: {chart_ids}")

            results.append({
                "index": idx,
                "category": cat,
                "query": q,
                "expected": expected,
                "duration": duration,
                "response": response_text,
                "chart_ids": chart_ids,
            })
        except Exception as exc:
            logger.error(f"Error executing query {idx}: {exc}")
            results.append({
                "index": idx,
                "category": cat,
                "query": q,
                "expected": expected,
                "duration": 0,
                "response": f"Execution error: {exc}",
                "chart_ids": [],
            })

    # Fetch chart specifications from backend
    all_charts = []
    for item in results:
        item_charts = []
        for cid in item["chart_ids"]:
            try:
                c_data = make_request(f"{BACKEND_URL}/api/charts/{cid}")
                c_title = c_data.get("title", f"Chart {cid}")
                c_spec = c_data.get("spec", {})
                if isinstance(c_spec, str):
                    c_spec = json.loads(c_spec)

                filename = f"chart_{cid}_{c_data.get('chart_type', 'plot')}.json"
                file_path = charts_dir / filename
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(c_spec, f, indent=2)

                item_charts.append({
                    "id": cid,
                    "title": c_title,
                    "chart_type": c_data.get("chart_type", "plot"),
                    "spec": c_spec,
                    "filename": filename,
                })
            except Exception as e:
                logger.warning(f"Could not load chart {cid}: {e}")
        item["charts"] = item_charts
        all_charts.extend(item_charts)

    logger.info(f"\nTotal charts collected: {len(all_charts)}")

    # Generate interactive HTML showcase
    html_file = output_dir / "charts_showcase.html"
    generate_html_gallery(results, session_id, html_file)
    logger.info(f"Showcase gallery generated at: {html_file.resolve()}")
    print(f"\nSUCCESS: Session ID is {session_id}")
    print(f"You can view it in the Web UI: http://localhost:8080")
    print(f"Or open standalone HTML showcase: {html_file.resolve()}")


def generate_html_gallery(results: list, session_id: str, html_path: Path):
    sections_html = []

    for item in results:
        idx = item["index"]
        cat = item["category"]
        q = item["query"]
        expected = item["expected"]
        resp = item["response"]
        charts = item.get("charts", [])

        chart_divs = []
        for c in charts:
            cid = c["id"]
            title = c["title"]
            spec_json = json.dumps(c["spec"])
            chart_divs.append(f"""
            <div class="chart-container">
                <div class="chart-header">
                    <h4>{title}</h4>
                    <span class="badge">{c.get('chart_type', 'Plotly')}</span>
                    <a class="download-link" href="charts/{c['filename']}" target="_blank">Download JSON</a>
                </div>
                <div id="plot_{cid}" style="width: 100%; height: 500px;"></div>
                <script>
                    (function() {{
                        const spec = {spec_json};
                        Plotly.newPlot('plot_{cid}', spec.data, spec.layout, {{responsive: true, displayModeBar: true}});
                    }})();
                </script>
            </div>
            """)

        charts_content = "".join(chart_divs) if chart_divs else "<p class='no-chart'>No chart produced</p>"

        # Format markdown response into simple paragraphs
        resp_paragraphs = "<br>".join(resp.split("\n"))

        sections_html.append(f"""
        <div class="card" id="section-{idx}">
            <div class="card-header">
                <div class="category-tag">{cat}</div>
                <h2>{q}</h2>
                <div class="meta-info">
                    <span><strong>Expected Target:</strong> {expected}</span>
                    <span><strong>Execution Time:</strong> {item['duration']}s</span>
                </div>
            </div>
            <div class="card-body">
                <div class="charts-grid">
                    {charts_content}
                </div>
                <div class="explanation">
                    <h3>Agent Synthesis & Metrics</h3>
                    <div class="explanation-text">{resp_paragraphs}</div>
                </div>
            </div>
        </div>
        """)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ML Agent Visualizations Showcase</title>
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-card: #182234;
            --accent: #38bdf8;
            --accent-glow: rgba(56, 189, 248, 0.2);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --border: #334155;
            --badge-bg: #0369a1;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}
        body {{
            background-color: var(--bg-primary);
            color: var(--text-primary);
            padding: 24px;
            line-height: 1.6;
        }}
        header {{
            max-width: 1300px;
            margin: 0 auto 32px auto;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border);
        }}
        h1 {{
            font-size: 2.2rem;
            color: #ffffff;
            margin-bottom: 8px;
            letter-spacing: -0.5px;
        }}
        .header-meta {{
            color: var(--text-secondary);
            font-size: 1rem;
            display: flex;
            gap: 20px;
            align-items: center;
        }}
        .session-badge {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            padding: 4px 12px;
            border-radius: 6px;
            font-family: monospace;
            color: var(--accent);
        }}
        .container {{
            max-width: 1300px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 36px;
        }}
        .card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }}
        .card-header {{
            background-color: var(--bg-secondary);
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
        }}
        .category-tag {{
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--accent);
            margin-bottom: 6px;
        }}
        h2 {{
            font-size: 1.35rem;
            margin-bottom: 10px;
            color: #ffffff;
        }}
        .meta-info {{
            display: flex;
            gap: 24px;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }}
        .card-body {{
            padding: 24px;
        }}
        .chart-container {{
            background: #0b1120;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 24px;
        }}
        .chart-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }}
        .chart-header h4 {{
            font-size: 1.1rem;
            color: #e2e8f0;
        }}
        .badge {{
            background: var(--badge-bg);
            color: #ffffff;
            font-size: 0.75rem;
            padding: 2px 8px;
            border-radius: 4px;
            text-transform: uppercase;
        }}
        .download-link {{
            color: var(--accent);
            text-decoration: none;
            font-size: 0.85rem;
        }}
        .download-link:hover {{
            text-decoration: underline;
        }}
        .explanation {{
            background: rgba(30, 41, 59, 0.5);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px 20px;
        }}
        .explanation h3 {{
            font-size: 1rem;
            color: var(--accent);
            margin-bottom: 8px;
        }}
        .explanation-text {{
            font-size: 0.95rem;
            color: #cbd5e1;
            white-space: pre-wrap;
            line-height: 1.5;
        }}
        .no-chart {{
            color: #f87171;
            font-style: italic;
            padding: 12px;
        }}
    </style>
</head>
<body>
    <header>
        <h1>ML Agent Visualizations Showcase</h1>
        <div class="header-meta">
            <span>Session: <span class="session-badge">{session_id}</span></span>
            <span>Total Queries: {len(results)}</span>
            <span>Open in Web UI: <a href="http://localhost:8080" target="_blank" style="color: var(--accent);">http://localhost:8080</a></span>
        </div>
    </header>
    <div class="container">
        {''.join(sections_html)}
    </div>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)


if __name__ == "__main__":
    main()
