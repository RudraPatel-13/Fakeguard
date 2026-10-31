import { useState } from 'react'
import './App.css'
import { AppProvider } from './context.jsx'
import Header from './components/Header.jsx'
import ArticleTab from './components/ArticleTab.jsx'
import ImageTab from './components/ImageTab.jsx'
import UrlTab from './components/UrlTab.jsx'
import RuleStudio from './components/RuleStudio.jsx'
import HistoryTab from './components/HistoryTab.jsx'
import { ErrorBoundary, Toasts } from './components/common.jsx'

function Workspace() {
  const [tab, setTab] = useState('article')
  // Article state lives here so switching tabs does not lose the user's draft or result.
  const [article, setArticle] = useState({ text: '', url: '', result: null, analyzedText: '', searchWeb: true })
  const [sample, setSample] = useState(null)
  const openImage = (file) => { setSample({ file, n: Date.now() }); setTab('image') }
  const openText = (p) => { setArticle((a) => ({ ...a, text: p.text, url: p.url || '', result: null })); setTab('article') }

  return (
    <div className="app">
      <Header tab={tab} setTab={(t) => { setTab(t); if (t !== 'image') setSample(null) }} />
      <main className="main">
        <ErrorBoundary key={tab}>
          {tab === 'article' && <ArticleTab state={article} setState={setArticle} onOpenImage={openImage} />}
          {tab === 'image' && <ImageTab key={sample?.n ?? 0} initialFile={sample?.file} onOpenImage={openImage} onText={openText} />}
          {tab === 'url' && <UrlTab />}
          {tab === 'rules' && <RuleStudio />}
          {tab === 'history' && <HistoryTab />}
        </ErrorBoundary>
      </main>
      <footer className="footer no-print">
        FakeGuard Phase 4 · live web verification + hybrid ML · Indicators, not verdicts: results are heuristic signals and do not establish truth.
      </footer>
      <Toasts />
    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <Workspace />
    </AppProvider>
  )
}
