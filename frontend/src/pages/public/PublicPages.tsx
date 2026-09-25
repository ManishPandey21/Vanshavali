import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Globe2 } from "lucide-react";
import type { RelatedPerson } from "../../api/types";
import { usePublicAncestors, usePublicFamily, usePublicPeople, usePublicPerson, usePublicTree } from "../../api/hooks/family";
import { nativeScriptNames, nameText } from "../../lib/names";
import { BrandMark } from "../../components/layout/AppShell";
import { LanguageSwitcher } from "../../components/layout/LanguageSwitcher";
import { DateText } from "../../components/dates/DateText";
import { PrivatePersonPlaceholder, RelTypeBadge, StatusBadge } from "../../components/person/badges";
import { TreeList } from "../../components/tree/TreeList";
import { EmptyState, ErrorAlert, Spinner } from "../../components/ui/feedback";
import type { ReactNode } from "react";
import { lifespan } from "../../lib/dates";

function PublicFrame({ slug, title, children }: { slug: string; title?: string; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="min-h-dvh">
      <header className="border-b border-stone-200 bg-white/80">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
          <BrandMark to={`/p/${slug}`} />
          <LanguageSwitcher />
        </div>
      </header>
      <main id="main" className="mx-auto max-w-5xl px-4 py-6">
        <p className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-leaf-50 px-3 py-1 text-xs text-leaf-700">
          <Globe2 className="size-3.5" aria-hidden /> {t("public.banner")}
        </p>
        {title && <h1 className="mb-4 font-display text-3xl font-bold">{title}</h1>}
        {children}
      </main>
    </div>
  );
}

export function PublicTreePage() {
  const { slug = "" } = useParams();
  const { t } = useTranslation();
  const tree = usePublicTree(slug);
  const people = usePublicPeople(slug);
  if (tree.isLoading) return <Spinner />;
  if (tree.error || !tree.data)
    return (
      <PublicFrame slug={slug}>
        <ErrorAlert error={tree.error} />
      </PublicFrame>
    );
  return (
    <PublicFrame slug={slug} title={tree.data.name}>
      {tree.data.description && <p className="mb-4 text-ink-muted">{tree.data.description}</p>}
      <p className="mb-4 text-sm text-ink-muted">{t("public.deceasedOnly")}</p>
      {people.isLoading && <Spinner />}
      <ErrorAlert error={people.error} />
      {people.data?.items.length === 0 && <EmptyState title={t("public.noPeople")} />}
      <ul className="card divide-y divide-stone-100">
        {people.data?.items.map((p) => (
          <li key={p.id} className="flex items-center justify-between px-4 py-2">
            <Link to={`/p/${slug}/people/${p.id}`} className="font-medium text-kumkum-800 hover:underline">
              {p.display_name}
            </Link>
            <span className="text-xs text-ink-muted">
              {lifespan(p, t)}
            </span>
          </li>
        ))}
      </ul>
    </PublicFrame>
  );
}

function PublicRelative({ slug, rel }: { slug: string; rel: RelatedPerson }) {
  return (
    <li className="flex flex-wrap items-center gap-2 py-1.5 text-sm">
      {rel.person ? (
        <Link to={`/p/${slug}/people/${rel.person.id}`} className="font-medium text-kumkum-800 hover:underline">
          {rel.person.display_name}
        </Link>
      ) : (
        <PrivatePersonPlaceholder />
      )}
      {rel.relationship_type && <RelTypeBadge type={rel.relationship_type} />}
    </li>
  );
}

export function PublicPersonPage() {
  const { slug = "", personId = "" } = useParams();
  const { t } = useTranslation();
  const person = usePublicPerson(slug, personId);
  const family = usePublicFamily(slug, personId);
  const ancestors = usePublicAncestors(slug, personId, 4);
  if (person.isLoading) return <Spinner />;
  if (person.error || !person.data)
    return (
      <PublicFrame slug={slug}>
        <ErrorAlert error={person.error} />
        <Link to={`/p/${slug}`} className="text-kumkum-800 underline">
          {t("public.back")}
        </Link>
      </PublicFrame>
    );
  const p = person.data;
  const native = nativeScriptNames(p.names);
  return (
    <PublicFrame slug={slug}>
      <Link to={`/p/${slug}`} className="text-sm text-kumkum-800 underline">
        ← {t("public.back")}
      </Link>
      <h1 className="mt-2 font-display text-3xl font-bold">{p.display_name}</h1>
      {native.length > 0 && (
        <p className="text-lg">
          {native.map((n) => (
            <span key={n.id} lang={n.language ?? undefined} className="mr-3">
              {nameText(n)}
            </span>
          ))}
        </p>
      )}
      <div className="mt-2">
        <StatusBadge status={p.profile_status} />
      </div>
      <dl className="card mt-4 grid grid-cols-1 gap-2 p-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs font-semibold uppercase text-ink-muted">{t("person.birthDate")}</dt>
          <dd>{p.birth?.date ? <DateText date={p.birth.date} /> : t("person.notRecorded")}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-ink-muted">{t("person.deathDate")}</dt>
          <dd>{p.death?.date ? <DateText date={p.death.date} /> : t("person.notRecorded")}</dd>
        </div>
      </dl>
      {family.data && (
        <section className="card mt-4 p-4" aria-labelledby="pub-fam">
          <h2 id="pub-fam" className="font-display text-lg font-semibold">
            {t("family.title")}
          </h2>
          <h3 className="mt-2 text-xs font-semibold uppercase text-ink-muted">{t("family.parents")}</h3>
          <ul>{family.data.parents.map((r, i) => <PublicRelative key={i} slug={slug} rel={r} />)}</ul>
          {family.data.unions.map((u, i) => (
            <div key={u.relationship?.id ?? `hidden-${i}`} className="mt-2">
              <h3 className="text-xs font-semibold uppercase text-ink-muted">{u.relationship ? t(`enum.relType.${u.relationship.type}`) : t("family.unionN", { n: i + 1 })}</h3>
              <ul>
                <PublicRelative slug={slug} rel={u.partner} />
              </ul>
              <ul className="ml-4 border-l border-stone-200 pl-3">{(u.children ?? []).map((c, i) => <PublicRelative key={i} slug={slug} rel={c} />)}</ul>
            </div>
          ))}
        </section>
      )}
      {ancestors.data && ancestors.data.nodes.length > 1 && (
        <section className="mt-4" aria-labelledby="pub-anc">
          <h2 id="pub-anc" className="mb-2 font-display text-lg font-semibold">
            {t("treeView.ancestors")}
          </h2>
          <TreeList graph={ancestors.data} personHref={(id) => `/p/${slug}/people/${id}`} />
        </section>
      )}
    </PublicFrame>
  );
}
