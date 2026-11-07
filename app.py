"""WasteWatt web app: serves the UI and the analysis API on http://localhost:8000."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import analyze
from clean import load

D = load()
FS = analyze.findings(D)
UI = Path(__file__).parent / 'static' / 'index.html'


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype='application/json'):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/':
            return self.send(200, UI.read_bytes(), 'text/html; charset=utf-8')
        if u.path == '/api/flats':
            return self.send(200, {'flats': {k: f['residents'] for k, f in D['flats'].items()},
                                   'fleet': analyze.fleet(D, FS), 'quality': D['quality']})
        if u.path == '/api/report':
            flat = parse_qs(u.query).get('flat', [''])[0]
            if flat not in D['flats']:
                return self.send(400, {'error': f'unknown flat {flat!r}'})
            return self.send(200, analyze.report(D, FS, flat))
        self.send(404, {'error': 'not found'})


if __name__ == '__main__':
    print('WasteWatt running on http://localhost:8000')
    ThreadingHTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
