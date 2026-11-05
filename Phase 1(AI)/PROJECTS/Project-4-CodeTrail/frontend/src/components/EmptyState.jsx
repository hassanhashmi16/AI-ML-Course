import { CASES } from '../cases.js'

export default function EmptyState({ onChooseCase }) {
  return <article className="document ws-empty">
    <header className="ws-empty-heading"><p className="doc-kicker">A new trail starts here</p><h1>Start with a question.<br />Leave with the evidence.</h1><p>Understand a decision by following the code, the change, and the conversation behind it.</p></header>
    <div className="ws-evidence-map" aria-label="CodeTrail connects source code, changes, and discussions"><div><span className="ws-map-icon" aria-hidden="true">{'{ }'}</span><span>Source code</span><code>the implementation</code></div><span className="ws-map-link" aria-hidden="true">&#8594;</span><div><span className="ws-map-icon" aria-hidden="true">&#8997;</span><span>Commits</span><code>what changed</code></div><span className="ws-map-link" aria-hidden="true">&#8594;</span><div><span className="ws-map-icon" aria-hidden="true">&#8220;</span><span>Discussions</span><code>the recorded why</code></div></div>
    <section className="ws-empty-examples"><div className="ws-section-title"><h2>Choose a starting point</h2><span>Four prepared cases</span></div><div className="ws-example-list">{CASES.map((item) => <button key={item.id} type="button" onClick={() => onChooseCase(item)}><span>{item.id.toUpperCase()}</span><strong>{item.title}</strong><span aria-hidden="true">&#8599;</span></button>)}</div><p>These fill in your brief. Nothing runs until you start the investigation.</p></section>
    <footer className="ws-empty-footer"><span className="stamp documented">Documented</span><span className="stamp inferred">Inferred</span><span className="stamp unknown">Unresolved</span><p>See what the evidence supports, and where it stops.</p></footer>
  </article>
}
