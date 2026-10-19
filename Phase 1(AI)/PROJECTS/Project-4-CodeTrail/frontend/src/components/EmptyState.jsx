import { CASES, payloadFor } from '../cases.js'

export default function EmptyState({ onRun }) {
  return (
    <article className="document">
      <header className="doc-head">
        <p className="doc-kicker">No investigation open</p>
        <h1 className="empty-title">Ask why the code changed, and get the evidence.</h1>
        <p className="empty-lede">
          A run reads the repository at a pinned snapshot, follows the trail through
          commits, pull requests, and reviews, and writes a report where every claim
          carries a quote you can inspect. What it cannot support, it marks unresolved
          instead of guessing.
        </p>
      </header>

      <section className="doc-section">
        <div className="specimen">
          <p className="specimen-tag">A claim looks like this</p>
          <div className="finding-body">
            <span className="stamp documented">documented</span>
            <p className="statement">
              The refactor replaced the LocalStack-based storage with direct ContextVar
              handling; the pull request states the overhead and async-propagation
              reasons.
            </p>
            <span className="cite">
              PR #4682
              <span className="cite-lines">lines 9–14</span>
            </span>
          </div>
        </div>
      </section>

      <section className="doc-section">
        <h2 className="section-title">Start with a prepared case</h2>
        <div className="empty-cases">
          {CASES.map((item) => (
            <button
              key={item.id}
              type="button"
              className="case"
              onClick={() => onRun(payloadFor(item))}
            >
              <span className="case-id">{item.id}</span>
              <span className="case-label">{item.title}</span>
            </button>
          ))}
        </div>
        <p className="error-hint">
          Or describe any public repository and question in the brief. Only one run
          happens at a time.
        </p>
      </section>
    </article>
  )
}
