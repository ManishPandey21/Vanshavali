import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bell, BellOff, Phone, Send, Trash2 } from "lucide-react";
import type { NotificationChannel, PreferenceOut } from "../../api/types";
import {
  useAddContact,
  useChannels,
  useContacts,
  useCreateReminder,
  useDeleteContact,
  useDeleteReminder,
  useDeliveryHistory,
  usePreferences,
  useReminders,
  useSavePreferences,
  useTestReminder,
  useUpcoming,
  useUpdateReminder,
  useVerifyContact,
} from "../../api/hooks/reminders";
import { useTreeCtx } from "../../lib/tree-context";
import { Button } from "../../components/ui/Button";
import { EmptyState, ErrorAlert, LiveRegion, PageHeader, Spinner } from "../../components/ui/feedback";
import { Checkbox, Field, Fieldset, Select, TextInput } from "../../components/ui/form";
import { Badge } from "../../components/ui/Badge";
import { LEAD_PRESETS } from "../../components/events/ReminderControl";

const TIMEZONES = ["Asia/Kolkata", "Asia/Kathmandu", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York", "America/Los_Angeles", "Australia/Sydney", "UTC"];
const CHANNELS: NotificationChannel[] = ["email", "sms", "whatsapp"];

/** Your reminders for this tree: opt-in settings, upcoming dates, phone numbers and delivery history. */
export function RemindersPage() {
  const { t } = useTranslation();
  const [status, setStatus] = useState("");
  return (
    <div className="space-y-8">
      <PageHeader title={t("reminders.pageTitle")} subtitle={t("reminders.pageSubtitle")} />
      <LiveRegion message={status} />
      <UpcomingSection onStatus={setStatus} />
      <MyReminders onStatus={setStatus} />
      <PreferencesSection onStatus={setStatus} />
      <ContactsSection onStatus={setStatus} />
      <HistorySection />
    </div>
  );
}

type StatusFn = (s: string) => void;

function UpcomingSection({ onStatus }: { onStatus: StatusFn }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const [days, setDays] = useState(30);
  const upcoming = useUpcoming(treeId, days, "tree");
  const create = useCreateReminder(treeId);
  return (
    <section aria-labelledby="up-title" className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="up-title" className="font-display text-xl font-semibold">
          {t("reminders.upcoming")}
        </h2>
        <Field label={t("reminders.window")}>
          {(p) => (
            <Select {...p} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[7, 30, 90, 365].map((d) => (
                <option key={d} value={d}>
                  {t("reminders.nextDays", { count: d })}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      {upcoming.isLoading && <Spinner />}
      <ErrorAlert error={upcoming.error || create.error} />
      {upcoming.data && upcoming.data.length === 0 && <EmptyState title={t("reminders.noneUpcoming")}>{t("reminders.noneUpcomingHint")}</EmptyState>}
      <ul className="divide-y divide-stone-200 rounded-xl border border-stone-200 bg-white">
        {upcoming.data?.map((u) => (
          <li key={`${u.event_id}-${u.occurrence_date}`} className="flex flex-wrap items-center justify-between gap-2 p-3">
            <div>
              <p className="font-semibold">
                {u.label}
                {u.anniversary ? <span className="ml-2 text-sm font-normal text-ink-muted">({t("reminders.nth", { count: u.anniversary })})</span> : null}
              </p>
              <p className="text-sm text-ink-muted">
                {new Date(`${u.occurrence_date}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" })} ·{" "}
                {u.days_until === 0 ? t("reminders.today") : t("reminders.inDays", { count: u.days_until })}
                {u.person_id && (
                  <>
                    {" · "}
                    <Link className="text-kumkum-800 underline" to={`/t/${treeId}/people/${u.person_id}?tab=events`}>
                      {u.display_name}
                    </Link>
                  </>
                )}
              </p>
            </div>
            {u.reminder_id ? (
              <Badge tone="green" icon={<Bell className="size-3" aria-hidden />}>
                {t("reminders.on")}
              </Badge>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                icon={<Bell className="size-3.5" aria-hidden />}
                loading={create.isPending && create.variables?.event_id === u.event_id}
                onClick={() => create.mutate({ event_id: u.event_id }, { onSuccess: () => onStatus(t("reminders.created", { label: u.label })) })}
                aria-label={t("reminders.addFor", { event: u.label })}
              >
                {t("reminders.remindMe")}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function MyReminders({ onStatus }: { onStatus: StatusFn }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const reminders = useReminders(treeId);
  const update = useUpdateReminder(treeId);
  const del = useDeleteReminder(treeId);
  const test = useTestReminder(treeId);
  return (
    <section aria-labelledby="my-title" className="space-y-3">
      <h2 id="my-title" className="font-display text-xl font-semibold">
        {t("reminders.mine")}
      </h2>
      {reminders.isLoading && <Spinner />}
      <ErrorAlert error={reminders.error || update.error || del.error || test.error} />
      {reminders.data && reminders.data.length === 0 && <EmptyState title={t("reminders.noneMine")}>{t("reminders.noneMineHint")}</EmptyState>}
      <ul className="grid gap-3 md:grid-cols-2">
        {reminders.data?.map((r) => (
          <li key={r.id} className="card space-y-2 p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-semibold">{r.label ?? t("reminders.unavailableEvent")}</p>
                {r.person_id && (
                  <Link className="text-sm text-kumkum-800 underline" to={`/t/${treeId}/people/${r.person_id}?tab=events`}>
                    {r.person_name}
                  </Link>
                )}
              </div>
              <Badge tone={r.active && r.deliverable ? "green" : "stone"}>{r.active ? (r.deliverable ? t("reminders.active") : t("reminders.notDeliverable")) : t("reminders.paused")}</Badge>
            </div>
            <p className="text-sm text-ink-muted">
              {t(`enum.reminderKind.${r.kind}`)} · {r.recurrence === "annual" ? t("reminders.everyYear") : t("reminders.once")} ·{" "}
              {(r.lead_days ?? []).map((d) => t("reminders.leadShort", { count: d })).join(", ")} · {(r.channels ?? []).map((c) => t(`enum.channel.${c}`)).join(", ")}
            </p>
            {r.next_occurrence && <p className="text-sm">{t("reminders.next", { date: new Date(`${r.next_occurrence}T00:00:00`).toLocaleDateString() })}</p>}
            {r.note && <p className="text-sm italic">{r.note}</p>}
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="secondary"
                icon={r.active ? <BellOff className="size-3.5" aria-hidden /> : <Bell className="size-3.5" aria-hidden />}
                onClick={() => update.mutate({ id: r.id, body: { active: !r.active } })}
              >
                {r.active ? t("reminders.pause") : t("reminders.resume")}
              </Button>
              <Button size="sm" variant="secondary" icon={<Send className="size-3.5" aria-hidden />} loading={test.isPending && test.variables === r.id} onClick={() => test.mutate(r.id, { onSuccess: () => onStatus(t("reminders.testSent")) })}>
                {t("reminders.sendTest")}
              </Button>
              <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" aria-hidden />} onClick={() => del.mutate(r.id, { onSuccess: () => onStatus(t("reminders.deleted")) })}>
                {t("reminders.stop")}
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PreferencesSection({ onStatus }: { onStatus: StatusFn }) {
  const { treeId } = useTreeCtx();
  const prefs = usePreferences(treeId);
  if (prefs.isLoading) return <Spinner />;
  if (prefs.error || !prefs.data) return <ErrorAlert error={prefs.error} />;
  return <PreferencesForm key={JSON.stringify(prefs.data)} initial={prefs.data} onStatus={onStatus} />;
}

function PreferencesForm({ initial, onStatus }: { initial: PreferenceOut; onStatus: StatusFn }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const channels = useChannels();
  const save = useSavePreferences(treeId);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [chosen, setChosen] = useState<NotificationChannel[]>(initial.channels);
  const [tz, setTz] = useState(initial.timezone);
  const [hour, setHour] = useState(initial.send_hour);
  const [lead, setLead] = useState<number[]>(initial.default_lead_days);
  const zones = TIMEZONES.includes(tz) ? TIMEZONES : [tz, ...TIMEZONES];
  return (
    <section aria-labelledby="pref-title" className="card space-y-3 p-4">
      <h2 id="pref-title" className="font-display text-xl font-semibold">
        {t("reminders.preferences")}
      </h2>
      <Checkbox label={t("reminders.enabled")} hint={t("reminders.enabledHint")} checked={enabled} onChange={setEnabled} />
      <Fieldset legend={t("reminders.channels")}>
        <div className="flex flex-wrap gap-4">
          {CHANNELS.map((c) => {
            const available = channels.data ? channels.data[c] : c === "email";
            return (
              <Checkbox
                key={c}
                label={`${t(`enum.channel.${c}`)}${available ? "" : ` (${t("reminders.unavailable")})`}`}
                checked={chosen.includes(c)}
                disabled={!available}
                onChange={(v) => setChosen(v ? [...chosen, c] : chosen.filter((x) => x !== c))}
              />
            );
          })}
        </div>
      </Fieldset>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t("reminders.timezone")}>
          {(p) => (
            <Select {...p} value={tz} onChange={(e) => setTz(e.target.value)}>
              {zones.map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("reminders.sendHour")}>
          {(p) => (
            <Select {...p} value={hour} onChange={(e) => setHour(Number(e.target.value))}>
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  {`${String(h).padStart(2, "0")}:00`}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <Fieldset legend={t("reminders.defaultLead")}>
        <div className="flex flex-wrap gap-4">
          {LEAD_PRESETS.map((d) => (
            <Checkbox key={d} label={t(`reminders.lead.${d}`)} checked={lead.includes(d)} onChange={(v) => setLead(v ? [...lead, d] : lead.filter((x) => x !== d))} />
          ))}
        </div>
      </Fieldset>
      <ErrorAlert error={save.error} />
      <Button
        loading={save.isPending}
        disabled={!chosen.length || !lead.length}
        onClick={() => save.mutate({ enabled, channels: chosen, timezone: tz, send_hour: hour, default_lead_days: lead }, { onSuccess: () => onStatus(t("reminders.prefsSaved")) })}
      >
        {t("common.save")}
      </Button>
    </section>
  );
}

function ContactsSection({ onStatus }: { onStatus: StatusFn }) {
  const { t } = useTranslation();
  const channels = useChannels();
  const contacts = useContacts();
  const add = useAddContact();
  const verify = useVerifyContact();
  const del = useDeleteContact();
  const phoneChannels = (["sms", "whatsapp"] as NotificationChannel[]).filter((c) => channels.data?.[c]);
  const [channel, setChannel] = useState<NotificationChannel>("sms");
  const [number, setNumber] = useState("");
  const [codes, setCodes] = useState<Record<string, string>>({});
  if (!phoneChannels.length) {
    return (
      <section aria-labelledby="ct-title" className="card space-y-2 p-4">
        <h2 id="ct-title" className="font-display text-xl font-semibold">
          {t("reminders.phones")}
        </h2>
        <p className="text-sm text-ink-muted">{t("reminders.phonesUnavailable")}</p>
      </section>
    );
  }
  return (
    <section aria-labelledby="ct-title" className="card space-y-3 p-4">
      <h2 id="ct-title" className="font-display text-xl font-semibold">
        {t("reminders.phones")}
      </h2>
      <p className="text-sm text-ink-muted">{t("reminders.phonesHint")}</p>
      <ul className="space-y-2">
        {contacts.data?.map((c) => (
          <li key={c.id} className="flex flex-wrap items-end gap-2">
            <span className="inline-flex items-center gap-1">
              <Phone className="size-4" aria-hidden /> {t(`enum.channel.${c.channel}`)}: {c.address_hint}
            </span>
            {c.verified ? (
              <Badge tone="green">{t("reminders.verified")}</Badge>
            ) : (
              <>
                <Field label={t("reminders.code")}>
                  {(p) => <TextInput {...p} inputMode="numeric" maxLength={6} value={codes[c.id] ?? ""} onChange={(e) => setCodes({ ...codes, [c.id]: e.target.value })} />}
                </Field>
                <Button size="sm" loading={verify.isPending} onClick={() => verify.mutate({ id: c.id, code: (codes[c.id] ?? "").trim() }, { onSuccess: () => onStatus(t("reminders.verifiedStatus")) })}>
                  {t("reminders.verify")}
                </Button>
              </>
            )}
            <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" aria-hidden />} onClick={() => del.mutate(c.id)}>
              {t("common.remove")}
            </Button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-end gap-2">
        <Field label={t("reminders.channel")}>
          {(p) => (
            <Select {...p} value={channel} onChange={(e) => setChannel(e.target.value as NotificationChannel)}>
              {phoneChannels.map((c) => (
                <option key={c} value={c}>
                  {t(`enum.channel.${c}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("reminders.phone")} hint="+919876543210">
          {(p) => <TextInput {...p} type="tel" autoComplete="tel" value={number} onChange={(e) => setNumber(e.target.value)} />}
        </Field>
        <Button loading={add.isPending} disabled={!number.trim()} onClick={() => add.mutate({ channel, address: number.trim() }, { onSuccess: () => { setNumber(""); onStatus(t("reminders.codeSent")); } })}>
          {t("reminders.sendCode")}
        </Button>
      </div>
      <ErrorAlert error={add.error || verify.error || del.error} />
    </section>
  );
}

function HistorySection() {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const history = useDeliveryHistory(treeId);
  const rows = history.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <section aria-labelledby="hist-title" className="space-y-3">
      <h2 id="hist-title" className="font-display text-xl font-semibold">
        {t("reminders.history")}
      </h2>
      {history.isLoading && <Spinner />}
      <ErrorAlert error={history.error} />
      {history.data && rows.length === 0 && <p className="text-sm text-ink-muted">{t("reminders.noHistory")}</p>}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-stone-200">
                <th scope="col" className="py-1 pr-2">{t("reminders.col.when")}</th>
                <th scope="col" className="py-1 pr-2">{t("reminders.col.what")}</th>
                <th scope="col" className="py-1 pr-2">{t("reminders.col.channel")}</th>
                <th scope="col" className="py-1 pr-2">{t("reminders.col.status")}</th>
                <th scope="col" className="py-1">{t("reminders.col.detail")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id} className="border-b border-stone-100">
                  <td className="py-1 pr-2">{new Date(d.scheduled_for).toLocaleString()}</td>
                  <td className="py-1 pr-2">
                    {d.label ?? t("reminders.unavailableEvent")}
                    {d.is_test && <span className="ml-1 text-xs text-ink-muted">({t("reminders.test")})</span>}
                  </td>
                  <td className="py-1 pr-2">{t(`enum.channel.${d.channel}`)}</td>
                  <td className="py-1 pr-2">
                    <Badge tone={d.status === "sent" ? "green" : d.status === "failed" ? "red" : "stone"}>{t(`enum.deliveryStatus.${d.status}`)}</Badge>
                  </td>
                  <td className="py-1 text-xs text-ink-muted">
                    {d.attempts > 1 ? t("reminders.attempts", { count: d.attempts }) : ""}
                    {d.last_error_code ? ` ${d.last_error_code}` : ""}
                    {d.cancelled_reason ? t(`reminders.cancelReason.${d.cancelled_reason}`, { defaultValue: d.cancelled_reason }) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {history.hasNextPage && (
        <Button variant="secondary" size="sm" onClick={() => void history.fetchNextPage()}>
          {t("common.loadMore")}
        </Button>
      )}
    </section>
  );
}
