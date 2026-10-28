import urllib.request
import json

req = urllib.request.Request(
    'http://localhost:8000/api/query',
    data=json.dumps({
        'query': 'Which top 10 categories have the highest number of products in the catalog? Please visualize this.',
        'session_id': 'test_chart_hover_session_002',
        'history': []
    }).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

resp = urllib.request.urlopen(req, timeout=120)
res = json.loads(resp.read().decode('utf-8'))
meta = res.get('metadata', {})
chart_ids = meta.get('chart_ids', [])
print('Chart IDs:', chart_ids)

for cid in chart_ids:
    c_req = urllib.request.Request(f'http://localhost:8000/api/charts/{cid}')
    c_res = json.loads(urllib.request.urlopen(c_req).read().decode('utf-8'))
    spec = c_res.get('spec', {})
    if isinstance(spec, str):
        spec = json.loads(spec)
    for t in spec.get('data', []):
        ttype = t.get('type')
        ht = t.get('hovertemplate')
        hi = t.get('hoverinfo')
        print(f"Chart {cid} trace {ttype}: hovertemplate={ht}, hoverinfo={hi}")

if meta.get('code'):
    print('Generated code snippet:')
    for line in meta['code'].split('\n'):
        if 'hover' in line or 'fig' in line:
            print('  ', line)
