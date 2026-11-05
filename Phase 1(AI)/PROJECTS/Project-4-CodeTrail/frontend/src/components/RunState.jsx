import { durationLabel } from '../format.js'

export function RunningPanel({ question, elapsed, threadId, jobStatus, events }) {
  const queued = jobStatus === 'queued'
  const current = queued ? 0 : events.length === 0 ? 1 : events.some((e) => e.kind === 'run_finished') ? 3 : 2
  const latest = events.filter((e) => e.kind === 'stage_finished').at(-1)
  return <article className="document ws-run-document">
    <div className="ws-run-top"><span className="doc-kicker">{queued ? 'Waiting for a worker' : 'Investigation in progress'}</span><span className="ws-elapsed"><span className="ws-pulse" />{durationLabel(elapsed)}</span></div>
    <h1 className="ws-run-title">{queued ? 'Your question is in line.' : 'Following the trail.'}</h1>
    <p className="ws-running-question">{question || 'Continuing your saved investigation.'}</p>
    <ol className="ws-progress-steps" aria-label="Investigation progress">{['Queued', 'Preparing sources', 'Investigating', 'Report ready'].map((label, index) => <li key={label} className={index < current ? 'finished' : index === current ? 'current' : ''} aria-current={index === current ? 'step' : undefined}><span>{index < current ? '✓' : String(index + 1).padStart(2, '0')}</span>{label}</li>)}</ol>
    <div className="ws-live-update"><span className="ws-kicker">{latest ? 'Latest completed step' : queued ? 'What happens next' : 'Getting started'}</span><p aria-live="polite">{latest?.message || (queued ? 'Your investigation will start when the current run finishes.' : 'Collecting public sources and preparing the evidence search.')}</p></div>
    <p className="ws-wait-note">A thorough investigation can take a few minutes. You can return to this run from History.</p>
    <details className="ws-run-reference"><summary>Investigation reference</summary><code>{threadId || 'Creating your run…'}</code></details>
  </article>
}

export function ErrorPanel({ message, question, onNew, onResume, resumable }) {
  return <article className="document ws-run-document"><p className="doc-kicker">Investigation needs attention</p><h1 className="ws-run-title">The trail paused here.</h1>{question && <p className="ws-running-question">{question}</p>}<div className="ws-error-note"><span aria-hidden="true">!</span><p role="alert">{message}</p></div><p className="ws-wait-note">A failed run doesn’t mean the question is unanswerable. If a checkpoint was saved, you can try continuing from it. Resuming uses another run allowance.</p><div className="ws-error-actions">{resumable && <button className="btn btn-primary" onClick={onResume}>Resume investigation <span aria-hidden="true">↗</span></button>}<button className="btn" onClick={onNew}>Start a new investigation</button></div></article>
}
