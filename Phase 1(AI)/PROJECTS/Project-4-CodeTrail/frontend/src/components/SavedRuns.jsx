import { describeReport } from '../format.js'

export default function SavedRuns({ runs, onOpen }) {
  return (
    <section className="rail-block">
      <h2 className="rail-title">Saved runs</h2>
      {runs.length === 0 ? (
        <p className="run-when">
          Finished runs appear here, and can be reopened without calling a model.
        </p>
      ) : (
        <ul className="run-list">
          {runs.map((item) => {
            const { title, when } = describeReport(item.name)
            return (
              <li key={item.name}>
                <button
                  type="button"
                  className="run"
                  onClick={() => onOpen(item.name)}
                  title={item.name}
                >
                  <span className="run-title">{title}</span>
                  <span className="run-when">{when}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
