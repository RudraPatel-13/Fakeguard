import { useCallback, useEffect, useMemo, useState } from 'react'
import { AuthContext } from './authContext.js'
import { authDemo, authLogin, authMe, authRegister, setAuthToken } from '../api.js'

const KEY = 'fakeguard.auth.v1'

function load() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || 'null')
    return s?.token && s?.user ? s : null
  } catch {
    return null
  }
}

/**
 * Session state: { user, token }. The session is restored from localStorage on load and re-validated
 * against /auth/me; a 401 signs the user out, while a network failure keeps the cached session.
 */
export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => {
    const s = load()
    setAuthToken(s?.token) // must be set before any child effect fires an authenticated call
    return s
  })
  const [modal, setModal] = useState(null) // null | 'login' | 'register'
  const [drawer, setDrawer] = useState(false)
  const [scanTick, setScanTick] = useState(0) // bumps whenever a scan is saved, so open views refresh

  const persist = useCallback((s) => {
    setAuthToken(s?.token)
    setSession(s)
    try {
      if (s) localStorage.setItem(KEY, JSON.stringify(s))
      else localStorage.removeItem(KEY)
    } catch {
      /* storage disabled: session lasts until the tab closes */
    }
  }, [])

  const logout = useCallback(() => {
    persist(null)
    setDrawer(false)
  }, [persist])

  useEffect(() => {
    if (!session?.token) return
    let alive = true
    authMe()
      .then((user) => alive && persist({ token: session.token, user }))
      .catch((e) => { if (alive && e.status === 401) logout() })
    return () => { alive = false }
    // validate once per page load for the restored token
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const enter = useCallback((res) => {
    persist({ token: res.access_token, user: res.user })
    setModal(null)
    return res.user
  }, [persist])

  const login = useCallback((c) => authLogin(c).then(enter), [enter])
  const register = useCallback((d) => authRegister(d).then(enter), [enter])
  const demoLogin = useCallback(() => authDemo().then(enter), [enter])

  const value = useMemo(() => ({
    user: session?.user ?? null,
    token: session?.token ?? null,
    isAuthenticated: !!session?.token,
    login, register, demoLogin, logout,
    modal, openAuth: (mode = 'login') => setModal(mode), closeAuth: () => setModal(null),
    drawer, openDrawer: () => setDrawer(true), closeDrawer: () => setDrawer(false),
    scanTick, noteScanSaved: () => setScanTick((n) => n + 1),
  }), [session, login, register, demoLogin, logout, modal, drawer, scanTick])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
