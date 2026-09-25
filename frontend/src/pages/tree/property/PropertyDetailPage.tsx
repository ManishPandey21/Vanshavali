import { useState, type FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Edit3, Trash2, Upload } from "lucide-react";
import type { PrivacyLevel, PropertyClassification, PropertyDetailOut, PropertyType } from "../../../api/types";
import { useDocuments } from "../../../api/hooks/documents";
import { useDeleteProperty, useProperty, useUpdateProperty } from "../../../api/hooks/property";
import { useTreeCtx } from "../../../lib/tree-context";
import { Perm } from "../../../lib/permissions";
import { PROPERTY_DOCUMENT_CATEGORIES } from "../../../lib/documents";
import { DocumentRow } from "../../../components/documents/DocumentBits";
import { UploadDocumentDialog } from "../../../components/documents/UploadDocumentDialog";
import { GrantsPanel } from "../../../components/privacy/GrantsPanel";
import { PRIVACY_LEVELS } from "../../../components/person/PersonForm";
import { PrivacyBadge } from "../../../components/person/badges";
import { Button } from "../../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../../components/ui/Dialog";
import { EmptyState, ErrorAlert, PageHeader, Spinner } from "../../../components/ui/feedback";
import { Field, Select, TextArea, TextInput } from "../../../components/ui/form";
import { Tabs } from "../../../components/ui/Tabs";
import { Badge } from "../../../components/ui/Badge";
import { CLASSIFICATIONS, InterestLine, LegalNotice, PROPERTY_TYPES } from "./common";
import { ParcelsPanel } from "./ParcelsPanel";
import { InterestsPanel } from "./InterestsPanel";
import { LineagePanel, TimelinePanel } from "./TimelinePanel";

const TABS = ["overview", "parcels", "interests", "timeline", "lineage", "documents"] as const;

export function PropertyDetailPage() {
  const { propertyId = "" } = useParams();
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const prop = useProperty(treeId, propertyId);
  const [params, setParams] = useSearchParams();
  const tab = (TABS as readonly string[]).includes(params.get("tab") ?? "") ? params.get("tab")! : "overview";
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const del = useDeleteProperty(treeId);
  const navigate = useNavigate();
  if (prop.isLoading) return <Spinner />;
  if (!prop.data) return <ErrorAlert error={prop.error} />;
  const p = prop.data;
  const canWrite = !!p.can_edit && can(Perm.PROPERTY_WRITE);
  return (
    <div>
      <PageHeader
        eyebrow={t("property.eyebrow")}
        title={p.display_name}
        subtitle={[p.place_name, p.address_text].filter(Boolean).join(" · ") || undefined}
        actions={
          canWrite ? (
            <>
              <Button variant="secondary" icon={<Edit3 className="size-4" aria-hidden />} onClick={() => setEditing(true)}>
                {t("common.edit")}
              </Button>
              <Button variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setDeleting(true)}>
                {t("common.delete")}
              </Button>
            </>
          ) : undefined
        }
      />
      <div className="mb-4 space-y-3">
        <LegalNotice text={p.legal_notice} />
        <div className="flex flex-wrap gap-1">
          <Badge tone="saffron">{t(`enum.propertyType.${p.property_type}`)}</Badge>
          <Badge tone="neutral">{t(`enum.classification.${p.classification}`)}</Badge>
          <PrivacyBadge level={p.privacy_level} />
          {p.current_status && <Badge tone="stone">{p.current_status}</Badge>}
        </div>
      </div>
      <Tabs
        label={t("property.sections")}
        tabs={TABS.map((id) => ({ id, label: t(`property.tab.${id}`), count: id === "parcels" ? p.counts?.parcels : id === "documents" ? p.counts?.documents : undefined }))}
        active={tab}
        onChange={(id) => setParams({ tab: id }, { replace: true })}
      >
        {tab === "overview" && <Overview p={p} />}
        {tab === "parcels" && <ParcelsPanel property={p} canWrite={canWrite} />}
        {tab === "interests" && <InterestsPanel property={p} canWrite={canWrite} />}
        {tab === "timeline" && <TimelinePanel property={p} canWrite={canWrite} />}
        {tab === "lineage" && <LineagePanel property={p} />}
        {tab === "documents" && <PropertyDocuments p={p} />}
      </Tabs>
      {p.privacy_level === "CUSTOM" && (
        <div className="mt-6">
          <GrantsPanel resourceType="property" resourceId={p.id} isCustom />
        </div>
      )}
      {editing && <EditPropertyDialog p={p} onClose={() => setEditing(false)} />}
      <ConfirmDialog
        open={deleting}
        onClose={() => setDeleting(false)}
        title={t("property.deleteTitle", { name: p.display_name })}
        body={t("property.deleteBody")}
        confirmLabel={t("common.delete")}
        danger
        loading={del.isPending}
        onConfirm={() => del.mutate(p.id, { onSuccess: () => navigate(`/t/${treeId}/property`) })}
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </div>
  );
}

function Overview({ p }: { p: PropertyDetailOut }) {
  const { t } = useTranslation();
  const c = p.counts;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="card p-4" aria-labelledby="po-holders">
        <h2 id="po-holders" className="font-display text-lg font-semibold">
          {t("property.currentHolders")}
        </h2>
        <p className="text-sm">
          {t("property.documentedTotal")}: <strong className="font-mono">{p.documented_share_total}</strong>
        </p>
        {p.has_overlapping_claims && <p className="mt-1 rounded bg-red-50 p-2 text-sm text-red-900">{t("property.overlapping")}</p>}
        {(p.current_interests ?? []).length === 0 ? (
          <p className="mt-2 text-sm text-ink-muted">{t("property.noInterests")}</p>
        ) : (
          <ul className="mt-2 divide-y divide-stone-100">
            {(p.current_interests ?? []).map((i) => (
              <li key={i.id} className="py-1.5">
                <InterestLine i={i} />
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card p-4" aria-labelledby="po-counts">
        <h2 id="po-counts" className="font-display text-lg font-semibold">
          {t("property.record")}
        </h2>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
          {(["parcels", "events", "interests", "current_interests", "documents", "citations"] as const).map((k) => (
            <div key={k}>
              <dt className="text-xs text-ink-muted">{t(`property.count.${k}`)}</dt>
              <dd className="font-display text-xl font-bold">{c?.[k] ?? 0}</dd>
            </div>
          ))}
        </dl>
        {p.description && <p className="mt-3 whitespace-pre-wrap text-sm">{p.description}</p>}
      </section>
    </div>
  );
}

function PropertyDocuments({ p }: { p: PropertyDetailOut }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const docs = useDocuments(treeId, { target_type: "property", target_id: p.id });
  const [uploading, setUploading] = useState(false);
  const items = docs.data?.items ?? [];
  return (
    <section aria-labelledby="pd-title" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="pd-title" className="font-display text-lg font-semibold">
          {t("property.tab.documents")}
        </h2>
        {can(Perm.DOCUMENT_UPLOAD) && (
          <Button size="sm" icon={<Upload className="size-4" aria-hidden />} onClick={() => setUploading(true)}>
            {t("documents.upload")}
          </Button>
        )}
      </div>
      {docs.isLoading && <Spinner />}
      <ErrorAlert error={docs.error} />
      {docs.data && items.length === 0 && <EmptyState title={t("property.noDocuments")} />}
      {items.length > 0 && (
        <ul className="card divide-y divide-stone-100">
          {items.map((d) => (
            <DocumentRow key={d.id} treeId={treeId} doc={d} />
          ))}
        </ul>
      )}
      {uploading && (
        <UploadDocumentDialog
          initialCategory="title_deed"
          categories={PROPERTY_DOCUMENT_CATEGORIES}
          linkTarget={{ type: "property", id: p.id, label: p.display_name }}
          onClose={() => setUploading(false)}
        />
      )}
    </section>
  );
}

function EditPropertyDialog({ p, onClose }: { p: PropertyDetailOut; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const update = useUpdateProperty(treeId, p.id);
  const [d, setD] = useState({
    display_name: p.display_name,
    property_type: p.property_type,
    classification: p.classification,
    privacy_level: p.privacy_level,
    address_text: p.address_text ?? "",
    current_status: p.current_status ?? "",
    description: p.description ?? "",
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!d.display_name.trim()) return;
    update.mutate(
      {
        display_name: d.display_name.trim(),
        property_type: d.property_type,
        classification: d.classification,
        privacy_level: d.privacy_level,
        address_text: d.address_text.trim() || null,
        current_status: d.current_status.trim() || null,
        description: d.description.trim() || null,
      },
      { onSuccess: onClose },
    );
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("property.editTitle")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="edit-prop" loading={update.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <form id="edit-prop" onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2" noValidate>
        <Field label={t("property.name")} className="sm:col-span-2">
          {(fp) => <TextInput {...fp} value={d.display_name} onChange={(e) => setD({ ...d, display_name: e.target.value })} />}
        </Field>
        <Field label={t("property.type")}>
          {(fp) => (
            <Select {...fp} value={d.property_type} onChange={(e) => setD({ ...d, property_type: e.target.value as PropertyType })}>
              {PROPERTY_TYPES.map((x) => (
                <option key={x} value={x}>
                  {t(`enum.propertyType.${x}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("property.classification")}>
          {(fp) => (
            <Select {...fp} value={d.classification} onChange={(e) => setD({ ...d, classification: e.target.value as PropertyClassification })}>
              {CLASSIFICATIONS.map((x) => (
                <option key={x} value={x}>
                  {t(`enum.classification.${x}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("privacy.level")}>
          {(fp) => (
            <Select {...fp} value={d.privacy_level} onChange={(e) => setD({ ...d, privacy_level: e.target.value as PrivacyLevel })}>
              {PRIVACY_LEVELS.map((l) => (
                <option key={l} value={l}>
                  {t(`enum.privacy.${l}`)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label={t("property.currentStatus")}>{(fp) => <TextInput {...fp} value={d.current_status} onChange={(e) => setD({ ...d, current_status: e.target.value })} />}</Field>
        <Field label={t("property.address")} className="sm:col-span-2">
          {(fp) => <TextArea {...fp} rows={2} value={d.address_text} onChange={(e) => setD({ ...d, address_text: e.target.value })} />}
        </Field>
        <Field label={t("property.description")} className="sm:col-span-2">
          {(fp) => <TextArea {...fp} rows={2} value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} />}
        </Field>
        <div className="sm:col-span-2">
          <ErrorAlert error={update.error} />
        </div>
      </form>
    </Dialog>
  );
}
