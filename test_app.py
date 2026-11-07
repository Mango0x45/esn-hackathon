import json
import tempfile
import unittest
from pathlib import Path

import app


class TestTickets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
        self.orig_tickets = app.TICKETS
        app.TICKETS = Path(self.tmp.name)

    def tearDown(self):
        app.TICKETS = self.orig_tickets
        try:
            Path(self.tmp.name).unlink(missing_ok=True)
        except OSError:
            pass

    def test_empty_tickets(self):
        self.assertEqual(app.tickets_list(), [])

    def test_save_and_retrieve_tickets(self):
        t1 = {
            'id': 'T001',
            'flat': 'F002',
            'channel': 'F002-A01',
            'appliance': 'fridge/freezer',
            'title': 'Fridge compressor fault',
            'detail': 'Draw surged to 116W',
            'action': 'Inspect seal and defrost',
            'notes': 'Door gasket feels loose',
            'kwh': 580,
            'sek': 834,
            'status': 'open',
            'created_at': '2026-11-07 14:00'
        }
        app.save_tickets([t1])
        ts = app.tickets_list()
        self.assertEqual(len(ts), 1)
        self.assertEqual(ts[0]['id'], 'T001')
        self.assertEqual(ts[0]['status'], 'open')

    def test_status_update(self):
        t1 = {'id': 'T001', 'flat': 'F002', 'status': 'open'}
        app.save_tickets([t1])
        ts = app.tickets_list()
        ts[0]['status'] = 'resolved'
        app.save_tickets(ts)
        self.assertEqual(app.tickets_list()[0]['status'], 'resolved')


if __name__ == '__main__':
    unittest.main()
