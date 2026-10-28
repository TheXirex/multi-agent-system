import urllib.request
import json

payload = {
    "query": "Analyze the distribution and quartiles of unit_price across top 5 product categories with a box plot visualization.",
    "session_id": "test_box_hover_session_001",
    "history": []
}

req = urllib.request.Request(
    "http://localhost:8000/api/query",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

try:
    resp = urllib.request.urlopen(req, timeout=120)
    data = json.loads(resp.read().decode("utf-8"))
    print("Status:", resp.status)
    print("Agent:", data.get("agent_type"))
    charts = data.get("charts", [])
    print("Charts count:", len(charts))
    for i, c in enumerate(charts):
        fig = c.get("figure", {})
        print(f"Chart {i+1} title:", c.get("title"))
        for t in fig.get("data", []):
            print(f"Trace type={t.get('type')}, hoverinfo={t.get('hoverinfo')}, hovertemplate={t.get('hovertemplate')}")
    if data.get("python_code"):
        print("Generated code hover lines:")
        for line in data["python_code"].split("\n"):
            if "hover" in line.lower() or "update_traces" in line.lower():
                print("  ", line)
except Exception as e:
    print("Error:", e)
