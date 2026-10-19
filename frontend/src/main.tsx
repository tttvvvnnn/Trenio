import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import { installErrorReporting } from './errors'
import { legalDocFromPath } from './legal'
import { ErrorBoundary } from './ui/Crash'
import LegalPage from './ui/LegalPage'
import './index.css'

installErrorReporting()

// /privacy и /terms — публичные страницы документов, их открывают и вне Telegram
const legalDoc = legalDocFromPath(window.location.pathname)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>{legalDoc ? <LegalPage doc={legalDoc} /> : <App />}</ErrorBoundary>
  </StrictMode>,
)
