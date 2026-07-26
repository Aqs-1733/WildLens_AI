import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { useAuth } from './context/AuthContext'

const AlertsPage = lazy(() => import('./pages/AlertsPage'))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'))
const CollectionPage = lazy(() => import('./pages/CollectionPage'))
const CommunityPage = lazy(() => import('./pages/CommunityPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const DatasetsPage = lazy(() => import('./pages/DatasetsPage'))
const JobsPage = lazy(() => import('./pages/JobsPage'))
const LearningPage = lazy(() => import('./pages/LearningPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const PhotoIdentifyPage = lazy(() => import('./pages/PhotoIdentifyPage'))
const DiscoveryHistoryPage = lazy(() => import('./pages/DiscoveryHistoryPage'))
const NatureClassroomPage = lazy(() => import('./pages/NatureClassroomPage'))
const ModelsPage = lazy(() => import('./pages/ModelsPage'))
const NatureMapPage = lazy(() => import('./pages/NatureMapPage'))
const QAHubPage = lazy(() => import('./pages/QAHubPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const ReviewPage = lazy(() => import('./pages/ReviewPage'))
const SpeciesPage = lazy(() => import('./pages/SpeciesPage'))
const VideoPage = lazy(() => import('./pages/VideoPage'))
const SystemSettingsPage = lazy(() => import('./pages/SystemSettingsPage'))

function RouteLoader() {
  return <div className="screen-loader"><div className="pulse-logo" />正在加载生态模块…</div>
}

function Protected() {
  const { user, loading } = useAuth()
  if (loading) return <RouteLoader />
  if (!user) return <Navigate to="/login" replace />
  return <Layout />
}

export default function App() {
  const { user } = useAuth()
  return (
    <Suspense fallback={<RouteLoader />}>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
        <Route path="/register" element={user ? <Navigate to="/" replace /> : <RegisterPage />} />
        <Route element={<Protected />}>
          <Route index element={<DashboardPage />} />
          <Route path="identify" element={<PhotoIdentifyPage />} />
          <Route path="history" element={<DiscoveryHistoryPage />} />
          <Route path="map" element={<NatureMapPage />} />
          <Route path="classroom" element={<NatureClassroomPage />} />
          <Route path="video" element={<VideoPage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="species" element={<SpeciesPage />} />
          <Route path="collection" element={<CollectionPage />} />
          <Route path="learning" element={<LearningPage />} />
          <Route path="community" element={<CommunityPage />} />
          <Route path="qa" element={<QAHubPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="review" element={<ReviewPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="models" element={<ModelsPage />} />
          <Route path="datasets" element={<DatasetsPage />} />
          <Route path="settings" element={<SystemSettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
