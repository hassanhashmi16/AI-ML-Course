import { shortDate, shortSource } from '../format.js'

export default function Timeline({ events, onOpenEvidence }) {
  if (!events || events.length === 0) return null
  return (
    <section className="doc-section">
      <h2 className="section-title">Trail</h2>
      <ol className="trail">
        {events.map((event, index) => (
          <li key={index}>
            <span className="trail-date">{shortDate(event.date)}</span>
            <div>
              <p className="trail-title">{event.title}</p>
              {event.summary && <p className="trail-summary">{event.summary}</p>}
              {event.source_id && (
                <button
                  type="button"
                  className="cite"
                  onClick={() =>
                    onOpenEvidence({
                      source_id: event.source_id,
                      quote: null,
                      title: event.title,
                    })
                  }
                >
                  {shortSource(event.source_id)}
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
