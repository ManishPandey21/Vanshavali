import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { OFFERABLE, useFamilyEntries, useOfferEntry, useOffers, useWithdrawOffer } from "../../api/hooks/culture";
import type { OfferOut, VocabularyTerm } from "../../api/types";
import { useTreeCtx } from "../../lib/tree-context";
import { Button } from "../ui/Button";
import { Badge, type Tone } from "../ui/Badge";
import { Dialog } from "../ui/Dialog";
import { ErrorAlert } from "../ui/feedback";
import { Field, TextArea, TextInput } from "../ui/form";

const STATUS_TONE: Record<string, Tone> = { offered: "saffron", accepted: "green", declined: "stone" };

/**
 * A family's own list entries (a kuladevata, a devak…) and offering them to everyone's
 * suggestions (ADR-0026 §4). Opt-in, one entry at a time; the shared entry never names the family.
 */
export function OffersCard() {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const offers = useOffers(treeId);
  const byCode = new Map((offers.data ?? []).map((o) => [`${o.vocabulary_key}:${o.code}`, o]));
  return (
    <section className="card mt-4 space-y-3 p-5" aria-labelledby="offers-title">
      <h2 id="offers-title" className="font-display text-lg font-semibold">
        {t("offers.title")}
      </h2>
      <p className="text-sm text-ink-muted">{t("offers.intro")}</p>
      <ErrorAlert error={offers.error} />
      {OFFERABLE.map((key) => (
        <FamilyList key={key} vocab={key} offers={byCode} />
      ))}
    </section>
  );
}

function FamilyList({ vocab, offers }: { vocab: string; offers: Map<string, OfferOut> }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const entries = useFamilyEntries(treeId, vocab);
  const withdraw = useWithdrawOffer(treeId, vocab);
  const [offering, setOffering] = useState<VocabularyTerm | null>(null);
  if (!entries.data?.length) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold">{t(`offers.vocab.${vocab}`)}</h3>
      <ul className="divide-y divide-stone-200">
        {entries.data.map((e) => {
          const offer = offers.get(`${vocab}:${e.code}`);
          const status = offer?.offer_status ?? e.offer_status ?? "none";
          return (
            <li key={e.code} className="flex flex-wrap items-center gap-2 py-2 text-sm">
              <span className="font-medium">{e.label}</span>
              {status !== "none" && <Badge tone={STATUS_TONE[status] ?? "neutral"}>{t(`offers.status.${status}`)}</Badge>}
              <span className="ml-auto flex gap-2">
                {(status === "none" || status === "declined") && (
                  <Button size="sm" variant="secondary" onClick={() => setOffering(e)}>
                    {t("offers.offer")}
                  </Button>
                )}
                {status === "offered" && (
                  <Button size="sm" variant="ghost" loading={withdraw.isPending} onClick={() => withdraw.mutate(e.code)}>
                    {t("offers.withdraw")}
                  </Button>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      <ErrorAlert error={withdraw.error} />
      {offering && <OfferDialog vocab={vocab} entry={offering} onClose={() => setOffering(null)} />}
    </div>
  );
}

function OfferDialog({ vocab, entry, onClose }: { vocab: string; entry: VocabularyTerm; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const offer = useOfferEntry(treeId, vocab);
  const [note, setNote] = useState("");
  const [temple, setTemple] = useState("");
  const deity = vocab === "kuladevata" || vocab === "kuladevi";
  const submit = (e: FormEvent) => {
    e.preventDefault();
    offer.mutate({ code: entry.code, body: { note: note.trim() || null, temple: deity ? temple.trim() || null : null } }, { onSuccess: onClose });
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("offers.dialogTitle", { label: entry.label })}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="offer-form" loading={offer.isPending}>
            {t("offers.send")}
          </Button>
        </>
      }
    >
      <form id="offer-form" onSubmit={submit} className="space-y-3" noValidate>
        <p className="text-sm text-ink-muted">{t("offers.dialogIntro")}</p>
        {deity && (
          <Field label={t("offers.temple")} hint={t("offers.templeHint")}>
            {(p) => <TextInput {...p} value={temple} maxLength={200} onChange={(e) => setTemple(e.target.value)} />}
          </Field>
        )}
        <Field label={t("offers.note")} hint={t("offers.noteHint")}>
          {(p) => <TextArea {...p} rows={2} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />}
        </Field>
        <ErrorAlert error={offer.error} />
      </form>
    </Dialog>
  );
}
