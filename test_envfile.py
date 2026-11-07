import os
import tempfile
import unittest
from pathlib import Path

import envfile


class TestEnvfile(unittest.TestCase):
    def test_load(self):
        keys = ('WW_A', 'WW_B', 'WW_C')
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in keys])
        os.environ['WW_C'] = 'from-env'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / '.env'
            p.write_text('# comment\nWW_A=1\nexport WW_B="two"\nWW_C=from-file\nnot a pair\n')
            envfile.load(p)
            envfile.load(Path(d) / 'missing')  # an absent file is fine
        self.assertEqual([os.environ[k] for k in keys], ['1', 'two', 'from-env'])


if __name__ == '__main__':
    unittest.main()
