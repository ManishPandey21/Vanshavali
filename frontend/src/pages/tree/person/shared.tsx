import { EyeOff } from "lucide-react";

export { ErrorAlert } from "../../../components/ui/feedback";

export function RedactionNoticeBlock({ text }: { text: string }) {
  return (
    <p className="flex items-start gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-950">
      <EyeOff className="mt-0.5 size-4 shrink-0" aria-hidden />
      {text}
    </p>
  );
}
