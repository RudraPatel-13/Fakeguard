import { useAuth } from '../context/authContext.js'

/** Shown in place of a members-only view for guests. */
export default function LockedPanel({ icon, title, blurb }) {
  const { openAuth } = useAuth()
  return (
    <section className="panel locked">
      <div className="locked-icon" aria-hidden="true">{icon}</div>
      <h3>{title}</h3>
      <p className="muted">{blurb}</p>
      <div className="row" style={{ justifyContent: 'center' }}>
        <button className="btn btn-primary" onClick={() => openAuth('login')}>Sign In</button>
        <button className="btn" onClick={() => openAuth('register')}>Create Account</button>
      </div>
    </section>
  )
}
