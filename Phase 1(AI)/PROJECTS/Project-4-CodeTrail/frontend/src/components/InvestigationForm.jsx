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
    <>
      <section className="rail-block">
        <h2 className="rail-title">Brief</h2>
        <div className="case-list">
          {CASES.map((item) => (
            <button
              key={item.id}
              type="button"
              className="case"
              onClick={() => loadCase(item)}
              disabled={running}
            >
              <span className="case-id">{item.id}</span>
              <span className="case-label">{item.title}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="rail-block">
        <h2 className="rail-title">New investigation</h2>
        <form onSubmit={submit}>
          <div className="field">
            <label className="field-label" htmlFor="brief-repository">
              Repository
            </label>
            <input
              id="brief-repository"
              value={form.repository}
              onChange={update('repository')}
              placeholder="https://github.com/owner/repo"
              required
            />
          </div>

          <details className="field-toggle">
            <summary>Ref, pull request, path (optional)</summary>
            <div className="pair">
              <div className="field">
                <label className="field-label" htmlFor="brief-ref">
                  Ref
                </label>
                <input
                  id="brief-ref"
                  value={form.ref}
                  onChange={update('ref')}
                  placeholder="branch or tag"
                />
              </div>
              <div className="field">
                <label className="field-label" htmlFor="brief-pull">
                  Pull request
                </label>
                <input
                  id="brief-pull"
                  value={form.pull}
                  onChange={update('pull')}
                  inputMode="numeric"
                  placeholder="4682"
                />
              </div>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="brief-path">
                File path
              </label>
              <input
                id="brief-path"
                value={form.path}
                onChange={update('path')}
                placeholder="src/flask/ctx.py"
              />
            </div>
          </details>

          <div className="field">
            <label className="field-label" htmlFor="brief-question">
              Question
            </label>
            <textarea
              id="brief-question"
              rows={3}
              value={form.question}
              onChange={update('question')}
              placeholder="Why did ... ?"
              required
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={running}>
            {running ? 'Investigating…' : 'Investigate'}
          </button>
        </form>
      </section>

      <details className="rail-block">
        <summary>Resume a run</summary>
        <div className="resume">
          <input
            aria-label="Thread id"
            value={thread}
            onChange={(event) => setThread(event.target.value)}
            placeholder="thread id"
          />
          <button
            type="button"
            className="btn"
            disabled={running || !thread.trim()}
            onClick={() => onResume(thread.trim())}
          >
            Resume
          </button>
        </div>
      </details>
    </>
  )
}
