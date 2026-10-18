export default function StageLog({ events }) {
  return (
    <section className="panel stage-log">
      <h2>Investigation stages</h2>
      <ol>
        {events.map((event, index) => (
          <li key={index} className={`stage ${event.kind}`}>
            <span className="stage-name">{event.stage}</span>
            <span>{event.message}</span>
            {event.duration_ms != null && (
              <span className="stage-ms">{event.duration_ms} ms</span>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}
