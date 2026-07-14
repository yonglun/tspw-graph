import { Navigate, Route, Routes } from 'react-router-dom'

import { AskPage } from '../features/ask/AskPage'
import { GraphPage } from '../features/graph/GraphPage'
import { GuidePage } from '../features/guide/GuidePage'
import { OntologyPage } from '../features/ontology/OntologyPage'
import { ReviewPage } from '../features/review/ReviewPage'
import { StoryPage } from '../features/story/StoryPage'
import { BuildPage } from '../features/build/BuildPage'
import { AdminPage } from '../features/admin/AdminPage'
import { ChangePasswordPage } from '../features/auth/ChangePasswordPage'
import { LoginPage } from '../features/auth/LoginPage'
import { ProtectedRoute } from './ProtectedRoute'

export function AppRoutes() {
  return <Routes>
    <Route path="/guide" element={<GuidePage />} />
    <Route path="/ontology" element={<OntologyPage />} />
    <Route path="/graph" element={<GraphPage />} />
    <Route path="/story" element={<StoryPage />} />
    <Route path="/ask" element={<AskPage />} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/change-password" element={<ChangePasswordPage />} />
    <Route path="/admin" element={<ProtectedRoute><AdminPage /></ProtectedRoute>} />
    <Route path="/build" element={<ProtectedRoute><BuildPage /></ProtectedRoute>} />
    <Route path="/review" element={<ProtectedRoute><ReviewPage /></ProtectedRoute>} />
    <Route path="*" element={<Navigate to="/guide" replace />} />
  </Routes>
}
