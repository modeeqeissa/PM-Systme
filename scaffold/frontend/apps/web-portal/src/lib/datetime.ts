/** `Date` -> value for `<input type="datetime-local">` (local wall time, minute precision). */
export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/** `<input type="datetime-local">` value (local) -> ISO 8601 UTC for the API. */
export function localInputToIso(value: string): string {
  return new Date(value).toISOString();
}

/** `YYYY-MM-DD` for a Date (local). */
export function toDateInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** [first-of-this-month, today] as `YYYY-MM-DD` strings. */
export function currentMonthRange(now = new Date()): { from: string; to: string } {
  return {
    from: toDateInputValue(new Date(now.getFullYear(), now.getMonth(), 1)),
    to: toDateInputValue(now),
  };
}

export function monthLabel(isoDate: string): string {
  // isoDate is YYYY-MM-DD (first of month)
  const [y, m] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}
