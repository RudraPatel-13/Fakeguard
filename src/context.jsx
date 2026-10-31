import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AppContext } from './appContext.js'

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
  }, [])
  const clearHistory = useCallback(() => setHistory([]), [])
  const removeHistory = useCallback((id) => setHistory((h) => h.filter((x) => x.id !== id)), [])

  const value = useMemo(
    () => ({ toasts, toast, dismiss, history, addHistory, clearHistory, removeHistory }),
    [toasts, toast, dismiss, history, addHistory, clearHistory, removeHistory],
  )
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
