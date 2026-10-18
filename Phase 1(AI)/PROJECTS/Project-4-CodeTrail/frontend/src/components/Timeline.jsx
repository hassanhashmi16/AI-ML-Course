export default function Timeline({ events, onOpenEvidence }) {
  if (!events || events.length === 0) return null
  return (
    <section>
      <h3>Timeline</h3>
      <ol className="timeline">
        {events.map((event, index) => (
          <li key={index}>
            <span className="timeline-date">{String(event.date).slice(0, 10)}</span>
            <div>
              <p>{event.title}</p>
              {event.summary && <p className="muted">{event.summary}</p>}
              {event.source_id && (
                <button
                  type="button"
                  className="link"
                  onClick={() =>
                    onOpenEvidence({
                      source_id: event.source_id,
                      quote: null,
                      title: event.title,
                    })
                  }
                >
                  {event.source_id}
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
