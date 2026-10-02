import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { EventMediaOut, PersonOut } from "../../../api/types";
import { usePersonPhotos } from "../../../api/hooks/lifeevents";
import { useDocuments } from "../../../api/hooks/documents";
import { useTreeCtx } from "../../../lib/tree-context";
import { PhotoThumb } from "../../../components/events/PhotoThumb";
import { EmptyState, ErrorAlert, Spinner } from "../../../components/ui/feedback";
import { Dialog } from "../../../components/ui/Dialog";

/** Photos of this person: event albums plus photos tagged with them in the vault. */
export function PhotosTab({ person }: { person: PersonOut }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const albums = usePersonPhotos(treeId, person.id);
  const tagged = useDocuments(treeId, { category: "photo", target_type: "person", target_id: person.id });
  const [open, setOpen] = useState<{ documentId: string; caption: string } | null>(null);
  const inAlbums = new Set((albums.data ?? []).map((m) => m.document_id));
  const others = (tagged.data?.items ?? []).filter((d) => !inAlbums.has(d.id) && d.can_access_content);
  const byEvent = new Map<string, EventMediaOut[]>();
  for (const m of albums.data ?? []) byEvent.set(m.event_id, [...(byEvent.get(m.event_id) ?? []), m]);
  if (albums.isLoading || tagged.isLoading) return <Spinner />;
  return (
    <section aria-labelledby="photos-title" className="space-y-5">
      <h2 id="photos-title" className="font-display text-lg font-semibold">
        {t("photos.title")}
      </h2>
      <ErrorAlert error={albums.error || tagged.error} />
      {byEvent.size === 0 && others.length === 0 && <EmptyState title={t("photos.none")}>{t("photos.personHint")}</EmptyState>}
      {[...byEvent.values()].map((list) => (
        <div key={list[0].event_id}>
          <h3 className="mb-2 text-sm font-semibold text-ink-muted">{list[0].document.title}</h3>
          <Grid items={list.map((m) => ({ id: m.document_id, caption: m.caption || m.document.title }))} onOpen={setOpen} />
        </div>
      ))}
      {others.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink-muted">{t("photos.tagged")}</h3>
          <Grid items={others.map((d) => ({ id: d.id, caption: d.title }))} onOpen={setOpen} />
        </div>
      )}
      {open && (
        <Dialog open onClose={() => setOpen(null)} size="lg" title={open.caption}>
          <PhotoThumb treeId={treeId} documentId={open.documentId} alt={open.caption} variant="preview" className="max-h-[70vh] w-full object-contain" />
          <Link className="mt-2 inline-block text-sm text-kumkum-800 underline" to={`/t/${treeId}/documents/${open.documentId}`}>
            {t("photos.openDocument")}
          </Link>
        </Dialog>
      )}
    </section>
  );
}

function Grid({ items, onOpen }: { items: { id: string; caption: string }[]; onOpen: (v: { documentId: string; caption: string }) => void }) {
  const { treeId } = useTreeCtx();
  return (
    <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {items.map((it) => (
        <li key={it.id}>
          <button type="button" className="block w-full text-left" onClick={() => onOpen({ documentId: it.id, caption: it.caption })}>
            <PhotoThumb treeId={treeId} documentId={it.id} alt={it.caption} className="aspect-square w-full rounded-md" />
            <span className="mt-1 block truncate text-xs">{it.caption}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
