import { useEffect, useRef, useState } from 'react'
import {
  account, logout, investigation, listInvestigations,
  fetchEvents,
  health,
  listReports,
  loadReport,
  resumeInvestigation,
  startInvestigation,
} from './api.js'
import EmptyState from './components/EmptyState.jsx'
import EvidenceDrawer from './components/EvidenceDrawer.jsx'
import InvestigationForm from './components/InvestigationForm.jsx'
import ReportView from './components/ReportView.jsx'
import SavedRuns from './components/SavedRuns.jsx'
import StageLog from './components/StageLog.jsx'

function RunningPanel({ question, elapsed, threadId, jobStatus }) {
  return (
    <article className="document">
      <header className="doc-head">
        <p className="doc-kicker">Investigation running</p>
        <h1 className="work-title">{question || 'Resuming the investigation'}</h1>
        <div className="work-bar" aria-hidden="true">
          <span />
        </div>
        <p className="work-note">
          {jobStatus === 'queued' ? 'Your investigation is queued. Progress appears here when the worker starts.' : 'Collecting evidence, searching, grading, and writing. Follow the live stage log.'}
        </p>
        <p className="work-note">Run: {threadId || 'starting'}</p>
        <p className="work-elapsed" aria-hidden="true">
          {elapsed}s elapsed
        </p>
      </header>
    </article>
  )
}

function ErrorPanel({ message, onRetry }) {
  return (
    <article className="document">
      <header className="doc-head">
        <p className="doc-kicker">Run failed</p>
        <h1 className="error-title">The investigation stopped before a report existed.</h1>
      </header>
      <section className="doc-section">
        <p className="error-text">{message}</p>
        <p className="error-hint">
          The run may still be resumable with its thread id, or start a new run from the
          brief.
        </p>
        <div className="doc-toolbar">
          <button type="button" className="btn" onClick={onRetry}>
            Start a new run
          </button>
        </div>
      </section>
    </article>
  )
}

export default function App() {
  const [api, setApi] = useState(null)
  const [identity, setIdentity] = useState(undefined)
  const [jobs, setJobs] = useState([])
  const [jobStatus, setJobStatus] = useState('queued')
  const monitor = useRef(null)
  useEffect(() => () => monitor.current?.abort(), [])
  useEffect(() => {
    if (!api?.public_app) return
    account().then((value) => {
      setIdentity(value.user)
      if (value.user) {
        listReports().then((value) => setRuns(value.reports)).catch(() => {})
        listInvestigations().then((value) => setJobs(value.investigations)).catch(() => {})
      }
    }).catch(() => setIdentity(null))
  }, [api])
  const [runs, setRuns] = useState([])
  const [phase, setPhase] = useState('idle') // idle | running | done | error
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [question, setQuestion] = useState('')
  const [report, setReport] = useState(null)
  const [events, setEvents] = useState([])
  const [threadId, setThreadId] = useState('')
  const [drawer, setDrawer] = useState(null)

  useEffect(() => {
    health()
      .then(setApi)
      .catch(() => setApi({ status: 'unreachable' }))
    listReports()
      .then((payload) => setRuns(payload.reports))
      .catch(() => setRuns([]))
  }, [])

  useEffect(() => {
    if (phase !== 'running') return undefined
    setElapsed(0)
    const started = Date.now()
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [phase])

  const refreshRuns = () => {
    if (api?.public_app) listInvestigations().then((value) => setJobs(value.investigations)).catch(() => {})
    listReports()
      .then((payload) => setRuns(payload.reports))
      .catch(() => {})
  }

  const settle = async (initial) => {
    monitor.current?.abort()
    const controller = new AbortController()
    monitor.current = controller
    setThreadId(initial.thread_id)
    setJobStatus(initial.status)
    if (api?.public_app) {
      // The POST returns immediately. Events stream while status polling recovers
      // from a dropped stream and detects errors before the graph starts.
      fetchEvents(initial.thread_id, (event) => { if (!controller.signal.aborted) setEvents((old) => [...old, event]) }, controller.signal).catch(() => {})
      let result = initial
      while (['queued', 'running'].includes(result.status)) {
        await new Promise((resolve) => setTimeout(resolve, 1000))
        if (controller.signal.aborted) return
        result = await investigation(initial.thread_id)
        setJobStatus(result.status)
      }
      controller.abort()
      if (!result.report) throw new Error(result.error || 'Investigation interrupted. Resume it from your investigations list.')
      setReport(result.report)
      try { setEvents((await fetchEvents(initial.thread_id)).events) } catch { /* the report remains available if replay fails */ }
    } else {
      setReport(initial.report)
      if (initial.report) setEvents((await fetchEvents(initial.thread_id)).events)
    }
    setPhase('done')
    refreshRuns()
  }

  const run = async (payload) => {
    setPhase('running')
    setError('')
    setReport(null)
    setEvents([])
    setQuestion(payload.question)
    try {
      await settle(await startInvestigation(payload))
    } catch (exc) {
      setError(exc.message)
      setPhase('error')
      refreshRuns()
    }
  }

  const resume = async (id) => {
    setPhase('running')
    setError('')
    setQuestion('')
    setReport(null)
    setEvents([])
    try {
      await settle(await resumeInvestigation(id))
    } catch (exc) {
      setError(exc.message)
      setPhase('error')
      refreshRuns()
    }
  }

  const openRun = async (name) => {
    try {
      const loaded = await loadReport(name)
      setReport(loaded)
      setEvents([])
      setThreadId('')
      setError('')
      setPhase('done')
    } catch (exc) {
      setError(exc.message)
      setPhase('error')
      refreshRuns()
    }
  }

  const startOver = () => {
    setPhase('idle')
    setReport(null)
    setEvents([])
    setError('')
  }

  const live =
    phase === 'running'
      ? 'Investigation running.'
      : phase === 'error'
        ? 'Investigation failed.'
        : report
          ? `Investigation finished: ${report.status}.`
          : ''

  if (api?.public_app && !identity) return (
    <main className="app" style={{ maxWidth: 700, margin: '4rem auto' }}>
      <h1>CodeTrail</h1><p>Trace the decisions behind public GitHub code.</p>
      <p>Sign in to start investigations and keep your reports in your own workspace.</p>
      {identity === undefined ? <p>Checking your session…</p> : <a className="btn btn-primary" href="/auth/login">Sign in with GitHub</a>}
      <p>CodeTrail does not request access to your private repositories. Investigations use limited shared API capacity. Your questions and public source excerpts are sent to the configured AI provider; reports are kept in your account workspace.</p>
    </main>
  )
  return (
    <div className="app">
      <a className="skip-link" href="#workspace">
        Skip to the report
      </a>
      <p className="sr-only" role="status">
        {live}
      </p>

      <div inert={drawer ? true : undefined}>
        <header className="masthead">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              CT
            </span>
            <div>
              <p className="brand-name">CodeTrail</p>
              <p className="brand-tag">Trace the decisions behind the code</p>
            </div>
          </div>
          {identity && <div><span>Signed in as {identity.login}</span> <button className="btn" onClick={async () => { await logout(); window.location.reload() }}>Sign out</button></div>}
          <p className="api-badge">
            <span
              className={`api-dot ${api?.status === 'ok' ? 'ok' : 'down'}`}
              aria-hidden="true"
            />
            {api?.status === 'ok'
              ? 'API connected'
              : api
                ? 'API unreachable'
                : 'Checking the API'}
          </p>
        </header>

        <main className="layout">
          <aside className="rail" aria-label="Brief, resume, and saved runs">
            <InvestigationForm
              running={phase === 'running'}
              onRun={run}
              onResume={resume}
            />
            {api?.public_app && <section className="rail-block"><h2 className="rail-title">Your investigations</h2>
              {jobs.map((job) => <div key={job.thread_id}>
                <p className="mono">{job.thread_id.slice(0, 12)} · {job.status}</p>
                {['queued', 'running'].includes(job.status) && <button className="btn" disabled={phase === 'running'} onClick={() => { setPhase('running'); setEvents([]); settle(job).catch((exc) => { setError(exc.message); setPhase('error'); refreshRuns() }) }}>Follow progress</button>}
                {['interrupted', 'failed'].includes(job.status) && <button className="btn" disabled={phase === 'running'} onClick={() => resume(job.thread_id)}>Resume</button>}
              </div>)}
              <p>Daily limits keep shared capacity available. Reports and research memory belong to your account.</p>
            </section>}
            <SavedRuns runs={runs} onOpen={openRun} />
            {events.length > 0 && <StageLog events={events} />}
          </aside>

          <section className="workspace" id="workspace" aria-label="Report">
            {phase === 'idle' && <EmptyState onRun={run} />}
            {phase === 'running' && (
              <RunningPanel question={question} elapsed={elapsed} threadId={threadId} jobStatus={jobStatus} />
            )}
            {phase === 'error' && <ErrorPanel message={error} onRetry={startOver} />}
            {phase === 'done' && report && (
              <ReportView
                report={report}
                threadId={threadId}
                onOpenEvidence={setDrawer}
              />
            )}
          </section>
        </main>
      </div>

      {drawer && (
        <EvidenceDrawer evidence={drawer} onClose={() => setDrawer(null)} />
      )}
    </div>
  )
}
