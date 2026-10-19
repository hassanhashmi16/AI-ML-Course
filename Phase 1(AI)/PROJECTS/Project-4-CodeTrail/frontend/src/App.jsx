import { useEffect, useState } from 'react'
import {
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

function RunningPanel({ question, elapsed }) {
  return (
    <article className="document">
      <header className="doc-head">
        <p className="doc-kicker">Investigation running</p>
        <h1 className="work-title">{question || 'Resuming the investigation'}</h1>
        <div className="work-bar" aria-hidden="true">
          <span />
        </div>
        <p className="work-note">
          Collecting evidence, searching, grading, and writing. The stage log appears
          when the run finishes.
        </p>
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
    listReports()
      .then((payload) => setRuns(payload.reports))
      .catch(() => {})
  }

  const settle = async (result) => {
    setThreadId(result.thread_id)
    setReport(result.report)
    if (result.report) {
      const streamed = await fetchEvents(result.thread_id)
      setEvents(streamed.events)
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
    }
  }

  const resume = async (id) => {
    setPhase('running')
    setError('')
    setQuestion('')
    try {
      await settle(await resumeInvestigation(id))
    } catch (exc) {
      setError(exc.message)
      setPhase('error')
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
            <SavedRuns runs={runs} onOpen={openRun} />
            {events.length > 0 && <StageLog events={events} />}
          </aside>

          <section className="workspace" id="workspace" aria-label="Report">
            {phase === 'idle' && <EmptyState onRun={run} />}
            {phase === 'running' && (
              <RunningPanel question={question} elapsed={elapsed} />
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
