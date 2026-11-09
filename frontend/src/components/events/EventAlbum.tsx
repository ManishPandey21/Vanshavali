import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Star, Trash2, Upload, X } from "lucide-react";
import type { EventOut, PersonSummary, SharingOut, SharingUpdate } from "../../api/types";
import { useEventMedia, useRemoveEventMedia, useUpdateEventMedia, useUploadEventPhoto } from "../../api/hooks/lifeevents";
import { eventLabel } from "../../lib/lifeEvents";
import { PersonPicker } from "../pickers";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { EmptyState, ErrorAlert, LiveRegion, Spinner } from "../ui/feedback";
import { Checkbox, Field, TextInput } from "../ui/form";
import { Badge } from "../ui/Badge";
import { PhotoThumb } from "./PhotoThumb";
import { RecordPrivacyBadge } from "../person/badges";
import { VisibilitySharing, draftProblem, type SharingDraft } from "../privacy/VisibilitySharing";
import { api } from "../../api/client";
import { useMembers } from "../../api/hooks/trees";
import { useBranches } from "../../api/hooks/family";
import { useMe } from "../../api/hooks/auth";
import { uploadErrorMessage } from "../documents/DocumentBits";

/** An event's photo album: cover, captions, people in the photo, uploads (privacy inherited). */
export function EventAlbum({ treeId, event, canEdit, onClose }: { treeId: string; event: EventOut; canEdit: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const media = useEventMedia(treeId, event.id);
  const update = useUpdateEventMedia(treeId, event.id);
  const remove = useRemoveEventMedia(treeId, event.id);
  const [status, setStatus] = useState("");
  const label = eventLabel(event, t);
  return (
    <Dialog open onClose={onClose} size="lg" title={t("photos.albumTitle", { event: label })} description={t("photos.albumHint")}>
      <div className="space-y-4">
        {media.isLoading && <Spinner />}
        <ErrorAlert error={media.error || update.error || remove.error} />
        {media.data && media.data.length === 0 && <EmptyState title={t("photos.none")}>{canEdit ? t("photos.noneHint") : null}</EmptyState>}
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3" aria-label={t("photos.listLabel")}>
          {media.data?.map((m) => (
            <li key={m.id} className="card overflow-hidden">
              <PhotoThumb treeId={treeId} documentId={m.document_id} alt={m.caption || t("photos.untitled")} className="aspect-[4/3] w-full" />
              <div className="space-y-1 p-2 text-sm">
                <div className="flex items-center justify-between gap-1">
                  <span className="font-medium">{m.caption || t("photos.untitled")}</span>
                  {m.is_cover && (
                    <Badge tone="saffron" icon={<Star className="size-3" aria-hidden />}>
                      {t("photos.cover")}
                    </Badge>
                  )}
                </div>
                <span className="flex flex-wrap items-center gap-1">
                  <RecordPrivacyBadge level={m.document.privacy_level} />
                  {m.document.can_edit_sharing && (
                    <Link className="text-xs text-kumkum-800 underline" to={`/t/${treeId}/documents/${m.document_id}`}>
                      {t("photos.whoCanSee")}
                    </Link>
                  )}
                </span>
                {m.taken_date_display && <p className="text-xs text-ink-muted">{m.taken_date_display}</p>}
                {(m.people ?? []).length > 0 && <p className="text-xs text-ink-muted">{t("photos.inPhoto")}: {(m.people ?? []).map((p) => p.display_name).join(", ")}</p>}
                {canEdit && (
                  <div className="flex gap-1 pt-1">
                    {!m.is_cover && (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Star className="size-3.5" aria-hidden />}
                        onClick={() => update.mutate({ id: m.id, body: { is_cover: true } }, { onSuccess: () => setStatus(t("photos.coverSet")) })}
                      >
                        {t("photos.makeCover")}
                      </Button>
                    )}
                    <button
                      type="button"
                      className="rounded p-1.5 text-red-800 hover:bg-red-50"
                      aria-label={t("photos.remove", { name: m.caption || t("photos.untitled") })}
                      onClick={() => remove.mutate(m.id, { onSuccess: () => setStatus(t("photos.removed")) })}
                    >
                      <Trash2 className="size-4" aria-hidden />
                    </button>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
        {canEdit && <UploadPhotoForm treeId={treeId} event={event} onDone={() => setStatus(t("photos.uploaded"))} />}
        <LiveRegion message={status} />
      </div>
    </Dialog>
  );
}

function UploadPhotoForm({ treeId, event, onDone }: { treeId: string; event: EventOut; onDone: () => void }) {
  const { t } = useTranslation();
  const upload = useUploadEventPhoto(treeId, event.id);
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [year, setYear] = useState("");
  const [cover, setCover] = useState(false);
  const [people, setPeople] = useState<PersonSummary[]>([]);
  const [picker, setPicker] = useState<PersonSummary | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [choose, setChoose] = useState(false);
  const [sharing, setSharing] = useState<SharingDraft>({ privacy_level: "ONLY_ME", audience_branch_id: null, allow_download: false, members: [] });
  const [shareError, setShareError] = useState<unknown>(null);
  const members = useMembers(treeId);
  const branches = useBranches(treeId);
  const me = useMe();
  const sharingProblem = choose ? draftProblem(sharing) : null;
  const yearNum = year.trim() ? Number(year) : null;
  const yearErr = year.trim() && (!Number.isInteger(yearNum) || (yearNum ?? 0) < 1 || (yearNum ?? 0) > 9999);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (!file || yearErr || sharingProblem) return;
    setShareError(null);
    upload.mutate(
      {
        file,
        caption: caption.trim(),
        takenYear: yearNum,
        isCover: cover,
        personIds: people.map((p) => p.id),
        ...(choose
          ? {
              // Selected members are attached right after the upload; until then it is Only me
              privacyLevel: sharing.privacy_level === "SELECTED_MEMBERS" ? "ONLY_ME" : sharing.privacy_level,
              audienceBranchId: sharing.privacy_level === "FAMILY_BRANCH" ? sharing.audience_branch_id : null,
              allowDownload: sharing.allow_download,
            }
          : {}),
      },
      {
        onSuccess: async (m) => {
          if (choose && sharing.privacy_level === "SELECTED_MEMBERS") {
            const body: SharingUpdate = { privacy_level: "SELECTED_MEMBERS", allow_download: false, members: sharing.members, confirm_wider: true };
            try {
              await api.put<SharingOut>(`/trees/${treeId}/documents/${m.document_id}/sharing`, body);
            } catch (e) {
              setShareError(e); // the photo stays Only me: safe; its owner can share it from its page
              return;
            }
          }
          setChoose(false);
          setFile(null);
          setCaption("");
          setYear("");
          setCover(false);
          setPeople([]);
          setSubmitted(false);
          if (fileRef.current) fileRef.current.value = "";
          onDone();
        },
      },
    );
  };
  const err = uploadErrorMessage(upload.error, t);
  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-dashed border-stone-300 p-3" aria-labelledby="upload-photo-title" noValidate>
      <h3 id="upload-photo-title" className="font-semibold">
        {t("photos.add")}
      </h3>
      <Field label={t("photos.file")} hint={t("photos.fileHint")} required error={submitted && !file ? t("common.required") : null}>
        {(p) => <input {...p} ref={fileRef} type="file" accept="image/*" className="block w-full text-sm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />}
      </Field>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_8rem]">
        <Field label={t("photos.caption")}>{(p) => <TextInput {...p} value={caption} maxLength={500} onChange={(e) => setCaption(e.target.value)} />}</Field>
        <Field label={t("photos.year")} error={submitted && yearErr ? t("photos.yearError") : null}>
          {(p) => <TextInput {...p} inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} />}
        </Field>
      </div>
      <div className="space-y-2">
        <PersonPicker
          treeId={treeId}
          label={t("photos.tagPerson")}
          value={picker}
          onChange={(p) => {
            if (p && !people.some((x) => x.id === p.id)) setPeople([...people, p]);
            setPicker(null);
          }}
        />
        {people.length > 0 && (
          <ul className="flex flex-wrap gap-1" aria-label={t("photos.inPhoto")}>
            {people.map((p) => (
              <li key={p.id}>
                <span className="inline-flex items-center gap-1 rounded-full bg-parchment-deep px-2 py-0.5 text-sm">
                  {p.display_name}
                  <button type="button" onClick={() => setPeople(people.filter((x) => x.id !== p.id))} aria-label={t("photos.untag", { name: p.display_name })}>
                    <X className="size-3.5" aria-hidden />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <Checkbox label={t("photos.setCover")} checked={cover} onChange={setCover} />
      <p className="text-xs text-ink-muted">{t("photos.privacyInherited")}</p>
      <Checkbox label={t("photos.chooseAudience")} checked={choose} onChange={setChoose} />
      {choose && (
        <VisibilitySharing
          value={sharing}
          onChange={setSharing}
          members={members.data ?? []}
          branches={branches.data ?? []}
          ownMembershipId={members.data?.find((x) => x.user_id === me.data?.id)?.id ?? null}
          showProblems={submitted}
        />
      )}
      {err ? <p role="alert" className="text-sm text-red-800">{err}</p> : <ErrorAlert error={upload.error || shareError} />}
      <Button type="submit" icon={<Upload className="size-4" aria-hidden />} loading={upload.isPending}>
        {t("photos.upload")}
      </Button>
    </form>
  );
}
