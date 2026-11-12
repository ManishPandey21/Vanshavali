import { useState } from "react";
import { Eye, MapPin, Pencil, Plus, Star, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  AddressIn,
  AddressOut,
  AddressPurpose,
  AddressStatus,
  PersonContactIn,
  ContactKind,
  PersonContactOut,
} from "../../../api/types";
import {
  useCreateAddress,
  useCreateContact,
  useAddressHistory,
  useDeleteAddress,
  useDeleteContact,
  usePersonAddresses,
  usePersonContacts,
  useMoveAddress,
  useRevealContact,
  useUpdateAddress,
  useUpdateContact,
} from "../../../api/hooks/profileDetails";
import { emptyPlace, PlacePicker, type PlaceValue } from "../../../components/pickers";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../../components/ui/Dialog";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Checkbox, Field, Select, TextArea, TextInput } from "../../../components/ui/form";
import { useTreeCtx } from "../../../lib/tree-context";

const PURPOSES: AddressPurpose[] = [
  "current_residence",
  "permanent",
  "previous_residence",
  "ancestral_home",
  "native_place",
  "correspondence",
  "other",
];
const CONTACT_KINDS: ContactKind[] = ["email", "mobile", "whatsapp", "telegram", "instagram", "legacy_note"];

export function AddressesContactsTab({ personId, canEdit }: { personId: string; canEdit: boolean }) {
  const { treeId } = useTreeCtx();
  const { t } = useTranslation();
  const label = (value: string) => t(`profileDetails.values.${value}`);
  const addresses = usePersonAddresses(treeId, personId);
  const contacts = usePersonContacts(treeId, personId);
  const deleteAddress = useDeleteAddress(treeId, personId);
  const deleteContact = useDeleteContact(treeId, personId);
  const reveal = useRevealContact(treeId, personId);
  const [addressEdit, setAddressEdit] = useState<AddressOut | "new" | null>(null);
  const [moveFrom, setMoveFrom] = useState<AddressOut | null>(null);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const [contactEdit, setContactEdit] = useState<{ row: PersonContactOut | null; value: string } | null>(null);
  const [remove, setRemove] = useState<{ type: "address" | "contact"; id: string; revision: number; label: string } | null>(null);
  const [revealed, setRevealed] = useState<Record<string, { value: string; profileUrl?: string | null }>>({});

  if (addresses.isLoading || contacts.isLoading) return <Spinner />;
  if (addresses.error || contacts.error) return <ErrorAlert error={addresses.error ?? contacts.error} />;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section aria-labelledby="addresses-heading" className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 id="addresses-heading" className="font-display text-lg font-semibold">{t("profileDetails.addresses.title")}</h2>
            <p className="text-sm text-ink-muted">{t("profileDetails.addresses.description")}</p>
          </div>
          {canEdit && <Button size="sm" icon={<Plus className="size-4" aria-hidden />} onClick={() => setAddressEdit("new")}>{t("profileDetails.addresses.add")}</Button>}
        </div>
        {!addresses.data?.items.length && <EmptyState title={t("profileDetails.addresses.emptyTitle")}>{t("profileDetails.addresses.emptyBody")}</EmptyState>}
        <ul className="space-y-3">
          {addresses.data?.items.map((address) => (
            <li key={address.id} className="card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-semibold"><MapPin className="size-4 text-kumkum-700" aria-hidden />{label(address.purpose)} {address.is_primary_current && <Badge tone="green">{t("profileDetails.values.primary")}</Badge>} {address.status === "former" && <Badge>{label("former")}</Badge>}</p>
                  <p className="mt-1 whitespace-pre-wrap text-sm">{addressLine(address, t("profileDetails.addresses.noDetails"))}</p>
                  {(address.locality || address.sub_district || address.district || address.state || address.postal_code) && <p className="text-sm text-ink-muted">{[address.locality, address.sub_district, address.district, address.state, address.postal_code, address.country_code].filter(Boolean).join(", ")}</p>}
                  {address.landmark && <p className="mt-1 text-xs text-ink-muted">{t("profileDetails.fields.landmark")}: {address.landmark}</p>}
                </div>
                <div className="flex shrink-0 flex-wrap gap-1">
                  <Button variant="ghost" size="sm" onClick={() => setHistoryId(address.id)}>{t("profileDetails.addresses.history")}</Button>
                  {canEdit && <>{address.status === "current" && <Button variant="ghost" size="sm" onClick={() => setMoveFrom(address)}>{t("profileDetails.addresses.moved")}</Button>}<Button variant="ghost" size="sm" aria-label={t("profileDetails.addresses.edit")} icon={<Pencil className="size-4" aria-hidden />} onClick={() => setAddressEdit(address)} /><Button variant="ghost" size="sm" aria-label={t("profileDetails.addresses.remove")} icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setRemove({ type: "address", id: address.id, revision: address.revision, label: addressLine(address, t("profileDetails.addresses.noDetails")) })} /></>}
                </div>
              </div>
            </li>
          ))}
        </ul>
        <ErrorAlert error={deleteAddress.error} />
      </section>

      <section aria-labelledby="contacts-heading" className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div><h2 id="contacts-heading" className="font-display text-lg font-semibold">{t("profileDetails.contacts.title")}</h2><p className="text-sm text-ink-muted">{t("profileDetails.contacts.description")}</p></div>
          {canEdit && <Button size="sm" icon={<Plus className="size-4" aria-hidden />} onClick={() => setContactEdit({ row: null, value: "" })}>{t("profileDetails.contacts.add")}</Button>}
        </div>
        {!contacts.data?.items.length && <EmptyState title={t("profileDetails.contacts.emptyTitle")}>{t("profileDetails.contacts.emptyBody")}</EmptyState>}
        <ul className="space-y-3">
          {contacts.data?.items.map((contact) => (
            <li key={contact.id} className="card flex items-center justify-between gap-3 p-4">
              <div className="min-w-0"><p className="flex items-center gap-2 font-semibold">{label(contact.kind)} {contact.is_preferred && <Star className="size-4 fill-haldi-300 text-haldi-700" aria-label={t("profileDetails.values.preferred")} />}</p><p className="break-all text-sm text-ink-muted">{revealed[contact.id]?.profileUrl ? <a className="text-kumkum-800 underline" href={revealed[contact.id].profileUrl!} target="_blank" rel="noreferrer">{revealed[contact.id].value}</a> : revealed[contact.id]?.value ?? contact.hint}</p>{contact.purpose && <p className="text-xs text-ink-muted">{contact.purpose}</p>}{contact.language && <p className="text-xs text-ink-muted">{t("profileDetails.contacts.language", { language: contact.language })}</p>}{contact.copy_outdated && <p className="mt-1 text-xs font-medium text-amber-800">{t("profileDetails.contacts.mobileChanged")}</p>}</div>
              <div className="flex shrink-0 gap-1">
                <Button variant="ghost" size="sm" aria-label={t("profileDetails.contacts.reveal", { kind: label(contact.kind) })} loading={reveal.isPending && reveal.variables === contact.id} icon={<Eye className="size-4" aria-hidden />} onClick={() => reveal.mutate(contact.id, { onSuccess: (data) => setRevealed((old) => ({ ...old, [contact.id]: { value: data.value, profileUrl: data.profile_url } })) })} />
                {canEdit && <><Button variant="ghost" size="sm" aria-label={t("profileDetails.contacts.edit", { kind: label(contact.kind) })} icon={<Pencil className="size-4" aria-hidden />} onClick={() => { const known = revealed[contact.id]?.value; if (known) setContactEdit({ row: contact, value: known }); else reveal.mutate(contact.id, { onSuccess: (data) => { setRevealed((old) => ({ ...old, [contact.id]: { value: data.value, profileUrl: data.profile_url } })); setContactEdit({ row: contact, value: data.value }); } }); }} /><Button variant="ghost" size="sm" aria-label={t("profileDetails.contacts.remove", { kind: label(contact.kind) })} icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setRemove({ type: "contact", id: contact.id, revision: contact.revision, label: label(contact.kind) })} /></>}
              </div>
            </li>
          ))}
        </ul>
        <ErrorAlert error={reveal.error ?? deleteContact.error} />
      </section>

      {addressEdit && <AddressDialog treeId={treeId} personId={personId} address={addressEdit === "new" ? null : addressEdit} moveFrom={null} onClose={() => setAddressEdit(null)} />}
      {moveFrom && <AddressDialog treeId={treeId} personId={personId} address={null} moveFrom={moveFrom} onClose={() => setMoveFrom(null)} />}
      {historyId && <AddressHistoryDialog treeId={treeId} personId={personId} addressId={historyId} onClose={() => setHistoryId(null)} />}
      {contactEdit && <ContactDialog treeId={treeId} personId={personId} contacts={contacts.data?.items ?? []} contact={contactEdit.row} initialValue={contactEdit.value} onClose={() => setContactEdit(null)} />}
      <ConfirmDialog open={!!remove} onClose={() => setRemove(null)} title={t("profileDetails.remove.title", { type: remove ? t(`profileDetails.remove.${remove.type}`) : t("profileDetails.remove.item") })} body={remove ? t("profileDetails.remove.body", { label: remove.label }) : ""} confirmLabel={t("profileDetails.remove.confirm")} danger loading={deleteAddress.isPending || deleteContact.isPending} onConfirm={() => { if (!remove) return; const done = { onSuccess: () => setRemove(null) }; if (remove.type === "address") deleteAddress.mutate(remove, done); else deleteContact.mutate(remove, done); }} />
    </div>
  );
}

function addressLine(address: AddressOut, fallback = ""): string {
  return [address.building, address.street, address.as_recorded].filter(Boolean).join(", ") || fallback;
}

interface AddressDraft {
  purpose: AddressPurpose;
  status: AddressStatus;
  primary: boolean;
  place: PlaceValue;
  building: string;
  street: string;
  locality: string;
  subDistrict: string;
  district: string;
  state: string;
  postal: string;
  country: string;
  landmark: string;
  gramPanchayat: string;
  postOffice: string;
  notes: string;
}

function AddressDialog({ treeId, personId, address, moveFrom, onClose }: { treeId: string; personId: string; address: AddressOut | null; moveFrom: AddressOut | null; onClose: () => void }) {
  const { t } = useTranslation();
  const label = (value: string) => t(`profileDetails.values.${value}`);
  const create = useCreateAddress(treeId, personId);
  const update = useUpdateAddress(treeId, personId, address?.id ?? "");
  const move = useMoveAddress(treeId, personId, moveFrom?.id ?? "");
  const [moveDate, setMoveDate] = useState("");
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [moveIdempotencyKey] = useState(() => crypto.randomUUID());
  const [draft, setDraft] = useState<AddressDraft>(() => ({ purpose: address?.purpose ?? "current_residence", status: address?.status ?? "current", primary: address?.is_primary_current ?? moveFrom?.is_primary_current ?? true, place: address ? { place_id: address.place_id ?? null, place_label: null, place_as_recorded: address.as_recorded ?? "" } : emptyPlace(), building: address?.building ?? "", street: address?.street ?? "", locality: address?.locality ?? "", subDistrict: address?.sub_district ?? "", district: address?.district ?? "", state: address?.state ?? "", postal: address?.postal_code ?? "", country: address?.country_code ?? "IN", landmark: address?.landmark ?? "", gramPanchayat: address?.gram_panchayat ?? "", postOffice: address?.post_office ?? "", notes: address?.notes ?? "" }));
  const set = (change: Partial<AddressDraft>) => setDraft((old) => ({ ...old, ...change }));
  const save = () => {
    const body: AddressIn = { purpose: draft.purpose, status: draft.status, is_primary_current: draft.status === "current" && draft.primary, place_id: draft.place.place_id, as_recorded: draft.place.place_as_recorded || null, building: draft.building || null, street: draft.street || null, locality: draft.locality || null, sub_district: draft.subDistrict || null, district: draft.district || null, state: draft.state || null, postal_code: draft.postal || null, country_code: draft.country || null, landmark: draft.landmark || null, gram_panchayat: draft.gramPanchayat || null, post_office: draft.postOffice || null, notes: draft.notes || null, idempotency_key: idempotencyKey };
    if (moveFrom) {
      const validUntil = moveDate ? { precision: "exact" as const, year: Number(moveDate.slice(0, 4)), month: Number(moveDate.slice(5, 7)), day: Number(moveDate.slice(8, 10)) } : null;
      move.mutate({ revision: moveFrom.revision, idempotency_key: moveIdempotencyKey, valid_until: validUntil, reason: t("profileDetails.addresses.movedReason"), new_address: { ...body, status: "current", valid_from: validUntil, idempotency_key: null } }, { onSuccess: onClose });
    } else if (address) update.mutate({ ...body, revision: address.revision, reason: t("profileDetails.addresses.editedReason") }, { onSuccess: onClose });
    else create.mutate(body, { onSuccess: onClose });
  };
  const error = create.error ?? update.error ?? move.error;
  return <Dialog open onClose={onClose} title={moveFrom ? t("profileDetails.addresses.moveTitle") : address ? t("profileDetails.addresses.editTitle") : t("profileDetails.addresses.addTitle")} description={t("profileDetails.addresses.formDescription")} size="lg" footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button loading={create.isPending || update.isPending || move.isPending} onClick={save}>{moveFrom ? t("profileDetails.addresses.saveMove") : t("profileDetails.addresses.save")}</Button></>}>
    <div className="grid gap-4 sm:grid-cols-2">
      {moveFrom && <Field label={t("profileDetails.fields.moveDate")} hint={t("profileDetails.fields.moveDateHint")}>{(p) => <TextInput {...p} type="date" value={moveDate} onChange={(e) => setMoveDate(e.target.value)} />}</Field>}
      <Field label={t("profileDetails.fields.purpose")} required>{(p) => <Select {...p} value={draft.purpose} onChange={(e) => set({ purpose: e.target.value as AddressPurpose })}>{draft.purpose === "unknown" && <option value="unknown">{label("unknown")}</option>}{PURPOSES.map((v) => <option key={v} value={v}>{label(v)}</option>)}</Select>}</Field>
      <Field label={t("profileDetails.fields.status")} required>{(p) => <Select {...p} disabled={!!moveFrom} value={draft.status} onChange={(e) => set({ status: e.target.value as AddressStatus, primary: e.target.value === "current" && draft.primary })}>{draft.status === "unknown" && <option value="unknown">{label("unknown")}</option>}<option value="current">{label("current")}</option><option value="former">{label("former")}</option></Select>}</Field>
      <div className="sm:col-span-2"><PlacePicker treeId={treeId} label={t("profileDetails.fields.place")} value={draft.place} onChange={(place) => set({ place })} /></div>
      <Field label={t("profileDetails.fields.building")}>{(p) => <TextInput {...p} value={draft.building} onChange={(e) => set({ building: e.target.value })} />}</Field>
      <Field label={t("profileDetails.fields.street")}>{(p) => <TextInput {...p} value={draft.street} onChange={(e) => set({ street: e.target.value })} />}</Field>
      <Field label={t("profileDetails.fields.locality")}>{(p) => <TextInput {...p} value={draft.locality} onChange={(e) => set({ locality: e.target.value })} />}</Field>
      <Field label={t("profileDetails.fields.subDistrict")}>{(p) => <TextInput {...p} value={draft.subDistrict} onChange={(e) => set({ subDistrict: e.target.value })} />}</Field>
      <Field label={t("profileDetails.fields.district")}>{(p) => <TextInput {...p} value={draft.district} onChange={(e) => set({ district: e.target.value })} />}</Field>
      <Field label={t("profileDetails.fields.state")}>{(p) => <TextInput {...p} value={draft.state} onChange={(e) => set({ state: e.target.value })} />}</Field>
      <Field label={t("profileDetails.fields.postal")}>{(p) => <TextInput {...p} value={draft.postal} onChange={(e) => set({ postal: e.target.value })} />}</Field>
      <Field label={t("profileDetails.fields.country")} hint={t("profileDetails.fields.countryHint")}>{(p) => <TextInput {...p} maxLength={2} value={draft.country} onChange={(e) => set({ country: e.target.value.toUpperCase() })} />}</Field>
      <Field label={t("profileDetails.fields.landmark")}>{(p) => <TextInput {...p} value={draft.landmark} onChange={(e) => set({ landmark: e.target.value })} />}</Field>
      <Field label={t("profileDetails.fields.gramPanchayat")}>{(p) => <TextInput {...p} value={draft.gramPanchayat} onChange={(e) => set({ gramPanchayat: e.target.value })} />}</Field>
      <Field label={t("profileDetails.fields.postOffice")}>{(p) => <TextInput {...p} value={draft.postOffice} onChange={(e) => set({ postOffice: e.target.value })} />}</Field>
      <Field className="sm:col-span-2" label={t("profileDetails.fields.notes")}>{(p) => <TextArea {...p} value={draft.notes} onChange={(e) => set({ notes: e.target.value })} />}</Field>
      {draft.status === "current" && <div className="sm:col-span-2"><Checkbox label={t("profileDetails.fields.primary")} checked={draft.primary} onChange={(primary) => set({ primary })} /></div>}
      <div className="sm:col-span-2"><ErrorAlert error={error} /></div>
    </div>
  </Dialog>;
}

function AddressHistoryDialog({ treeId, personId, addressId, onClose }: { treeId: string; personId: string; addressId: string; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const history = useAddressHistory(treeId, personId, addressId);
  return <Dialog open onClose={onClose} title={t("profileDetails.addresses.historyTitle")} footer={<Button variant="secondary" onClick={onClose}>{t("common.close")}</Button>}>
    {history.isLoading && <Spinner />}
    <ErrorAlert error={history.error} />
    {!history.isLoading && !history.data?.items.length && <EmptyState title={t("profileDetails.addresses.historyEmpty")} />}
    <ol className="space-y-3">
      {history.data?.items.map((entry) => <li key={`${entry.revision}-${entry.operation}`} className="rounded-xl border border-line p-3">
        <p className="font-semibold">{t("profileDetails.addresses.revision", { revision: entry.revision })} · {t(`profileDetails.values.${entry.operation}`, { defaultValue: entry.operation })}</p>
        <p className="text-xs text-ink-muted">{new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" }).format(new Date(entry.created_at))}</p>
        {entry.reason && <p className="mt-1 text-sm">{entry.reason}</p>}
      </li>)}
    </ol>
  </Dialog>;
}

function ContactDialog({ treeId, personId, contacts, contact, initialValue, onClose }: { treeId: string; personId: string; contacts: PersonContactOut[]; contact: PersonContactOut | null; initialValue: string; onClose: () => void }) {
  const { t } = useTranslation();
  const label = (item: string) => t(`profileDetails.values.${item}`);
  const create = useCreateContact(treeId, personId);
  const update = useUpdateContact(treeId, personId, contact?.id ?? "");
  const copyMobile = useRevealContact(treeId, personId);
  const [kind, setKind] = useState<ContactKind>(contact?.kind ?? "email");
  const [value, setValue] = useState(initialValue);
  const [purpose, setPurpose] = useState(contact?.purpose ?? "");
  const [language, setLanguage] = useState(contact?.language ?? "");
  const [preferred, setPreferred] = useState(contact?.is_preferred ?? false);
  const [copiedFrom, setCopiedFrom] = useState<{ id: string; revision: number } | null>(null);
  const [copyTouched, setCopyTouched] = useState(false);
  const [valueTouched, setValueTouched] = useState(false);
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const mobile = contacts.find((item) => item.kind === "mobile");
  const save = () => {
    const copyFields = copiedFrom ? { copied_from_contact_id: copiedFrom.id, copied_from_revision: copiedFrom.revision } : {};
    const body: PersonContactIn = { kind, value, purpose: purpose || null, language: language || null, is_preferred: preferred, ...copyFields, idempotency_key: idempotencyKey };
    if (contact) update.mutate({ ...(valueTouched ? { value } : {}), purpose: purpose || null, language: language || null, is_preferred: preferred, ...(copyTouched ? { copied_from_contact_id: copiedFrom?.id ?? null, copied_from_revision: copiedFrom?.revision ?? null } : {}), revision: contact.revision, reason: t("profileDetails.contacts.editedReason") }, { onSuccess: onClose });
    else create.mutate(body, { onSuccess: onClose });
  };
  return <Dialog open onClose={onClose} title={contact ? t("profileDetails.contacts.editTitle") : t("profileDetails.contacts.addTitle")} description={t("profileDetails.contacts.formDescription")} footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button><Button loading={create.isPending || update.isPending} onClick={save}>{t("profileDetails.contacts.save")}</Button></>}>
    <div className="space-y-4">
      <Field label={t("profileDetails.fields.type")} required>{(p) => <Select {...p} disabled={!!contact} value={kind} onChange={(e) => { setKind(e.target.value as ContactKind); setCopiedFrom(null); setCopyTouched(true); }}>{CONTACT_KINDS.map((v) => <option key={v} value={v}>{label(v)}</option>)}</Select>}</Field>
      {kind === "whatsapp" && mobile && <Button variant="secondary" size="sm" loading={copyMobile.isPending} onClick={() => copyMobile.mutate(mobile.id, { onSuccess: (data) => { setValue(data.value); setCopiedFrom({ id: mobile.id, revision: mobile.revision }); setCopyTouched(true); } })}>{t("profileDetails.contacts.sameAsMobile")}</Button>}
      <Field label={t("profileDetails.fields.value")} required hint={kind === "mobile" || kind === "whatsapp" ? t("profileDetails.fields.phoneHint") : kind === "instagram" || kind === "telegram" ? t("profileDetails.fields.socialHint") : undefined}>{(p) => kind === "legacy_note" ? <TextArea {...p} value={value} onChange={(e) => { setValue(e.target.value); setValueTouched(true); setCopiedFrom(null); setCopyTouched(true); }} /> : <TextInput {...p} type={kind === "email" ? "email" : "text"} value={value} onChange={(e) => { setValue(e.target.value); setValueTouched(true); setCopiedFrom(null); setCopyTouched(true); }} />}</Field>
      <Field label={t("profileDetails.fields.contactPurpose")} hint={t("profileDetails.fields.contactPurposeHint")}>{(p) => <TextInput {...p} value={purpose} onChange={(e) => setPurpose(e.target.value)} />}</Field>
      <Field label={t("profileDetails.fields.language")} hint={t("profileDetails.fields.languageHint")}>{(p) => <TextInput {...p} maxLength={16} value={language} onChange={(e) => setLanguage(e.target.value)} />}</Field>
      <Checkbox label={t("profileDetails.fields.preferred")} checked={preferred} onChange={setPreferred} />
      <ErrorAlert error={create.error ?? update.error ?? copyMobile.error} />
    </div>
  </Dialog>;
}
