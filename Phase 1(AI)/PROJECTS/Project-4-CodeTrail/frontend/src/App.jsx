import { useEffect, useState } from 'react'
import {
  fetchEvents,
  health,
  listReports,
  loadReport,
  resumeInvestigation,
  startInvestigation,
} from './api.js'
import EvidenceDrawer from './components/EvidenceDrawer.jsx'
import InvestigationForm from './components/InvestigationForm.jsx'
import ReportView from './components/ReportView.jsx'
import StageLog from './components/StageLog.jsx'
import StatusBanner from './components/StatusBanner.jsx'

export default function App() {
  const [api, setApi] = useState(null)
  const [reports, setReports] = useState([])
  const [phase, setPhase] = useState('idle') // idle | running | done | error
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [report, setReport] = useState(null)
  const [events, setEvents] = useState([])
  const [threadId, setThreadId] = useState('')
  const [drawer, setDrawer] = useState(null)

  useEffect(() => {
    health()
      .then(setApi)
      .catch(() => setApi({ status: 'unreachable' }))
    listReports()
      .then((payload) => setReports(payload.reports))
      .catch(() => setReports([]))
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

  const refreshReports = () => {
    listReports()
      .then((payload) => setReports(payload.reports))
      .catch(() => {})
  }

  const run = async (payload) => {
    setPhase('running')
    setError('')
    setReport(null)
    setEvents([])
    try {
      const result = await startInvestigation(payload)
      setThreadId(result.thread_id)
      setReport(result.report)
      if (result.report) {
        const streamed = await fetchEvents(result.thread_id)
        setEvents(streamed.events)
      }
      setPhase('done')
      refreshReports()
    } catch (exc) {
      setError(exc.message)
      setPhase('error')
    }
  }

  const resume = async (id) => {
    setPhase('running')
    setError('')
    try {
      const result = await resumeInvestigation(id)
      setThreadId(result.thread_id)
      setReport(result.report)
      if (result.report) {
        const streamed = await fetchEvents(result.thread_id)
        setEvents(streamed.events)
      }
      setPhase('done')
      refreshReports()
    } catch (exc) {
      setError(exc.message)
      setPhase('error')
    }
  }

  const openSaved = async (name) => {
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

  return (
    <div className="app">
      <header className="masthead">
        <div>
          <h1>CodeTrail</h1>
          <p className="tagline">Trace the decisions behind the code.</p>
        </div>
        <span className={`api-badge ${api?.status === 'ok' ? 'ok' : 'down'}`}>
          API {api?.status === 'ok' ? 'connected' : api ? 'unreachable' : 'checking…'}
        </span>
      </header>

      <main className="layout">
        <aside className="sidebar">
          <InvestigationForm running={phase === 'running'} onRun={run} onResume={resume} />
          <section className="panel">
            <h2>Saved reports</h2>
            {reports.length === 0 ? (
              <p className="muted">No saved reports yet.</p>
            ) : (
              <ul className="report-list">
                {reports.map((item) => (
                  <li key={item.name}>
                    <button type="button" className="link" onClick={() => openSaved(item.name)}>
                      {item.name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>

        <section className="workspace">
          {phase === 'running' && (
            <div className="panel running">
              <span className="spinner" aria-hidden="true" />
              Investigating… {elapsed}s
              <span className="muted"> A full run usually takes one to three minutes.</span>
            </div>
          )}

          {phase === 'error' && (
            <div className="panel error">
              <strong>Something went wrong.</strong>
              <p>{error}</p>
              <p className="muted">
                The run may still be resumable: use its thread id in the Resume panel.
              </p>
            </div>
          )}

          {report && <StatusBanner report={report} />}
          {report && (
            <ReportView report={report} threadId={threadId} onOpenEvidence={setDrawer} />
          )}
          {events.length > 0 && <StageLog events={events} />}
        </section>
      </main>

      {drawer && <EvidenceDrawer evidence={drawer} onClose={() => setDrawer(null)} />}
    </div>
  )
}
