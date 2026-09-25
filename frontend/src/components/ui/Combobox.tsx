import { useId, useState, type ReactNode, type KeyboardEvent } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LiveRegion } from "./feedback";

export interface ComboOption<T> {
  key: string;
  value: T;
  label: ReactNode;
  textValue: string;
}

/**
 * ARIA 1.2 combobox (editable input + listbox popup). The caller owns the text and the options
 * (usually fetched from the API as the user types).
 */
export function Combobox<T>({
  label,
  text,
  onTextChange,
  options,
  onSelect,
  loading,
  placeholder,
  hint,
  emptyText,
  labelHidden,
  inputProps,
}: {
  label: ReactNode;
  text: string;
  onTextChange: (s: string) => void;
  options: ComboOption<T>[];
  onSelect: (v: T) => void;
  loading?: boolean;
  placeholder?: string;
  hint?: ReactNode;
  emptyText?: string;
  labelHidden?: boolean;
  inputProps?: { lang?: string; "aria-invalid"?: boolean; required?: boolean };
}) {
  const { t } = useTranslation();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = `${id}-list`;
  const showList = open && (options.length > 0 || (!!emptyText && text.trim().length > 0 && !loading));
  // Search-as-you-type results arrive asynchronously; announce how many (WCAG 4.1.3).
  const status = open && text.trim() && !loading ? (options.length ? t("people.resultCount", { count: options.length }) : (emptyText ?? "")) : "";

  const choose = (i: number) => {
    const o = options[i];
    if (!o) return;
    onSelect(o.value);
    setOpen(false);
    setActive(-1);
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(options.length - 1, a + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === "Enter" && open && active >= 0) {
      e.preventDefault();
      choose(active);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <label htmlFor={id} className={labelHidden ? "sr-only" : "label"}>
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 && showList ? `${id}-opt-${active}` : undefined}
          aria-describedby={hint ? `${id}-hint` : undefined}
          autoComplete="off"
          className="input pr-8"
          value={text}
          placeholder={placeholder}
          onChange={(e) => {
            onTextChange(e.target.value);
            setOpen(true);
            setActive(-1);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKey}
          {...inputProps}
        />
        {loading && <Loader2 className="absolute right-2 top-2.5 size-4 animate-spin text-ink-muted" aria-hidden />}
      </div>
      {hint && (
        <p id={`${id}-hint`} className="hint">
          {hint}
        </p>
      )}
      <ul
        id={listId}
        role="listbox"
        className={`absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-stone-300 bg-white py-1 shadow-lg ${showList ? "" : "hidden"}`}
      >
        {options.map((o, i) => (
          <li
            key={o.key}
            id={`${id}-opt-${i}`}
            role="option"
            aria-selected={i === active}
            className={`cursor-pointer px-3 py-2 text-sm ${i === active ? "bg-haldi-100" : "hover:bg-parchment"}`}
            onMouseDown={(e) => {
              e.preventDefault();
              choose(i);
            }}
          >
            {o.label}
          </li>
        ))}
        {options.length === 0 && emptyText && <li className="px-3 py-2 text-sm text-ink-muted">{emptyText}</li>}
      </ul>
      <LiveRegion message={status} />
    </div>
  );
}
