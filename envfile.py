"""Load KEY=value lines from a .env file into the environment."""
import os


def load(path):
    """Real environment variables win over the file, like python-dotenv's default."""
    # shortcut: no inline comments or multi-line values; switch to python-dotenv if .env grows
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        k, sep, v = line.partition('=')
        k = k.strip().removeprefix('export ').strip()
        if sep and k and not k.startswith('#'):
            os.environ.setdefault(k, v.strip().strip('\'"'))
