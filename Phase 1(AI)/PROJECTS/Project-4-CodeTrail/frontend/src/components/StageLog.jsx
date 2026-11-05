import { durationLabel } from '../format.js'

export default function StageLog({ events }) {
  return (
    <details className="rail-block ws-stage-log">
      <summary>Investigation activity <span>{events.length} updates</span></summary>
      <ol className="stages">
        {events.map((event, index) => (
          <li key={index} className={`stage ${event.kind}`}>
            <span className="stage-name">{event.stage}</span>
            <span>
              {event.message}
              {event.duration_ms != null && (
                <span className="stage-ms"> · {durationLabel(event.duration_ms / 1000)}</span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </details>
  )
}
