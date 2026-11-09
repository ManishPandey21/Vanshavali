import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Images, Plus, Star, Trash2 } from "lucide-react";
import type { RecordPrivacyLevel, SharingOut, SharingUpdate } from "../../api/types";
import { api } from "../../api/client";
import { useAddCollectionItems, useCollection, useCollections, useCreateCollection, useDeleteCollection, useRemoveCollectionItem, useUpdateCollectionItem } from "../../api/hooks/collections";
import { useDocuments } from "../../api/hooks/documents";
import { useMembers } from "../../api/hooks/trees";
import { useBranches } from "../../api/hooks/family";
import { useMe } from "../../api/hooks/auth";
import { useTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { PhotoThumb } from "../../components/events/PhotoThumb";
import { RecordPrivacyBadge } from "../../components/person/badges";
import { RecordSharingPanel } from "../../components/privacy/RecordSharingPanel";
import { VisibilitySharing, draftProblem, type SharingDraft } from "../../components/privacy/VisibilitySharing";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { ConfirmDialog, Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorAlert, LiveRegion, PageHeader, Spinner } from "../../components/ui/feedback";
import { Checkbox, Field, TextArea, TextInput } from "../../components/ui/form";

/** Standalone photo collections (ADR-0027 §6): shareable on their own; each photo keeps its own audience. */
export function CollectionsPage() {
  const { t } = useTranslation();
  const { treeId, can } = useTreeCtx();
  const list = useCollections(treeId);
  const navigate = useNavigate();
  const [adding, setAdding] = useState(false);
  return (
    <div>
      <PageHeader
        title={t("collections.title")}
        subtitle={t("collections.subtitle")}
        actions={
          can(Perm.DOCUMENT_UPLOAD) && (
            <Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setAdding(true)}>
              {t("collections.new")}
            </Button>
          )
        }
      />
      {list.isLoading && <Spinner />}
      <ErrorAlert error={list.error} />
      {list.data && list.data.length === 0 && <EmptyState icon={<Images className="size-6" aria-hidden />} title={t("collections.none")}>{t("collections.noneHint")}</EmptyState>}
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label={t("collections.title")}>
        {list.data?.map((c) => (
          <li key={c.id} className="card overflow-hidden">
            <Link to={`/t/${treeId}/collections/${c.id}`} className="block">
              {c.cover_document_id ? (
                <PhotoThumb treeId={treeId} documentId={c.cover_document_id} alt={c.title} className="aspect-[4/3] w-full" />
              ) : (
                <div className="flex aspect-[4/3] w-full items-center justify-center bg-parchment-deep text-ink-muted">
                  <Images className="size-8" aria-hidden />
                </div>
              )}
              <div className="space-y-1 p-3">
                <h2 className="font-display text-base font-semibold">{c.title}</h2>
                <p className="flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
                  <RecordPrivacyBadge level={c.privacy_level} />
                  {t("collections.photoCount", { count: c.item_count })}
                </p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {adding && <NewCollectionDialog onClose={() => setAdding(false)} onCreated={(id) => navigate(`/t/${treeId}/collections/${id}`)} />}
    </div>
  );
}

function NewCollectionDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const create = useCreateCollection(treeId);
  const members = useMembers(treeId);
  const branches = useBranches(treeId);
  const me = useMe();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [sharing, setSharing] = useState<SharingDraft>({ privacy_level: "ONLY_ME", audience_branch_id: null, allow_download: false, members: [] });
  const [submitted, setSubmitted] = useState(false);
  const [shareError, setShareError] = useState<unknown>(null);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!title.trim() || draftProblem(sharing)) return;
    setShareError(null);
    const level: RecordPrivacyLevel = sharing.privacy_level === "SELECTED_MEMBERS" ? "ONLY_ME" : sharing.privacy_level; // members are attached next
    create.mutate(
      { title: title.trim(), description: description.trim() || null, privacy_level: level, audience_branch_id: sharing.privacy_level === "FAMILY_BRANCH" ? sharing.audience_branch_id : null },
      {
        onSuccess: async (c) => {
          if (sharing.privacy_level === "SELECTED_MEMBERS") {
            const body: SharingUpdate = { privacy_level: "SELECTED_MEMBERS", allow_download: false, members: sharing.members, confirm_wider: true };
            try {
              await api.put<SharingOut>(`/trees/${treeId}/collections/${c.id}/sharing`, body);
            } catch (err) {
              setShareError(err); // stays Only me: safe; the owner can share it from its page
              return;
            }
          }
          onCreated(c.id);
        },
      },
    );
  };
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={t("collections.newTitle")}
      description={t("collections.newIntro")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" form="collection-form" loading={create.isPending}>
            {t("collections.create")}
          </Button>
        </>
      }
    >
      <form id="collection-form" onSubmit={submit} className="space-y-3" noValidate>
        <Field label={t("collections.name")} required error={submitted && !title.trim() ? t("common.required") : null}>
          {(p) => <TextInput {...p} value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} />}
        </Field>
        <Field label={t("collections.description")}>{(p) => <TextArea {...p} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
        <fieldset className="space-y-2 rounded-lg border border-stone-200 p-3">
          <legend className="px-1 text-sm font-semibold">{t("sharing.title")}</legend>
          <p className="text-xs text-ink-muted">{t("collections.photosKeepTheirOwn")}</p>
          <VisibilitySharing
            value={sharing}
            onChange={setSharing}
            members={members.data ?? []}
            branches={branches.data ?? []}
            ownMembershipId={members.data?.find((m) => m.user_id === me.data?.id)?.id ?? null}
            downloads={false}
            showProblems={submitted}
          />
        </fieldset>
        <ErrorAlert error={create.error || shareError} />
      </form>
    </Dialog>
  );
}

export function CollectionDetailPage() {
  const { t } = useTranslation();
  const { collectionId = "" } = useParams();
  const { treeId } = useTreeCtx();
  const navigate = useNavigate();
  const col = useCollection(treeId, collectionId);
  const update = useUpdateCollectionItem(treeId, collectionId);
  const remove = useRemoveCollectionItem(treeId, collectionId);
  const del = useDeleteCollection(treeId);
  const [picking, setPicking] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [status, setStatus] = useState("");
  if (col.isLoading) return <Spinner />;
  if (!col.data) return <ErrorAlert error={col.error} />;
  const c = col.data;
  const items = c.items ?? [];
  return (
    <article className="mx-auto max-w-5xl" aria-labelledby="collection-title">
      <p className="mb-2 text-sm">
        <Link to={`/t/${treeId}/collections`} className="text-kumkum-800 underline">
          {t("collections.back")}
        </Link>
      </p>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 id="collection-title" className="font-display text-2xl font-bold">
            {c.title}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-1.5 text-sm text-ink-muted">
            <RecordPrivacyBadge level={c.privacy_level} />
            {t("collections.photoCount", { count: c.item_count })}
          </p>
          {c.description && <p className="mt-2 text-sm">{c.description}</p>}
        </div>
        {c.is_owner && (
          <div className="flex flex-wrap gap-2">
            <Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setPicking(true)}>
              {t("collections.addPhotos")}
            </Button>
            <Button variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setConfirm(true)}>
              {t("common.delete")}
            </Button>
          </div>
        )}
      </header>
      {c.is_owner && (c.items_not_shared ?? 0) > 0 && (
        <p className="mb-3 flex items-start gap-2 rounded-lg bg-haldi-100 p-3 text-sm text-haldi-700" role="note">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {t("collections.notSharedWarning", { count: c.items_not_shared ?? 0 })}
        </p>
      )}
      <ErrorAlert error={update.error || remove.error} />
      {items.length === 0 ? (
        <EmptyState icon={<Images className="size-6" aria-hidden />} title={t("collections.empty")}>{c.is_owner ? t("collections.emptyHint") : null}</EmptyState>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" aria-label={t("collections.photos")}>
          {items.map((i) => (
            <li key={i.id} className="card overflow-hidden">
              <Link to={`/t/${treeId}/documents/${i.document_id}`}>
                <PhotoThumb treeId={treeId} documentId={i.document_id} alt={i.caption || i.document.title} className="aspect-square w-full" />
              </Link>
              <div className="space-y-1 p-2 text-sm">
                <p className="truncate font-medium">{i.caption || i.document.title}</p>
                <span className="flex flex-wrap items-center gap-1">
                  <RecordPrivacyBadge level={i.document.privacy_level} />
                  {i.is_cover && (
                    <Badge tone="saffron" icon={<Star className="size-3" aria-hidden />}>
                      {t("photos.cover")}
                    </Badge>
                  )}
                </span>
                {i.shared_with_collection_audience === false && <p className="text-xs text-haldi-700">{t("collections.notSharedItem")}</p>}
                {c.is_owner && (
                  <div className="flex gap-1 pt-1">
                    {!i.is_cover && (
                      <Button size="sm" variant="ghost" onClick={() => update.mutate({ itemId: i.id, body: { is_cover: true } }, { onSuccess: () => setStatus(t("photos.coverSet")) })}>
                        {t("photos.makeCover")}
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => remove.mutate(i.id, { onSuccess: () => setStatus(t("collections.removed")) })} aria-label={t("collections.remove", { name: i.caption || i.document.title })}>
                      <Trash2 className="size-3.5" aria-hidden />
                    </Button>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <LiveRegion message={status} />
      {c.can_edit_sharing && (
        <div className="mt-6">
          <RecordSharingPanel path={`collections/${c.id}`} downloads={false} />
        </div>
      )}
      {picking && <PhotoPicker collectionId={c.id} existing={new Set(items.map((i) => i.document_id))} onClose={() => setPicking(false)} onAdded={(n) => setStatus(t("collections.added", { count: n }))} />}
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={t("collections.deleteTitle")}
        body={t("collections.deleteBody")}
        confirmLabel={t("common.delete")}
        danger
        loading={del.isPending}
        onConfirm={() => del.mutate(c.id, { onSuccess: () => navigate(`/t/${treeId}/collections`) })}
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </article>
  );
}

/** Pick photos the owner can see. Adding a photo never changes who can see it. */
function PhotoPicker({ collectionId, existing, onClose, onAdded }: { collectionId: string; existing: Set<string>; onClose: () => void; onAdded: (n: number) => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const photos = useDocuments(treeId, { category: "photo" });
  const add = useAddCollectionItems(treeId, collectionId);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const candidates = (photos.data?.items ?? []).filter((d) => !existing.has(d.id) && d.mime_type.startsWith("image/"));
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={t("collections.addPhotos")}
      description={t("collections.photosKeepTheirOwn")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button disabled={chosen.size === 0} loading={add.isPending} onClick={() => add.mutate([...chosen], { onSuccess: () => { onAdded(chosen.size); onClose(); } })}>
            {t("collections.addChosen", { count: chosen.size })}
          </Button>
        </>
      }
    >
      {photos.isLoading && <Spinner />}
      <ErrorAlert error={photos.error || add.error} />
      {candidates.length === 0 && !photos.isLoading && <p className="text-sm text-ink-muted">{t("collections.noPhotosToAdd")}</p>}
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3" aria-label={t("collections.photosToAdd")}>
        {candidates.map((d) => (
          <li key={d.id} className="rounded-lg border border-stone-200 p-1.5">
            <PhotoThumb treeId={treeId} documentId={d.id} alt={d.title} className="aspect-square w-full rounded" />
            <Checkbox
              label={<span className="truncate">{d.title}</span>}
              checked={chosen.has(d.id)}
              onChange={(v) => {
                const next = new Set(chosen);
                if (v) next.add(d.id);
                else next.delete(d.id);
                setChosen(next);
              }}
            />
            <RecordPrivacyBadge level={d.privacy_level} />
          </li>
        ))}
      </ul>
    </Dialog>
  );
}
