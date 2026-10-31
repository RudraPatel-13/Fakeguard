export const bandColor = (band) =>
  band === 'High trust' ? 'var(--emerald)' : band === 'Mixed / verify' ? 'var(--amber)' : 'var(--crimson)'

export const riskColor = (v) => (v == null ? 'var(--muted)' : v < 33 ? 'var(--emerald)' : v < 66 ? 'var(--amber)' : 'var(--crimson)')

export function download(filename, text, mime = 'application/json') {
  const url = URL.createObjectURL(new Blob([text], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const exportJson = (name, data) => download(`${name}.json`, JSON.stringify(data, null, 2))

const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// Split text into [{text, category|null}] segments for highlighting detected terms.
export function highlightSegments(text, matched) {
  if (!text || !matched) return [{ text: text || '', category: null }]
  const table = new Map()
  ;(matched.clickbait || []).forEach((t) => table.set(t.toLowerCase(), 'clickbait'))
  ;(matched.keywords || []).forEach((t) => table.set(t.toLowerCase(), 'keyword'))
  ;(matched.wordnet || []).forEach((t) => table.set(t.toLowerCase(), 'synonym'))
  if (!table.size) return [{ text, category: null }]
  const terms = [...table.keys()].sort((a, b) => b.length - a.length).map(escapeRegExp)
  const re = new RegExp(`\\b(${terms.join('|')})\\b`, 'gi')
  const out = []
  let last = 0
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push({ text: text.slice(last, m.index), category: null })
    out.push({ text: m[0], category: table.get(m[0].toLowerCase()) })
    last = m.index + m[0].length
  }
  if (last < text.length) out.push({ text: text.slice(last), category: null })
  return out
}

export const fmtDate = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
