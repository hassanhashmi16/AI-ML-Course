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

// Consume complete SSE frames as they arrive, including frames split across reads.
export async function fetchEvents(threadId, onEvent, signal) {
  const response = await fetch(`/investigations/${encodeURIComponent(threadId)}/events`, { signal })
  if (!response.ok) return { events: [] }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const events = []
  let buffer = ''
  function parse() {
    buffer = buffer.replaceAll('\r\n', '\n')
    let end
    while ((end = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      const data = frame.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n')
      if (!data) continue
      try {
        const event = JSON.parse(data)
        if (event.kind) { events.push(event); onEvent?.(event) }
      } catch { /* ignore incomplete/unrecognized public events */ }
    }
  }
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      parse()
      if (done) break
    }
  } finally { reader.releaseLock() }
  return { events }
}

export async function investigation(id) {
  return readJson(await fetch(`/investigations/${encodeURIComponent(id)}`))
}
export async function account() { return readJson(await fetch('/auth/me')) }
export async function logout() { return readJson(await fetch('/auth/logout', { method: 'POST' })) }
export async function listInvestigations() { return readJson(await fetch('/investigations')) }
