import type { ReactNode } from "react";

export type Tone = "neutral" | "saffron" | "green" | "red" | "blue" | "violet" | "stone";

const tones: Record<Tone, string> = {
  neutral: "bg-stone-100 text-stone-800 border-stone-300",
  saffron: "bg-haldi-100 text-haldi-700 border-haldi-300",
  green: "bg-leaf-50 text-leaf-700 border-green-300",
  red: "bg-red-50 text-red-800 border-red-300",
  blue: "bg-sky-50 text-sky-900 border-sky-300",
  violet: "bg-violet-50 text-violet-900 border-violet-300",
  stone: "bg-white text-ink-muted border-stone-300",
};

export function Badge({ tone = "neutral", children, icon, title }: { tone?: Tone; children: ReactNode; icon?: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {icon}
      {children}
    </span>
  );
}
