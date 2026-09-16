import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../components/auth/AuthProvider';
import { ProtectedRoute } from '../components/auth/ProtectedRoute';
import { AuthPage } from '../pages/AuthPage';
import { ProcessingPage } from '../pages/ProcessingPage';
import { ResultsPage } from '../pages/ResultsPage';
import { SiltProcessingPage } from '../pages/SiltProcessingPage';
import { SiltResultsPage } from '../pages/SiltResultsPage';
import { SiltWorkspacePage } from '../pages/SiltWorkspacePage';
import { WorkspacePage } from '../pages/WorkspacePage';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route
          path="/app"
          element={
            <ProtectedRoute>
              <WorkspacePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/processing/:jobId"
          element={
            <ProtectedRoute>
              <ProcessingPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/results/:jobId"
          element={
            <ProtectedRoute>
              <ResultsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/silt"
          element={
            <ProtectedRoute>
              <SiltWorkspacePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/silt-processing/:jobId"
          element={
            <ProtectedRoute>
              <SiltProcessingPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/silt-results/:jobId"
          element={
            <ProtectedRoute>
              <SiltResultsPage />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<Navigate to="/app" replace />} />
        <Route path="*" element={<Navigate to="/app" replace />} />
      </Routes>
    </AuthProvider>
  );
}
