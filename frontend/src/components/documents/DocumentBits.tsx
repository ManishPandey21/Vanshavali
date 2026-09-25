import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { FileText, ShieldAlert, Vault } from "lucide-react";
import type { DocumentOut } from "../../api/types";
import { ApiError } from "../../api/client";
import { formatDate } from "../../lib/dates";
import { formatBytes } from "../../lib/documents";
import { Badge, type Tone } from "../ui/Badge";
import { PrivacyBadge } from "../person/badges";

const statusTone: Record<string, Tone> = {
  completed: "green",
  clean: "green",
  pending: "saffron",
  running: "saffron",
  failed: "red",
  infected: "red",
  error: "red",
  skipped: "stone",
  not_requested: "stone",
};

export function StorageBadge({ doc }: { doc: Pick<DocumentOut, "storage_class"> }) {
  const { t } = useTranslation();
  if (doc.storage_class !== "VAULT") return null;
  return (
    <Badge tone="violet" icon={<Vault className="size-3" aria-hidden />} title={t("documents.vaultHint")}>
      {t("documents.vault")}
    </Badge>
  );
}

/** Scan, preview and OCR/extraction pipeline states. */
export function PipelineBadges({ doc }: { doc: DocumentOut }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex flex-wrap gap-1">
      <Badge tone={statusTone[doc.scan_status] ?? "neutral"} icon={doc.scan_status === "infected" ? <ShieldAlert className="size-3" aria-hidden /> : undefined}>
        {t("documents.scan")}: {t(`enum.scanStatus.${doc.scan_status}`)}
      </Badge>
      {doc.preview_status !== "not_requested" && (
        <Badge tone={statusTone[doc.preview_status] ?? "neutral"}>
          {t("documents.preview")}: {t(`enum.processingStatus.${doc.preview_status}`)}
        </Badge>
      )}
      {doc.ocr_status !== "not_requested" && (
        <Badge tone={statusTone[doc.ocr_status] ?? "neutral"}>
          {t("documents.ocr")}: {t(`enum.processingStatus.${doc.ocr_status}`)}
        </Badge>
      )}
      {(doc.pending_proposals ?? 0) > 0 && <Badge tone="saffron">{t("documents.pendingReview", { count: doc.pending_proposals })}</Badge>}
    </span>
  );
}

export function DocumentRow({ treeId, doc }: { treeId: string; doc: DocumentOut }) {
  const { t, i18n } = useTranslation();
  return (
    <li className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <Link to={`/t/${treeId}/documents/${doc.id}`} className="inline-flex items-center gap-1.5 font-medium text-kumkum-800 hover:underline">
          <FileText className="size-4 shrink-0" aria-hidden />
          {doc.title}
        </Link>
        <p className="text-xs text-ink-muted">
          {t(`enum.docCategory.${doc.category}`)} · {doc.original_filename} · {formatBytes(doc.size_bytes)}
          {doc.document_date ? ` · ${formatDate(doc.document_date, t, i18n.language)}` : ""}
          {doc.deleted_at ? ` · ${t("documents.inRecycleBin")}` : ""}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        <StorageBadge doc={doc} />
        <PrivacyBadge level={doc.privacy_level} />
        <PipelineBadges doc={doc} />
      </div>
    </li>
  );
}

/** Upload errors by code; unknown codes fall back to the server's message. */
export function uploadErrorMessage(err: unknown, t: (k: string, o?: Record<string, unknown>) => string): string | null {
  if (!(err instanceof ApiError)) return null;
  const known = ["malware_detected", "unsupported_type", "duplicate_document", "file_too_large", "empty_file", "encrypted_pdf", "invalid_pdf", "invalid_image", "image_too_large", "too_many_pages", "unsafe_pdf", "invalid_media", "scanner_unavailable", "use_gedcom_import"];
  return known.includes(err.code) ? t(`documents.err.${err.code}`) : null;
}
