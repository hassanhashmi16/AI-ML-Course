"""Score existing reports with Ragas; never rerun answer generation.

python eval/score_faithfulness.py --run-dir reports/eval/<run>
New evaluation runs save complete inspected evidence. Legacy runs can recover
cited source documents from the local cache; that narrower scope is labelled.
An abstention is not automatically a perfect score. It is marked not applicable.
"""
import argparse
import asyncio
import json
import math
import hashlib
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
os.environ['RAGAS_DO_NOT_TRACK'] = 'true'

from diskcache import Cache
from models import Report, SourceRecord

def sample_data(report, records):
    cited = {excerpt.source_id for claim in report.claims for excerpt in claim.excerpts}
    if not report.claims:
        return None
    if not cited.issubset(records):
        raise ValueError('Evidence is missing; scoring would give a misleading result')
    for claim in report.claims:
        for excerpt in claim.excerpts:
            if excerpt.quote not in records[excerpt.source_id].content:
                raise ValueError('Saved evidence no longer matches the report citation')
    return {'user_input': report.question,
            'response': '\n'.join([report.summary, *[claim.statement for claim in report.claims]]),
            'retrieved_contexts': [record.content for record in records.values()]}

async def score_directory(directory, *, limit=None, scorer=None):
    from config import settings
    from ragas.dataset_schema import SingleTurnSample
    if scorer is None:
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import Faithfulness
        from ragas.run_config import RunConfig
        from generation.answer import build_llm
        scorer = Faithfulness(llm=LangchainLLMWrapper(build_llm(), run_config=RunConfig(timeout=90, max_retries=1)))
    paths = sorted(p for p in directory.glob('ct-*.json') if not p.name.endswith('.evidence.json'))
    if limit:
        paths = paths[:limit]
    results = []
    existing_path = directory/'faithfulness.json'
    existing = json.loads(existing_path.read_text()) if existing_path.exists() else {}
    reusable = {row['report']: row for row in existing.get('results', [])}
    with Cache(str(settings.data_dir/'cache')) as cache:
        for path in paths:
            fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
            previous = reusable.get(path.name, {})
            if previous.get('report_sha256') == fingerprint and previous.get('status') in {'scored', 'not_applicable_abstention'} and existing.get('model_provider') == settings.gen_provider and existing.get('model') == (settings.groq_gen_model if settings.gen_provider == 'groq' else settings.gen_model):
                results.append(previous)
                print(json.dumps(previous | {'cached_score': True}), flush=True)
                continue
            row = {'report': path.name, 'report_sha256': fingerprint, 'faithfulness': None}
            try:
                report = Report.model_validate_json(path.read_text(encoding='utf-8'))
                evidence = path.with_suffix('.evidence.json')
                if evidence.exists():
                    records = {r['source_id']: SourceRecord.model_validate(r) for r in json.loads(evidence.read_text(encoding='utf-8'))}
                    row['context_scope'] = 'all inspected source documents saved with this evaluation'
                else:
                    ids = {e.source_id for c in report.claims for e in c.excerpts}
                    records = {i: SourceRecord.model_validate_json(cache[i]) for i in ids if i in cache}
                    row['context_scope'] = 'legacy reconstruction: cited source documents from local cache'
                data = sample_data(report, records)
                if data is None:
                    row['status'] = 'not_applicable_abstention'
                else:
                    value = float(await asyncio.wait_for(scorer.single_turn_ascore(SingleTurnSample(**data)), timeout=120))
                    if not math.isfinite(value):
                        raise ValueError('Ragas produced no finite score')
                    row.update(status='scored', faithfulness=value)
            except Exception as exc:
                # Do not dump provider exceptions; they can contain credentials.
                row.update(status='error', error_type=type(exc).__name__)
            results.append(row)
            print(json.dumps(row), flush=True)
    output = {'metric': 'Ragas faithfulness', 'model_provider': settings.gen_provider,
              'model': settings.groq_gen_model if settings.gen_provider == 'groq' else settings.gen_model,
              'scope': 'summary and claims, relative to the labelled source contexts; not an independent factual-correctness test',
              'results': results}
    (directory/'faithfulness.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    return output

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    result = asyncio.run(score_directory(args.run_dir, limit=args.limit))
    if any(row['status'] == 'error' for row in result['results']):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
