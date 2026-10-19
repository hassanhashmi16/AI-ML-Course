export default function StageLog({ events }) {
  return (
    <details className="rail-block" open>
      <summary>Stages ({events.length})</summary>
      <ol className="stages">
        {events.map((event, index) => (
          <li key={index} className={`stage ${event.kind}`}>
            <span className="stage-name">{event.stage}</span>
            <span>
              {event.message}
              {event.duration_ms != null && (
                <span className="stage-ms"> · {event.duration_ms} ms</span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </details>
  )
}
