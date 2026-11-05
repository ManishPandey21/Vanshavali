import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Crown, Home, Landmark, Plus, Trash2, UserMinus } from "lucide-react";
import type { GenealogicalDate, HouseholdMemberOut, HouseholdOut, HouseholdRole, PersonSummary } from "../../api/types";
import {
  useAddHouseholdMember,
  useBranches,
  useCreateHousehold,
  useDeleteHousehold,
  useEndHouseholdMember,
  useHousehold,
  useHouseholds,
  useUpdateHousehold,
} from "../../api/hooks/family";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { emptyDate, normalizeDate, validateDate } from "../../lib/dates";
import { GenealogicalDateEditor } from "../../components/dates/GenealogicalDateEditor";
import { DateText } from "../../components/dates/DateText";
import { PersonPicker, PlacePicker, emptyPlace, type PlaceValue } from "../../components/pickers";
import { PersonBadges, PersonLink, PrivatePersonPlaceholder } from "../../components/person/badges";
import { hasDate } from "../../components/person/PersonForm";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../components/ui/feedback";
import { Checkbox, Field, Select, TextArea, TextInput } from "../../components/ui/form";
import { Badge } from "../../components/ui/Badge";

export const HOUSEHOLD_ROLES: HouseholdRole[] = ["karta", "head", "reference_person", "member", "dependent", "other"];

export function HouseholdsPage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [params, setParams] = useSearchParams();
  const branchFilter = params.get("branch") ?? undefined;
  const households = useHouseholds(treeId, branchFilter);
  const branches = useBranches(treeId);
  const [creating, setCreating] = useState(false);
  const open = params.get("open");
  const setOpen = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set("open", id);
    else next.delete("open");
    setParams(next, { replace: true });
  };
  return (
    <div>
      <PageHeader
        title={t("households.title")}
        subtitle={t("households.subtitle")}
        actions={
          can(Perm.FAMILY_WRITE) ? (
            <Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setCreating(true)}>
              {t("households.create")}
            </Button>
          ) : undefined
        }
      />
      <div className="mb-4 max-w-xs">
        <Field label={t("households.filterBranch")}>
          {(p) => (
            <Select
              {...p}
              value={branchFilter ?? ""}
              onChange={(e) => {
                const next = new URLSearchParams(params);
                if (e.target.value) next.set("branch", e.target.value);
                else next.delete("branch");
                setParams(next, { replace: true });
              }}
            >
              <option value="">{t("common.all")}</option>
              {branches.data?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      {households.isLoading && <Spinner />}
      <ErrorAlert error={households.error} />
      {households.data?.length === 0 && <EmptyState icon={<Home className="size-10" aria-hidden />} title={t("households.empty")}>{t("households.emptyHint")}</EmptyState>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <ul className="space-y-2">
          {households.data?.map((h) => (
            <li key={h.id}>
              <button
                type="button"
                onClick={() => setOpen(h.id)}
                aria-pressed={open === h.id}
                className={`card w-full p-3 text-left hover:border-kumkum-200 ${open === h.id ? "border-kumkum-600 ring-1 ring-kumkum-600" : ""}`}
              >
                <p className="font-display font-semibold">{h.name}</p>
                {h.house_name && <p className="text-sm text-ink-muted">{h.house_name}</p>}
                <p className="mt-1 text-xs text-ink-muted">
                  {t("households.memberCount", { count: h.member_count ?? 0 })}
                  {(h.provisional_member_count ?? 0) > 0 ? ` · ${t("people.toComplete.count", { count: h.provisional_member_count })}` : ""}
                  {h.place_name ? ` · ${h.place_name}` : ""}
                </p>
              </button>
            </li>
          ))}
        </ul>
        {open && <HouseholdDetail householdId={open} onDeleted={() => setOpen(null)} />}
      </div>
      {creating && <CreateHouseholdDialog onClose={() => setCreating(false)} onCreated={(h) => setOpen(h.id)} />}
    </div>
  );
}

function CreateHouseholdDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (h: HouseholdOut) => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const branches = useBranches(treeId);
  const create = useCreateHousehold(treeId);
  const [name, setName] = useState("");
  const [houseName, setHouseName] = useState("");
  const [branchId, setBranchId] = useState("");
  const [place, setPlace] = useState<PlaceValue>(emptyPlace());
  const [start, setStart] = useState<GenealogicalDate>(emptyDate());
  const [notes, setNotes] = useState("");
  const [submitted, setSubmitted] = useState(false);
  // Households store a linked place only (no free-text place), so typed text must be linked first.
  const placeUnlinked = !place.place_id && !!place.place_as_recorded.trim();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!name.trim() || (hasDate(start) && Object.keys(validateDate(start)).length) || placeUnlinked) return;
    create.mutate(
      {
        name: name.trim(),
        house_name: houseName.trim() || null,
        branch_id: branchId || null,
        place_id: place.place_id,
        start_date: hasDate(start) ? normalizeDate(start) : null,
        notes: notes.trim() || null,
      },
      {
        onSuccess: (h) => {
          onCreated(h);
          onClose();
        },
      },
    );
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("households.create")}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="hh-form" loading={create.isPending}>
            {t("common.create")}
          </Button>
        </>
      }
    >
      <form id="hh-form" onSubmit={submit} className="space-y-3" noValidate>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("households.name")} required error={submitted && !name.trim() ? t("common.required") : null}>
            {(p) => <TextInput {...p} value={name} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label={t("households.houseName")} hint={t("households.houseNameHint")}>
            {(p) => <TextInput {...p} value={houseName} onChange={(e) => setHouseName(e.target.value)} />}
          </Field>
          <Field label={t("households.branch")}>
            {(p) => (
              <Select {...p} value={branchId} onChange={(e) => setBranchId(e.target.value)}>
                <option value="">{t("common.none")}</option>
                {branches.data?.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <PlacePicker treeId={treeId} label={t("households.place")} value={place} onChange={setPlace} />
        {submitted && placeUnlinked && (
          <p role="alert" className="field-error">
            {t("households.placeMustLink")}
          </p>
        )}
        <GenealogicalDateEditor legend={t("households.startDate")} value={start} onChange={setStart} showErrors={submitted && hasDate(start)} />
        <Field label={t("households.notes")}>{(p) => <TextArea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        <ErrorAlert error={create.error} />
      </form>
    </Dialog>
  );
}

export function HouseholdDetail({ householdId, onDeleted }: { householdId: string; onDeleted?: () => void }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const hh = useHousehold(treeId, householdId);
  const add = useAddHouseholdMember(treeId, householdId);
  const del = useDeleteHousehold(treeId);
  const [person, setPerson] = useState<PersonSummary | null>(null);
  const [role, setRole] = useState<HouseholdRole>("member");
  const [start, setStart] = useState<GenealogicalDate>(emptyDate());
  const [ending, setEnding] = useState<HouseholdMemberOut | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editingHh, setEditingHh] = useState(false);
  const canWrite = can(Perm.FAMILY_WRITE);
  if (hh.isLoading) return <Spinner />;
  if (!hh.data) return <ErrorAlert error={hh.error} />;
  const h = hh.data;
  const current = (h.members ?? []).filter((m) => m.current);
  const former = (h.members ?? []).filter((m) => !m.current);

  return (
    <section className="card p-4" aria-labelledby="hh-detail">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="hh-detail" className="font-display text-xl font-semibold">
            {h.name}
          </h2>
          {h.house_name && <p className="text-sm text-ink-muted">{h.house_name}</p>}
          <p className="mt-1 text-xs text-ink-muted">
            {h.place_name && <>{h.place_name} · </>}
            {h.start_date && (
              <>
                {t("households.from")} <DateText date={h.start_date} showOriginal={false} />
              </>
            )}
          </p>
          {h.notes && <p className="mt-1 whitespace-pre-wrap text-sm">{h.notes}</p>}
        </div>
        {canWrite && (
          <div className="flex gap-1">
            <Button size="sm" variant="secondary" onClick={() => setEditingHh(true)}>
              {t("common.edit")}
            </Button>
            <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setConfirmDelete(true)}>
              {t("common.delete")}
            </Button>
          </div>
        )}
      </div>
      <MemberList title={t("households.currentMembers")} members={current} onEnd={canWrite ? setEnding : undefined} />
      {former.length > 0 && <MemberList title={t("households.formerMembers")} members={former} />}
      {(h.hidden_member_count ?? 0) > 0 && (
        <p className="mt-2 text-sm">
          <PrivatePersonPlaceholder /> <span className="text-xs text-ink-muted">× {h.hidden_member_count}</span>
        </p>
      )}
      {canWrite && (
        <form
          className="mt-4 space-y-3 rounded-lg border border-dashed border-stone-300 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!person) return;
            add.mutate(
              { person_id: person.id, role, start_date: hasDate(start) ? normalizeDate(start) : null },
              {
                onSuccess: () => {
                  setPerson(null);
                  setStart(emptyDate());
                },
              },
            );
          }}
        >
          <p className="text-sm font-semibold">{t("households.addMember")}</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <PersonPicker treeId={treeId} label={t("households.person")} value={person} onChange={setPerson} />
            <Field label={t("households.role")} hint={role === "karta" ? t("households.kartaHint") : undefined}>
              {(p) => (
                <Select {...p} value={role} onChange={(e) => setRole(e.target.value as HouseholdRole)}>
                  {HOUSEHOLD_ROLES.map((r) => (
                    <option key={r} value={r}>
                      {t(`enum.householdRole.${r}`)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <GenealogicalDateEditor legend={t("households.memberFrom")} value={start} onChange={setStart} />
          <ErrorAlert error={add.error} />
          <Button type="submit" size="sm" disabled={!person} loading={add.isPending}>
            {t("common.add")}
          </Button>
        </form>
      )}
      {editingHh && <EditHouseholdDialog household={h} onClose={() => setEditingHh(false)} />}
      {ending && <EndMembershipDialog householdId={householdId} member={ending} onClose={() => setEnding(null)} />}
      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title={t("households.deleteTitle", { name: h.name })}
        body={t("households.deleteBody")}
        confirmLabel={t("common.delete")}
        danger
        loading={del.isPending}
        onConfirm={() => del.mutate(h.id, { onSuccess: () => onDeleted?.() })}
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </section>
  );
}

function MemberList({ title, members, onEnd }: { title: string; members: HouseholdMemberOut[]; onEnd?: (m: HouseholdMemberOut) => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  return (
    <div className="mt-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{title}</h3>
      {members.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("households.noMembers")}</p>
      ) : (
        <ul className="divide-y divide-stone-100">
          {members.map((m) => (
            <li key={m.id} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap items-center gap-2">
                {m.role === "karta" && <Crown className="size-4 text-haldi-700" aria-hidden />}
                {m.person ? <PersonLink treeId={treeId} person={m.person} /> : <PrivatePersonPlaceholder />}
                <Badge tone={m.role === "karta" ? "saffron" : "neutral"}>{t(`enum.householdRole.${m.role}`)}</Badge>
                <span className="text-xs text-ink-muted">
                  {m.start_date && (
                    <>
                      {t("households.from")} <DateText date={m.start_date} showOriginal={false} />{" "}
                    </>
                  )}
                  {m.end_date && (
                    <>
                      {t("households.until")} <DateText date={m.end_date} showOriginal={false} />
                    </>
                  )}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {m.person && <PersonBadges person={m.person} />}
                {onEnd && (
                  <Button size="sm" variant="ghost" icon={<UserMinus className="size-4" aria-hidden />} onClick={() => onEnd(m)}>
                    {t("households.endMembership")}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EndMembershipDialog({ householdId, member, onClose }: { householdId: string; member: HouseholdMemberOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const end = useEndHouseholdMember(treeId, householdId);
  const [date, setDate] = useState<GenealogicalDate>({ calendar: "gregorian", precision: "year_only", year: new Date().getFullYear() });
  const [remove, setRemove] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const submit = () => {
    setSubmitted(true);
    if (!remove && hasDate(date) && Object.keys(validateDate(date)).length) return;
    // An unknown end is sent explicitly as precision "unknown" so the server does not assume "this year".
    const endDate = hasDate(date) ? normalizeDate(date) : { calendar: "gregorian" as const, precision: "unknown" as const };
    end.mutate({ id: member.id, endDate: remove ? null : endDate, remove }, { onSuccess: onClose });
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("households.endTitle", { name: member.person?.display_name ?? t("person.privatePerson") })}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button variant={remove ? "danger" : "primary"} loading={end.isPending} onClick={submit}>
            {remove ? t("households.removeRecord") : t("households.endMembership")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {!remove && <GenealogicalDateEditor legend={t("households.endDate")} value={date} onChange={setDate} showErrors={submitted} />}
        <Checkbox label={t("households.removeInstead")} hint={t("households.removeInsteadHint")} checked={remove} onChange={setRemove} />
        <ErrorAlert error={end.error} />
      </div>
    </Dialog>
  );
}

/** Joint Family View: households grouped under their branch, each with current and former members. */
export function JointFamilyPage() {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const branches = useBranches(treeId);
  const households = useHouseholds(treeId);
  if (branches.isLoading || households.isLoading) return <Spinner />;
  const groups = [
    ...(branches.data ?? []).map((b) => ({ id: b.id, name: b.name, rule: b.descent_rule, items: (households.data ?? []).filter((h) => h.branch_id === b.id) })),
    { id: "", name: t("jointFamily.unassigned"), rule: null, items: (households.data ?? []).filter((h) => !h.branch_id) },
  ].filter((g) => g.id || g.items.length);
  return (
    <div>
      <PageHeader title={t("jointFamily.title")} subtitle={t("jointFamily.subtitle")} />
      <ErrorAlert error={branches.error || households.error} />
      {groups.length === 0 && (
        <EmptyState icon={<Landmark className="size-10" aria-hidden />} title={t("jointFamily.empty")}>
          <Link className="text-kumkum-800 underline" to={`/t/${treeId}/branches`}>
            {t("nav.branches")}
          </Link>{" "}
          ·{" "}
          <Link className="text-kumkum-800 underline" to={`/t/${treeId}/households`}>
            {t("nav.households")}
          </Link>
        </EmptyState>
      )}
      <div className="space-y-6">
        {groups.map((g) => (
          <section key={g.id || "none"} aria-labelledby={`jf-${g.id || "none"}`} className="rounded-2xl border border-haldi-300 bg-white/70 p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Landmark className="size-5 text-haldi-700" aria-hidden />
              <h2 id={`jf-${g.id || "none"}`} className="font-display text-xl font-semibold">
                {g.id ? (
                  <Link to={`/t/${treeId}/branches/${g.id}`} className="hover:underline">
                    {g.name}
                  </Link>
                ) : (
                  g.name
                )}
              </h2>
              {g.rule && <Badge tone="saffron">{t(`enum.descentRule.${g.rule}`)}</Badge>}
              <span className="text-xs text-ink-muted">{t("jointFamily.householdCount", { count: g.items.length })}</span>
            </div>
            {g.items.length === 0 ? (
              <p className="text-sm text-ink-muted">{t("jointFamily.noHouseholds")}</p>
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                {g.items.map((h) => (
                  <JointHousehold key={h.id} householdId={h.id} />
                ))}
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}

function JointHousehold({ householdId }: { householdId: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const hh = useHousehold(treeId, householdId);
  if (!hh.data) return <Spinner />;
  const h = hh.data;
  const current = (h.members ?? []).filter((m) => m.current);
  const former = (h.members ?? []).filter((m) => !m.current);
  return (
    <article className="card p-4">
      <h3 className="font-display font-semibold">
        <Link to={`/t/${treeId}/households?open=${h.id}`} className="text-kumkum-900 hover:underline">
          {h.name}
        </Link>
      </h3>
      {h.house_name && <p className="text-sm text-ink-muted">{h.house_name}</p>}
      <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">{t("households.currentMembers")}</p>
      <ul className="text-sm">
        {current.map((m) => (
          <li key={m.id} className="flex items-center gap-1.5 py-0.5">
            {m.role === "karta" && <Crown className="size-3.5 text-haldi-700" aria-label={t("enum.householdRole.karta")} />}
            {m.person ? <PersonLink treeId={treeId} person={m.person} /> : <PrivatePersonPlaceholder compact />}
            <span className="text-xs text-ink-muted">· {t(`enum.householdRole.${m.role}`)}</span>
          </li>
        ))}
        {current.length === 0 && <li className="text-ink-muted">{t("households.noMembers")}</li>}
      </ul>
      {former.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-ink-muted">{t("households.formerMembers")} ({former.length})</summary>
          <ul className="text-sm">
            {former.map((m) => (
              <li key={m.id} className="py-0.5">
                {m.person ? <PersonLink treeId={treeId} person={m.person} /> : <PrivatePersonPlaceholder compact />}{" "}
                <span className="text-xs text-ink-muted">
                  · {t(`enum.householdRole.${m.role}`)}
                  {m.end_date && (
                    <>
                      {" "}
                      · {t("households.until")} <DateText date={m.end_date} showOriginal={false} />
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {(h.hidden_member_count ?? 0) > 0 && <p className="mt-1 text-xs text-ink-muted">{t("households.hiddenCount", { count: h.hidden_member_count })}</p>}
    </article>
  );
}

function EditHouseholdDialog({ household, onClose }: { household: HouseholdOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const branches = useBranches(treeId);
  const update = useUpdateHousehold(treeId, household.id);
  const [name, setName] = useState(household.name);
  const [houseName, setHouseName] = useState(household.house_name ?? "");
  const [branchId, setBranchId] = useState(household.branch_id ?? "");
  const [place, setPlace] = useState<PlaceValue>(household.place_id ? { place_id: household.place_id, place_label: household.place_name ?? null, place_as_recorded: household.place_name ?? "" } : emptyPlace());
  const [start, setStart] = useState<GenealogicalDate>((household.start_date as GenealogicalDate | null) ?? emptyDate());
  const [end, setEnd] = useState<GenealogicalDate>((household.end_date as GenealogicalDate | null) ?? emptyDate());
  const [notes, setNotes] = useState(household.notes ?? "");
  const [submitted, setSubmitted] = useState(false);
  const bad = (d: GenealogicalDate) => hasDate(d) && Object.keys(validateDate(d)).length > 0;
  const placeUnlinked = !place.place_id && !!place.place_as_recorded.trim();
  const save = () => {
    setSubmitted(true);
    if (!name.trim() || bad(start) || bad(end) || placeUnlinked) return;
    update.mutate(
      {
        name: name.trim(),
        house_name: houseName.trim() || null,
        branch_id: branchId || null,
        place_id: place.place_id,
        start_date: hasDate(start) ? normalizeDate(start) : null,
        end_date: hasDate(end) ? normalizeDate(end) : null,
        notes: notes.trim() || null,
      },
      { onSuccess: onClose },
    );
  };
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={t("households.editTitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button loading={update.isPending} onClick={save}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={t("households.name")} required error={submitted && !name.trim() ? t("common.required") : null}>
            {(p) => <TextInput {...p} value={name} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label={t("households.houseName")}>{(p) => <TextInput {...p} value={houseName} onChange={(e) => setHouseName(e.target.value)} />}</Field>
          <Field label={t("households.branch")}>
            {(p) => (
              <Select {...p} value={branchId} onChange={(e) => setBranchId(e.target.value)}>
                <option value="">{t("common.none")}</option>
                {branches.data?.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <PlacePicker treeId={treeId} label={t("households.place")} value={place} onChange={setPlace} />
        {submitted && placeUnlinked && <p className="field-error">{t("households.placeMustLink")}</p>}
        <GenealogicalDateEditor legend={t("households.startDate")} value={start} onChange={setStart} showErrors={submitted && hasDate(start)} />
        <GenealogicalDateEditor legend={t("households.endedOn")} value={end} onChange={setEnd} showErrors={submitted && hasDate(end)} />
        <Field label={t("households.notes")}>{(p) => <TextArea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
        <ErrorAlert error={update.error} />
      </div>
    </Dialog>
  );
}
