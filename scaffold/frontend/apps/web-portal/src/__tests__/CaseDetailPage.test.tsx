import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CaseDetailPage } from "../pages/CaseDetailPage";
import {
  ApiError,
  type Arrest,
  type Case,
  type CourtProceeding,
  type CustodyEvent,
  type EvidenceItem,
  type Statement,
} from "../lib/api";
import { setToken } from "../lib/auth";
import { fakeJwt } from "../test/jwt";

const getCase = vi.fn();
const createEvidence = vi.fn();
const getCustody = vi.fn();
const verify = vi.fn();
const getArrests = vi.fn();
const recordArrest = vi.fn();
const getStatements = vi.fn();
const recordStatement = vi.fn();
const getCourtProceedings = vi.fn();
const recordCourtProceeding = vi.fn();

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    cases: {
      ...actual.cases,
      get: (...a: unknown[]) => getCase(...a),
      arrests: (...a: unknown[]) => getArrests(...a),
      recordArrest: (...a: unknown[]) => recordArrest(...a),
      statements: (...a: unknown[]) => getStatements(...a),
      recordStatement: (...a: unknown[]) => recordStatement(...a),
      courtProceedings: (...a: unknown[]) => getCourtProceedings(...a),
      recordCourtProceeding: (...a: unknown[]) => recordCourtProceeding(...a),
    },
    evidence: {
      create: (...a: unknown[]) => createEvidence(...a),
      custody: (...a: unknown[]) => getCustody(...a),
      verify: (...a: unknown[]) => verify(...a),
    },
  };
});

const SUB = "11111111-1111-4111-8111-111111111111";
const CASE_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const EV_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const SUSPECT_ID = "99999999-9999-4999-8999-999999999999";

function theCase(over: Partial<Case> = {}): Case {
  return {
    id: CASE_ID,
    case_number: "CASE-2026-000010",
    incident_id: null,
    status: "open",
    lead_officer_id: SUB,
    opened_at: "2026-09-05T09:00:00Z",
    closed_at: null,
    ...over,
  };
}

function item(over: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    id: EV_ID,
    case_id: CASE_ID,
    item_type: "digital_file",
    description: "seized laptop image",
    collected_by: SUB,
    collected_at: "2026-09-05T09:05:00Z",
    storage_ref: "ev_abc123",
    sha256_hash: "a".repeat(64),
    status: "logged",
    ...over,
  };
}

function custodyEvent(over: Partial<CustodyEvent> = {}): CustodyEvent {
  return {
    id: 1,
    evidence_id: EV_ID,
    action: "collected",
    from_officer: null,
    to_officer: SUB,
    acknowledgement: false,
    occurred_at: "2026-09-05T09:05:01Z",
    ...over,
  };
}

function arrest(over: Partial<Arrest> = {}): Arrest {
  return {
    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    case_id: CASE_ID,
    officer_id: SUB,
    suspect_id: SUSPECT_ID,
    arrest_date: "2026-09-05T10:00:00Z",
    location: "Central Market",
    legal_basis: "caught in the act",
    ...over,
  };
}

function statement(over: Partial<Statement> = {}): Statement {
  return {
    id: "ssssssss-ssss-4sss-8sss-ssssssssssss",
    case_id: CASE_ID,
    recorded_by: SUB,
    party_type: "witness",
    statement_text: "I saw the suspect leave through the back door.",
    recorded_at: "2026-09-05T10:05:00Z",
    ...over,
  };
}

function courtProceeding(over: Partial<CourtProceeding> = {}): CourtProceeding {
  return {
    id: "pppppppp-pppp-4ppp-8ppp-pppppppppppp",
    case_id: CASE_ID,
    hearing_date: "2026-10-01T09:00:00Z",
    court_name: "Central Magistrates Court",
    verdict: "Guilty",
    notes: "First hearing, plea entered.",
    ...over,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/cases/${CASE_ID}`]}>
        <Routes>
          <Route path="/cases/:caseId" element={<CaseDetailPage />} />
          <Route path="/cases" element={<div>cases list</div>} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getCase.mockReset();
  createEvidence.mockReset();
  getCustody.mockReset();
  verify.mockReset();
  getArrests.mockReset();
  recordArrest.mockReset();
  getStatements.mockReset();
  recordStatement.mockReset();
  getCourtProceedings.mockReset();
  recordCourtProceeding.mockReset();
  setToken(fakeJwt({ sub: SUB, badge_number: "OFF-9" }));
  getCase.mockResolvedValue(theCase());
  getCustody.mockResolvedValue([custodyEvent()]);
  getArrests.mockResolvedValue([]);
  getStatements.mockResolvedValue([]);
  getCourtProceedings.mockResolvedValue([]);
});

async function addEvidence(user: ReturnType<typeof userEvent.setup>, withFile = true) {
  await user.type(screen.getByLabelText("Item type"), "digital_file");
  await user.type(screen.getByLabelText("Description"), "seized laptop image");
  if (withFile) {
    const file = new File(["hello evidence"], "disk.img", { type: "application/octet-stream" });
    await user.upload(screen.getByLabelText(/file \(optional/i), file);
  }
  await user.click(screen.getByRole("button", { name: "Add evidence" }));
}

describe("CaseDetailPage", () => {
  it("renders the case header", async () => {
    renderPage();
    expect(await screen.findByText("CASE-2026-000010")).toBeInTheDocument();
    expect(screen.getByText("Open")).toBeInTheDocument();
  });

  it("shows a clear message for a case the caller can't read (403)", async () => {
    getCase.mockReset();
    getCase.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/can't view this case/i);
  });

  it("shows 404 for an unknown case", async () => {
    getCase.mockReset();
    getCase.mockRejectedValue(new ApiError(404, "Case not found"));
    renderPage();
    expect(await screen.findByText(/no case with that id/i)).toBeInTheDocument();
  });

  describe("upload flow", () => {
    it("POSTs multipart form data with case_id, collected_by from the token, and the file", async () => {
      const user = userEvent.setup();
      createEvidence.mockResolvedValue(item());
      renderPage();
      await screen.findByText("CASE-2026-000010");

      await addEvidence(user);

      expect(await screen.findByText(/logged digital_file/i)).toBeInTheDocument();
      expect(createEvidence).toHaveBeenCalledTimes(1);
      const form = createEvidence.mock.calls[0][0] as FormData;
      expect(form.get("case_id")).toBe(CASE_ID);
      expect(form.get("item_type")).toBe("digital_file");
      expect(form.get("description")).toBe("seized laptop image");
      expect(form.get("collected_by")).toBe(SUB);
      expect(typeof form.get("collected_at")).toBe("string");
      const file = form.get("file") as File;
      expect(file).toBeInstanceOf(File);
      expect(file.name).toBe("disk.img");
    });

    it("shows the returned SHA-256 hash for a digital item", async () => {
      const user = userEvent.setup();
      createEvidence.mockResolvedValue(item({ sha256_hash: "b".repeat(64) }));
      renderPage();
      await screen.findByText("CASE-2026-000010");
      await addEvidence(user);
      expect(await screen.findByText("b".repeat(64))).toBeInTheDocument();
    });

    it("omits the file field for a physical item and shows no hash", async () => {
      const user = userEvent.setup();
      createEvidence.mockResolvedValue(
        item({ item_type: "physical", sha256_hash: null, storage_ref: null }),
      );
      renderPage();
      await screen.findByText("CASE-2026-000010");
      await addEvidence(user, /* withFile */ false);

      const form = createEvidence.mock.calls[0][0] as FormData;
      expect(form.get("file")).toBeNull();
      expect(await screen.findByText(/no digital file/i)).toBeInTheDocument();
      // no verify button for an item with nothing to hash
      expect(screen.queryByRole("button", { name: "Verify integrity" })).not.toBeInTheDocument();
    });

    it("surfaces a 403 with a clear permission message", async () => {
      const user = userEvent.setup();
      createEvidence.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
      renderPage();
      await screen.findByText("CASE-2026-000010");
      await addEvidence(user);
      expect(await screen.findByRole("alert")).toHaveTextContent(/can't log evidence/i);
      expect(screen.getByText(/evidence\.vault\.write/)).toBeInTheDocument();
    });

    it("surfaces 422 field errors", async () => {
      const user = userEvent.setup();
      createEvidence.mockRejectedValue(
        new ApiError(422, "Unprocessable Entity", {
          detail: [{ loc: ["body", "description"], msg: "field required", type: "missing" }],
        }),
      );
      renderPage();
      await screen.findByText("CASE-2026-000010");
      await addEvidence(user);
      expect(await screen.findByText("field required")).toBeInTheDocument();
    });
  });

  describe("chain of custody", () => {
    it("renders custody events in the order the API returns them", async () => {
      const user = userEvent.setup();
      createEvidence.mockResolvedValue(item());
      getCustody.mockResolvedValue([
        custodyEvent({ id: 1, action: "collected" }),
        custodyEvent({ id: 2, action: "stored", to_officer: null }),
        custodyEvent({
          id: 3,
          action: "transferred",
          to_officer: "22222222-2222-4222-8222-222222222222",
          acknowledgement: true,
        }),
      ]);

      renderPage();
      await screen.findByText("CASE-2026-000010");
      await addEvidence(user);

      expect(getCustody).toHaveBeenCalledWith(EV_ID);
      const heading = await screen.findByText("Chain of custody");
      const items = within(heading.closest("div")!).getAllByRole("listitem");
      expect(items).toHaveLength(3);
      expect(items[0]).toHaveTextContent("collected");
      expect(items[1]).toHaveTextContent("stored");
      expect(items[2]).toHaveTextContent("transferred");
      expect(items[2]).toHaveTextContent("acknowledged");
    });

    it("surfaces a 403 on the custody fetch", async () => {
      const user = userEvent.setup();
      createEvidence.mockResolvedValue(item());
      getCustody.mockReset();
      getCustody.mockRejectedValue(new ApiError(403, "RBAC scope denied"));

      renderPage();
      await screen.findByText("CASE-2026-000010");
      await addEvidence(user);

      expect(await screen.findByText(/permission to view custody/i)).toBeInTheDocument();
    });
  });

  describe("record arrest", () => {
    async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
      await user.type(screen.getByLabelText("Suspect id"), SUSPECT_ID);
      await user.type(screen.getByLabelText("Location"), "Central Market");
      await user.type(screen.getByLabelText("Legal basis"), "caught in the act");
      await user.click(screen.getByRole("button", { name: "Record arrest" }));
    }

    it("lists arrests already recorded against the case", async () => {
      getArrests.mockResolvedValue([arrest()]);
      renderPage();
      expect(await screen.findByText(SUSPECT_ID)).toBeInTheDocument();
      expect(screen.getByText("caught in the act")).toBeInTheDocument();
      expect(getArrests).toHaveBeenCalledWith(CASE_ID);
    });

    it("shows an empty-state message with no arrests", async () => {
      renderPage();
      expect(await screen.findByText(/no arrests recorded yet/i)).toBeInTheDocument();
    });

    it("POSTs officer_id from the token plus the form fields, and adds the result to the list", async () => {
      const user = userEvent.setup();
      recordArrest.mockResolvedValue(arrest());
      renderPage();
      await screen.findByText("CASE-2026-000010");

      await fillAndSubmit(user);

      expect(await screen.findByText(/arrest recorded/i)).toBeInTheDocument();
      expect(recordArrest).toHaveBeenCalledTimes(1);
      const [postedCaseId, body] = recordArrest.mock.calls[0];
      expect(postedCaseId).toBe(CASE_ID);
      expect(body.officer_id).toBe(SUB);
      expect(body.suspect_id).toBe(SUSPECT_ID);
      expect(body.location).toBe("Central Market");
      expect(body.legal_basis).toBe("caught in the act");
      expect(typeof body.arrest_date).toBe("string");

      expect(await screen.findAllByText(SUSPECT_ID)).toHaveLength(1);
    });

    it("surfaces a 403 with a clear permission message", async () => {
      const user = userEvent.setup();
      recordArrest.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
      renderPage();
      await screen.findByText("CASE-2026-000010");
      await fillAndSubmit(user);
      expect(await screen.findByRole("alert")).toHaveTextContent(/can't record an arrest/i);
      expect(screen.getByText(/case\.write/)).toBeInTheDocument();
    });

    it("surfaces 422 field errors", async () => {
      const user = userEvent.setup();
      recordArrest.mockRejectedValue(
        new ApiError(422, "Unprocessable Entity", {
          detail: [{ loc: ["body", "suspect_id"], msg: "invalid uuid", type: "value_error" }],
        }),
      );
      renderPage();
      await screen.findByText("CASE-2026-000010");
      await fillAndSubmit(user);
      expect(await screen.findByText("invalid uuid")).toBeInTheDocument();
    });

    it("surfaces a 403 fetching the arrest list", async () => {
      getArrests.mockReset();
      getArrests.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
      renderPage();
      expect(
        await screen.findByText(/permission to view arrests/i),
      ).toBeInTheDocument();
    });
  });

  describe("record statement", () => {
    async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
      await user.selectOptions(screen.getByLabelText("Party type"), "victim");
      await user.type(
        screen.getByLabelText("Statement"),
        "My wallet was taken from my bag.",
      );
      await user.click(screen.getByRole("button", { name: "Record statement" }));
    }

    it("lists statements already recorded against the case", async () => {
      getStatements.mockResolvedValue([statement()]);
      renderPage();
      // "Witness" alone would also match the party-type <option>, so anchor on
      // the (unique) statement text and assert its list item's full content.
      const text = await screen.findByText(
        "I saw the suspect leave through the back door.",
      );
      expect(text.closest("li")).toHaveTextContent("Witness");
      expect(getStatements).toHaveBeenCalledWith(CASE_ID);
    });

    it("shows an empty-state message with no statements", async () => {
      renderPage();
      expect(await screen.findByText(/no statements recorded yet/i)).toBeInTheDocument();
    });

    it("POSTs recorded_by from the token plus the form fields, and adds the result to the list", async () => {
      const user = userEvent.setup();
      recordStatement.mockResolvedValue(
        statement({ party_type: "victim", statement_text: "My wallet was taken from my bag." }),
      );
      renderPage();
      await screen.findByText("CASE-2026-000010");

      await fillAndSubmit(user);

      expect(await screen.findByText(/statement recorded/i)).toBeInTheDocument();
      expect(recordStatement).toHaveBeenCalledTimes(1);
      const [postedCaseId, body] = recordStatement.mock.calls[0];
      expect(postedCaseId).toBe(CASE_ID);
      expect(body.recorded_by).toBe(SUB);
      expect(body.party_type).toBe("victim");
      expect(body.statement_text).toBe("My wallet was taken from my bag.");

      expect(await screen.findAllByText("My wallet was taken from my bag.")).toHaveLength(1);
    });

    it("surfaces a 403 with a clear permission message", async () => {
      const user = userEvent.setup();
      recordStatement.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
      renderPage();
      await screen.findByText("CASE-2026-000010");
      await fillAndSubmit(user);
      expect(await screen.findByRole("alert")).toHaveTextContent(
        /can't record a statement/i,
      );
      expect(screen.getByText(/case\.write/)).toBeInTheDocument();
    });

    it("surfaces 422 field errors", async () => {
      const user = userEvent.setup();
      recordStatement.mockRejectedValue(
        new ApiError(422, "Unprocessable Entity", {
          detail: [{ loc: ["body", "statement_text"], msg: "field required", type: "missing" }],
        }),
      );
      renderPage();
      await screen.findByText("CASE-2026-000010");
      await fillAndSubmit(user);
      expect(await screen.findByText("field required")).toBeInTheDocument();
    });

    it("surfaces a 403 fetching the statement list", async () => {
      getStatements.mockReset();
      getStatements.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
      renderPage();
      expect(
        await screen.findByText(/permission to view statements/i),
      ).toBeInTheDocument();
    });
  });

  describe("record court proceeding", () => {
    async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
      await user.type(screen.getByLabelText("Court name"), "Central Magistrates Court");
      await user.type(screen.getByLabelText("Verdict"), "Guilty");
      await user.type(screen.getByLabelText("Notes"), "First hearing, plea entered.");
      await user.click(
        screen.getByRole("button", { name: "Record court proceeding" }),
      );
    }

    it("lists court proceedings already recorded against the case", async () => {
      getCourtProceedings.mockResolvedValue([courtProceeding()]);
      renderPage();
      // Anchor on the (unique) court name rather than "Guilty" alone, in case a
      // verdict value ever collides with other on-screen text (see the
      // dedicated collision regression test below).
      const item = (await screen.findByText("Central Magistrates Court")).closest("li")!;
      expect(item).toHaveTextContent("Guilty");
      expect(item).toHaveTextContent("First hearing, plea entered.");
      expect(getCourtProceedings).toHaveBeenCalledWith(CASE_ID);
    });

    it("shows an empty-state message with no court proceedings", async () => {
      renderPage();
      expect(
        await screen.findByText(/no court proceedings recorded yet/i),
      ).toBeInTheDocument();
    });

    it("omits verdict and notes when unset", async () => {
      getCourtProceedings.mockResolvedValue([
        courtProceeding({ verdict: null, notes: null }),
      ]);
      renderPage();
      const item = (await screen.findByText("Central Magistrates Court")).closest("li")!;
      expect(item).not.toHaveTextContent("Verdict:");
      expect(item).not.toHaveTextContent("Guilty");
    });

    it("a verdict colliding with the case status badge stays scoped to its own list item", async () => {
      // theCase() defaults to status: "open", which renders as an "Open" badge
      // in the header — the exact same string this proceeding uses as its
      // verdict. A naive screen.getByText("Open") would be ambiguous.
      getCourtProceedings.mockResolvedValue([
        courtProceeding({
          hearing_date: "2026-10-02T09:00:00Z",
          court_name: "Traffic Court",
          verdict: "Open",
          notes: null,
        }),
      ]);
      renderPage();

      // Wait for both the header and the proceedings list to have resolved
      // before counting "Open" occurrences — they load via independent
      // queries, so an earlier findAllByText could catch just one of them.
      await screen.findByText("Traffic Court");
      const matches = screen.getAllByText("Open");
      expect(matches.length).toBeGreaterThan(1); // the status badge + the verdict

      const item = screen.getByText("Traffic Court").closest("li")!;
      expect(within(item).getByText("Open")).toBeInTheDocument();
    });

    it("POSTs the form fields and adds the result to the list", async () => {
      const user = userEvent.setup();
      recordCourtProceeding.mockResolvedValue(courtProceeding());
      renderPage();
      await screen.findByText("CASE-2026-000010");

      await fillAndSubmit(user);

      expect(await screen.findByText(/court proceeding recorded/i)).toBeInTheDocument();
      expect(recordCourtProceeding).toHaveBeenCalledTimes(1);
      const [postedCaseId, body] = recordCourtProceeding.mock.calls[0];
      expect(postedCaseId).toBe(CASE_ID);
      expect(body.court_name).toBe("Central Magistrates Court");
      expect(body.verdict).toBe("Guilty");
      expect(body.notes).toBe("First hearing, plea entered.");
      expect(typeof body.hearing_date).toBe("string");

      expect(
        await screen.findAllByText("Central Magistrates Court"),
      ).toHaveLength(1);
    });

    it("surfaces a 403 with a clear permission message", async () => {
      const user = userEvent.setup();
      recordCourtProceeding.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
      renderPage();
      await screen.findByText("CASE-2026-000010");
      await fillAndSubmit(user);
      expect(await screen.findByRole("alert")).toHaveTextContent(
        /can't record a court proceeding/i,
      );
      expect(screen.getByText(/case\.write/)).toBeInTheDocument();
    });

    it("surfaces 422 field errors", async () => {
      const user = userEvent.setup();
      recordCourtProceeding.mockRejectedValue(
        new ApiError(422, "Unprocessable Entity", {
          detail: [{ loc: ["body", "court_name"], msg: "field too long", type: "value_error" }],
        }),
      );
      renderPage();
      await screen.findByText("CASE-2026-000010");
      await fillAndSubmit(user);
      expect(await screen.findByText("field too long")).toBeInTheDocument();
    });

    it("surfaces a 403 fetching the court proceedings list", async () => {
      getCourtProceedings.mockReset();
      getCourtProceedings.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
      renderPage();
      expect(
        await screen.findByText(/permission to view court proceedings/i),
      ).toBeInTheDocument();
    });
  });

  describe("verify integrity", () => {
    it("shows a clear match:true result", async () => {
      const user = userEvent.setup();
      createEvidence.mockResolvedValue(item());
      verify.mockResolvedValue({
        evidence_id: EV_ID,
        stored_hash: "a".repeat(64),
        computed_hash: "a".repeat(64),
        match: true,
        verified_at: "2026-09-05T09:10:00Z",
      });

      renderPage();
      await screen.findByText("CASE-2026-000010");
      await addEvidence(user);
      await user.click(await screen.findByRole("button", { name: "Verify integrity" }));

      expect(await screen.findByText(/match: file is intact/i)).toBeInTheDocument();
      expect(verify).toHaveBeenCalledWith(EV_ID);
    });

    it("shows a clear match:false (tamper) result", async () => {
      const user = userEvent.setup();
      createEvidence.mockResolvedValue(item());
      verify.mockResolvedValue({
        evidence_id: EV_ID,
        stored_hash: "a".repeat(64),
        computed_hash: "f".repeat(64),
        match: false,
        verified_at: "2026-09-05T09:10:00Z",
      });

      renderPage();
      await screen.findByText("CASE-2026-000010");
      await addEvidence(user);
      await user.click(await screen.findByRole("button", { name: "Verify integrity" }));

      expect(await screen.findByText(/mismatch — tampering detected/i)).toBeInTheDocument();
    });

    it("explains a 409 (no stored file)", async () => {
      const user = userEvent.setup();
      createEvidence.mockResolvedValue(item());
      verify.mockRejectedValue(new ApiError(409, "Item has no stored digital file to verify"));

      renderPage();
      await screen.findByText("CASE-2026-000010");
      await addEvidence(user);
      await user.click(await screen.findByRole("button", { name: "Verify integrity" }));

      expect(await screen.findByText(/no stored file to verify/i)).toBeInTheDocument();
    });
  });
});
