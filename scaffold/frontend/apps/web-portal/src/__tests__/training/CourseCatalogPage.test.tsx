import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CourseCatalogPage } from "../../pages/training/CourseCatalogPage";
import { ApiError, type Certification, type Course } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const listCourses = vi.fn();
const createCourse = vi.fn();
const updateCourse = vi.fn();
const removeCourse = vi.fn();
const listCerts = vi.fn();
const createCert = vi.fn();
const removeCert = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    training: {
      ...actual.training,
      courses: {
        list: (...a: unknown[]) => listCourses(...a),
        create: (...a: unknown[]) => createCourse(...a),
        update: (...a: unknown[]) => updateCourse(...a),
        remove: (...a: unknown[]) => removeCourse(...a),
      },
      certifications: {
        list: (...a: unknown[]) => listCerts(...a),
        create: (...a: unknown[]) => createCert(...a),
        remove: (...a: unknown[]) => removeCert(...a),
      },
    },
  };
});

const course = (over: Partial<Course> = {}): Course => ({ id: 1, title: "First Aid", validity_months: 12, mandatory: true, ...over });
const cert = (over: Partial<Certification> = {}): Certification => ({ id: 10, course_id: 1, ...over });

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "TR-1" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/training/courses"]}>
        <Routes>
          <Route path="/training/courses" element={<CourseCatalogPage />} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  [listCourses, createCourse, updateCourse, removeCourse, listCerts, createCert, removeCert].forEach((m) => m.mockReset());
  listCourses.mockResolvedValue([]);
  listCerts.mockResolvedValue([]);
});

describe("CourseCatalogPage", () => {
  it("lists courses and their certifications", async () => {
    listCourses.mockResolvedValue([course()]);
    listCerts.mockResolvedValue([cert(), cert({ id: 11 })]);
    renderPage(["training.cert.read"]);
    expect(await screen.findByText("First Aid")).toBeInTheDocument();
    expect(screen.getByText(/valid 12 months/)).toBeInTheDocument();
    expect(screen.getByText("Certification #10")).toBeInTheDocument();
    expect(screen.getByText("Certification #11")).toBeInTheDocument();
  });

  it("hides create/edit/delete controls without training.cert.write", async () => {
    listCourses.mockResolvedValue([course()]);
    renderPage(["training.cert.read"]);
    await screen.findByText("First Aid");
    expect(screen.queryByRole("button", { name: "Add course" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add certification" })).not.toBeInTheDocument();
  });

  it("creates a course with title/validity/mandatory", async () => {
    createCourse.mockResolvedValue(course({ id: 2, title: "Firearms" }));
    const user = userEvent.setup();
    renderPage(["training.cert.read", "training.cert.write"]);
    await screen.findByText(/No courses in the catalog/i);
    await user.click(screen.getByRole("button", { name: "Add course" }));
    await user.type(screen.getByLabelText("Title"), "Firearms");
    await user.type(screen.getByLabelText("Validity (months)"), "24");
    await user.click(screen.getByLabelText("Mandatory"));
    listCourses.mockResolvedValue([course({ id: 2, title: "Firearms", validity_months: 24 })]);
    await user.click(screen.getByRole("button", { name: "Add course" }));
    expect(createCourse).toHaveBeenCalledWith({ title: "Firearms", validity_months: 24, mandatory: true });
    expect(await screen.findByText("Course added.")).toBeInTheDocument();
  });

  it("adds a certification to a course", async () => {
    listCourses.mockResolvedValue([course()]);
    createCert.mockResolvedValue(cert({ id: 99 }));
    const user = userEvent.setup();
    renderPage(["training.cert.read", "training.cert.write"]);
    await screen.findByText("First Aid");
    await user.click(screen.getByRole("button", { name: "Add certification" }));
    expect(createCert).toHaveBeenCalledWith({ course_id: 1 });
  });

  it("surfaces a 409 when deleting a course still referenced", async () => {
    listCourses.mockResolvedValue([course()]);
    removeCourse.mockRejectedValue(new ApiError(409, "Course still has certifications referencing it"));
    const user = userEvent.setup();
    renderPage(["training.cert.read", "training.cert.write"]);
    await screen.findByText("First Aid");
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByText(/still has certifications referencing it/i)).toBeInTheDocument();
  });
});
