"""Container entry point with an optional fixed storage diagnostic before serving."""
import os
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    probe = os.environ.get('STORAGE_PROBE', '')
    if probe:
        if probe not in {'init', 'verify'}:
            raise SystemExit('STORAGE_PROBE must be init, verify, or unset')
        subprocess.run([sys.executable, str(Path(__file__).with_name('probe_storage.py')), '--'+probe], check=True)
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'api.main:app',
        '--host', '0.0.0.0', '--port', '8000', '--workers', '1',
        '--no-proxy-headers', '--no-access-log'])
