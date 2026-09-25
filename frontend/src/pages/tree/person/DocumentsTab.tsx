import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileBadge, Landmark, Upload } from "lucide-react";
import type { DocumentCategory, PersonOut } from "../../../api/types";
import { useDocuments } from "../../../api/hooks/documents";
import { usePersonPropertyInterests } from "../../../api/hooks/property";
import { useTreeCtx } from "../../../lib/tree-context";
import { Perm } from "../../../lib/permissions";
import { DocumentRow } from "../../../components/documents/DocumentBits";
import { UploadDocumentDialog } from "../../../components/documents/UploadDocumentDialog";
import { Button } from "../../../components/ui/Button";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Badge } from "../../../components/ui/Badge";

export function DocumentsTab({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const navigate = useNavigate();
  const docs = useDocuments(treeId, { target_type: "person", target_id: person.id });
  const [upload, setUpload] = useState<DocumentCategory | null>(null);
  const canUpload = can(Perm.DOCUMENT_UPLOAD);
  const items = docs.data?.items ?? [];
  return (
    <section aria-labelledby="docs-title" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="docs-title" className="font-display text-lg font-semibold">
          {t("documents.aboutThisPerson")}
        </h2>
        {canUpload && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" icon={<FileBadge className="size-4" aria-hidden />} onClick={() => setUpload("birth_certificate")}>
              {t("documents.uploadBirthCertificate")}
            </Button>
            <Button size="sm" variant="secondary" icon={<Upload className="size-4" aria-hidden />} onClick={() => setUpload("other")}>
              {t("documents.upload")}
            </Button>
          </div>
        )}
      </div>
      {docs.isLoading && <Spinner />}
      <ErrorAlert error={docs.error} />
      {docs.data && items.length === 0 && <EmptyState title={t("documents.noneForPerson")}>{t("documents.noneForPersonHint")}</EmptyState>}
      {items.length > 0 && (
        <ul className="card divide-y divide-stone-100">
          {items.map((d) => (
            <DocumentRow key={d.id} treeId={treeId} doc={d} />
          ))}
        </ul>
      )}
      {upload && (
        <UploadDocumentDialog
          initialCategory={upload}
          title={upload === "birth_certificate" ? t("documents.uploadBirthCertificate") : undefined}
          linkTarget={{ type: "person", id: person.id, label: person.display_name }}
          onClose={() => setUpload(null)}
          onUploaded={(d) => navigate(`/t/${treeId}/documents/${d.id}`)}
        />
      )}
    </section>
  );
}

/** Property interests held by this person (only for members who may read the property register). */
export function PropertyInterestsSection({ personId }: { personId: string }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const q = usePersonPropertyInterests(treeId, personId, true);
  return (
    <section aria-labelledby="ppi-title" className="space-y-3">
      <h2 id="ppi-title" className="flex items-center gap-2 font-display text-lg font-semibold">
        <Landmark className="size-5 text-haldi-700" aria-hidden /> {t("property.interestsOfPerson")}
      </h2>
      <p className="rounded-lg border border-haldi-300 bg-haldi-100 px-3 py-2 text-sm font-medium text-haldi-700" role="note">
        {q.data?.legal_notice ?? t("property.legalNoticeFallback")}
      </p>
      {q.isLoading && <Spinner />}
      <ErrorAlert error={q.error} />
      {q.data && (q.data.items ?? []).length === 0 && <p className="text-sm text-ink-muted">{t("property.noInterestsForPerson")}</p>}
      <ul className="space-y-2">
        {(q.data?.items ?? []).map(({ property, interest }) => (
          <li key={interest.id} className="card flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
            <span>
              <Link to={`/t/${treeId}/property/${property.id}`} className="font-medium text-kumkum-800 underline">
                {property.display_name}
              </Link>{" "}
              · {t(`enum.interestType.${interest.interest_type}`)} · <strong>{interest.share}</strong>
              {interest.valid_from_display && <span className="text-ink-muted"> · {t("property.from", { date: interest.valid_from_display })}</span>}
              {interest.valid_to_display && <span className="text-ink-muted"> · {t("property.until", { date: interest.valid_to_display })}</span>}
            </span>
            <span className="flex gap-1">
              <Badge tone={interest.is_current ? "green" : "stone"}>{interest.is_current ? t("property.current") : t("property.ended")}</Badge>
              <Badge tone="neutral">{t(`enum.interestStatus.${interest.status}`)}</Badge>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
