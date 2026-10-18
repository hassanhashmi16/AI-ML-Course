// The three verified demo cases from docs/demo-cases.md and eval/cases.jsonl.
export const CASES = [
  {
    id: 'ct-001',
    label: 'CT-001 · ContextVar refactor',
    repository: 'https://github.com/pallets/flask',
    ref: '2.2.0',
    question:
      'Why did Flask replace the LocalStack-based context storage with direct ContextVar handling?',
    path: 'src/flask/ctx.py',
    pull: '4682',
  },
  {
    id: 'ct-002',
    label: 'CT-002 · JSON provider',
    repository: 'https://github.com/pallets/flask',
    ref: '2.2.0',
    question:
      'Why was the JSONProvider interface introduced instead of relying on custom JSONEncoder and JSONDecoder classes?',
    path: 'src/flask/json/provider.py',
    pull: '4692',
  },
  {
    id: 'ct-003',
    label: 'CT-003 · unknown number',
    repository: 'https://github.com/pallets/flask',
    ref: '2.2.0',
    question:
      'What exact percentage improvement in end-to-end request throughput was measured for the LocalStack refactor, and under which benchmark setup?',
    path: 'src/flask/ctx.py',
    pull: '4682',
  },
]
