"""Find energy waste per flat and price it in kWh, SEK and CO2e per year."""
from collections import Counter, defaultdict
from statistics import mean, median

from clean import load

# The dataset has no appliance lookup: these types are inferred from load shapes (see README).
TYPES = {'A01': 'fridge/freezer', 'A02': 'cooking', 'A03': 'small kitchen appliances',
         'A04': 'dishwasher/washer', 'A05': 'lighting & misc', 'A06': 'electronics', 'A07': 'portable heater'}
GRID = 0.312  # SEK/kWh excl. VAT; variable transfer fee, Vattenfall Eldistribution 2025 (39.0 öre incl. VAT)
TAX = 0.36  # SEK/kWh excl. VAT; energy tax on electricity 2026 (Skatteverket)
VAT = 1.25
YEAR_H = 8760
HEAT_DAYS = 212  # Oct-Apr heating season; October is milder than winter, so scaling from it is conservative
SHIFT_H = 12  # longest delay-start common dishwashers and washers offer
WARM = 22.0  # degC; heating above this is comfort overshoot (common advice: 20-21 degC)
MIN_SEK = 20  # hide findings too small to be worth a student's time
ADOPT = 0.7  # assumed share of the potential students realise (partial follow-through, rebound)
OUTLIER = 1.5  # flag flats using this multiple of the median kWh per resident, or more
KEYS = ('kwh', 'sek', 'co2')


def kind(app):
    return TYPES[app.split('-')[1]]


def rates(d, area):
    """Mean all-in price (SEK/kWh with grid fee, tax and VAT) and carbon factor (gCO2e/kWh) over the data."""
    ps = d['price'][area].values()
    return (mean(s for s, _ in ps if s is not None) + GRID + TAX) * VAT, mean(c for _, c in ps if c is not None)


def finding(d, app, k, title, detail, action, kwh, sek=None, co2=None, evidence=None):
    flat = app.split('-')[0]
    price, carbon = rates(d, d['flats'][flat]['price_area'])
    if sek is None:
        sek = kwh * price
    if co2 is None:
        co2 = kwh * carbon / 1000
    res = {'flat': flat, 'channel': app, 'type': kind(app), 'kind': k, 'title': title, 'detail': detail,
           'action': action, 'kwh': round(kwh), 'sek': round(sek), 'co2': round(co2, 1)}
    if evidence is not None:
        res['evidence'] = evidence
    return res


def always_on(s):
    return sum(v == 0 for v in s.values()) <= 0.05 * len(s)


def faults(d):
    """Sustained level shifts: an appliance that suddenly and lastingly draws much more is likely broken."""
    out = []
    for app, s in d['kwh'].items():
        if not always_on(s):
            continue  # switched loads (heaters, cooking) shift with weather and habits
        by = defaultdict(list)
        for ts, v in s.items():
            by[ts[:10]].append(v)
        days = sorted(by)
        med = {day: median(by[day]) for day in days}
        base, now = median(med[x] for x in days[:7]), median(med[x] for x in days[-7:])
        if now < 1.5 * base or now - base < 0.02:
            continue
        start = days[-1]
        for day in reversed(days):
            if med[day] < 1.5 * base:
                break
            start = day
        ev = {
            'type': 'timeseries',
            'series': [{'day': day[5:], 'watts': round(med[day] * 1000)} for day in days],
            'fault_day': start[5:],
            'base_w': round(base * 1000),
            'now_w': round(now * 1000),
            'label': 'Daily median power (W)'
        }
        out.append(finding(
            d, app, 'fault', f'Your {kind(app)} uses {now / base:.1f}x its normal power since {start}',
            f'It drew {base * 1000:.0f} W on average, now {now * 1000:.0f} W, day and night. A sudden jump '
            'that lasts is a fault (door seal, thermostat, ice build-up), not a bad meter reading.',
            'Check the door seal and defrost it. If it stays high, report it to your landlord: '
            'broken white goods are usually theirs to fix.',
            (now - base) * YEAR_H, evidence=ev))
    return out


def baseload(d, skip=()):
    """Overnight load far above the same circuit in similar flats: something is left on around the clock."""
    night = {app: median(v for ts, v in s.items() if 1 <= d['local'][ts] <= 5)
             for app, s in d['kwh'].items() if always_on(s) and app not in skip}
    by = defaultdict(list)
    for app, v in night.items():
        by[app.split('-')[1]].append(v)
    out = []
    for app, v in night.items():
        peer = median(by[app.split('-')[1]])
        if v < 2 * peer or v - peer < 0.03:
            continue
        s = d['kwh'][app]
        flat_curve = [round(median([v for ts, v in s.items() if d['local'].get(ts) == h] or [0]) * 1000) for h in range(24)]
        peer_hourly = []
        for h in range(24):
            vs = [val for a, s_a in d['kwh'].items() if a.split('-')[1] == app.split('-')[1] and always_on(s_a)
                  for ts, val in s_a.items() if d['local'].get(ts) == h]
            peer_hourly.append(round(median(vs) * 1000) if vs else 0)
        ev = {
            'type': 'profile_24h',
            'hours': list(range(24)),
            'flat_w': flat_curve,
            'peer_w': peer_hourly,
            'night_window': [1, 5],
            'label': '24-hour load curve (W)'
        }
        out.append(finding(
            d, app, 'always-on', f'Your {kind(app)} circuit draws {v * 1000:.0f} W all night, {v / peer:.1f}x similar flats',
            f'Between 01:00 and 05:00, when everyone sleeps, this circuit uses {v * 1000:.0f} W. The same circuit in '
            f'the other flats uses {peer * 1000:.0f} W. Something is left on around the clock.',
            'Find what is plugged in there (gaming PC, server, old router, TV box). Turn on sleep mode, '
            'or put it on a timer plug that switches it off at night.',
            (v - peer) * YEAR_H, evidence=ev))
    return out


def heater(d):
    """Supplementary heater running while the room is already warm or nobody is home."""
    out = []
    for app, s in d['kwh'].items():
        if not app.endswith('-A07') or not s:
            continue
        flat, warm, empty = app.split('-')[0], 0, 0
        for ts, v in s.items():
            c = d['ctx'].get((flat, ts), {})
            if c.get('in') is not None and c['in'] >= WARM:
                warm += v
            elif c.get('occ') == 0:
                empty += v
        if warm + empty == 0:
            continue
        useful = sum(v for ts, v in s.items() if (d['ctx'].get((flat, ts), {}).get('in') or 0) < WARM and (d['ctx'].get((flat, ts), {}).get('occ') or 0) > 0)
        ev = {
            'type': 'breakdown',
            'useful_kwh': round(useful),
            'warm_kwh': round(warm),
            'empty_kwh': round(empty),
            'label': 'Observed heater energy (kWh)'
        }
        out.append(finding(
            d, app, 'heating', 'Your heater runs when the room is already warm or empty',
            f'Over {len(d["hours"]) // 168} weeks, {(warm + empty) / sum(s.values()):.0%} of the heater\'s energy went '
            f'into hours when it was already {WARM:.0f} °C or more inside ({warm:.0f} kWh) or nobody was home '
            f'({empty:.0f} kWh). District heating already keeps the flat warm; the heater only tops up.',
            'Set the heater thermostat to 21 °C and plug it into a timer plug that cuts power when you leave. '
            'Each degree lower saves about 5 % heating energy.',
            (warm + empty) / len(s) * HEAT_DAYS * 24, evidence=ev))
    return out


def shift(d):
    """Dishwasher/washer runs in expensive hours that a delay-start could move to the cheapest hour ahead."""
    out, hours = [], d['hours']
    for app, s in d['kwh'].items():
        if not app.endswith('-A04'):
            continue
        p = d['price'][d['flats'][app.split('-')[0]]['price_area']]
        sek = co2 = 0
        frm, to = Counter(), Counter()
        for i, ts in enumerate(hours):
            v, (spot, c) = s.get(ts, 0), p[ts]
            if v < 0.1 or spot is None:
                continue
            # shortcut: each hour of a run moves on its own; fine for 1-2 hour programmes
            best = min((h for h in hours[i:i + SHIFT_H + 1] if p[h][0] is not None), key=lambda h: p[h][0])
            sek += v * (spot - p[best][0]) * VAT
            co2 += v * (c - p[best][1]) / 1000
            frm[d['local'][ts]] += 1
            to[d['local'][best]] += 1
        if not frm:
            continue
        k = 365 * 24 / len(hours)
        avg_prices = [round(mean([p[ts][0] for ts in hours if d['local'].get(ts) == h and p[ts][0] is not None] or [0]), 2) for h in range(24)]
        ev = {
            'type': 'price_profile',
            'hours': list(range(24)),
            'prices': avg_prices,
            'run_h': frm.most_common(1)[0][0],
            'shift_h': to.most_common(1)[0][0],
            'label': 'Average spot price by hour (SEK/kWh)'
        }
        out.append(finding(
            d, app, 'timing', f'Delay-start your {kind(app)}: same energy, lower price',
            f'It usually runs around {frm.most_common(1)[0][0]:02d}:00. '
            f'Within {SHIFT_H} hours there is almost always a cheaper hour. ' +
            ('The cheaper hours are also cleaner.' if co2 >= 0 else
             'The cheaper hours have slightly more CO2e, so this saves money, not carbon.'),
            f'Press delay-start so it runs around {to.most_common(1)[0][0]:02d}:00 instead.',
            0, sek * k, co2 * k, evidence=ev))
    return out


def away(d, skip=()):
    """Lighting or equipment left on when nobody is home (occupants_home == 0)."""
    out = []
    for app, s in d['kwh'].items():
        if app in skip or not s or not (app.endswith('-A05') or app.endswith('-A06')):
            continue
        flat = app.split('-')[0]
        empty = [(ts, v) for ts, v in s.items() if d['ctx'].get((flat, ts), {}).get('occ') == 0]
        if not empty:
            continue
        standby = min(v for _, v in empty)
        waste = [(ts, v) for ts, v in empty if v > standby + 0.01]
        if not waste:
            continue
        waste_kwh = sum(v - standby for _, v in waste)
        avg_draw = mean(v for _, v in waste)
        ev = {
            'type': 'away_stats',
            'standby_w': round(standby * 1000),
            'waste_w': round(avg_draw * 1000),
            'normal_hours': len(empty) - len(waste),
            'waste_hours': len(waste),
            'label': 'Unoccupied hours consumption'
        }
        out.append(finding(
            d, app, 'away', f'Your {kind(app)} is left on while everyone is out ({len(waste)} hours)',
            f'In {len(waste)} hours when nobody was home, this circuit drew {avg_draw * 1000:.0f} W '
            f'instead of its {standby * 1000:.0f} W empty baseline. Over 4 weeks, that is {waste_kwh:.1f} kWh '
            f'wasted on an empty flat.',
            'Switch off lights and electronics when leaving the flat. '
            'Consider an entryway reminder note or smart power strips.',
            waste_kwh / len(s) * YEAR_H, evidence=ev))
    return out


def findings(d):
    fs = faults(d)
    fs += baseload(d, skip={f['channel'] for f in fs})
    fs += away(d, skip={f['channel'] for f in fs}) + heater(d) + shift(d)
    fs = [f for f in fs if f['sek'] >= MIN_SEK]
    return sorted(fs, key=lambda f: -f['sek'])



def annual(d, app):
    """Yearly kWh from the mean of observed hours; heaters only run in the heating season."""
    s = d['kwh'][app]
    return mean(s.values()) * (HEAT_DAYS * 24 if app.endswith('-A07') else YEAR_H) if s else 0


def total(fs, n=1):
    return {k: round(sum(f[k] for f in fs) / n, 1) for k in KEYS}


def report(d, fs, flat, added=(), info=None):
    """info describes a flat added by hand; dataset flats use their own row."""
    f = info or d['flats'][flat]
    price, carbon = rates(d, f['price_area'])
    use = [{'channel': a, 'type': kind(a), 'kwh': round(annual(d, a)), 'sek': round(annual(d, a) * price),
            'co2': round(annual(d, a) * carbon / 1000, 1),
            'coverage': round(len(d['kwh'][a]) / len(d['hours']), 3)}
           for a in sorted(d['kwh']) if a.startswith(flat + '-')]
    for dev in added:  # unmeasured devices residents add by hand: rated watts x hours a day, all year
        kwh = dev['watts'] / 1000 * dev['hours'] * 365
        use.append({'channel': 'added', 'id': dev['id'], 'type': dev['name'], 'kwh': round(kwh),
                    'sek': round(kwh * price), 'co2': round(kwh * carbon / 1000, 1), 'coverage': None})
    mine = [x for x in fs if x['flat'] == flat]
    return {'flat': flat, **f, 'channels': use, 'use': total(use), 'findings': mine,
            'savings': total(mine), 'per_student': total(mine, f['residents'])}


def fleet(d, fs):
    n = sum(f['residents'] for f in d['flats'].values())
    pot = total(fs, n)
    return {'residents': n, 'use_kwh': round(sum(annual(d, a) for a in d['kwh']) / n),
            'coverage': round(1 - d['quality']['missing hours'] / (len(d['kwh']) * len(d['hours'])), 3),
            'potential': pot, 'expected': {k: round(v * ADOPT, 1) for k, v in pot.items()}}


def leaderboard(d):
    """Flats ranked by yearly kWh per resident, compared with the median flat. Flats, never people."""
    rows = []
    for flat, f in d['flats'].items():
        use = {a: annual(d, a) for a in d['kwh'] if a.startswith(flat + '-')}
        kwh = sum(use.values())
        rows.append({'flat': flat, 'residents': f['residents'], 'kwh': round(kwh),
                     'per_resident': round(kwh / f['residents']), 'top': kind(max(use, key=use.get))})
    mid = median(r['per_resident'] for r in rows)
    for r in rows:
        r['ratio'] = round(r['per_resident'] / mid, 1)
        r['outlier'] = r['per_resident'] >= OUTLIER * mid
    return {'median': round(mid), 'threshold': OUTLIER, 'flats': sorted(rows, key=lambda r: -r['per_resident'])}


if __name__ == '__main__':
    d = load()
    fs = findings(d)
    print('Data quality (rows repaired or excluded):')
    for k, v in d['quality'].items():
        print(f'  {v:5}  {k}')
    for flat in d['flats']:
        r = report(d, fs, flat)
        print(f"\n{flat} ({r['residents']} residents, {r['use']['kwh']:.0f} kWh/yr): "
              f"save {r['savings']['kwh']:.0f} kWh, {r['savings']['sek']:.0f} SEK, {r['savings']['co2']} kg CO2e per year")
        for f in r['findings']:
            print(f"  {f['kind']:9} {f['kwh']:5} kWh {f['sek']:5} SEK {f['co2']:5} kg  {f['title']}")
    s = fleet(d, fs)
    print(f"\nPer student per year ({s['residents']} residents, {s['use_kwh']} kWh/yr each, "
          f"{s['coverage']:.1%} of appliance-hours measured):")
    for k in ('potential', 'expected'):
        print(f"  {k:9} {s[k]['kwh']:6} kWh {s[k]['sek']:6} SEK {s[k]['co2']:5} kg CO2e")
    b = leaderboard(d)
    print(f"\nFlats by kWh per resident per year (median {b['median']}):")
    for r in b['flats']:
        flag = f"  <- {r['ratio']}x median, biggest circuit: {r['top']}" if r['outlier'] else ''
        print(f"  {r['flat']} {r['per_resident']:5} kWh ({r['residents']} residents){flag}")
