import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { IssueCertificationPage } from "../../pages/training/IssueCertificationPage";
import { ApiError, type OfficerCertification } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const listCourses = vi.fn();
const listCerts = vi.fn();
const listOfficerCerts = vi.fn();
const issue = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    training: {
      ...actual.training,
      courses: { list: (...a: unknown[]) => listCourses(...a) },
      certifications: { list: (...a: unknown[]) => listCerts(...a) },
      officerCerts: { list: (...a: unknown[]) => listOfficerCerts(...a), issue: (...a: unknown[]) => issue(...a) },
    },
  };
});

const oc = (over: Partial<OfficerCertification> = {}): OfficerCertification => ({
  id: "oc-1",
  officer_id: "0ffffff0-0000-0000-0000-000000000000",
  certification_id: 10,
  issued_date: "2026-01-01",
  expires_date: "2027-01-01",
  status: "active",
  ...over,
});

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "TR-1" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/training/issue"]}>
        <Routes>
          <Route path="/training/issue" element={<IssueCertificationPage />} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  [listCourses, listCerts, listOfficerCerts, issue].forEach((m) => m.mockReset());
  listCourses.mockResolvedValue([{ id: 1, title: "First Aid", validity_months: 12, mandatory: true }]);
  listCerts.mockResolvedValue([{ id: 10, course_id: 1 }]);
  listOfficerCerts.mockResolvedValue([]);
});

describe("IssueCertificationPage", () => {
  it("issues a certification and shows the server-computed expiry + status", async () => {
    issue.mockResolvedValue(oc({ expires_date: "2027-06-30", status: "expiring_soon" }));
    const user = userEvent.setup();
    renderPage(["training.cert.read", "training.cert.write"]);
    await screen.findByLabelText("Officer id");
    await user.type(screen.getByLabelText("Officer id"), "0ffffff0-0000-0000-0000-000000000000");
    await user.selectOptions(screen.getByLabelText("Certification"), "10");
    await user.click(screen.getByRole("button", { name: "Issue certification" }));

    expect(issue).toHaveBeenCalledWith({
      officer_id: "0ffffff0-0000-0000-0000-000000000000",
      certification_id: 10,
      issued_date: undefined,
    });
    const banner = await screen.findByText(/Expires/);
    expect(banner).toHaveTextContent("2027-06-30");
    expect(banner).toHaveTextContent("expiring_soon");
  });

  it("blocks issuing without training.cert.write", async () => {
    renderPage(["training.cert.read"]);
    expect(await screen.findByText(/can't issue certifications/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Issue certification" })).not.toBeInTheDocument();
  });

  it("surfaces a 404 for an unknown certification_id", async () => {
    issue.mockRejectedValue(new ApiError(404, "certification_id does not exist"));
    const user = userEvent.setup();
    renderPage(["training.cert.read", "training.cert.write"]);
    await screen.findByLabelText("Officer id");
    await user.type(screen.getByLabelText("Officer id"), "0ffffff0-0000-0000-0000-000000000000");
    await user.selectOptions(screen.getByLabelText("Certification"), "10");
    await user.click(screen.getByRole("button", { name: "Issue certification" }));
    expect(await screen.findByText(/not found/i)).toBeInTheDocument();
  });
});
