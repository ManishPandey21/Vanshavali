import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Flag, MessageCircle, Network, Route, Trash2 } from "lucide-react";
import { useMe } from "../../../api/hooks/auth";
import { useDeletePerson, usePerson, usePersonEvents } from "../../../api/hooks/people";
import { useRequestClaim } from "../../../api/hooks/heritage";
import { useTreeCtx } from "../../../lib/tree-context";
import { Perm } from "../../../lib/permissions";
import { dirOfText, langOfText, nativeScriptNames, nameText } from "../../../lib/names";
import { forgetPerson, rememberPerson } from "../../../lib/recent";
import { PersonBadges, PrivacyBadge, RedactionNotice } from "../../../components/person/badges";
import { DateText } from "../../../components/dates/DateText";
import { HeritageProfile } from "../../../components/heritage/HeritageProfile";
import { CitationList } from "../../../components/evidence/Citations";
import { Button, ButtonLink } from "../../../components/ui/Button";
import { ConfirmDialog, Dialog } from "../../../components/ui/Dialog";
import { ErrorAlert, LiveRegion, Spinner } from "../../../components/ui/feedback";
import { Field, TextArea } from "../../../components/ui/form";
import { Tabs } from "../../../components/ui/Tabs";
import { Badge } from "../../../components/ui/Badge";
import { OverviewTab } from "./OverviewTab";
import { TimelineTab } from "./TimelineTab";
import { FamilyTab } from "./FamilyTab";
import { HouseholdsTab } from "./HouseholdsTab";
import { PrivacyTab } from "./PrivacyTab";
import { AstrologyTab } from "./AstrologyTab";
import { DocumentsTab, PropertyInterestsSection } from "./DocumentsTab";
import { ApiError } from "../../../api/client";
import { ClaimInviteDialog } from "../../../components/consent/ClaimInviteShare";

const TABS = ["overview", "family", "timeline", "heritage", "documents", "astrology", "property", "sources", "households", "privacy"] as const;
type TabId = (typeof TABS)[number];

export function PersonProfilePage() {
  const { personId = "" } = useParams();
  const { t } = useTranslation();
  const { treeId, can, isAdmin } = useTreeCtx();
  const me = useMe();
  const person = usePerson(treeId, personId);
  const [params, setParams] = useSearchParams();
  const tab = (TABS as readonly string[]).includes(params.get("tab") ?? "") ? (params.get("tab") as TabId) : "overview";
  const [claimOpen, setClaimOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const del = useDeletePerson(treeId);
  const navigate = useNavigate();

  useEffect(() => {
    if (person.data) rememberPerson(treeId, person.data.id);
    if (person.error instanceof ApiError && person.error.status === 404) forgetPerson(treeId, personId);
  }, [person.data, person.error, treeId, personId]);

  if (person.isLoading) return <Spinner />;
  if (person.error || !person.data) return <ErrorAlert error={person.error} />;
  const p = person.data;
  const isClaimant = !!me.data && p.claimed_by_user_id === me.data.id;
  const canPrivacy = can(Perm.PRIVACY_MANAGE) || isClaimant;
  const native = nativeScriptNames(p.names);
  const canProperty = can(Perm.PROPERTY_READ) || can(Perm.PROPERTY_WRITE);
  const visibleTabs = TABS.filter((id) => (id !== "privacy" || canPrivacy) && (id !== "property" || canProperty));
  const redacted = p.redacted_fields ?? [];

  return (
    <article aria-labelledby="person-name">
      <header className="mb-5 rounded-2xl border border-stone-200 bg-gradient-to-br from-white to-kumkum-50 p-4 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 id="person-name" lang={langOfText(p.display_name)} dir={dirOfText(p.display_name)} className="font-display text-2xl font-bold sm:text-3xl">
              {p.display_name}
            </h1>
            {native.length > 0 && (
              <p className="mt-1 flex flex-wrap gap-x-3 text-lg text-ink">
                {native.map((n) => (
                  <span key={n.id} lang={n.language ?? undefined} dir={n.script === "Arab" ? "rtl" : undefined}>
                    {nameText(n)}
                  </span>
                ))}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <PersonBadges person={p} />
              {p.privacy_level && <PrivacyBadge level={p.privacy_level} />}
              {p.claimed_by_user_id && <Badge tone="green">{isClaimant ? t("claim.yours") : t("claim.claimed")}</Badge>}
            </div>
            <p className="mt-2 text-sm text-ink-muted">
              {p.birth?.date ? (
                <>
                  {t("person.born")} <DateText date={p.birth.date} showOriginal={false} />
                </>
              ) : null}
              {p.death?.date ? (
                <>
                  {" · "}
                  {t("person.died")} <DateText date={p.death.date} showOriginal={false} />
                </>
              ) : null}
            </p>
            {redacted.length > 0 && (
              <p className="mt-1">
                <RedactionNotice label={t("privacy.someHidden", { count: redacted.length })} />
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <ButtonLink to={`/t/${treeId}/tree/${p.id}`} variant="secondary" size="sm" icon={<Network className="size-4" aria-hidden />}>
              {t("person.viewInTree")}
            </ButtonLink>
            <ButtonLink to={`/t/${treeId}/relationship?from=${p.id}`} variant="secondary" size="sm" icon={<Route className="size-4" aria-hidden />}>
              {t("person.howRelated")}
            </ButtonLink>
            {!p.claimed_by_user_id && (
              <Button variant="secondary" size="sm" icon={<Flag className="size-4" aria-hidden />} onClick={() => setClaimOpen(true)}>
                {t("claim.button")}
              </Button>
            )}
            {/* Hint only: the server re-checks write access, living status and age (ADR-0011). */}
            {!p.claimed_by_user_id && p.can_edit && p.profile_status !== "deceased" && (
              <Button variant="secondary" size="sm" icon={<MessageCircle className="size-4" aria-hidden />} onClick={() => setInviteOpen(true)}>
                {t("claimInvite.button")}
              </Button>
            )}
            {p.can_edit && (
              <Button variant="ghost" size="sm" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setDeleting(true)}>
                {t("person.remove")}
              </Button>
            )}
          </div>
        </div>
      </header>

      <Tabs
        label={t("person.sections")}
        tabs={visibleTabs.map((id) => ({ id, label: t(`person.tab.${id}`) }))}
        active={tab}
        onChange={(id) => {
          const next = new URLSearchParams(params);
          next.set("tab", id);
          setParams(next, { replace: true });
        }}
      >
        {tab === "overview" && <OverviewTab person={p} />}
        {tab === "family" && <FamilyTab person={p} />}
        {tab === "timeline" && <TimelineTab person={p} />}
        {tab === "heritage" && <HeritageProfile subject={{ kind: "person", id: p.id }} canWrite={can(Perm.ASSERTION_WRITE)} />}
        {tab === "documents" && <DocumentsTab person={p} />}
        {tab === "astrology" && <AstrologyTab person={p} />}
        {tab === "property" && canProperty && <PropertyInterestsSection personId={p.id} />}
        {tab === "sources" && <SourcesTab personId={p.id} canEdit={!!p.can_edit} />}
        {tab === "households" && <HouseholdsTab person={p} />}
        {tab === "privacy" && canPrivacy && <PrivacyTab person={p} isClaimant={isClaimant} />}
      </Tabs>

      {inviteOpen && <ClaimInviteDialog treeId={treeId} personId={p.id} personName={p.display_name} canOfferContributor={isAdmin} onClose={() => setInviteOpen(false)} />}
      {claimOpen && <ClaimDialog personId={p.id} name={p.display_name} onClose={() => setClaimOpen(false)} />}
      <ConfirmDialog
        open={deleting}
        onClose={() => setDeleting(false)}
        title={t("person.removeTitle", { name: p.display_name })}
        body={isAdmin ? t("person.removeBodyAdmin") : t("person.removeBody")}
        confirmLabel={t("person.remove")}
        danger
        loading={del.isPending}
        onConfirm={() =>
          del.mutate(p.id, {
            onSuccess: () => {
              forgetPerson(treeId, p.id);
              navigate(`/t/${treeId}/people`);
            },
          })
        }
      >
        <ErrorAlert error={del.error} />
      </ConfirmDialog>
    </article>
  );
}

function SourcesTab({ personId, canEdit }: { personId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const events = usePersonEvents(treeId, personId);
  return (
    <section aria-labelledby="src-title" className="space-y-4">
      <h2 id="src-title" className="font-display text-lg font-semibold">
        {t("citations.forPerson")}
      </h2>
      <CitationList targetType="person" targetId={personId} canEditTarget={canEdit} />
      <h3 className="font-display font-semibold">{t("citations.forEvents")}</h3>
      {events.isLoading && <Spinner />}
      <ul className="space-y-3">
        {events.data?.map((e) => (
          <li key={e.id} className="card p-3">
            <p className="text-sm font-semibold">
              {t(`enum.eventType.${e.type}`)}
              {e.date && (
                <span className="ml-2 font-normal text-ink-muted">
                  <DateText date={e.date} showOriginal={false} />
                </span>
              )}
            </p>
            <CitationList targetType="event" targetId={e.id} canEditTarget={canEdit} />
          </li>
        ))}
      </ul>
      <Link to={`/t/${treeId}/sources`} className="text-sm text-kumkum-800 underline">
        {t("sources.manage")}
      </Link>
    </section>
  );
}

function ClaimDialog({ personId, name, onClose }: { personId: string; name: string; onClose: () => void }) {
  const { t } = useTranslation();
  const { treeId } = useTreeCtx();
  const claim = useRequestClaim(treeId, personId);
  const [message, setMessage] = useState("");
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("claim.title", { name })}
      description={t("claim.description")}
      footer={
        claim.isSuccess ? (
          <Button onClick={onClose}>{t("common.close")}</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button loading={claim.isPending} onClick={() => claim.mutate(message)}>
              {t("claim.submit")}
            </Button>
          </>
        )
      }
    >
      {claim.isSuccess ? (
        <p role="status" className="text-sm">
          {t("claim.submitted")}
        </p>
      ) : (
        <div className="space-y-3">
          <Field label={t("claim.message")} hint={t("claim.messageHint")}>
            {(p) => <TextArea {...p} value={message} onChange={(e) => setMessage(e.target.value)} />}
          </Field>
          <ErrorAlert error={claim.error} />
        </div>
      )}
      <LiveRegion message={claim.isSuccess ? t("claim.submitted") : ""} />
    </Dialog>
  );
}
