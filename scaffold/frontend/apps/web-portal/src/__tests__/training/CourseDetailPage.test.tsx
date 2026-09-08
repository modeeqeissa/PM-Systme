import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CourseDetailPage } from "../../pages/training/CourseDetailPage";
import {
  type Assessment,
  type AssessmentResult,
  type AttendanceRow,
  type Course,
  type Material,
  type TrainingSession,
} from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const listCourses = vi.fn();
const forCourseMaterials = vi.fn();
const uploadMaterial = vi.fn();
const removeMaterial = vi.fn();
const listSessions = vi.fn();
const createSession = vi.fn();
const sessionAttendance = vi.fn();
const registerAttendance = vi.fn();
const setAttendanceStatus = vi.fn();
const forCourseAssessments = vi.fn();
const createAssessment = vi.fn();
const assessmentResults = vi.fn();
const recordResult = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    training: {
      ...actual.training,
      courses: { ...actual.training.courses, list: (...a: unknown[]) => listCourses(...a) },
      materials: {
        forCourse: (...a: unknown[]) => forCourseMaterials(...a),
        upload: (...a: unknown[]) => uploadMaterial(...a),
        remove: (...a: unknown[]) => removeMaterial(...a),
      },
      sessions: {
        list: (...a: unknown[]) => listSessions(...a),
        create: (...a: unknown[]) => createSession(...a),
        update: actual.training.sessions.update,
        attendance: (...a: unknown[]) => sessionAttendance(...a),
        register: (...a: unknown[]) => registerAttendance(...a),
        setAttendanceStatus: (...a: unknown[]) => setAttendanceStatus(...a),
      },
      assessments: {
        forCourse: (...a: unknown[]) => forCourseAssessments(...a),
        create: (...a: unknown[]) => createAssessment(...a),
        results: (...a: unknown[]) => assessmentResults(...a),
        recordResult: (...a: unknown[]) => recordResult(...a),
      },
    },
  };
});

const COURSE_ID = 7;
const course = (o: Partial<Course> = {}): Course => ({
  id: COURSE_ID, title: "De-escalation", validity_months: 24, mandatory: true, ...o,
});
const material = (o: Partial<Material> = {}): Material => ({
  id: "m-1", course_id: COURSE_ID, title: "Handbook", file_ref: "mat_abc", ...o,
});
const session = (o: Partial<TrainingSession> = {}): TrainingSession => ({
  id: "s-1", course_id: COURSE_ID, scheduled_at: "2026-11-01T09:00:00Z",
  location: "Room 4", instructor_officer_id: null, capacity: 20, ...o,
});
const attendance = (o: Partial<AttendanceRow> = {}): AttendanceRow => ({
  id: "a-1", session_id: "s-1", officer_id: "off-9", status: "registered", ...o,
});
const assessment = (o: Partial<Assessment> = {}): Assessment => ({
  id: "as-1", course_id: COURSE_ID, title: "Final", passing_score: 70, ...o,
});
const result = (o: Partial<AssessmentResult> = {}): AssessmentResult => ({
  id: "r-1", assessment_id: "as-1", officer_id: "off-9", score: 82, taken_at: "2026-11-02T10:00:00Z", passed: true, ...o,
});

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "TR-1", sub: "u-1" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/training/courses/${COURSE_ID}`]}>
        <Routes>
          <Route path="/training/courses/:courseId" element={<CourseDetailPage />} />
          <Route path="/training/courses" element={<div>catalog</div>} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  [
    listCourses, forCourseMaterials, uploadMaterial, removeMaterial, listSessions, createSession,
    sessionAttendance, registerAttendance, setAttendanceStatus, forCourseAssessments, createAssessment,
    assessmentResults, recordResult,
  ].forEach((m) => m.mockReset());
  listCourses.mockResolvedValue([course()]);
  forCourseMaterials.mockResolvedValue([]);
  listSessions.mockResolvedValue([]);
  forCourseAssessments.mockResolvedValue([]);
  sessionAttendance.mockResolvedValue([]);
  assessmentResults.mockResolvedValue([]);
});

describe("CourseDetailPage", () => {
  it("shows the course header and empty sections", async () => {
    renderPage(["training.cert.read"]);
    expect(await screen.findByRole("heading", { name: "De-escalation" })).toBeInTheDocument();
    expect(await screen.findByText("No materials yet.")).toBeInTheDocument();
    expect(await screen.findByText("No sessions scheduled.")).toBeInTheDocument();
    expect(await screen.findByText("No assessments yet.")).toBeInTheDocument();
  });

  it("uploads a material as multipart", async () => {
    uploadMaterial.mockResolvedValue(material());
    const user = userEvent.setup();
    renderPage(["training.cert.read", "training.cert.write"]);
    await screen.findByRole("heading", { name: "De-escalation" });

    const matForm = screen.getByRole("button", { name: "Upload material" }).closest("form")!;
    await user.type(within(matForm).getByLabelText("Title"), "Handbook");
    const file = new File(["pdf"], "handbook.pdf", { type: "application/pdf" });
    await user.upload(within(matForm).getByLabelText("File"), file);
    forCourseMaterials.mockResolvedValue([material()]);
    await user.click(screen.getByRole("button", { name: "Upload material" }));

    expect(uploadMaterial).toHaveBeenCalledTimes(1);
    const [postedCourseId, form] = uploadMaterial.mock.calls[0];
    expect(postedCourseId).toBe(COURSE_ID);
    expect((form as FormData).get("title")).toBe("Handbook");
    expect((form as FormData).get("file")).toBeInstanceOf(File);
  });

  it("schedules a session with instructor defaulted from the token", async () => {
    createSession.mockResolvedValue(session());
    const user = userEvent.setup();
    renderPage(["training.cert.read", "training.cert.write"]);
    await screen.findByRole("heading", { name: "De-escalation" });

    await user.type(screen.getByLabelText("Location"), "Auditorium");
    await user.type(screen.getByLabelText("Capacity"), "30");
    await user.click(screen.getByRole("button", { name: "Schedule session" }));

    expect(createSession).toHaveBeenCalledTimes(1);
    const [body] = createSession.mock.calls[0];
    expect(body.course_id).toBe(COURSE_ID);
    expect(body.location).toBe("Auditorium");
    expect(body.capacity).toBe(30);
    expect(body.instructor_officer_id).toBe("u-1");
  });

  it("registers an officer on a session and marks them attended", async () => {
    listSessions.mockResolvedValue([session()]);
    registerAttendance.mockResolvedValue(attendance());
    setAttendanceStatus.mockResolvedValue(attendance({ status: "attended" }));
    const user = userEvent.setup();
    renderPage(["training.cert.read", "training.cert.write"]);
    await screen.findByText(/Room 4/);

    await user.click(screen.getByRole("button", { name: "Attendance" }));
    await user.type(await screen.findByLabelText("Officer id"), "off-9");
    sessionAttendance.mockResolvedValue([attendance()]);
    await user.click(screen.getByRole("button", { name: "Register" }));
    expect(registerAttendance).toHaveBeenCalledWith("s-1", { officer_id: "off-9" });

    const row = (await screen.findByText("off-9")).closest("li")!;
    await user.click(within(row).getByRole("button", { name: "mark attended" }));
    expect(setAttendanceStatus).toHaveBeenCalledWith("a-1", "attended");
  });

  it("creates an assessment and records a graded result", async () => {
    forCourseAssessments.mockResolvedValue([assessment()]);
    recordResult.mockResolvedValue(result({ passed: false, score: 55 }));
    const user = userEvent.setup();
    renderPage(["training.cert.read", "training.cert.write"]);
    await screen.findByText(/pass ≥ 70/);

    await user.click(screen.getByRole("button", { name: "Results" }));
    const gradeForm = (await screen.findByRole("button", { name: "Record" })).closest("form")!;
    await user.type(within(gradeForm).getByLabelText("Officer id"), "off-3");
    await user.type(within(gradeForm).getByLabelText("Score"), "55");
    assessmentResults.mockResolvedValue([result({ passed: false, score: 55 })]);
    await user.click(screen.getByRole("button", { name: "Record" }));

    expect(recordResult).toHaveBeenCalledWith("as-1", { officer_id: "off-3", score: 55 });
    expect(await screen.findByText("Fail")).toBeInTheDocument();
  });

  it("hides all write controls without training.cert.write", async () => {
    forCourseMaterials.mockResolvedValue([material()]);
    forCourseAssessments.mockResolvedValue([assessment()]);
    renderPage(["training.cert.read"]);
    await screen.findByRole("heading", { name: "De-escalation" });
    expect(screen.queryByRole("button", { name: "Upload material" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Schedule session" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add assessment" })).not.toBeInTheDocument();
  });

  it("shows a 404 for an unknown course", async () => {
    listCourses.mockResolvedValue([]);
    renderPage(["training.cert.read"]);
    expect(await screen.findByText(/no course with that id/i)).toBeInTheDocument();
  });
});
