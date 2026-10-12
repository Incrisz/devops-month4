import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/health':
            return self.reply(200, {'status':'ok','service':'payments'})
        self.reply(404, {'error':'not found'})

    def do_POST(self):
        if self.path != '/charge':
            return self.reply(404, {'error':'not found'})
        length = int(self.headers.get('Content-Length','0'))
        if length > 4096: return self.reply(413, {'error':'too large'})
        try: data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError): return self.reply(400, {'error':'bad JSON'})
        self.reply(200, {'approved':True,'amount':data.get('amount',0),'reference':'DEMO-0001','note':'Simulation only; no payment processed'})

ThreadingHTTPServer(('0.0.0.0',8080), Handler).serve_forever()
