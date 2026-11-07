"""Load the organiser dataset and repair its known defects, counting every repair."""
import csv
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

MAX_KWH = 4.0  # one 16 A / 230 V circuit delivers at most ~3.7 kWh in an hour
MISSING = {'', 'N/A'}


def utc(s):
    s = s.strip()
    if '/' in s:  # legacy export, still UTC
        return datetime.strptime(s, '%Y/%m/%d %H:%M').strftime('%Y-%m-%dT%H:%M:%SZ')
    return s


def num(s):
    try:
        return float(s.strip().replace(',', '.'))
    except ValueError:
        return None


def rows(d, name):
    with open(d / name, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def load(d='data'):
    d = Path(d)
    q = Counter()
    flats = {r['flat_id']: {'residents': int(r['residents']), 'area': float(r['floor_area_m2']),
                            'price_area': r['price_area']} for r in rows(d, 'flats.csv')}

    vals = defaultdict(list)
    for r in rows(d, 'energy_readings.csv'):
        app = r['appliance_id'].strip().upper()
        q['appliance ids normalised'] += app != r['appliance_id']
        flat = app.split('-')[0]
        if flat not in flats:
            q['orphan appliance rows dropped'] += 1
            continue
        q['flat ids corrected from appliance id'] += flat != r['flat_id']
        ts = r['timestamp_utc']
        q['legacy timestamps converted'] += '/' in ts
        raw, unit = r['energy_value'].strip(), r['energy_unit'].strip().lower()
        v = num(raw)
        if raw in MISSING or v is None or unit not in ('kwh', 'wh'):
            q['missing values (not zero)'] += 1
            v = None
        else:
            q['comma decimals parsed'] += ',' in raw
            if unit == 'wh':
                q['Wh converted to kWh'] += 1
                v /= 1000
            if not 0 <= v <= MAX_KWH:
                q['impossible values dropped'] += 1
                v = None
        vals[app, utc(ts)].append(v)

    kwh = {app: {} for app, _ in vals}
    for (app, ts), vs in vals.items():
        q['duplicate rows removed'] += len(vs) - 1
        ok = [v for v in vs if v is not None]
        if len(set(ok)) > 1:
            q['conflicting duplicates (kept lower)'] += 1
        if ok:
            kwh[app][ts] = min(ok)

    ctx, local = {}, {}
    for r in rows(d, 'hourly_context.csv'):
        ts, flat = utc(r['timestamp_utc']), r['flat_id'].strip()
        occ = num(r['occupants_home'])
        if occ is None or not 0 <= occ <= flats[flat]['residents']:
            q['occupancy unknown'] += 1
            occ = None
        ctx[flat, ts] = {'out': num(r['outdoor_temp_c']), 'in': num(r['indoor_temp_c']), 'occ': occ}
        local[ts] = int(r['timestamp_local'][11:13])

    price = defaultdict(dict)
    for r in rows(d, 'hourly_prices.csv'):
        spot = num(r['spot_sek_per_kwh'])
        q['missing prices'] += spot is None
        price[r['price_area'].strip()][utc(r['timestamp_utc'])] = (spot, num(r['carbon_gco2e_per_kwh']))

    hours = sorted(local)
    q['missing hours'] = len(kwh) * len(hours) - sum(len(s) for s in kwh.values())
    return {'flats': flats, 'kwh': kwh, 'ctx': ctx, 'local': local, 'price': dict(price),
            'hours': hours, 'quality': dict(q)}
