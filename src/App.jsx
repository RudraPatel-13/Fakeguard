import { useEffect, useState } from 'react'
import './App.css'
import './fx.css'
import './auth.css'
import { AppProvider } from './context.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import { useAuth } from './context/authContext.js'
import AuthModal from './components/AuthModal.jsx'
import HistoryDrawer from './components/HistoryDrawer.jsx'
import LockedPanel from './components/LockedPanel.jsx'
import Header from './components/Header.jsx'
import HeroHeader from './components/HeroHeader.jsx'
import AmbientBackground from './components/AmbientBackground.jsx'
import ArticleTab from './components/ArticleTab.jsx'
import ImageTab from './components/ImageTab.jsx'
import UrlTab from './components/UrlTab.jsx'
import RuleStudio from './components/RuleStudio.jsx'
import HistoryTab from './components/HistoryTab.jsx'
import { ErrorBoundary, Toasts } from './components/common.jsx'

/** 3D tilt on result cards: one delegated listener sets --rx/--ry on the hovered card (skipped on touch and reduced motion). */
function useTilt() {
  useEffect(() => {
    if (window.matchMedia('(pointer: coarse), (prefers-reduced-motion: reduce)').matches) return undefined
    let cur = null
    const reset = () => {
      if (!cur) return
      cur.style.removeProperty('--rx')
      cur.style.removeProperty('--ry')
      cur = null
    }
    const move = (e) => {
      const el = e.target.closest?.('.report .panel:not(:has(.compare)), .tilt') ?? null
      if (el !== cur) reset()
      if (!el) return
      cur = el
      const r = el.getBoundingClientRect()
      el.style.setProperty('--rx', `${(-((e.clientY - r.top) / r.height - 0.5) * 5).toFixed(2)}deg`)
      el.style.setProperty('--ry', `${(((e.clientX - r.left) / r.width - 0.5) * 6).toFixed(2)}deg`)
    }
    document.addEventListener('pointermove', move, { passive: true })
    document.addEventListener('pointerleave', reset)
    return () => {
      document.removeEventListener('pointermove', move)
      document.removeEventListener('pointerleave', reset)
    }
  }, [])
}

function Workspace() {
  useTilt()
  const { isAuthenticated, modal } = useAuth()
  const [tab, setTab] = useState('article')
  // Article state lives here so switching tabs does not lose the user's draft or result.
  const [article, setArticle] = useState({ text: '', url: '', result: null, analyzedText: '', searchWeb: true })
  const [sample, setSample] = useState(null)
  const openImage = (file) => { setSample({ file, n: Date.now() }); setTab('image') }
  const openText = (p) => { setArticle((a) => ({ ...a, text: p.text, url: p.url || '', result: null })); setTab('article') }

  return (
    <div className="app">
      <AmbientBackground />
      <HeroHeader />
      <Header tab={tab} setTab={(t) => { setTab(t); if (t !== 'image') setSample(null) }} />
      <main className="main">
        <ErrorBoundary key={tab}>
          {tab === 'article' && <ArticleTab state={article} setState={setArticle} onOpenImage={openImage} />}
          {tab === 'image' && <ImageTab key={sample?.n ?? 0} initialFile={sample?.file} onOpenImage={openImage} onText={openText} />}
          {tab === 'url' && <UrlTab />}
          {tab === 'rules' && (isAuthenticated ? <RuleStudio /> : <LockedPanel icon="🔐" title="Rule Studio is for signed-in analysts" blurb="Sign in to inspect and test the custom keyword library. Guests can still run scans on the Article, Image and URL tabs." />)}
          {tab === 'history' && (isAuthenticated ? <HistoryTab /> : <LockedPanel icon="📜" title="Scan history is saved for signed-in users" blurb="Sign in and every scan you run is saved to your account and listed here and in the history drawer." />)}
        </ErrorBoundary>
      </main>
      <footer className="footer no-print">
        FakeGuard Phase 4 · live web verification + hybrid ML · Indicators, not verdicts: results are heuristic signals and do not establish truth.
      </footer>
      <Toasts />
      {modal && <AuthModal />}
      <HistoryDrawer />
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
    <AppProvider>
      <Workspace />
    </AppProvider>
    </AuthProvider>
  )
}
