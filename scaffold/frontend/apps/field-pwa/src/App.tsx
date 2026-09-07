import { Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./pages/LoginPage";
import { CasesPage } from "./pages/CasesPage";
import { FileIncidentPage } from "./pages/FileIncidentPage";
import { CaseActionsPage } from "./pages/CaseActionsPage";
import { RequireAuth } from "./routes/RequireAuth";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <CasesPage />
          </RequireAuth>
        }
      />
      <Route
        path="/incident"
        element={
          <RequireAuth>
            <FileIncidentPage />
          </RequireAuth>
        }
      />
      <Route
        path="/case/:caseId"
        element={
          <RequireAuth>
            <CaseActionsPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
