import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import type { KinshipPackOut } from "../../api/types";
import { useMe } from "../../api/hooks/auth";
import { useUpdateTree } from "../../api/hooks/trees";
import { useBranches } from "../../api/hooks/family";
import {
  useDeleteKinshipOverride,
  useKinshipOverrides,
  useKinshipPacks,
  usePutKinshipOverride,
  useSetKinshipPreference,
} from "../../api/hooks/culture";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { ErrorAlert, LiveRegion } from "../ui/feedback";
import { Field, Select, TextInput } from "../ui/form";

/** "lang|region" for a pack; "" = no choice of one's own. */
const packValue = (p: Pick<KinshipPackOut, "lang" | "region">) => `${p.lang}|${p.region}`;
const parse = (v: string) => {
  const [lang, region] = v.split("|");
  return { lang: lang || null, region: region || null };
};

function PackOptions({ packs }: { packs: KinshipPackOut[] }) {
  const { t, i18n } = useTranslation();
  const ui = i18n.language.startsWith("hi") ? "hi" : "en";
  return (
    <>
      {packs.map((p) => (
        <option key={p.key} value={packValue(p)}>
          {p.name[ui] ?? p.name.en}
          {p.status === "reviewed" ? "" : ` (${t("kinship.unreviewed")})`}
        </option>
      ))}
    </>
  );
}

/**
 * A reader's own choice of relationship words (ADR-0026 §6), in every tree. Separate from the UI
 * language: the app can stay in English while relationships read चाचा, ताऊ, मामा.
 */
export function KinshipPreferenceCard() {
  const { t } = useTranslation();
  const me = useMe();
  const packs = useKinshipPacks();
  const set = useSetKinshipPreference();
  const current = me.data?.kinship_lang ? `${me.data.kinship_lang}|${me.data.kinship_region ?? ""}` : "";
  const [value, setValue] = useState<string | null>(null);
  const [saved, setSaved] = useState("");
  const chosen = value ?? current;
  return (
    <section className="card space-y-3 p-5" aria-labelledby="kin-pref">
      <h2 id="kin-pref" className="font-display text-lg font-semibold">
        {t("kinship.preferenceTitle")}
      </h2>
      <p className="text-sm text-ink-muted">{t("kinship.preferenceIntro")}</p>
      <form
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          set.mutate(parse(chosen), { onSuccess: () => setSaved(t("common.saved")) });
        }}
      >
        <Field label={t("kinship.wordsIn")} className="flex-1">
          {(p) => (
            <Select {...p} value={chosen} onChange={(e) => setValue(e.target.value)}>
              <option value="">{t("kinship.followTree")}</option>
              <option value="en|">{t("kinship.english")}</option>
              <PackOptions packs={packs.data ?? []} />
            </Select>
          )}
        </Field>
        <Button type="submit" loading={set.isPending}>
          {t("common.save")}
        </Button>
      </form>
      <ErrorAlert error={set.error ?? packs.error} />
      <LiveRegion message={saved} />
    </section>
  );
}

const CHAIN_WORDS = ["father", "mother", "son", "daughter", "brother", "sister", "husband", "wife"] as const;

/**
 * The tree's default relationship words, and the family's own words for some relationships
 * ("Bhayo" for bhabhi), tree-wide or for one branch. A word never changes anyone's record.
 */
export function TreeKinshipCard() {
  const { t } = useTranslation();
  const { treeId, tree, can } = useTreeCtx();
  const packs = useKinshipPacks();
  const update = useUpdateTree(treeId);
  const words = useKinshipOverrides(treeId);
  const put = usePutKinshipOverride(treeId);
  const del = useDeleteKinshipOverride(treeId);
  const branches = useBranches(treeId);
  const [def, setDef] = useState<string | null>(null);
  const [chain, setChain] = useState<string[]>(["brother", "wife", ""]);
  const [age, setAge] = useState<"" | "elder" | "younger">("");
  const [lang, setLang] = useState("hi");
  const [word, setWord] = useState("");
  const [branch, setBranch] = useState("");
  const [saved, setSaved] = useState("");
  const canManage = can(Perm.TREE_MANAGE);
  const canWrite = can(Perm.FAMILY_WRITE);
  const currentDef = tree.kinship_lang ? `${tree.kinship_lang}|${tree.kinship_region ?? ""}` : "";
  const pattern = chain.filter(Boolean).join(".") + (age ? `:${age}` : "");
  const langs = [...new Set((packs.data ?? []).map((p) => p.lang))];
  const branchName = (id: string | null | undefined) => (branches.data ?? []).find((b) => b.id === id)?.name;

  return (
    <section className="card mt-4 space-y-4 p-5" aria-labelledby="kin-tree">
      <h2 id="kin-tree" className="font-display text-lg font-semibold">
        {t("kinship.treeTitle")}
      </h2>
      {canManage && (
        <form
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            const { lang: l, region } = parse(def ?? currentDef);
            update.mutate({ kinship_lang: l, kinship_region: l ? region : null }, { onSuccess: () => setSaved(t("common.saved")) });
          }}
        >
          <Field label={t("kinship.treeDefault")} hint={t("kinship.treeDefaultHint")} className="flex-1">
            {(p) => (
              <Select {...p} value={def ?? currentDef} onChange={(e) => setDef(e.target.value)}>
                <option value="">{t("kinship.followUi")}</option>
                <PackOptions packs={packs.data ?? []} />
              </Select>
            )}
          </Field>
          <Button type="submit" variant="secondary" loading={update.isPending}>
            {t("common.save")}
          </Button>
        </form>
      )}
      <ErrorAlert error={update.error} />

      <div>
        <h3 className="text-sm font-semibold">{t("kinship.familyWords")}</h3>
        <p className="text-xs text-ink-muted">{t("kinship.familyWordsIntro")}</p>
        {(words.data ?? []).length === 0 && <p className="mt-2 text-sm text-ink-muted">{t("kinship.noFamilyWords")}</p>}
        <ul className="mt-2 divide-y divide-stone-200">
          {(words.data ?? []).map((w) => (
            <li key={w.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
              <span className="font-medium" lang={w.lang}>
                {w.word}
              </span>
              <span className="text-ink-muted">{describePattern(w.pattern, t)}</span>
              {w.branch_id && <Badge tone="blue">{branchName(w.branch_id) ?? t("kinship.oneBranch")}</Badge>}
              {canWrite && (
                <button
                  type="button"
                  className="ml-auto rounded p-1 text-red-800 hover:bg-red-50"
                  aria-label={t("kinship.removeWord", { word: w.word })}
                  onClick={() => del.mutate(w.id)}
                >
                  <Trash2 className="size-4" aria-hidden />
                </button>
              )}
            </li>
          ))}
        </ul>
        <ErrorAlert error={del.error} />
      </div>

      {canWrite && (
        <form
          className="space-y-3 rounded-lg border border-stone-200 p-3"
          aria-labelledby="kin-add"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (!word.trim() || !chain[0]) return;
            put.mutate(
              { pattern, lang, word: word.trim(), branch_id: branch || null },
              {
                onSuccess: () => {
                  setWord("");
                  setSaved(t("common.saved"));
                },
              },
            );
          }}
        >
          <h3 id="kin-add" className="text-sm font-semibold">
            {t("kinship.addWord")}
          </h3>
          <fieldset className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <legend className="mb-1 text-xs text-ink-muted">{t("kinship.relationship")}</legend>
            {[0, 1, 2].map((i) => (
              <Field key={i} label={t("kinship.step", { n: i + 1 })}>
                {(p) => (
                  <Select
                    {...p}
                    value={chain[i]}
                    onChange={(e) => setChain(chain.map((c, j) => (j === i ? e.target.value : c)))}
                  >
                    {i > 0 && <option value="">{t("kinship.noStep")}</option>}
                    {CHAIN_WORDS.map((w) => (
                      <option key={w} value={w}>
                        {t(`kin.${w}`)}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            ))}
          </fieldset>
          <p className="text-xs text-ink-muted">
            {t("kinship.reads")}: {describePattern(pattern, t)}
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Field label={t("kinship.ageOnly")}>
              {(p) => (
                <Select {...p} value={age} onChange={(e) => setAge(e.target.value as "" | "elder" | "younger")}>
                  <option value="">{t("kinship.anyAge")}</option>
                  <option value="elder">{t("kinship.elder")}</option>
                  <option value="younger">{t("kinship.younger")}</option>
                </Select>
              )}
            </Field>
            <Field label={t("kinship.language")}>
              {(p) => (
                <Select {...p} value={lang} onChange={(e) => setLang(e.target.value)}>
                  {(langs.length ? langs : ["hi"]).map((l) => (
                    <option key={l} value={l}>
                      {t(`kinship.lang.${l}`, { defaultValue: l })}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label={t("kinship.word")} required>
              {(p) => <TextInput {...p} lang={lang} value={word} maxLength={120} onChange={(e) => setWord(e.target.value)} />}
            </Field>
            <Field label={t("kinship.branch")}>
              {(p) => (
                <Select {...p} value={branch} onChange={(e) => setBranch(e.target.value)}>
                  <option value="">{t("kinship.wholeTree")}</option>
                  {(branches.data ?? []).map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <ErrorAlert error={put.error} />
          <Button type="submit" size="sm" loading={put.isPending} disabled={!word.trim()}>
            {t("kinship.saveWord")}
          </Button>
        </form>
      )}
      <LiveRegion message={saved} />
    </section>
  );
}

/** "father.brother:elder" → "father's brother (elder)" in the UI language. */
export function describePattern(pattern: string, t: (k: string, o?: Record<string, unknown>) => string): string {
  const [chain, age] = pattern.split(":");
  const words = chain
    .split(".")
    .filter(Boolean)
    .map((w) => t(`kin.${w}`, { defaultValue: w }));
  const steps = chain.split(".").filter(Boolean);
  const feminine = new Set(["mother", "daughter", "sister", "wife"]);
  const text = words.reduce((acc, w, i) => (i === 0 ? w : t(feminine.has(steps[i]) ? "kinship.ofFeminine" : "kinship.of", { acc, word: w })), "");
  return age ? `${text} (${t(`kinship.${age}`)})` : text;
}
