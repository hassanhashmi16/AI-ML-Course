// The three verified demo cases from docs/demo-cases.md and eval/cases.jsonl.
export const CASES = [
  {
    id: 'ct-001',
    title: 'ContextVar refactor',
    repository: 'https://github.com/pallets/flask',
    ref: '2.2.0',
    question:
      'Why did Flask replace the LocalStack-based context storage with direct ContextVar handling?',
    path: 'src/flask/ctx.py',
    pull: '4682',
  },
  {
    id: 'ct-002',
    title: 'JSON provider',
    repository: 'https://github.com/pallets/flask',
    ref: '2.2.0',
    question:
      'Why was the JSONProvider interface introduced instead of relying on custom JSONEncoder and JSONDecoder classes?',
    path: 'src/flask/json/provider.py',
    pull: '4692',
  },
  {
    id: 'ct-003',
    title: 'unknown number',
    repository: 'https://github.com/pallets/flask',
    ref: '2.2.0',
    question:
      'What exact percentage improvement in end-to-end request throughput was measured for the LocalStack refactor, and under which benchmark setup?',
    path: 'src/flask/ctx.py',
    pull: '4682',
  },
  {
    id: 'ct-004',
    title: 'removed or kept?',
    repository: 'https://github.com/pallets/flask',
    ref: '2.2.0',
    question:
      'Was the LocalStack API removed entirely in Flask 2.2.0, or kept for compatibility?',
    path: 'src/flask/ctx.py',
    pull: '4682',
  },
]

// The API request body for a prepared case.
export function payloadFor(item) {
  return {
    repository: item.repository,
    ref: item.ref,
    question: item.question,
    paths: item.path ? [item.path] : [],
    pulls: item.pull ? [Number(item.pull)] : [],
  }
}
