"""Read-only deployment preflight; never prints secret values or calls providers."""
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import BASE_DIR, settings


def main():
    checks = []
    def check(name, passed, detail):
        checks.append({'check': name, 'ok': bool(passed), 'detail': detail})
    check('public_mode', settings.public_app, 'PUBLIC_APP must be true on an internet-facing server.')
    check('https_origin', urlsplit(settings.app_origin).scheme == 'https', 'APP_ORIGIN must use the final HTTPS origin.')
    check('oauth', settings.oauth_client_id and settings.oauth_client_secret.get_secret_value(), 'Both server-side OAuth credentials must be configured.')
    provider_key = settings.groq_api_key if settings.gen_provider == 'groq' else settings.gemini_api_key
    check('generation_key', provider_key.get_secret_value(), 'The selected AI provider needs a key; free-plan eligibility is checked in its console.')
    check('frontend', (BASE_DIR/'frontend'/'dist'/'index.html').is_file(), 'Build the frontend before starting a release.')
    check('tracing', not settings.langsmith_tracing, 'Review user-data disclosure before enabling external tracing.')
    location = settings.data_dir
    while not location.exists():
        location = location.parent
    check('disk_headroom', shutil.disk_usage(location).free >= 2*1024**3, 'Allow at least 2 GiB free for models and initial research; monitor actual growth.')
    print(json.dumps({'checks':checks, 'retention_days':settings.retention_days,
        'manual_checks':['Persistent storage with local filesystem locking',
                         'One API process and one worker; sufficient CPU/RAM',
                         'Real HTTPS GitHub callback and cross-account URL checks',
                         'Provider free-plan limits and no automatic paid upgrades',
                         'Stopped-volume backup and isolated restore drill']}, indent=2))
    return 0 if all(item['ok'] for item in checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
