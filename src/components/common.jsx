import { Component } from 'react'
import { useApp } from '../appContext.js'
import { highlightSegments } from '../utils.js'

/** CSS-only tooltip (also keyboard-focusable). */
export function Tip({ text, children }) {
  return (
    <span className="tip" tabIndex={0} data-tip={text}>
      {children ?? <span className="tip-i">i</span>}
    </span>
  )
}

export function Panel({ title, tip, actions, children, className = '' }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel-head">
          <h3>
            {title} {tip && <Tip text={tip} />}
          </h3>
          <div className="panel-actions">{actions}</div>
        </header>
      )}
      {children}
    </section>
  )
}

export function Toasts() {
  const { toasts, dismiss } = useApp()
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <button key={t.id} className={`toast toast-${t.kind}`} onClick={() => dismiss(t.id)}>
          <span className="toast-dot" />
          {t.message}
        </button>
      ))}
    </div>
  )
}

export function HighlightedText({ text, matched }) {
  return (
    <p className="hl-text">
      {highlightSegments(text, matched).map((s, i) =>
        s.category ? (
          <mark key={i} className={`hl hl-${s.category}`} title={`${s.category} match`}>{s.text}</mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </p>
  )
}

export function Legend() {
  return (
    <div className="legend">
      <span><i className="sw sw-keyword" />suspicious keyword</span>
      <span><i className="sw sw-synonym" />WordNet synonym</span>
      <span><i className="sw sw-clickbait" />clickbait phrase</span>
    </div>
  )
}

export class ErrorBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      return (
        <div className="panel boundary">
          <h3>Something went wrong rendering this view</h3>
          <p className="muted">{String(this.state.error.message || this.state.error)}</p>
          <button className="btn" onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      )
    }
    return this.props.children
  }
}
