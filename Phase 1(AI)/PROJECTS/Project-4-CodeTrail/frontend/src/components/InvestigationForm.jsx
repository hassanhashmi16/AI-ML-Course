import { useState } from 'react'
import { CASES } from '../cases.js'

const EMPTY = { repository: '', ref: '', question: '', path: '', pull: '' }

export default function InvestigationForm({ running, onRun, onResume }) {
  const [form, setForm] = useState(EMPTY)
  const [thread, setThread] = useState('')

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value })
  const loadCase = (item) =>
    setForm({
      repository: item.repository,
      ref: item.ref,
      question: item.question,
      path: item.path,
      pull: item.pull,
    })

  const submit = (event) => {
    event.preventDefault()
    onRun({
      repository: form.repository.trim(),
      ref: form.ref.trim() || null,
      question: form.question.trim(),
      paths: form.path.trim() ? [form.path.trim()] : [],
      pulls: form.pull.trim() ? [Number(form.pull.trim())] : [],
    })
  }

  return (
    <section className="panel">
      <h2>New investigation</h2>
      <div className="cases">
        {CASES.map((item) => (
          <button
            key={item.id}
            type="button"
            className="case"
            onClick={() => loadCase(item)}
            disabled={running}
          >
            {item.label}
          </button>
        ))}
      </div>

      <form onSubmit={submit}>
        <label>
          Repository
          <input
            value={form.repository}
            onChange={update('repository')}
            placeholder="https://github.com/owner/repo"
            required
          />
        </label>
        <div className="row">
          <label>
            Ref
            <input value={form.ref} onChange={update('ref')} placeholder="branch or tag" />
          </label>
          <label>
            Pull request
            <input
              value={form.pull}
              onChange={update('pull')}
              inputMode="numeric"
              placeholder="4682"
            />
          </label>
        </div>
        <label>
          File path
          <input
            value={form.path}
            onChange={update('path')}
            placeholder="src/flask/ctx.py"
          />
        </label>
        <label>
          Question
          <textarea
            rows={3}
            value={form.question}
            onChange={update('question')}
            placeholder="Why did … ?"
            required
          />
        </label>
        <button type="submit" className="primary" disabled={running}>
          {running ? 'Running…' : 'Investigate'}
        </button>
      </form>

      <hr />
      <h2>Resume</h2>
      <div className="row">
        <input
          value={thread}
          onChange={(event) => setThread(event.target.value)}
          placeholder="thread id from an interrupted run"
        />
        <button
          type="button"
          disabled={running || !thread.trim()}
          onClick={() => onResume(thread.trim())}
        >
          Resume
        </button>
      </div>
    </section>
  )
}
