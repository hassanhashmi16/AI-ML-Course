async function readJson(response) {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      if (body && body.detail) detail = body.detail
    } catch {
      // keep the status text
    }
    throw new Error(detail)
  }
  return response.json()
}

export async function health() {
  return readJson(await fetch('/health'))
}

export async function listReports() {
  return readJson(await fetch('/reports'))
}

export async function loadReport(name) {
  return readJson(await fetch(`/reports/${encodeURIComponent(name)}`))
}

export async function startInvestigation(payload) {
  return readJson(
    await fetch('/investigations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  )
}

export async function resumeInvestigation(threadId) {
  return readJson(
    await fetch(`/investigations/${encodeURIComponent(threadId)}/resume`, {
      method: 'POST',
    }),
  )
}

// The API replays the recorded stage log as SSE. Parse the small event stream
// into plain objects the UI can render.
export async function fetchEvents(threadId) {
  const response = await fetch(
    `/investigations/${encodeURIComponent(threadId)}/events`,
  )
  if (!response.ok) return { events: [] }
  const text = await response.text()
  const events = []
  for (const block of text.split(/\r?\n\r?\n/)) {
    const line = block.split(/\r?\n/).find((item) => item.startsWith('data:'))
    if (!line) continue
    try {
      events.push(JSON.parse(line.slice(5).trim()))
    } catch {
      // skip a malformed event rather than failing the whole view
    }
  }
  return { events }
}
