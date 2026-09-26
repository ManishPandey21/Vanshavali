import { useId, type ReactNode, type SelectHTMLAttributes, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface FieldRenderProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
}

/** Label + control + hint + error, wired with ids for screen readers. */
export function Field({
  label,
  hint,
  error,
  required,
  children,
  className = "",
  labelHidden,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  required?: boolean;
  className?: string;
  labelHidden?: boolean;
  children: (p: FieldRenderProps) => ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errId = `${id}-err`;
  const describedBy = [hint ? hintId : null, error ? errId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={className}>
      <label htmlFor={id} className={labelHidden ? "sr-only" : "label"}>
        {label}
        {required && (
          <span className="text-kumkum-700" aria-hidden>
            {" "}
            *
          </span>
        )}
      </label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && (
        <p id={hintId} className="hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errId} className="field-error">
          {error}
        </p>
      )}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`input ${props.className ?? ""}`} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={3} {...props} className={`input ${props.className ?? ""}`} />;
}

export function Select({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={`input pr-8 ${props.className ?? ""}`}>
      {children}
    </select>
  );
}

export function Fieldset({ legend, children, description, className = "" }: { legend: ReactNode; children: ReactNode; description?: ReactNode; className?: string }) {
  return (
    <fieldset className={`rounded-xl border border-stone-200 bg-white p-4 ${className}`}>
      <legend className="px-1 font-display text-base font-semibold">{legend}</legend>
      {description && <p className="mb-3 text-xs text-ink-muted">{description}</p>}
      {children}
    </fieldset>
  );
}

export function Checkbox({ label, checked, onChange, disabled, hint }: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; hint?: ReactNode }) {
  const id = useId();
  return (
    <div className="flex items-start gap-2">
      <input id={id} type="checkbox" className="mt-1 size-4 accent-kumkum-700" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <label htmlFor={id} className="text-sm">
        {label}
        {hint && <span className="block text-xs text-ink-muted">{hint}</span>}
      </label>
    </div>
  );
}

/** Parse an <input type=number> value into int | null. */
export function intOrNull(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

export function strOrNull(v: string | null | undefined): string | null {
  const s = (v ?? "").trim();
  return s ? s : null;
}

/**
 * After a failed submit, move focus to the first invalid control so keyboard and screen-reader
 * users land on the problem (its error is read via aria-describedby). Runs after React re-renders
 * the error state.
 */
export function focusFirstInvalid(root: HTMLElement | null | undefined) {
  requestAnimationFrame(() => root?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
}
