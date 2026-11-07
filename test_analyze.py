import unittest

import analyze
from clean import load

H = [f'2026-10-{1 + i // 24:02d}T{i % 24:02d}:00:00Z' for i in range(28 * 24)]


def data(kwh, ctx=None, spot=lambda i: 1.0, carbon=lambda i: 40.0):
    return {'flats': {f'F00{n}': {'residents': 2, 'area': 56, 'price_area': 'SE3'} for n in (1, 2, 3)},
            'kwh': kwh, 'ctx': ctx or {}, 'local': {t: int(t[11:13]) for t in H},
            'price': {'SE3': {t: (spot(i), carbon(i)) for i, t in enumerate(H)}}, 'hours': H, 'quality': {}}


def series(f):
    return {t: f(i) for i, t in enumerate(H)}


class TestDetectors(unittest.TestCase):
    def test_fault(self):
        d = data({'F001-A01': series(lambda i: 0.05 if i < 14 * 24 else 0.12),
                  'F002-A01': series(lambda i: 0.05),
                  'F003-A07': series(lambda i: 0.0 if i % 2 else (0.1 if i < 14 * 24 else 0.5))})
        [f] = analyze.faults(d)
        self.assertEqual(f['channel'], 'F001-A01')
        self.assertIn('2026-10-15', f['title'])
        self.assertEqual(f['kwh'], round(0.07 * 8760))

    def test_baseload(self):
        d = data({'F001-A06': series(lambda i: 0.04), 'F002-A06': series(lambda i: 0.045),
                  'F003-A06': series(lambda i: 0.15)})
        [f] = analyze.baseload(d)
        self.assertEqual((f['channel'], f['kind']), ('F003-A06', 'always-on'))
        self.assertEqual(f['kwh'], round(0.105 * 8760))
        self.assertEqual(analyze.baseload(d, skip={'F003-A06'}), [])

    def test_heater(self):
        ctx = {('F001', t): {'in': (23.0, 20.0, 20.0)[i % 3], 'occ': (2, 0, 2)[i % 3]} for i, t in enumerate(H)}
        [f] = analyze.heater(data({'F001-A07': series(lambda i: 0.5)}, ctx))
        self.assertEqual(f['kind'], 'heating')
        self.assertEqual(f['kwh'], round(0.5 * 2 / 3 * 212 * 24))
        self.assertIn('67%', f['detail'])

    def test_shift(self):
        d = data({'F001-A04': series(lambda i: 0.5 if i % 24 == 20 else 0)},
                 spot=lambda i: {20: 2.0, 2: 0.5}.get(i % 24, 1.0), carbon=lambda i: 30.0 if i % 24 == 2 else 40.0)
        [f] = analyze.shift(d)
        self.assertEqual((f['kind'], f['kwh']), ('timing', 0))
        # the last evening has no 02:00 ahead within the window, so it moves to a 1.0 SEK hour instead
        self.assertEqual(f['sek'], round((27 * 0.5 * 1.5 + 0.5 * 1.0) * 1.25 * 365 / 28))
        self.assertIn('20:00', f['detail'])
        self.assertIn('02:00', f['action'])

    def test_leaderboard(self):
        b = analyze.leaderboard(data({'F001-A01': series(lambda i: 0.1), 'F002-A01': series(lambda i: 0.1),
                                      'F003-A01': series(lambda i: 0.3)}))
        self.assertEqual(b['median'], 438)
        top, *rest = b['flats']
        self.assertEqual((top['flat'], top['per_resident'], top['ratio'], top['outlier']), ('F003', 1314, 3.0, True))
        self.assertEqual(top['top'], 'fridge/freezer')
        self.assertFalse(any(r['outlier'] for r in rest))


class TestDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load()
        cls.fs = analyze.findings(cls.d)

    def test_planted_issues_found(self):
        got = {(f['channel'], f['kind']) for f in self.fs}
        self.assertIn(('F002-A01', 'fault'), got)
        self.assertIn(('F005-A06', 'always-on'), got)
        self.assertIn(('F007-A07', 'heating'), got)

    def test_no_false_faults(self):
        self.assertEqual([f['channel'] for f in self.fs if f['kind'] == 'fault'], ['F002-A01'])

    def test_summaries(self):
        s = analyze.fleet(self.d, self.fs)
        self.assertEqual(s['residents'], 25)
        self.assertAlmostEqual(s['expected']['sek'], s['potential']['sek'] * analyze.ADOPT, delta=0.1)
        r = analyze.report(self.d, self.fs, 'F002')
        self.assertEqual(len(r['channels']), 7)
        self.assertAlmostEqual(r['per_student']['kwh'], r['savings']['kwh'] / 3, delta=0.1)


if __name__ == '__main__':
    unittest.main()
