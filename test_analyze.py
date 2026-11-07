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


class TestDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fs = analyze.findings(load())

    def test_planted_issues_found(self):
        got = {(f['channel'], f['kind']) for f in self.fs}
        self.assertIn(('F002-A01', 'fault'), got)

    def test_no_false_faults(self):
        self.assertEqual([f['channel'] for f in self.fs if f['kind'] == 'fault'], ['F002-A01'])


if __name__ == '__main__':
    unittest.main()
