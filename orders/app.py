import json, os, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
PAYMENTS_URL = os.getenv('PAYMENTS_URL', 'http://payments:8080')

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        body=json.dumps(payload).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path=='/health': return self.reply(200, {'status':'ok','service':'orders'})
        self.reply(404, {'error':'not found'})
    def do_POST(self):
        if self.path!='/order': return self.reply(404, {'error':'not found'})
        request=urllib.request.Request(PAYMENTS_URL+'/charge', data=json.dumps({'amount':2500}).encode(), headers={'Content-Type':'application/json'},method='POST')
        try:
            with urllib.request.urlopen(request,timeout=5) as r: result=json.load(r)
            self.reply(200, {'order':'ORD-1001','item':'Kubernetes Notebook','payment':result})
        except urllib.error.HTTPError as e: self.reply(502,{'error':'payment service rejected request','status':e.code})
        except (urllib.error.URLError,TimeoutError) as e: self.reply(502,{'error':'payment service unreachable','detail':str(e)})

ThreadingHTTPServer(('0.0.0.0',8080), Handler).serve_forever()
