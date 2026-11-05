import { useEffect, useState } from 'react'
import { CASES } from '../cases.js'

const EMPTY = { repository: '', ref: '', question: '', path: '', pull: '' }
const formFor = (item) => ({ repository: item.repository, ref: item.ref, question: item.question, path: item.path, pull: item.pull })

export default function InvestigationForm({ running, onRun, onResume, preset, showResume = true }) {
  const [form, setForm] = useState(EMPTY)
  const [thread, setThread] = useState('')
  useEffect(() => { if (preset) setForm(formFor(preset)) }, [preset])
  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value })
  const submit = (event) => {
    event.preventDefault()
    onRun({ repository: form.repository.trim(), ref: form.ref.trim() || null,
      question: form.question.trim(), paths: form.path.trim() ? [form.path.trim()] : [],
      pulls: form.pull.trim() ? [Number(form.pull.trim())] : [] })
  }
  return <>
    <section className="rail-block">
      <h2 className="rail-title">Start with a prepared case</h2>
      <div className="case-list">{CASES.map((item) => <button key={item.id} type="button" className="case" onClick={() => setForm(formFor(item))} disabled={running} title={item.question}><span className="case-id">{item.id.toUpperCase()}</span><span className="case-label">{item.title}</span></button>)}</div>
    </section>
    <section className="rail-block">
      <h2 className="rail-title">Your investigation</h2>
      <form onSubmit={submit} id="investigation-form">
        <div className="field"><label className="field-label" htmlFor="brief-repository">Public repository</label><input id="brief-repository" value={form.repository} onChange={update('repository')} placeholder="https://github.com/owner/repo" maxLength={230} disabled={running} required /></div>
        <div className="field ws-question-field"><label className="field-label" htmlFor="brief-question">What do you want to understand?</label><textarea id="brief-question" rows={4} value={form.question} onChange={update('question')} placeholder="Why did this function change? What led to this design?" maxLength={2000} disabled={running} required /><span className="ws-field-hint">Ask about a decision. CodeTrail will look for its evidence.</span></div>
        <details className="field-toggle"><summary>Narrow the search <span className="ws-optional">optional</span></summary>
          <div className="pair">
            <div className="field"><label className="field-label" htmlFor="brief-ref">Revision</label><input id="brief-ref" value={form.ref} onChange={update('ref')} placeholder="Branch or tag" maxLength={200} disabled={running} /></div>
            <div className="field"><label className="field-label" htmlFor="brief-pull">Pull request</label><input id="brief-pull" value={form.pull} onChange={update('pull')} type="number" min="1" max="2147483647" placeholder="4682" disabled={running} /></div>
          </div>
          <div className="field"><label className="field-label" htmlFor="brief-path">File path</label><input id="brief-path" value={form.path} onChange={update('path')} placeholder="src/flask/ctx.py" maxLength={300} disabled={running} /></div>
        </details>
        <button type="submit" className="btn btn-primary" disabled={running}>{running ? 'Investigation in progress' : <>Start investigation <span aria-hidden="true">&#8599;</span></>}</button>
        <p className="ws-form-footnote">Public repositories only. Investigations can take a few minutes.</p>
      </form>
    </section>
    {showResume && <details className="rail-block"><summary>Resume a saved run</summary><div className="resume"><input aria-label="Thread id" value={thread} onChange={(event) => setThread(event.target.value)} placeholder="Investigation reference" /><button type="button" className="btn" disabled={running || !thread.trim()} onClick={() => onResume(thread.trim())}>Resume</button></div></details>}
  </>
}
