import { Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./pages/LoginPage";
import { CasesPage } from "./pages/CasesPage";
import { IncidentPage } from "./pages/IncidentPage";
import { DashboardPage } from "./pages/DashboardPage";
import { CaseDetailPage } from "./pages/CaseDetailPage";
import { OfficerDirectoryPage } from "./pages/hr/OfficerDirectoryPage";
import { OfficerProfilePage } from "./pages/hr/OfficerProfilePage";
import { TransferApprovalsPage } from "./pages/hr/TransferApprovalsPage";
import { LeaveApprovalsPage } from "./pages/hr/LeaveApprovalsPage";
import { RequireAuth } from "./routes/RequireAuth";
import { RequirePermission } from "./routes/RequirePermission";

function Protected({ children }: { children: React.ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/cases" element={<Protected><CasesPage /></Protected>} />
      <Route path="/cases/:caseId" element={<Protected><CaseDetailPage /></Protected>} />
      <Route path="/incidents/new" element={<Protected><IncidentPage /></Protected>} />
      <Route path="/dashboard" element={<Protected><DashboardPage /></Protected>} />

      <Route
        path="/hr/officers"
        element={
          <Protected>
            <RequirePermission anyOf={["hr.officer.read"]}>
              <OfficerDirectoryPage />
            </RequirePermission>
          </Protected>
        }
      />
      <Route
        path="/hr/officers/:officerId"
        element={
          <Protected>
            <RequirePermission anyOf={["hr.officer.read"]}>
              <OfficerProfilePage />
            </RequirePermission>
          </Protected>
        }
      />
      <Route
        path="/hr/transfers"
        element={
          <Protected>
            <RequirePermission anyOf={["hr.transfer.read", "hr.transfer.approve"]}>
              <TransferApprovalsPage />
            </RequirePermission>
          </Protected>
        }
      />
      <Route
        path="/hr/leave"
        element={
          <Protected>
            <RequirePermission anyOf={["hr.leave.read", "hr.leave.approve"]}>
              <LeaveApprovalsPage />
            </RequirePermission>
          </Protected>
        }
      />

      <Route path="*" element={<Navigate to="/cases" replace />} />
    </Routes>
  );
}
