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
    const status = res.status
    const detail = body?.message || (typeof body?.detail === 'string' ? body.detail : null)
    throw Object.assign(new Error(detail || `Request failed (HTTP ${status}).`), { status })
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

// ---- Accounts (JWT). The token is attached only to /auth calls that need it, never to analysis requests. ----
let authToken = null
export const setAuthToken = (t) => { authToken = t || null }
const withAuth = (o = {}) => ({ ...o, headers: { ...(o.headers || {}), ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) } })

export const authRegister = (d) => request('/auth/register', json('POST', d))
export const authLogin = (d) => request('/auth/login', json('POST', d))
export const authDemo = () => request('/auth/demo', { method: 'POST' })
export const authMe = () => request('/auth/me', withAuth())
export const getScanHistory = (limit = 50) => request(`/auth/history?limit=${limit}`, withAuth())
export const getScanStats = () => request('/auth/stats', withAuth())
export const saveScan = (scan) => request('/auth/save-scan', withAuth(json('POST', scan)))
