import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Spinner, TextInput } from "@pmp/ui";
import { ApiError, persons as personsApi, validationErrors, type Person } from "../lib/api";

/**
 * "Search existing or create new" person control (docs §9.3.2). Replaces the
 * bare suspect/person UUID fields on the arrest and statement forms: the caller
 * gets back a real `persons.id`, never a hand-typed UUID.
 */
export interface PersonPickerProps {
  /** Selected person id, or null when nothing is chosen. */
  value: string | null;
  onChange: (personId: string | null, person: Person | null) => void;
  label?: string;
  /** Shown under the label; also gates the empty-state hint. */
  required?: boolean;
  /** Field-level error passed from the parent form (e.g. a 422 on submit). */
  error?: string;
  /** Test / layout hook. */
  idPrefix?: string;
}

function personLine(p: Person): string {
  const bits = [`${p.last_name}, ${p.first_name}`];
  if (p.national_id) bits.push(`ID ${p.national_id}`);
  if (p.date_of_birth) bits.push(`b. ${p.date_of_birth}`);
  return bits.join(" · ");
}

export function PersonPicker({
  value,
  onChange,
  label = "Person",
  required = false,
  error,
  idPrefix = "person",
}: PersonPickerProps) {
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  const [selected, setSelected] = useState<Person | null>(null);
  const [creating, setCreating] = useState(false);

  // Keep a resolved Person object for the current `value` so the chip can show
  // a name even after a page refresh handed us just an id.
  useEffect(() => {
    if (!value) {
      setSelected(null);
      return;
    }
    if (selected?.id === value) return;
    let live = true;
    personsApi
      .get(value)
      .then((p) => live && setSelected(p))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [value, selected?.id]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(term.trim()), 300);
    return () => clearTimeout(t);
  }, [term]);

  const search = useQuery({
    queryKey: ["person-search", debounced],
    queryFn: () => personsApi.search({ q: debounced, limit: 8 }),
    enabled: debounced.length >= 2 && !value,
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  function choose(p: Person) {
    setSelected(p);
    setTerm("");
    setDebounced("");
    setCreating(false);
    onChange(p.id, p);
  }

  function clear() {
    setSelected(null);
    onChange(null, null);
  }

  if (value && selected) {
    return (
      <div className="flex flex-col gap-1">
        <span className="text-sm font-medium text-ink-muted">{label}</span>
        <div className="flex items-center justify-between rounded-md border border-hair bg-surface-2 px-3 py-2 text-sm">
          <span className="text-ink">
            {personLine(selected)}{" "}
            <span className="ml-1 font-mono text-xs text-ink-faint">{selected.id.slice(0, 8)}…</span>
          </span>
          <Button type="button" variant="secondary" onClick={clear}>
            Change
          </Button>
        </div>
        {error && <p className="text-xs text-bad">{error}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <TextInput
        label={label}
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        error={error}
        placeholder="Search by name or national ID"
        aria-describedby={`${idPrefix}-picker-hint`}
      />
      <p id={`${idPrefix}-picker-hint`} className="text-xs text-ink-faint">
        {required ? "Required. " : ""}Type at least 2 characters to search existing
        people, or create a new record.
      </p>

      {search.isFetching && <Spinner label="Searching people…" />}
      {search.error instanceof ApiError && search.error.status === 403 && (
        <Alert variant="error">
          Needs the <code>case.read</code> permission to search people.
        </Alert>
      )}
      {search.data && search.data.length === 0 && debounced.length >= 2 && (
        <p className="text-sm text-ink-faint">
          No match for “{debounced}”. Create a new person below.
        </p>
      )}
      {search.data && search.data.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-md border border-hair">
          {search.data.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => choose(p)}
                className="w-full px-3 py-2 text-left text-sm text-ink hover:bg-surface-2"
              >
                {personLine(p)}
              </button>
            </li>
          ))}
        </ul>
      )}

      {!creating && (
        <div>
          <Button type="button" variant="secondary" onClick={() => setCreating(true)}>
            + New person
          </Button>
        </div>
      )}
      {creating && (
        <NewPersonForm
          onCancel={() => setCreating(false)}
          onCreated={choose}
          idPrefix={idPrefix}
        />
      )}
    </div>
  );
}

function NewPersonForm({
  onCreated,
  onCancel,
  idPrefix,
}: {
  onCreated: (p: Person) => void;
  onCancel: () => void;
  idPrefix: string;
}) {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [dob, setDob] = useState("");
  const [nationalId, setNationalId] = useState("");
  const [gender, setGender] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [fieldErr, setFieldErr] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setFieldErr({});
    setMessage(null);
    try {
      const person = await personsApi.create({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        date_of_birth: dob || null,
        national_id: nationalId.trim() || null,
        gender: gender.trim() || null,
        phone: phone.trim() || null,
      });
      onCreated(person);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setFieldErr(validationErrors(err));
      } else if (err instanceof ApiError && err.status === 409) {
        setMessage("That national ID already belongs to another person — search for them instead.");
      } else if (err instanceof ApiError && err.status === 403) {
        setMessage("Your role can't create a person record (needs case.write).");
      } else {
        setMessage("Couldn't create the person. Try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="flex flex-col gap-3 rounded-md border border-hair bg-surface-2 p-3"
      role="group"
      aria-label="New person"
    >
      {message && <Alert variant="error">{message}</Alert>}
      <div className="grid grid-cols-2 gap-3">
        <TextInput
          label="First name"
          value={firstName}
          onChange={(e) => setFirstName(e.target.value)}
          error={fieldErr.first_name}
          required
        />
        <TextInput
          label="Last name"
          value={lastName}
          onChange={(e) => setLastName(e.target.value)}
          error={fieldErr.last_name}
          required
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor={`${idPrefix}-new-dob`} className="text-sm font-medium text-ink-muted">
            Date of birth
          </label>
          <input
            id={`${idPrefix}-new-dob`}
            type="date"
            value={dob}
            onChange={(e) => setDob(e.target.value)}
            className="rounded-md border border-hair px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-command/50"
          />
        </div>
        <TextInput
          label="National ID"
          value={nationalId}
          onChange={(e) => setNationalId(e.target.value)}
          error={fieldErr.national_id}
          placeholder="optional"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <TextInput
          label="Gender"
          value={gender}
          onChange={(e) => setGender(e.target.value)}
          placeholder="optional"
        />
        <TextInput
          label="Phone"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="optional"
        />
      </div>
      <div className="flex gap-2">
        <Button type="button" loading={busy} onClick={submit}>
          Create &amp; select
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
