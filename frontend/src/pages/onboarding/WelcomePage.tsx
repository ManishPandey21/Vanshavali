import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Check, EyeOff, Lock, ShieldCheck, Trash2, Users } from "lucide-react";
import { useMe } from "../../api/hooks/auth";
import { useAttest } from "../../api/hooks/onboarding";
import { useCreateTree } from "../../api/hooks/trees";
import { api } from "../../api/client";
import type { PersonCreate, PersonOut, ProfileStatus, RelativeOut, SexAtBirth, StatementOut, TreeOut } from "../../api/types";
import { ClaimInviteShare } from "../../components/consent/ClaimInviteShare";
import { StatementCheckbox } from "../../components/consent/FamilyConsent";
import { Button, ButtonLink } from "../../components/ui/Button";
import { ErrorAlert, PageHeader } from "../../components/ui/feedback";
import { Field, Fieldset, Select, TextInput } from "../../components/ui/form";

type Step = "notice" | "tree" | "family" | "invite";
const STEPS: Step[] = ["notice", "tree", "family", "invite"];

interface RelativeDraft {
  given: string;
  surname: string;
  status: ProfileStatus;
}

export interface AddedRelative {
  id: string;
  name: string;
  living: boolean;
}

function splitName(display: string | undefined): { given: string; surname: string } {
  const parts = (display ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length < 2) return { given: parts[0] ?? "", surname: "" };
  return { given: parts.slice(0, -1).join(" "), surname: parts[parts.length - 1] ?? "" };
}

function personBody(given: string, surname: string, status: ProfileStatus, sex?: SexAtBirth): PersonCreate {
  return {
    profile_status: status,
    ...(sex ? { sex_at_birth: sex } : {}),
    names: [{ given_name: given.trim(), surname: surname.trim() || null, is_preferred: true }],
  };
}

/**
 * First-run flow (ADR-0011): a plain-language privacy notice, name the tree, add yourself and
 * your parents behind the family-data consent checkbox, then invite living relatives to claim
 * their own profiles. Every step uses the ordinary API; the server enforces the consent.
 */
export function WelcomePage() {
  const { t } = useTranslation();
  const [step, setStep] = useState<Step>("notice");
  const [tree, setTree] = useState<TreeOut | null>(null);
  const [added, setAdded] = useState<AddedRelative[]>([]);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const index = STEPS.indexOf(step);

  // Move focus to the new step's heading so screen-reader and keyboard users know the page changed.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [step]);

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader eyebrow={t("onboarding.stepOf", { n: index + 1, total: STEPS.length })} title={t("onboarding.title")} />
      <ol className="mb-5 flex gap-2" aria-label={t("onboarding.progress")}>
        {STEPS.map((s, i) => (
          <li key={s} className="flex-1">
            <span className={`block h-1.5 rounded-full ${i <= index ? "bg-kumkum-700" : "bg-stone-200"}`} aria-hidden />
            <span className="sr-only">
              {t(`onboarding.steps.${s}`)}
              {i < index ? `, ${t("onboarding.done")}` : i === index ? `, ${t("onboarding.current")}` : ""}
            </span>
          </li>
        ))}
      </ol>
      <section className="card p-5 sm:p-6" aria-labelledby="onboarding-step-title">
        <h2 id="onboarding-step-title" ref={headingRef} tabIndex={-1} className="font-display text-xl font-semibold outline-none">
          {t(`onboarding.steps.${step}`)}
        </h2>
        <div className="mt-4">
          {step === "notice" && <NoticeStep onNext={() => setStep("tree")} />}
          {step === "tree" && (
            <TreeStep
              onCreated={(tr) => {
                setTree(tr);
                setStep("family");
              }}
            />
          )}
          {step === "family" && tree && (
            <FamilyStep
              tree={tree}
              onDone={(people) => {
                setAdded(people);
                setStep("invite");
              }}
            />
          )}
          {step === "invite" && tree && <InviteStep tree={tree} added={added} />}
        </div>
      </section>
    </div>
  );
}

function NoticeStep({ onNext }: { onNext: () => void }) {
  const { t } = useTranslation();
  const points = [
    { icon: Lock, key: "private" },
    { icon: EyeOff, key: "living" },
    { icon: Users, key: "claim" },
    { icon: Trash2, key: "control" },
  ] as const;
  return (
    <div className="space-y-4">
      <p className="text-sm">{t("onboarding.notice.intro")}</p>
      <ul className="space-y-3">
        {points.map(({ icon: Icon, key }) => (
          <li key={key} className="flex gap-3 text-sm">
            <Icon className="mt-0.5 size-5 shrink-0 text-kumkum-700" aria-hidden />
            <span>{t(`onboarding.notice.${key}`)}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-ink-muted">{t("onboarding.notice.noSale")}</p>
      <div className="flex justify-end gap-2">
        <ButtonLink to="/" variant="secondary">
          {t("onboarding.later")}
        </ButtonLink>
        <Button onClick={onNext}>{t("onboarding.notice.next")}</Button>
      </div>
    </div>
  );
}

function TreeStep({ onCreated }: { onCreated: (t: TreeOut) => void }) {
  const { t } = useTranslation();
  const create = useCreateTree();
  const [name, setName] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!name.trim()) return;
    create.mutate({ name: name.trim() }, { onSuccess: onCreated });
  };
  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <Field label={t("trees.name")} required hint={t("trees.nameHint")} error={submitted && !name.trim() ? t("common.required") : null}>
        {(p) => <TextInput {...p} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" />}
      </Field>
      <p className="rounded-lg bg-parchment-deep p-3 text-xs text-ink-muted">{t("trees.privateByDefault")}</p>
      <ErrorAlert error={create.error} />
      <div className="flex justify-end">
        <Button type="submit" loading={create.isPending}>
          {t("onboarding.tree.create")}
        </Button>
      </div>
    </form>
  );
}

function RelativeFields({ legend, value, onChange }: { legend: string; value: RelativeDraft; onChange: (v: RelativeDraft) => void }) {
  const { t } = useTranslation();
  return (
    <Fieldset legend={legend} description={t("onboarding.family.optional")}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label={t("onboarding.family.given")}>{(p) => <TextInput {...p} value={value.given} onChange={(e) => onChange({ ...value, given: e.target.value })} />}</Field>
        <Field label={t("onboarding.family.surname")}>{(p) => <TextInput {...p} value={value.surname} onChange={(e) => onChange({ ...value, surname: e.target.value })} />}</Field>
        <Field label={t("onboarding.family.status")}>
          {(p) => (
            <Select {...p} value={value.status} onChange={(e) => onChange({ ...value, status: e.target.value as ProfileStatus })}>
              <option value="living">{t("onboarding.family.living")}</option>
              <option value="deceased">{t("onboarding.family.deceased")}</option>
            </Select>
          )}
        </Field>
      </div>
    </Fieldset>
  );
}

function FamilyStep({ tree, onDone }: { tree: TreeOut; onDone: (people: AddedRelative[]) => void }) {
  const { t } = useTranslation();
  const me = useMe();
  const attest = useAttest();
  const [self, setSelf] = useState(() => splitName(me.data?.display_name));
  const [father, setFather] = useState<RelativeDraft>({ given: "", surname: self.surname, status: "living" });
  const [mother, setMother] = useState<RelativeDraft>({ given: "", surname: "", status: "living" });
  // Suggest the account name once it has loaded, unless the user has already typed something.
  const displayName = me.data?.display_name;
  useEffect(() => {
    if (!displayName) return;
    const guess = splitName(displayName);
    setSelf((cur) => (cur.given || cur.surname ? cur : guess));
    setFather((cur) => (cur.surname ? cur : { ...cur, surname: guess.surname }));
  }, [displayName]);
  const [consent, setConsent] = useState(false);
  const [statement, setStatement] = useState<StatementOut | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // Remember what was already saved so a retry after a failure never creates duplicates.
  const saved = useRef<{ selfId: string | null; parents: Record<string, AddedRelative> }>({ selfId: null, parents: {} });

  const selfMissing = !self.given.trim();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (selfMissing || !consent || !statement) return;
    setBusy(true);
    setError(null);
    try {
      // The server refuses to add anyone until this confirmation is recorded (ADR-0011).
      await attest.mutateAsync({ treeId: tree.id, statement });
      if (!saved.current.selfId) {
        const person = await api.post<PersonOut>(`/trees/${tree.id}/people`, personBody(self.given, self.surname, "living"));
        saved.current.selfId = person.id;
      }
      const selfId = saved.current.selfId;
      for (const [key, draft, sex] of [
        ["father", father, "male"],
        ["mother", mother, "female"],
      ] as const) {
        if (!draft.given.trim() || saved.current.parents[key]) continue;
        const res = await api.post<RelativeOut>(`/trees/${tree.id}/people/${selfId}/relatives`, {
          relation: "parent",
          new_person: personBody(draft.given, draft.surname, draft.status, sex),
        });
        saved.current.parents[key] = { id: res.person.id, name: res.person.display_name, living: draft.status === "living" };
      }
      onDone(Object.values(saved.current.parents));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="space-y-4">
      <p className="text-sm text-ink-muted">{t("onboarding.family.intro")}</p>
      <Fieldset legend={t("onboarding.family.you")}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("onboarding.family.given")} required error={submitted && selfMissing ? t("common.required") : null}>
            {(p) => <TextInput {...p} value={self.given} onChange={(e) => setSelf({ ...self, given: e.target.value })} autoComplete="given-name" />}
          </Field>
          <Field label={t("onboarding.family.surname")}>
            {(p) => <TextInput {...p} value={self.surname} onChange={(e) => setSelf({ ...self, surname: e.target.value })} autoComplete="family-name" />}
          </Field>
        </div>
      </Fieldset>
      <RelativeFields legend={t("onboarding.family.father")} value={father} onChange={setFather} />
      <RelativeFields legend={t("onboarding.family.mother")} value={mother} onChange={setMother} />
      <StatementCheckbox
        kind="family_data"
        checked={consent}
        onChange={setConsent}
        onStatement={setStatement}
        error={submitted && !consent ? t("onboarding.consent.required") : null}
      />
      <p className="text-xs text-ink-muted">{t("onboarding.consent.why")}</p>
      <ErrorAlert error={error} />
      <div className="flex flex-wrap justify-end gap-2">
        <ButtonLink to={`/t/${tree.id}`} variant="secondary">
          {t("onboarding.family.skip")}
        </ButtonLink>
        <Button type="submit" loading={busy} icon={<Check className="size-4" aria-hidden />}>
          {t("onboarding.family.save")}
        </Button>
      </div>
    </form>
  );
}

function InviteStep({ tree, added }: { tree: TreeOut; added: AddedRelative[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const living = added.filter((p) => p.living);
  return (
    <div className="space-y-4">
      <p className="text-sm">{t("onboarding.invite.intro")}</p>
      <p className="flex items-start gap-2 rounded-lg bg-leaf-50 p-3 text-xs text-leaf-700">
        <ShieldCheck className="size-4 shrink-0" aria-hidden />
        {t("onboarding.invite.safety")}
      </p>
      {living.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("onboarding.invite.none")}</p>
      ) : (
        <ul className="space-y-4">
          {living.map((p) => (
            <li key={p.id} className="rounded-lg border border-stone-200 p-3">
              <p className="mb-2 font-medium">{p.name}</p>
              <ClaimInviteShare treeId={tree.id} personId={p.id} personName={p.name} canOfferContributor />
            </li>
          ))}
        </ul>
      )}
      <div className="flex justify-end">
        <Button onClick={() => navigate(`/t/${tree.id}`)}>{t("onboarding.invite.finish")}</Button>
      </div>
    </div>
  );
}
