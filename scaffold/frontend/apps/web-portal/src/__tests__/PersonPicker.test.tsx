import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PersonPicker } from "../components/PersonPicker";
import { ApiError, type Person } from "../lib/api";

const search = vi.fn();
const get = vi.fn();
const create = vi.fn();

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    persons: {
      search: (...a: unknown[]) => search(...a),
      get: (...a: unknown[]) => get(...a),
      create: (...a: unknown[]) => create(...a),
    },
  };
});

function person(over: Partial<Person> = {}): Person {
  return {
    id: "p1p1p1p1-0000-4000-8000-000000000001",
    first_name: "Aïcha",
    last_name: "Traoré",
    date_of_birth: "1992-07-11",
    national_id: "NID-42",
    gender: null,
    address: null,
    phone: null,
    notes: null,
    created_at: "2026-09-01T00:00:00Z",
    ...over,
  };
}

function renderPicker(
  onChange = vi.fn(),
  props: Partial<React.ComponentProps<typeof PersonPicker>> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <PersonPicker value={null} onChange={onChange} label="Person" {...props} />
    </QueryClientProvider>,
  );
  return { onChange, ...utils };
}

beforeEach(() => {
  search.mockReset();
  get.mockReset();
  create.mockReset();
  search.mockResolvedValue([]);
});

describe("PersonPicker", () => {
  it("does not search until 2+ characters are typed", async () => {
    const user = userEvent.setup();
    renderPicker();
    await user.type(screen.getByLabelText("Person"), "a");
    // let the debounce window (300ms) elapse
    await act(() => new Promise((r) => setTimeout(r, 400)));
    expect(search).not.toHaveBeenCalled();
  });

  it("searches (debounced) and selects a result", async () => {
    const user = userEvent.setup();
    search.mockResolvedValue([person()]);
    const { onChange } = renderPicker();

    await user.type(screen.getByLabelText("Person"), "trao");
    const hit = await screen.findByRole("button", { name: /Traoré, Aïcha/ });
    await user.click(hit);

    expect(search).toHaveBeenCalledWith({ q: "trao", limit: 8 });
    expect(onChange).toHaveBeenLastCalledWith(
      "p1p1p1p1-0000-4000-8000-000000000001",
      expect.objectContaining({ last_name: "Traoré" }),
    );
  });

  it("shows a no-match hint", async () => {
    const user = userEvent.setup();
    search.mockResolvedValue([]);
    renderPicker();
    await user.type(screen.getByLabelText("Person"), "zzz");
    expect(await screen.findByText(/No match for/i)).toBeInTheDocument();
  });

  it("creates a new person and selects it", async () => {
    const user = userEvent.setup();
    const created = person({ id: "new00000-0000-4000-8000-000000000009", last_name: "Ba", first_name: "Ola" });
    create.mockResolvedValue(created);
    const { onChange } = renderPicker();

    await user.click(screen.getByRole("button", { name: "+ New person" }));
    await user.type(screen.getByLabelText("First name"), "Ola");
    await user.type(screen.getByLabelText("Last name"), "Ba");
    await user.type(screen.getByLabelText("National ID"), "NID-9");
    await user.click(screen.getByRole("button", { name: /Create & select/ }));

    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({ first_name: "Ola", last_name: "Ba", national_id: "NID-9" }),
    );
    expect(onChange).toHaveBeenLastCalledWith(created.id, created);
  });

  it("explains a 409 national_id clash from create", async () => {
    const user = userEvent.setup();
    create.mockRejectedValue(new ApiError(409, "national_id already belongs to another person"));
    renderPicker();

    await user.click(screen.getByRole("button", { name: "+ New person" }));
    await user.type(screen.getByLabelText("First name"), "Ola");
    await user.type(screen.getByLabelText("Last name"), "Ba");
    await user.click(screen.getByRole("button", { name: /Create & select/ }));

    expect(await screen.findByText(/already belongs to another person/i)).toBeInTheDocument();
  });

  it("resolves and shows the selected person's name when given only an id", async () => {
    get.mockResolvedValue(person());
    render(
      <QueryClientProvider client={new QueryClient()}>
        <PersonPicker value={person().id} onChange={vi.fn()} label="Person" />
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Traoré, Aïcha/)).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(person().id);
  });

  it("surfaces a 403 on search", async () => {
    const user = userEvent.setup();
    search.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
    renderPicker();
    await user.type(screen.getByLabelText("Person"), "trao");
    expect(await screen.findByText(/permission to search people/i)).toBeInTheDocument();
  });
});
