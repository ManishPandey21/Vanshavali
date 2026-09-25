import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabDef {
  id: string;
  label: ReactNode;
  count?: number;
}

/** WAI-ARIA tabs with roving tabindex and arrow/Home/End keys. Scrolls horizontally on mobile. */
export function Tabs({
  tabs,
  active,
  onChange,
  label,
  children,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
  label: string;
  children: ReactNode;
}) {
  const base = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const onKey = (e: KeyboardEvent) => {
    const i = tabs.findIndex((t) => t.id === active);
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    if (next >= 0) {
      e.preventDefault();
      onChange(tabs[next].id);
      refs.current[tabs[next].id]?.focus();
    }
  };
  return (
    <div>
      <div
        role="tablist"
        aria-label={label}
        className="relative -mx-4 flex gap-1 overflow-x-auto border-b border-stone-300 px-4 sm:mx-0 sm:px-0"
      >
        {tabs.map((tab) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                refs.current[tab.id] = el;
              }}
              role="tab"
              type="button"
              id={`${base}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${base}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.id)}
              onKeyDown={onKey}
              className={`-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium ${
                selected ? "border-kumkum-700 text-kumkum-800" : "border-transparent text-ink-muted hover:text-ink"
              }`}
            >
              {tab.label}
              {tab.count !== undefined && <span className="ml-1.5 rounded-full bg-stone-100 px-1.5 text-xs text-ink-muted">{tab.count}</span>}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${base}-panel-${active}`} aria-labelledby={`${base}-tab-${active}`} className="pt-4" tabIndex={0}>
        {children}
      </div>
    </div>
  );
}
