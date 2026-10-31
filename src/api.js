// Thin API client. Every call throws an Error with a user-presentable message.
export const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(`${API_BASE}${path}`, options)
  } catch {
    throw new Error('Cannot reach the FakeGuard backend. Is it running on ' + API_BASE + '?')
  }
  let body = null
  try {
    body = await res.json()
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const detail = body?.message || (typeof body?.detail === 'string' ? body.detail : null)
    throw new Error(detail || `Request failed (HTTP ${res.status}).`)
  }
  return body
}

const json = (method, payload) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})

export const analyzeText = (text, url, verifyWeb = false) =>
  request(`/analyze?verify_web=${verifyWeb}`, json('POST', { text, url: url || null }))
export const verifyWeb = (text, url) => request('/verify-web', json('POST', { text, url: url || null }))
export const verifyClaim = (text, url) =>
  request('/verify-claim', json('POST', { text: text || null, url: url || null }))
export const analyzeImage = (file, verifyWeb = true) => {
  const form = new FormData()
  form.append('file', file)
  return request(`/analyze-image?verify_web=${verifyWeb}`, { method: 'POST', body: form })
}
export const getModelInfo = () => request('/model-info')
export const getKeywordMeta = () => request('/keywords')
export const getKeywordRules = () => request('/keywords/rules')
export const reloadKeywords = () => request('/keywords/reload', { method: 'POST' })
