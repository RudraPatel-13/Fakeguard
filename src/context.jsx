import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AppContext } from './appContext.js'
import { useAuth } from './context/authContext.js'
import { saveScan } from './api.js'

const HISTORY_KEY = 'fakeguard.history.v1'
const MAX_HISTORY = 50

function loadHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// Strip bulky fields (base64 ELA image, per-word OCR boxes) before persisting.
function slim(result) {
  if (!result) return result
  const copy = JSON.parse(JSON.stringify(result))
  if (copy.ela) copy.ela.ela_image = null
  if (copy.ocr) copy.ocr.words = []
  return copy
}

export function AppProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const [history, setHistory] = useState(loadHistory)
  const idRef = useRef(0)
  const { isAuthenticated, logout, noteScanSaved } = useAuth()

  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])
  const toast = useCallback(
    (message, kind = 'info') => {
      const id = ++idRef.current
      setToasts((t) => [...t.slice(-3), { id, message, kind }])
      setTimeout(() => dismiss(id), 4500)
    },
    [dismiss],
  )

  useEffect(() => {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history))
    } catch {
      /* quota exceeded or storage disabled: history is best-effort */
    }
  }, [history])

  const addHistory = useCallback((entry) => {
    const item = { id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, at: new Date().toISOString(), ...entry, result: slim(entry.result) }
    setHistory((h) => [item, ...h].slice(0, MAX_HISTORY))
    // Signed-in users also get the scan saved to their account (best effort: never blocks or breaks a scan).
    if (isAuthenticated) {
      const score = Number.isFinite(entry.score) ? Math.max(0, Math.min(100, entry.score)) : null
      saveScan({
        input_type: entry.kind === 'image' ? 'image' : 'text',
        verdict: String(entry.band || 'Unknown').slice(0, 60),
        credibility_score: score,
        summary: String(entry.title || '').slice(0, 500),
      })
        .then(noteScanSaved)
        .catch((e) => { if (e.status === 401) logout() })
    }
  }, [isAuthenticated, logout, noteScanSaved])
  const clearHistory = useCallback(() => setHistory([]), [])
  const removeHistory = useCallback((id) => setHistory((h) => h.filter((x) => x.id !== id)), [])

  const value = useMemo(
    () => ({ toasts, toast, dismiss, history, addHistory, clearHistory, removeHistory }),
    [toasts, toast, dismiss, history, addHistory, clearHistory, removeHistory],
  )
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
