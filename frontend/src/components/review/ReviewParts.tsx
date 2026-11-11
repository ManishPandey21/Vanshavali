import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Bell, Flag, ShieldCheck, Users } from "lucide-react";
import type { DuplicateCheckIn, NotificationOut, ProposalItemIn, ReviewState, ReviewTarget } from "../../api/types";
import type { PersonDraft } from "../person/PersonForm";
import { useCreateChallenge, useCreateProposal, useDuplicateCheck, useMarkNotificationsRead, useNotifications } from "../../api/hooks/review";
import { reviewBus } from "../../lib/reviewBus";
import { useDebounced } from "../../lib/useDebounced";
import { Badge } from "../ui/Badge";
import { Button, ButtonLink } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { ErrorAlert } from "../ui/feedback";
import { Field, TextArea } from "../ui/form";

/** "given_name" -> "Given name": a readable label for a changed field (translated when known). */
export function useFieldLabel() {
  const { t } = useTranslation();
  return (field: string) => {
    const human = field.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
    return t(`review.field.${field}`, { defaultValue: human });
  };
}

/** A value as the family would read it: dates as day/month/year, lists joined, objects summarised. */
export function formatValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "✓" : "✗";
  if (Array.isArray(v)) return v.map(formatValue).join(", ");
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    if ("year" in o || "original_text" in o) {
      const parts = [o.day, o.month, o.year].filter((x) => x !== null && x !== undefined);
      return parts.length ? parts.join("/") : String(o.original_text ?? "—");
    }
    return Object.entries(o)
      .filter(([, x]) => x !== null && x !== undefined)
      .map(([k, x]) => `${k}: ${formatValue(x)}`)
      .join("; ");
  }
  return String(v);
}

/** Family review state of a fact (ADR-0021 §6). Nothing is shown for unreviewed facts. */
export function ReviewBadge({ state }: { state?: ReviewState | null }) {
  const { t } = useTranslation();
  if (state === "family_reviewed")
    return (
      <Badge tone="green" icon={<ShieldCheck className="size-3" aria-hidden />}>
        {t("review.state.family_reviewed")}
      </Badge>
    );
  if (state === "contested")
    return (
      <Badge tone="red" icon={<Flag className="size-3" aria-hidden />}>
        {t("review.state.contested")}
      </Badge>
    );
  return null;
}

/** "Challenge": any member who can see a fact may dispute it; it marks nothing until a reviewer upholds it. */
export function ChallengeButton({ treeId, targetType, targetId, label }: { treeId: string; targetType: ReviewTarget; targetId: string; label: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [done, setDone] = useState(false);
  const create = useCreateChallenge(treeId);
  return (
    <>
      <button
        type="button"
        className="rounded p-1.5 text-ink-muted hover:bg-parchment-deep"
        onClick={() => {
          setOpen(true);
          setDone(false);
        }}
        aria-label={t("review.challengeLabel", { what: label })}
      >
        <Flag className="size-4" aria-hidden />
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={t("review.challengeTitle")}
        description={t("review.challengeHint")}
        footer={
          done ? (
            <Button onClick={() => setOpen(false)}>{t("common.close")}</Button>
          ) : (
            <>
              <Button variant="secondary" onClick={() => setOpen(false)}>
                {t("common.cancel")}
              </Button>
              <Button
                loading={create.isPending}
                disabled={reason.trim().length < 3}
                onClick={() =>
                  create.mutate({ target_type: targetType, target_id: targetId, rationale: reason.trim() }, { onSuccess: () => setDone(true) })
                }
              >
                {t("review.sendChallenge")}
              </Button>
            </>
          )
        }
      >
        {done ? (
          <p role="status">{t("review.challengeSent")}</p>
        ) : (
          <div className="space-y-3">
            <p className="text-sm">
              <span className="font-medium">{label}</span>
            </p>
            <Field label={t("review.challengeReason")} required>
              {(p) => <TextArea {...p} rows={4} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000} />}
            </Field>
            <ErrorAlert error={create.error} />
          </div>
        )}
      </Dialog>
    </>
  );
}

/**
 * Offers a change the server refused with review_required as a proposed change (ADR-0021 §1).
 * Mounted once in the tree layout; the edit hooks hand it the attempted change.
 */
export function ProposeChangeHost({ treeId }: { treeId: string }) {
  const { t } = useTranslation();
  const fieldLabel = useFieldLabel();
  const [item, setItem] = useState<ProposalItemIn | null>(null);
  const [rationale, setRationale] = useState("");
  const [sentId, setSentId] = useState<string | null>(null);
  const create = useCreateProposal(treeId);
  useEffect(
    () =>
      reviewBus.subscribe((next) => {
        setItem(next);
        setRationale("");
        setSentId(null);
        create.reset();
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  if (!item) return null;
  const fields = Object.keys(item.patch ?? {});
  return (
    <Dialog
      open
      onClose={() => setItem(null)}
      title={t("review.proposeTitle")}
      description={t("review.proposeHint")}
      footer={
        sentId ? (
          <>
            <Button variant="secondary" onClick={() => setItem(null)}>
              {t("common.close")}
            </Button>
            <ButtonLink to={`/t/${treeId}/review/${sentId}`} onClick={() => setItem(null)}>
              {t("review.openProposal")}
            </ButtonLink>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={() => setItem(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              loading={create.isPending}
              disabled={!rationale.trim()}
              onClick={() => create.mutate({ rationale: rationale.trim(), items: [item], submit: true }, { onSuccess: (p) => setSentId(p.id) })}
            >
              {t("review.sendForReview")}
            </Button>
          </>
        )
      }
    >
      {sentId ? (
        <p role="status">{t("review.sent")}</p>
      ) : (
        <div className="space-y-3">
          <p className="text-sm">
            {t(`review.op.${item.op}`)} · {t(`review.target.${item.target_type}`)}
          </p>
          {fields.length > 0 && (
            <ul className="rounded-md bg-parchment p-2 text-sm">
              {fields.map((f) => (
                <li key={f}>
                  <span className="text-ink-muted">{fieldLabel(f)}:</span> {formatValue((item.patch as Record<string, unknown>)[f])}
                </li>
              ))}
            </ul>
          )}
          <Field label={t("review.rationale")} hint={t("review.rationaleHint")} required>
            {(p) => <TextArea {...p} rows={3} value={rationale} onChange={(e) => setRationale(e.target.value)} maxLength={2000} />}
          </Field>
          <ErrorAlert error={create.error} />
        </div>
      )}
    </Dialog>
  );
}

/** In-app notifications (ids only on the server; text built for the reader when read). */
export function NotificationBell({ treeId }: { treeId: string }) {
  const { t } = useTranslation();
  const notes = useNotifications(treeId);
  const markRead = useMarkNotificationsRead(treeId);
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);
  const unread = notes.data?.unread ?? 0;
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        className="relative rounded-full p-2 hover:bg-parchment-deep"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={unread ? t("review.notificationsUnread", { count: unread }) : t("review.notifications")}
        onClick={() => setOpen((o) => !o)}
      >
        <Bell className="size-5" aria-hidden />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-kumkum-700 px-1 text-center text-[10px] font-semibold leading-4 text-white" aria-hidden>
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div id={panelId} className="absolute right-0 z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-stone-200 bg-white p-2 shadow-lg">
          <div className="flex items-center justify-between px-1 pb-1">
            <h2 className="text-sm font-semibold">{t("review.notifications")}</h2>
            {unread > 0 && (
              <button type="button" className="text-xs text-kumkum-800 underline" onClick={() => markRead.mutate([])}>
                {t("review.markAllRead")}
              </button>
            )}
          </div>
          {(notes.data?.items ?? []).length === 0 ? (
            <p className="px-1 py-2 text-sm text-ink-muted">{t("review.noNotifications")}</p>
          ) : (
            <ul className="max-h-80 divide-y divide-stone-100 overflow-auto">
              {notes.data!.items.map((n) => (
                <li key={n.id}>
                  <Link
                    to={notificationHref(treeId, n)}
                    className={`block rounded px-1 py-2 text-sm hover:bg-parchment ${n.read ? "text-ink-muted" : "font-medium"}`}
                    onClick={() => {
                      if (!n.read) markRead.mutate([n.id]);
                      setOpen(false);
                    }}
                  >
                    {n.text}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** Where a notification leads; a "made more private" notice opens the record (ADR-0027 §5). */
export function notificationHref(treeId: string, n: Pick<NotificationOut, "kind" | "proposal_id" | "subject_id">): string {
  if (n.kind === "document_narrowed" && n.subject_id) return `/t/${treeId}/documents/${n.subject_id}`;
  if (n.kind === "tradition_narrowed" && n.subject_id) return `/t/${treeId}/traditions/${n.subject_id}`;
  if (n.kind.startsWith("nomination_")) return `/t/${treeId}/admin/members`;
  return n.proposal_id ? `/t/${treeId}/review/${n.proposal_id}` : `/t/${treeId}/review`;
}

/**
 * "Already in the tree?" while adding someone (ADR-0021 §8): candidates with reasons, from people
 * the user can already see. Nothing is chosen for the user.
 */
export function DuplicatePanel({
  treeId,
  check,
  onUse,
}: {
  treeId: string;
  check: DuplicateCheckIn | null;
  onUse?: (person: { id: string; display_name: string }) => void;
}) {
  const { t } = useTranslation();
  const debounced = useDebounced(check ? JSON.stringify(check) : "", 600);
  const parsed = debounced ? (JSON.parse(debounced) as DuplicateCheckIn) : null;
  const res = useDuplicateCheck(treeId, parsed);
  const [dismissed, setDismissed] = useState<string>("");
  const cands = res.data?.candidates ?? [];
  if (!parsed || cands.length === 0 || dismissed === debounced) return null;
  return (
    <section className="rounded-md border border-sky-200 bg-sky-50 p-3 text-sm" role="status" aria-live="polite">
      <h3 className="flex items-center gap-1 font-semibold">
        <Users className="size-4" aria-hidden />
        {t("review.dupTitle")}
      </h3>
      <ul className="mt-2 space-y-2">
        {cands.map((c) => (
          <li key={c.person.id} className="flex flex-wrap items-center justify-between gap-2">
            <span>
              <Link to={`/t/${treeId}/people/${c.person.id}`} target="_blank" rel="noreferrer" className="font-medium text-kumkum-800 underline">
                {c.person.display_name}
              </Link>
              <span className="ml-1 text-xs text-ink-muted">{c.reasons.join(" · ")}</span>
            </span>
            {onUse && (
              <Button size="sm" variant="secondary" onClick={() => onUse({ id: c.person.id, display_name: c.person.display_name })}>
                {t("review.dupUse")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      <button type="button" className="mt-2 text-xs text-ink-muted underline" onClick={() => setDismissed(debounced)}>
        {t("review.dupSomeoneElse")}
      </button>
    </section>
  );
}

/** The duplicate check for a person being typed in; null until there is a name to check. */
export function duplicateCheckFor(
  draft: PersonDraft,
  links: { parentIds?: string[]; spouseIds?: string[]; excludeIds?: string[] } = {},
): DuplicateCheckIn | null {
  const names = draft.names
    .map((n) => ({ given_name: (n.given_name ?? "").trim() || null, surname: (n.surname ?? "").trim() || null }))
    .filter((n) => (n.given_name ?? "").length >= 2 || (n.surname ?? "").length >= 2)
    .slice(0, 5);
  if (!names.length || !names.some((n) => n.given_name)) return null;
  return {
    names,
    birth_year: draft.birth.date.year ?? null,
    sex_at_birth: draft.sex_at_birth || null,
    parent_ids: links.parentIds ?? [],
    spouse_ids: links.spouseIds ?? [],
    birth_place_id: draft.birth.place.place_id ?? null,
    exclude_ids: links.excludeIds ?? [],
  };
}
