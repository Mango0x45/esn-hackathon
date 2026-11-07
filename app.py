"""WasteWatt web app: serves the UI and the analysis API on http://localhost:8000."""
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google import genai
from google.genai import errors, types

import analyze
import envfile
from clean import MAX_KWH, load

envfile.load(Path(__file__).parent / '.env')
D = load()
FS = analyze.findings(D)
UI = Path(__file__).parent / 'static' / 'index.html'
DEVICES = Path(__file__).parent / 'devices.json'  # unmeasured devices residents add by hand, per flat
FLATS = Path(__file__).parent / 'flats.json'  # flats added by hand; they have no meter data
LOCK = threading.Lock()
COACH = """You are WasteWatt, an energy coach for students living in shared flats in Sweden.
You get a JSON report for one flat: estimated yearly electricity per circuit and the waste the analysis found,
each with yearly kWh, SEK and kg CO2e savings and a suggested action.
- Use only numbers from the report. Never invent figures, prices or appliances.
- Circuit types are inferred from load patterns, not labelled; say so when it matters.
- Channels marked "added" are devices residents entered by hand (watts x hours a day), not measurements. A flat with
  only added channels was created by hand and has no meter data: advise on its added devices, or ask the resident to add
  the devices they use.
- Write plain English a first-year student understands, no jargon.
- For a plan: at most 5 steps, biggest SEK saving first, each with its yearly saving and one concrete first action.
- Stay under 200 words."""


def saved(path):
    return json.loads(path.read_text()) if path.exists() else {}


def save(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(path)  # atomic, so a crash mid-write can't corrupt the file


def flats():
    return {**D['flats'], **saved(FLATS)}


def report(flat):
    return analyze.report(D, FS, flat, saved(DEVICES).get(flat, []), flats()[flat])


def add_flat(f):
    if not 1 <= f['residents'] <= 20 or not 0 < f['area'] <= 1000:
        return 400, {'error': 'A flat needs 1 to 20 residents and a floor area up to 1,000 m².'}
    with LOCK:
        added = saved(FLATS)
        if len(added) >= 100:
            return 400, {'error': 'At most 100 flats can be added.'}
        flat = f"F{max(int(k[1:]) for k in {**D['flats'], **added}) + 1:03d}"
        added[flat] = f
        save(FLATS, added)
    return 200, {'flat': flat}


def coach(flat, question):
    report_ = json.dumps(report(flat))
    try:
        client = genai.Client()
    except ValueError:  # the SDK raises this when GEMINI_API_KEY is not set
        return 503, {'error': 'The AI coach needs an API key: put GEMINI_API_KEY in .env and restart the app.'}
    try:
        resp = client.models.generate_content(
            model='gemini-3.6-flash', config=types.GenerateContentConfig(system_instruction=COACH),
            contents=f'<report>{report_}</report>\n\n{question or "Give me my action plan."}')
    except errors.ClientError as e:
        if e.code == 429:
            return 503, {'error': 'The AI coach is busy. Try again in a minute.'}
        return 503, {'error': f'Gemini rejected the request: {e.message}'}
    except errors.APIError as e:
        return 502, {'error': f'The AI coach is unavailable right now ({e.code}).'}
    return 200, {'answer': resp.text or "The coach can't help with that. Ask about your flat's energy use."}


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
            return self.send(200, {'flats': {k: {'residents': f['residents'], 'added': k not in D['flats']}
                                             for k, f in flats().items()},
                                   'fleet': analyze.fleet(D, FS), 'quality': D['quality'],
                                   'leaderboard': analyze.leaderboard(D)})
        if u.path == '/api/report':
            flat = parse_qs(u.query).get('flat', [''])[0]
            if flat not in flats():
                return self.send(400, {'error': f'unknown flat {flat!r}'})
            return self.send(200, report(flat))
        self.send(404, {'error': 'not found'})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ('/api/coach', '/api/devices', '/api/flats'):
            return self.send(404, {'error': 'not found'})
        try:
            n = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(n)) if 0 < n <= 10_000 else None
            if path == '/api/flats':  # the dataset only has SE3 prices
                new = {'residents': int(body['residents']), 'area': float(body['area']), 'price_area': 'SE3'}
            elif path == '/api/coach':
                flat, question = str(body['flat']), str(body.get('question', ''))[:500]
            else:
                flat = str(body['flat'])
                dev = {'name': str(body['name']).strip()[:40], 'watts': float(body['watts']),
                       'hours': float(body['hours'])}
        except (ValueError, KeyError, TypeError):
            return self.send(400, {'error': 'expected a JSON object under 10 kB with the documented fields'})
        if path == '/api/flats':
            return self.send(*add_flat(new))
        if flat not in flats():
            return self.send(400, {'error': f'unknown flat {flat!r}'})
        if path == '/api/coach':
            return self.send(*coach(flat, question))
        if not dev['name'] or not 0 < dev['watts'] <= MAX_KWH * 1000 or not 0 < dev['hours'] <= 24:
            return self.send(400, {'error': 'A device needs a name, up to 4,000 W and up to 24 hours a day.'})
        with LOCK:
            devs = saved(DEVICES)
            if len(devs.get(flat, [])) >= 20:
                return self.send(400, {'error': 'A flat can have at most 20 added devices.'})
            devs.setdefault(flat, []).append({'id': uuid.uuid4().hex[:8], **dev})
            save(DEVICES, devs)
        self.send(200, report(flat))

    def do_DELETE(self):
        u = urlparse(self.path)
        if u.path != '/api/devices':
            return self.send(404, {'error': 'not found'})
        q = parse_qs(u.query)
        flat, dev = q.get('flat', [''])[0], q.get('id', [''])[0]
        if flat not in flats():
            return self.send(400, {'error': f'unknown flat {flat!r}'})
        with LOCK:
            devs = saved(DEVICES)
            devs[flat] = [x for x in devs.get(flat, []) if x['id'] != dev]
            save(DEVICES, devs)
        self.send(200, report(flat))


if __name__ == '__main__':
    print('WasteWatt running on http://localhost:8000')
    ThreadingHTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
