import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/authContext.js'
import { useApp } from '../appContext.js'

const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/

/** 0-4 points for length, mixed case, digits and symbols. */
function strength(pw) {
  let s = 0
  if (pw.length >= 8) s++
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++
  if (/\d/.test(pw)) s++
  if (/[^A-Za-z0-9]/.test(pw)) s++
  if (pw.length < 6) return { s: 0, label: pw ? 'Too short' : '' }
  return { s: Math.max(1, s), label: s <= 1 ? 'Weak' : s <= 3 ? 'Medium' : 'Strong' }
}

function Field({ id, label, type = 'text', value, onChange, autoComplete, error, inputRef, trailing }) {
  return (
    <div className={`afield ${error ? 'has-error' : ''}`}>
      <input id={id} ref={inputRef} type={type} value={value} placeholder=" " autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)} aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined} />
      <label htmlFor={id}>{label}</label>
      {trailing}
      {error && <small id={`${id}-err`} className="afield-err">{error}</small>}
    </div>
  )
}

export default function AuthModal() {
  const { modal, closeAuth, openAuth, login, register, demoLogin } = useAuth()
  const { toast } = useApp()
  const mode = modal === 'register' ? 'register' : 'login'
  const [form, setForm] = useState({ email: '', username: '', password: '' })
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(null) // 'submit' | 'demo' | null
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState('')
  const first = useRef(null)
  const set = (k) => (v) => { setForm((f) => ({ ...f, [k]: v })); setErrors((e) => ({ ...e, [k]: undefined })); setFormError('') }

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && closeAuth()
    document.addEventListener('keydown', onKey)
    const t = setTimeout(() => first.current?.focus(), 60)
    return () => { document.removeEventListener('keydown', onKey); clearTimeout(t) }
  }, [closeAuth])

  const pw = strength(form.password)

  function validate() {
    const e = {}
    if (!EMAIL_RE.test(form.email.trim())) e.email = 'Enter a valid email address.'
    if (mode === 'register') {
      const u = form.username.trim()
      if (u.length < 2 || u.length > 32) e.username = 'Username must be 2-32 characters.'
      if (form.password.length < 6) e.password = 'At least 6 characters.'
    } else if (!form.password) {
      e.password = 'Enter your password.'
    }
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function submit(ev) {
    ev.preventDefault()
    if (busy || !validate()) return
    setBusy('submit')
    try {
      const user = mode === 'register'
        ? await register({ email: form.email.trim(), username: form.username.trim(), password: form.password })
        : await login({ email: form.email.trim(), password: form.password })
      toast(mode === 'register' ? `Welcome to FakeGuard, ${user.username}!` : `Welcome back, ${user.username}.`, 'ok')
    } catch (e) {
      setFormError(e.message)
      setBusy(null)
    }
  }

  async function demo() {
    if (busy) return
    setBusy('demo')
    try {
      const user = await demoLogin()
      toast(`Signed in as ${user.username}. Scans are saved to the shared demo account.`, 'ok')
    } catch (e) {
      setFormError(e.message)
      setBusy(null)
    }
  }

  return (
    <div className="auth-backdrop" onMouseDown={(e) => e.target === e.currentTarget && closeAuth()}>
      <span className="auth-float af-1">🛡️ Verified Access</span>
      <span className="auth-float af-2">⚡ 256-Bit Encrypted</span>
      <span className="auth-float af-3">🔍 FactGuard Intelligence</span>

      <div className="auth-card" role="dialog" aria-modal="true" aria-label={mode === 'login' ? 'Sign in' : 'Create account'}>
        <button className="auth-x" onClick={closeAuth} aria-label="Close">✕</button>
        <div className="auth-inner">
          <div className="auth-logo" aria-hidden="true">🛡️</div>
          <h2 className="auth-title"><span className="grad-text">{mode === 'login' ? 'Welcome back' : 'Join FakeGuard'}</span></h2>
          <p className="auth-sub">Sign in to save scans, unlock Rule Studio and export audit reports. Guests can still scan.</p>

          <div className="auth-tabs" role="tablist" data-mode={mode}>
            <i className="auth-pill" />
            <button role="tab" aria-selected={mode === 'login'} onClick={() => { openAuth('login'); setErrors({}); setFormError('') }}>Sign In</button>
            <button role="tab" aria-selected={mode === 'register'} onClick={() => { openAuth('register'); setErrors({}); setFormError('') }}>Create Account</button>
          </div>

          <form onSubmit={submit} noValidate key={mode} className="auth-form">
            {mode === 'register' && (
              <Field id="au-name" label="Username" value={form.username} onChange={set('username')} autoComplete="username"
                error={errors.username} inputRef={first} />
            )}
            <Field id="au-email" label="Email" type="email" value={form.email} onChange={set('email')} autoComplete="email"
              error={errors.email} inputRef={mode === 'login' ? first : undefined} />
            <Field id="au-pw" label="Password" type={show ? 'text' : 'password'} value={form.password} onChange={set('password')}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'} error={errors.password}
              trailing={
                <button type="button" className="eye" onClick={() => setShow((s) => !s)} aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}>
                  {show ? '🙈' : '👁️'}
                </button>
              } />

            {mode === 'register' && form.password && (
              <div className={`meter m-${pw.s}`} aria-live="polite">
                <div className="meter-bars">{[1, 2, 3, 4].map((n) => <i key={n} className={pw.s >= n ? 'on' : ''} />)}</div>
                <span>{pw.label}</span>
              </div>
            )}

            {formError && <p className="auth-error" role="alert">⚠ {formError}</p>}

            <button className="auth-submit" type="submit" disabled={!!busy}>
              {busy === 'submit' ? <><i className="spin" /> {mode === 'login' ? 'Signing in…' : 'Creating account…'}</> : mode === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>

          <div className="auth-or"><span>or</span></div>
          <button className="auth-demo" type="button" onClick={demo} disabled={!!busy}>
            {busy === 'demo' ? <><i className="spin dark" /> Entering…</> : <>🚀 Explore as Demo Analyst</>}
          </button>
          <p className="auth-fine">The demo account is shared: anyone using it sees the same saved scans.</p>
        </div>
      </div>
    </div>
  )
}
