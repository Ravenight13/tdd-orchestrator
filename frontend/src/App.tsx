import { Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { TaskBoardPage } from '@/pages/TaskBoardPage'
import { TaskDetailPage } from '@/pages/TaskDetailPage'
import { WorkersPage } from '@/pages/WorkersPage'
import { CircuitsPage } from '@/pages/CircuitsPage'
import { AnalyticsPage } from '@/pages/AnalyticsPage'
import { PrdPage } from '@/pages/PrdPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/tasks" element={<TaskBoardPage />} />
        <Route path="/tasks/:taskKey" element={<TaskDetailPage />} />
        <Route path="/workers" element={<WorkersPage />} />
        <Route path="/circuits" element={<CircuitsPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/prd" element={<PrdPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  )
}
