import tempfile
import unittest
from pathlib import Path

import clean

FILES = {
    'flats.csv': 'flat_id,residents,floor_area_m2,price_area,main_heating,tariff_id\n'
                 'F001,2,56,SE3,district_heat_excluded,T01\n',
    'energy_readings.csv': 'reading_id,flat_id,appliance_id,timestamp_utc,energy_value,energy_unit\n'
                           'R1,F001,F001-A01,2026-10-01T00:00:00Z,50,Wh\n'
                           'R2,F001, f001-a02 ,2026/10/01 00:00,"0,25", kwh \n'
                           'R3,F001,F001-A03,2026-10-01T00:00:00Z,N/A,kWh\n'
                           'R4,F001,F001-A04,2026-10-01T00:00:00Z,-0.2,kWh\n'
                           'R5,F001,F001-A05,2026-10-01T00:00:00Z,40.8,kWh\n'
                           'R6,F001,F001-A06,2026-10-01T00:00:00Z,0.033,kWh\n'
                           'R6,F001,F001-A06,2026-10-01T00:00:00Z,0.163,kWh\n'
                           'R7,F001,F999-A01,2026-10-01T00:00:00Z,0.1,kWh\n'
                           'R8,F008,F001-A07,2026-10-01T00:00:00Z,0.2,kWh\n',
    'hourly_context.csv': 'flat_id,timestamp_utc,timestamp_local,outdoor_temp_c,indoor_temp_c,occupants_home\n'
                          'F001,2026-10-01T00:00:00Z,2026-10-01T02:00:00+02:00,6.5,21.0,9\n',
    'hourly_prices.csv': 'timestamp_utc,price_area,spot_sek_per_kwh,carbon_gco2e_per_kwh\n'
                         '2026-10-01T00:00:00Z,SE3,,36.5\n',
}
T = '2026-10-01T00:00:00Z'


class TestClean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as d:
            for name, text in FILES.items():
                (Path(d) / name).write_text(text)
            cls.d = clean.load(d)

    def test_values(self):
        k = self.d['kwh']
        self.assertEqual(k['F001-A01'][T], 0.05)  # Wh -> kWh
        self.assertEqual(k['F001-A02'][T], 0.25)  # comma decimal, messy id, legacy timestamp
        self.assertEqual(k['F001-A06'][T], 0.033)  # conflicting duplicate keeps the lower value
        self.assertEqual(k['F001-A07'][T], 0.2)  # appliance prefix beats wrong flat_id
        for app in ('F001-A03', 'F001-A04', 'F001-A05'):  # N/A, negative, impossible -> missing, not zero
            self.assertNotIn(T, k.get(app, {}))
        self.assertNotIn('F999-A01', k)

    def test_context_and_prices(self):
        self.assertIsNone(self.d['ctx']['F001', T]['occ'])  # 9 occupants in a 2-person flat
        self.assertEqual(self.d['price']['SE3'][T], (None, 36.5))
        self.assertEqual(self.d['local'][T], 2)

    def test_quality_counts(self):
        q = self.d['quality']
        self.assertEqual(q['orphan appliance rows dropped'], 1)
        self.assertEqual(q['conflicting duplicates (kept lower)'], 1)
        self.assertEqual(q['impossible values dropped'], 2)
        self.assertEqual(q['missing hours'], 3)


if __name__ == '__main__':
    unittest.main()
