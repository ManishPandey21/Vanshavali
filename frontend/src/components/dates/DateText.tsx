import { useTranslation } from "react-i18next";
import { Clock } from "lucide-react";
import type { GenealogicalDate, GenealogicalTime } from "../../api/types";
import { formatDate, formatTime } from "../../lib/dates";
import { DateQualifierBadge } from "../person/badges";
import { Badge } from "../ui/Badge";

/** Date text plus its precision/redaction badges. Original text (as recorded) shown on request. */
export function DateText({ date, showOriginal = true }: { date: GenealogicalDate | Record<string, unknown> | null | undefined; showOriginal?: boolean }) {
  const { t, i18n } = useTranslation();
  if (!date) return <span className="text-ink-muted">{t("date.display.unknown")}</span>;
  const g = date as GenealogicalDate;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span>{formatDate(g, t, i18n.language)}</span>
      <DateQualifierBadge date={g} />
      {showOriginal && g.original_text && g.precision !== "unknown" && (
        <span className="text-xs text-ink-muted">
          {t("date.recordedAs")} “{g.original_text}”
        </span>
      )}
    </span>
  );
}

/** A time with its precision always visible; only `exact` times omit the "about/recalled" wording. */
export function TimeText({ time }: { time: GenealogicalTime | Record<string, unknown> | null | undefined }) {
  const { t } = useTranslation();
  const text = formatTime(time, t);
  if (!text) return null;
  const precision = (time as GenealogicalTime).precision ?? "unknown";
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Clock className="size-3.5 text-ink-muted" aria-hidden />
      <span>{text}</span>
      {precision !== "exact" && <Badge tone="saffron">{t(`enum.timePrecision.${precision}`)}</Badge>}
    </span>
  );
}
