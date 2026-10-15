import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import { installErrorReporting } from './errors'
import { ErrorBoundary } from './ui/Crash'
import './index.css'

installErrorReporting()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
