import StatusBanner from './StatusBanner.jsx'
import Timeline from './Timeline.jsx'
import { shortDateTime, shortSource } from '../format.js'

function exportReport(report, threadId) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `codetrail-${threadId || 'report'}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

export default function ReportView({ report, threadId, onOpenEvidence }) {
  const snapshot = report.snapshot
  return (
    <article className="document" aria-labelledby="report-title">
      <header className="doc-head">
        <p className="doc-kicker">Investigation report</p>
        <h1 className="doc-title" id="report-title">
          {report.question}
        </h1>
        <p className="doc-meta">
          {snapshot.repository} @ {snapshot.sha.slice(0, 7)}
          {snapshot.ref_requested ? ` · ${snapshot.ref_requested}` : ''}
          {report.created_at ? ` · ${shortDateTime(report.created_at)}` : ''}
        </p>
        <div className="doc-toolbar">
          <StatusBanner status={report.status} />
          <button
            type="button"
            className="btn"
            onClick={() => exportReport(report, threadId)}
          >
            Export JSON
          </button>
        </div>
      </header>

      <section className="doc-section">
        <h2 className="section-title">Decision</h2>
        <p className="lede">{report.summary}</p>
      </section>

      <section className="doc-section">
        <h2 className="section-title">
          Findings
          <span className="section-count">{report.claims.length}</span>
        </h2>
        {report.claims.length === 0 ? (
          <p className="error-hint">
            No claim survived citation and grounding checks. The unresolved list below
            says what could not be supported.
          </p>
        ) : (
          <ol className="findings">
            {report.claims.map((claim, index) => (
              <li className="finding" key={index} style={{ '--i': index }}>
                <div className="finding-body">
                  <span className={`stamp ${claim.label}`}>{claim.label}</span>
                  <p className="statement">{claim.statement}</p>
                  {claim.excerpts.map((excerpt, position) => (
                    <button
                      key={position}
                      type="button"
                      className="cite"
                      onClick={() =>
                        onOpenEvidence({
                          source_id: excerpt.source_id,
                          quote: excerpt.quote,
                          start_line: excerpt.start_line,
                          end_line: excerpt.end_line,
                          title: 'Cited excerpt',
                        })
                      }
                    >
                      {shortSource(excerpt.source_id)}
                      <span className="cite-lines">
                        lines {excerpt.start_line}–{excerpt.end_line}
                      </span>
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      {report.unresolved.length > 0 && (
        <section className="doc-section">
          <h2 className="section-title">
            Unresolved
            <span className="section-count">{report.unresolved.length}</span>
          </h2>
          <ul className="unresolved">
            {report.unresolved.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      <Timeline events={report.timeline} onOpenEvidence={onOpenEvidence} />

      <section className="doc-section">
        <h2 className="section-title">Scope inspected</h2>
        <dl className="scope">
          <div>
            <dt>Files</dt>
            <dd>{report.coverage.files_read}</dd>
          </div>
          <div>
            <dt>Commits</dt>
            <dd>{report.coverage.commits_read}</dd>
          </div>
          <div>
            <dt>Discussions</dt>
            <dd>{report.coverage.discussions_read}</dd>
          </div>
          <div>
            <dt>Comments</dt>
            <dd>{report.coverage.comments_read}</dd>
          </div>
        </dl>
        <p className="error-hint">
          {report.coverage.complete
            ? 'Coverage complete for this scope.'
            : 'Coverage incomplete: some planned reads failed or were truncated.'}
        </p>
        {report.coverage.notes.length > 0 && (
          <ul className="notes">
            {report.coverage.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        )}
      </section>
    </article>
  )
}
