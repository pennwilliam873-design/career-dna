import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import App from './App'
import Dashboard from './pages/Dashboard'
import ClientWorkspace from './pages/ClientWorkspace'
import AccessGate from './AccessGate'
import './App.css'
import './os.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AccessGate>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/legacy" element={<App />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/client/:id" element={<ClientWorkspace />} />
        </Routes>
      </BrowserRouter>
    </AccessGate>
  </React.StrictMode>
)
