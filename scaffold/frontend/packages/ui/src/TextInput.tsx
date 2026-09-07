import { forwardRef, useId } from "react";
import type { InputHTMLAttributes } from "react";

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
}

export const TextInput = forwardRef<HTMLInputElement, Props>(function TextInput(
  { label, error, hint, id, className = "", ...rest },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium text-ink-muted">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${inputId}-error` : undefined}
        className={
          "rounded-lg border bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-ink-faint " +
          "focus:outline-none focus:ring-2 focus:ring-accent-command/50 " +
          (error ? "border-bad" : "border-hair") +
          " " +
          className
        }
        {...rest}
      />
      {hint && !error && <p className="text-xs text-ink-faint">{hint}</p>}
      {error && (
        <p id={`${inputId}-error`} className="text-xs text-bad">
          {error}
        </p>
      )}
    </div>
  );
});
