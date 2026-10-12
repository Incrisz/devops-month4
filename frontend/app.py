import json, os, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ORDERS_URL = os.getenv('ORDERS_URL','http://orders:8080')
PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Secure Mesh Lab</title><style>body{background:#0f172a;color:#e2e8f0;font-family:system-ui;margin:0;display:grid;place-items:center;min-height:100vh}.panel{max-width:600px;margin:20px;padding:35px;background:#1e293b;border-radius:20px}button{background:#14b8a6;color:#042f2e;border:0;padding:14px 23px;border-radius:8px;font-weight:700;cursor:pointer}pre{white-space:pre-wrap;background:#020617;padding:15px;border-radius:8px}.muted{color:#94a3b8}</style></head><body><main class="panel"><h1>🔐 Secure Mesh Lab</h1><p>Frontend → Orders → Payments</p><p class="muted">Practice Kubernetes DNS, Services, RBAC, NetworkPolicy, Istio mTLS and authorization. No real transactions.</p><button onclick="order()">Place demo order</button><pre id="out">Click the button to begin.</pre></main><script>async function order(){const el=document.getElementById('out');el.textContent='Calling Orders API...';try{const r=await fetch('/api/order',{method:'POST'});const body=await r.json();el.textContent='HTTP '+r.status+'\\n'+JSON.stringify(body,null,2)}catch(e){el.textContent=String(e)}}</script></body></html>'''
class Handler(BaseHTTPRequestHandler):
    def send_data(self,status,body,content_type):
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path=='/health': return self.send_data(200,b'{"status":"ok"}','application/json')
        if self.path=='/': return self.send_data(200,PAGE.encode(),'text/html; charset=utf-8')
        self.send_data(404,b'Not found','text/plain')
    def do_POST(self):
        if self.path!='/api/order': return self.send_data(404,b'Not found','text/plain')
        req=urllib.request.Request(ORDERS_URL+'/order',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=8) as r: self.send_data(r.status,r.read(),'application/json')
        except urllib.error.HTTPError as e: self.send_data(502,json.dumps({'error':'orders returned error','status':e.code}).encode(),'application/json')
        except (urllib.error.URLError,TimeoutError) as e: self.send_data(502,json.dumps({'error':'orders unreachable','detail':str(e)}).encode(),'application/json')
ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
