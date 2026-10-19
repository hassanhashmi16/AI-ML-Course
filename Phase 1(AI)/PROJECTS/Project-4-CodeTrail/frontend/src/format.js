const DATE = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

const DATE_TIME = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

export function shortDate(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : DATE.format(date)
}

export function shortDateTime(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : DATE_TIME.format(date)
}

// "github:pallets/flask:pr:4682" -> "PR #4682"
// "github:pallets/flask@sha:file:src/flask/ctx.py" -> "src/flask/ctx.py"
export function shortSource(sourceId) {
  if (!sourceId) return 'source'
  const value = String(sourceId)
  const pull = value.match(/:pr:(\d+)$/)
  if (pull) return `PR #${pull[1]}`
  const review = value.match(/:review:pr-(\d+)-review-\d+$/)
  if (review) return `review on PR #${review[1]}`
  const issue = value.match(/:issue:(\d+)$/)
  if (issue) return `issue #${issue[1]}`
  const commit = value.match(/:commit:([0-9a-f]{7})/)
  if (commit) return `commit ${commit[1]}`
  const file = value.match(/:file:(.+)$/)
  if (file) return file[1]
  return value
}

// "pallets-flask@b17bb9ed563a-20261018T062904Z.json" -> a human row label.
export function describeReport(name) {
  const match = String(name).match(/^(.*)@([0-9a-f]{6,})[a-z0-9]*-(\d{8}T\d{6})Z?\.json$/i)
  if (!match) return { title: String(name), when: '' }
  const [, repo, sha, stamp] = match
  const iso = `${stamp.slice(0, 4)}-${stamp.slice(4, 6)}-${stamp.slice(6, 8)}T${stamp.slice(9, 11)}:${stamp.slice(11, 13)}:${stamp.slice(13, 15)}Z`
  const repoName = repo.split('/').pop()
  return { title: `${repoName} @ ${sha.slice(0, 7)}`, when: shortDateTime(iso) }
}
