import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { AppProviders } from './app/app-providers'
import { AppRouter } from './app/app-router'
import './styles/droom.css'

const container = document.getElementById('root')
if (container === null) throw new Error('#root is missing from index.html')

createRoot(container).render(
  <StrictMode>
    <AppProviders>
      <AppRouter />
    </AppProviders>
  </StrictMode>,
)
