const BADGES = [
  ['b-a', '⚡', 'Real-time Fact Engine Active'],
  ['b-b', '🛡️', 'ELA Forensics Ready'],
  ['b-c', '🧠', 'ML Classifier V4'],
]

/** Gradient title plus levitating status badges. */
export default function HeroHeader() {
  return (
    <section className="hero no-print">
      <div className="hero-copy">
        <h2 className="hero-title">
          <svg viewBox="0 0 32 32" width="46" height="46" aria-hidden="true" className="hero-shield">
            <defs>
              <linearGradient id="shieldG" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#8b5cf6" />
                <stop offset="0.55" stopColor="#06b6d4" />
                <stop offset="1" stopColor="#10b981" />
              </linearGradient>
            </defs>
            <path d="M16 2 4 7v8c0 7.5 5 13 12 15 7-2 12-7.5 12-15V7z" fill="rgba(255,255,255,.7)" stroke="url(#shieldG)" strokeWidth="2.2" />
            <path d="m10.5 16 4 4 7-8" fill="none" stroke="url(#shieldG)" strokeWidth="2.6" strokeLinecap="round" />
          </svg>
          <span className="grad-text">FakeGuard</span>
        </h2>
        <p>Fuse rules, machine learning, live internet corroboration and image forensics into one credibility index.</p>
      </div>
      <div className="hero-badges">
        {BADGES.map(([cls, icon, label]) => (
          <span key={label} className={`float-badge ${cls}`}>
            <span aria-hidden="true">{icon}</span> {label}
          </span>
        ))}
      </div>
    </section>
  )
}
