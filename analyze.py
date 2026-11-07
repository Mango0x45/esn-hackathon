"""Find energy waste per flat and price it in kWh, SEK and CO2e per year."""
from collections import defaultdict
from statistics import mean, median

from clean import load

# The dataset has no appliance lookup: these types are inferred from load shapes (see README).
TYPES = {'A01': 'fridge/freezer', 'A02': 'cooking', 'A03': 'small kitchen appliances',
         'A04': 'dishwasher/washer', 'A05': 'lighting & misc', 'A06': 'electronics', 'A07': 'portable heater'}
GRID = 0.312  # SEK/kWh excl. VAT; variable transfer fee, Vattenfall Eldistribution 2025 (39.0 öre incl. VAT)
TAX = 0.36  # SEK/kWh excl. VAT; energy tax on electricity 2026 (Skatteverket)
VAT = 1.25
YEAR_H = 8760
MIN_SEK = 20  # hide findings too small to be worth a student's time
KEYS = ('kwh', 'sek', 'co2')


def kind(app):
    return TYPES[app.split('-')[1]]


def rates(d, area):
    ps = d['price'][area].values()
    return mean(s for s, _ in ps if s is not None), mean(c for _, c in ps if c is not None)


def finding(d, app, k, title, detail, action, kwh, sek=None, co2=None):
    flat = app.split('-')[0]
    spot, carbon = rates(d, d['flats'][flat]['price_area'])
    if sek is None:
        sek = kwh * (spot + GRID + TAX) * VAT
    if co2 is None:
        co2 = kwh * carbon / 1000
    return {'flat': flat, 'channel': app, 'type': kind(app), 'kind': k, 'title': title, 'detail': detail,
            'action': action, 'kwh': round(kwh), 'sek': round(sek), 'co2': round(co2, 1)}


def faults(d):
    """Sustained level shifts: an appliance that suddenly and lastingly draws much more is likely broken."""
    out = []
    for app, s in d['kwh'].items():
        if sum(v == 0 for v in s.values()) > 0.05 * len(s):
            continue  # only always-on loads: switched loads (heaters, cooking) shift with weather and habits
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
        out.append(finding(
            d, app, 'fault', f'Your {kind(app)} uses {now / base:.1f}x its normal power since {start}',
            f'It drew {base * 1000:.0f} W on average, now {now * 1000:.0f} W, day and night. A sudden jump '
            'that lasts is a fault (door seal, thermostat, ice build-up), not a bad meter reading.',
            'Check the door seal and defrost it. If it stays high, report it to your landlord: '
            'broken white goods are usually theirs to fix.',
            (now - base) * YEAR_H))
    return out


def findings(d):
    fs = [f for f in faults(d) if f['sek'] >= MIN_SEK]
    return sorted(fs, key=lambda f: -f['sek'])


if __name__ == '__main__':
    for f in findings(load()):
        print(f"{f['channel']:9} {f['kind']:6} {f['kwh']:5} kWh {f['sek']:5} SEK {f['co2']:5} kg  {f['title']}")
