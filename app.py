"""WasteWatt web app: serves the UI and the analysis API on http://localhost:8000."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import anthropic

import analyze
from clean import load

D = load()
FS = analyze.findings(D)
UI = Path(__file__).parent / 'static' / 'index.html'
COACH = """You are WasteWatt, an energy coach for students living in shared flats in Sweden.
You get a JSON report for one flat: estimated yearly electricity per circuit and the waste the analysis found,
each with yearly kWh, SEK and kg CO2e savings and a suggested action.
- Use only numbers from the report. Never invent figures, prices or appliances.
- Circuit types are inferred from load patterns, not labelled; say so when it matters.
- Write plain English a first-year student understands, no jargon.
- For a plan: at most 5 steps, biggest SEK saving first, each with its yearly saving and one concrete first action.
- Stay under 200 words."""


def coach(flat, question):
    report = json.dumps(analyze.report(D, FS, flat))
    try:
        msg = anthropic.Anthropic().beta.messages.create(
            model='claude-opus-5-5', max_tokens=16000, system=COACH,
            betas=['server-side-fallback-2026-07-01'], fallbacks='default',
            output_config={'effort': 'low'},
            messages=[{'role': 'user', 'content': f'<report>{report}</report>\n\n{question or "Give me my action plan."}'}])
    except TypeError as e:  # the SDK raises this when no API key or `ant auth login` profile is configured
        if 'authentication' not in str(e):
            raise
        return 503, {'error': 'The AI coach needs an API key: set ANTHROPIC_API_KEY and restart the app.'}
    except anthropic.AuthenticationError:
        return 503, {'error': 'The API key was rejected. Check ANTHROPIC_API_KEY.'}
    except anthropic.RateLimitError:
        return 503, {'error': 'The AI coach is busy. Try again in a minute.'}
    except anthropic.APIError as e:
        return 502, {'error': f'The AI coach is unavailable right now ({type(e).__name__}).'}
    if msg.stop_reason == 'refusal':
        return 200, {'answer': "The coach can't help with that. Ask about your flat's energy use."}
    return 200, {'answer': ''.join(b.text for b in msg.content if b.type == 'text')}


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

    def do_POST(self):
        if urlparse(self.path).path != '/api/coach':
            return self.send(404, {'error': 'not found'})
        try:
            n = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(n)) if 0 < n <= 10_000 else None
            flat, question = str(body['flat']), str(body.get('question', ''))[:500]
        except (ValueError, KeyError, TypeError):
            return self.send(400, {'error': 'expected JSON {"flat": "F001", "question": "..."} under 10 kB'})
        if flat not in D['flats']:
            return self.send(400, {'error': f'unknown flat {flat!r}'})
        self.send(*coach(flat, question))


if __name__ == '__main__':
    print('WasteWatt running on http://localhost:8000')
    ThreadingHTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
