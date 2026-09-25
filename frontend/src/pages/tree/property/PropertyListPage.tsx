import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Landmark, Plus } from "lucide-react";
import type { PrivacyLevel, PropertyClassification, PropertyType } from "../../../api/types";
import { useCreateProperty, useProperties } from "../../../api/hooks/property";
import { useTreeCtx } from "../../../lib/tree-context";
import { Perm } from "../../../lib/permissions";
import { useDebounced } from "../../../lib/useDebounced";
import { PlacePicker, emptyPlace, type PlaceValue } from "../../../components/pickers";
import { PRIVACY_LEVELS } from "../../../components/person/PersonForm";
import { PrivacyBadge } from "../../../components/person/badges";
import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../../components/ui/feedback";
import { Field, Select, TextArea, TextInput } from "../../../components/ui/form";
import { Badge } from "../../../components/ui/Badge";
import { CLASSIFICATIONS, LegalNotice, PROPERTY_TYPES } from "./common";

export function PropertyListPage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const [q, setQ] = useState("");
  const debounced = useDebounced(q.trim(), 300);
  const allowed = can(Perm.PROPERTY_READ) || can(Perm.PROPERTY_WRITE);
  const props = useProperties(treeId, debounced, allowed);
  const [creating, setCreating] = useState(false);
  if (!allowed) return <Navigate to={`/t/${treeId}`} replace />;
  return (
    <div>
      <PageHeader
        title={t("property.title")}
        subtitle={t("property.subtitle")}
        actions={
          can(Perm.PROPERTY_WRITE) ? (
            <Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setCreating(true)}>
              {t("property.create")}
            </Button>
          ) : undefined
        }
      />
      <div className="mb-4 space-y-3">
        <LegalNotice />
        <div className="max-w-md">
          <Field label={t("property.search")}>{(p) => <TextInput {...p} type="search" value={q} onChange={(e) => setQ(e.target.value)} />}</Field>
        </div>
      </div>
      {props.isLoading && <Spinner />}
      <ErrorAlert error={props.error} />
      {props.data?.length === 0 && (
        <EmptyState icon={<Landmark className="size-10" aria-hidden />} title={t("property.empty")}>
          {t("property.emptyHint")}
        </EmptyState>
      )}
      <ul className="grid gap-3 md:grid-cols-2">
        {props.data?.map((p) => (
          <li key={p.id}>
            <Link to={`/t/${treeId}/property/${p.id}`} className="card block h-full p-4 hover:border-kumkum-200">
              <h2 className="font-display text-lg font-semibold text-kumkum-900">{p.display_name}</h2>
              <p className="text-sm text-ink-muted">{[p.place_name, p.address_text].filter(Boolean).join(" · ")}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                <Badge tone="saffron">{t(`enum.propertyType.${p.property_type}`)}</Badge>
                <Badge tone="neutral">{t(`enum.classification.${p.classification}`)}</Badge>
                <Badge tone="stone">{t("property.parcelCount", { count: p.parcel_count ?? 0 })}</Badge>
                <PrivacyBadge level={p.privacy_level} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {creating && <CreatePropertyDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

function CreatePropertyDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const create = useCreateProperty(treeId);
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [type, setType] = useState<PropertyType>("agricultural_land");
  const [classification, setClassification] = useState<PropertyClassification>("ancestral");
  const [privacy, setPrivacy] = useState<PrivacyLevel>("PRIVATE_TREE_ADMINS");
  const [place, setPlace] = useState<PlaceValue>(emptyPlace());
  const [address, setAddress] = useState("");
  const [description, setDescription] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!name.trim()) return;
    create.mutate(
      {
        display_name: name.trim(),
        property_type: type,
        classification,
        privacy_level: privacy,
        place_id: place.place_id,
        address_text: address.trim() || (!place.place_id && place.place_as_recorded.trim()) || null,
        description: description.trim() || null,
      },
      { onSuccess: (p) => navigate(`/t/${treeId}/property/${p.id}`) },
    );
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("property.create")}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="prop-form" loading={create.isPending}>
            {t("common.create")}
          </Button>
        </>
      }
    >
      <form id="prop-form" onSubmit={submit} className="space-y-3" noValidate>
        <LegalNotice />
        <Field label={t("property.name")} required error={submitted && !name.trim() ? t("common.required") : null}>
          {(p) => <TextInput {...p} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={t("property.type")}>
            {(p) => (
              <Select {...p} value={type} onChange={(e) => setType(e.target.value as PropertyType)}>
                {PROPERTY_TYPES.map((x) => (
                  <option key={x} value={x}>
                    {t(`enum.propertyType.${x}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("property.classification")} hint={t("property.classificationHint")}>
            {(p) => (
              <Select {...p} value={classification} onChange={(e) => setClassification(e.target.value as PropertyClassification)}>
                {CLASSIFICATIONS.map((x) => (
                  <option key={x} value={x}>
                    {t(`enum.classification.${x}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label={t("privacy.level")}>
            {(p) => (
              <Select {...p} value={privacy} onChange={(e) => setPrivacy(e.target.value as PrivacyLevel)}>
                {PRIVACY_LEVELS.map((l) => (
                  <option key={l} value={l}>
                    {t(`enum.privacy.${l}`)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <PlacePicker treeId={treeId} label={t("property.place")} value={place} onChange={setPlace} />
        <Field label={t("property.address")}>{(p) => <TextArea {...p} rows={2} value={address} onChange={(e) => setAddress(e.target.value)} />}</Field>
        <Field label={t("property.description")}>{(p) => <TextArea {...p} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
        <ErrorAlert error={create.error} />
      </form>
    </Dialog>
  );
}
