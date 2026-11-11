import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bell, BellRing } from "lucide-react";
import type { EventOut, GenealogicalDate, LunarDate, NotificationChannel, ReminderDateRule, ReminderOut, ReminderRecurrence } from "../../api/types";
import { useCalendarSettings } from "../../api/hooks/calendar";
import { lunarLabel } from "../../lib/lunar";
import { useChannels, useCreateReminder, useDeleteReminder, useReminders, useTestReminder, useUpdateReminder } from "../../api/hooks/reminders";
import { eventLabel } from "../../lib/lifeEvents";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { ErrorAlert, LiveRegion } from "../ui/feedback";
import { Checkbox, Field, Fieldset, Select, TextInput } from "../ui/form";

export const LEAD_PRESETS = [0, 1, 7] as const;
const ALL_CHANNELS: NotificationChannel[] = ["email", "sms", "whatsapp"];
const ANNUAL_TYPES = new Set(["birth", "marriage", "death", "memorial", "cremation", "burial"]);

/** "Remind me" for one event. Reminders are personal: only you see and receive them (ADR-0016). */
export function ReminderControl({ treeId, event }: { treeId: string; event: EventOut }) {
  const { t } = useTranslation();
  const reminders = useReminders(treeId);
  const existing = reminders.data?.find((r) => r.event_id === event.id) ?? null;
  const [open, setOpen] = useState(false);
  const label = eventLabel(event, t);
  return (
    <>
      <button
        type="button"
        className={`inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs hover:bg-kumkum-50 ${existing ? "font-semibold text-kumkum-900" : "text-kumkum-800"}`}
        onClick={() => setOpen(true)}
        aria-label={existing ? t("reminders.editFor", { event: label }) : t("reminders.addFor", { event: label })}
      >
        {existing ? <BellRing className="size-3.5" aria-hidden /> : <Bell className="size-3.5" aria-hidden />}
        {existing ? t("reminders.on") : t("reminders.remindMe")}
      </button>
      {open && <ReminderDialog treeId={treeId} event={event} existing={existing} onClose={() => setOpen(false)} />}
    </>
  );
}

export function ReminderDialog({ treeId, event, existing, onClose }: { treeId: string; event: EventOut; existing: ReminderOut | null; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const channels = useChannels();
  const settings = useCalendarSettings(treeId);
  const create = useCreateReminder(treeId);
  const update = useUpdateReminder(treeId);
  const del = useDeleteReminder(treeId);
  const test = useTestReminder(treeId);
  const annualByDefault = ANNUAL_TYPES.has(event.type);
  const [lead, setLead] = useState<number[]>(existing?.lead_days ?? [0]);
  const [custom, setCustom] = useState(() => (existing?.lead_days ?? []).filter((d) => !(LEAD_PRESETS as readonly number[]).includes(d)).join(", "));
  const [chosen, setChosen] = useState<NotificationChannel[]>(existing?.channels ?? ["email"]);
  const [recurrence, setRecurrence] = useState<ReminderRecurrence>(existing?.recurrence ?? (annualByDefault ? "annual" : "none"));
  const [note, setNote] = useState(existing?.note ?? "");
  const [dateRule, setDateRule] = useState<ReminderDateRule>(existing?.date_rule ?? "solar");
  const [city, setCity] = useState<string>(existing?.observance_city ?? "");
  const [status, setStatus] = useState("");
  const lunar = ((event.date as GenealogicalDate | null)?.lunar ?? null) as LunarDate | null;
  const conv = settings.data?.conventions?.find((c) => c.key === (existing?.convention ?? settings.data?.convention));
  // the tithi option appears only for a recorded tithi and a convention that has passed its checks (ADR-0022 §8)
  const lunarOffered = !!lunar && !!conv?.offered;
  const followTithi = lunarOffered && dateRule === "lunar";
  const customDays = custom
    .split(/[,\s]+/)
    .filter(Boolean)
    .map(Number);
  const customErr = customDays.some((d) => !Number.isInteger(d) || d < 0 || d > 365);
  const allLead = [...new Set([...lead, ...(customErr ? [] : customDays)])].sort((a, b) => a - b);
  const invalid = customErr || !allLead.length || !chosen.length || allLead.length > 6 || (followTithi && !city && !settings.data?.observance_city);
  const mutation = existing ? update : create;
  const save = () => {
    if (invalid) return;
    const body = {
      lead_days: allLead,
      channels: chosen,
      note: note.trim() || null,
      recurrence: followTithi ? ("annual" as const) : recurrence,
      // without an offered convention the rule is left as it is (a paused tithi reminder stays a tithi reminder)
      ...(lunarOffered ? { date_rule: followTithi ? ("lunar" as const) : ("solar" as const) } : {}),
      ...(followTithi ? { convention: conv!.key, observance_city: city || null } : {}),
    };
    if (existing) update.mutate({ id: existing.id, body: { ...body, active: true } }, { onSuccess: onClose });
    else create.mutate({ event_id: event.id, ...body }, { onSuccess: onClose });
  };
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  return (
    <Dialog
      open
      onClose={onClose}
      title={existing ? t("reminders.editTitle") : t("reminders.addTitle")}
      description={t("reminders.dialogHint", { event: eventLabel(event, t) })}
      footer={
        <>
          {existing && (
            <Button variant="ghost" loading={del.isPending} onClick={() => del.mutate(existing.id, { onSuccess: onClose })}>
              {t("reminders.stop")}
            </Button>
          )}
          {existing && (
            <Button variant="secondary" loading={test.isPending} onClick={() => test.mutate(existing.id, { onSuccess: () => setStatus(t("reminders.testSent")) })}>
              {t("reminders.sendTest")}
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={save} loading={mutation.isPending} disabled={invalid}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Fieldset legend={t("reminders.when")}>
          <div className="flex flex-wrap gap-4">
            {LEAD_PRESETS.map((d) => (
              <Checkbox key={d} label={t(`reminders.lead.${d}`)} checked={lead.includes(d)} onChange={() => setLead(toggle(lead, d))} />
            ))}
          </div>
          <Field label={t("reminders.customDays")} hint={t("reminders.customDaysHint")} error={customErr ? t("reminders.customDaysError") : null}>
            {(p) => <TextInput {...p} value={custom} inputMode="numeric" onChange={(e) => setCustom(e.target.value)} />}
          </Field>
        </Fieldset>
        <Fieldset legend={t("reminders.repeat")}>
          <Checkbox
            label={t("reminders.everyYear")}
            hint={annualByDefault ? t("reminders.everyYearHint") : t("reminders.onceHint")}
            checked={recurrence === "annual" || followTithi}
            disabled={followTithi}
            onChange={(v) => setRecurrence(v ? "annual" : "none")}
          />
          {lunarOffered && lunar && (
            <>
              <Checkbox
                label={t("reminders.followTithi", { tithi: lunarLabel(lunar, i18n.language) })}
                hint={t("reminders.followTithiHint", { convention: conv!.label })}
                checked={followTithi}
                onChange={(v) => setDateRule(v ? "lunar" : "solar")}
              />
              {followTithi && (
                <Field label={t("reminders.observedIn")} hint={t("reminders.observedInHint")}>
                  {(p) => (
                    <Select {...p} value={city} onChange={(e) => setCity(e.target.value)}>
                      <option value="">
                        {settings.data?.observance_city
                          ? t("reminders.treeCity", { city: settings.data.cities.find((c) => c.key === settings.data?.observance_city)?.label ?? settings.data.observance_city })
                          : t("reminders.chooseCity")}
                      </option>
                      {settings.data?.cities?.map((c) => (
                        <option key={c.key} value={c.key}>
                          {c.label}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
              )}
            </>
          )}
        </Fieldset>
        <Fieldset legend={t("reminders.channels")} description={t("reminders.channelsHint")}>
          <div className="flex flex-wrap gap-4">
            {ALL_CHANNELS.map((c) => {
              const available = channels.data ? channels.data[c] : c === "email";
              return (
                <Checkbox
                  key={c}
                  label={`${t(`enum.channel.${c}`)}${available ? "" : ` (${t("reminders.unavailable")})`}`}
                  checked={chosen.includes(c)}
                  disabled={!available}
                  onChange={() => setChosen(toggle(chosen, c))}
                />
              );
            })}
          </div>
        </Fieldset>
        <Field label={t("reminders.note")} hint={t("reminders.noteHint")}>
          {(p) => <TextInput {...p} value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />}
        </Field>
        <ErrorAlert error={mutation.error || del.error || test.error} />
        <LiveRegion message={status} />
        {status && <p className="text-sm text-green-800">{status}</p>}
      </div>
    </Dialog>
  );
}
