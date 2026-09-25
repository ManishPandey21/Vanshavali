import { useMemo, useState, type ComponentType } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArchiveRestore,
  ArrowDownUp,
  FileText,
  LandPlot,
  BookOpen,
  ClipboardList,
  Copy,
  Home,
  Landmark,
  LayoutGrid,
  MapPin,
  MoreHorizontal,
  Network,
  Route,
  Search,
  Settings,
  ShieldCheck,
  UserPlus,
  Users,
  UsersRound,
  type LucideProps,
} from "lucide-react";
import { useTree } from "../../api/hooks/trees";
import { TreeContext, makeTreeCtx } from "../../lib/tree-context";
import { Perm } from "../../lib/permissions";
import { ErrorAlert, Spinner } from "../ui/feedback";
import { Dialog } from "../ui/Dialog";
import { BrandMark, UserMenu } from "./AppShell";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<LucideProps>;
  end?: boolean;
  group: "main" | "family" | "records" | "research" | "admin";
}

export function TreeLayout() {
  const { treeId = "" } = useParams();
  const { t } = useTranslation();
  const tree = useTree(treeId);
  const [moreOpen, setMoreOpen] = useState(false);
  const ctx = useMemo(() => (tree.data ? makeTreeCtx(tree.data) : null), [tree.data]);

  const items: NavItem[] = useMemo(() => {
    if (!ctx) return [];
    const base = `/t/${treeId}`;
    const list: NavItem[] = [
      { to: base, label: t("nav.overview"), icon: Home, end: true, group: "main" },
      { to: `${base}/people`, label: t("nav.people"), icon: Users, group: "main" },
      { to: `${base}/tree`, label: t("nav.treeView"), icon: Network, group: "main" },
      { to: `${base}/relationship`, label: t("nav.relationship"), icon: Route, group: "main" },
      { to: `${base}/joint-family`, label: t("nav.jointFamily"), icon: LayoutGrid, group: "family" },
      { to: `${base}/branches`, label: t("nav.branches"), icon: Landmark, group: "family" },
      { to: `${base}/households`, label: t("nav.households"), icon: UsersRound, group: "family" },
      { to: `${base}/documents`, label: t("nav.documents"), icon: FileText, group: "records" },
      ...(ctx.can(Perm.PROPERTY_READ) || ctx.can(Perm.PROPERTY_WRITE) ? [{ to: `${base}/property`, label: t("nav.property"), icon: LandPlot, group: "records" as const }] : []),
      ...(ctx.can(Perm.GEDCOM_IMPORT) || ctx.can(Perm.GEDCOM_EXPORT) ? [{ to: `${base}/import-export`, label: t("nav.importExport"), icon: ArrowDownUp, group: "records" as const }] : []),
      { to: `${base}/places`, label: t("nav.places"), icon: MapPin, group: "research" },
      { to: `${base}/sources`, label: t("nav.sources"), icon: BookOpen, group: "research" },
      { to: `${base}/search`, label: t("nav.search"), icon: Search, group: "research" },
      { to: `${base}/duplicates`, label: t("nav.duplicates"), icon: Copy, group: "research" },
    ];
    list.push({ to: `${base}/admin/members`, label: t("nav.members"), icon: ShieldCheck, group: "admin" });
    if (ctx.can(Perm.MEMBERS_MANAGE)) list.push({ to: `${base}/admin/invitations`, label: t("nav.invitations"), icon: UserPlus, group: "admin" });
    list.push({ to: `${base}/admin/claims`, label: t("nav.claims"), icon: ClipboardList, group: "admin" });
    if (ctx.can(Perm.AUDIT_READ)) list.push({ to: `${base}/admin/audit`, label: t("nav.audit"), icon: ClipboardList, group: "admin" });
    if (ctx.can(Perm.AUDIT_READ) && ctx.can(Perm.TREE_MANAGE)) list.push({ to: `${base}/admin/restore`, label: t("nav.restore"), icon: ArchiveRestore, group: "admin" });
    if (ctx.can(Perm.TREE_MANAGE)) list.push({ to: `${base}/admin/settings`, label: t("nav.settings"), icon: Settings, group: "admin" });
    return list;
  }, [ctx, t, treeId]);

  if (tree.isLoading) return <Spinner />;
  if (tree.error || !ctx)
    return (
      <div className="mx-auto max-w-xl p-6">
        <ErrorAlert error={tree.error} />
      </div>
    );

  const groups: { id: NavItem["group"]; label: string }[] = [
    { id: "main", label: t("nav.group.main") },
    { id: "family", label: t("nav.group.family") },
    { id: "records", label: t("nav.group.records") },
    { id: "research", label: t("nav.group.research") },
    { id: "admin", label: t("nav.group.admin") },
  ];
  const mobileMain = items.filter((i) => [`/t/${treeId}`, `/t/${treeId}/people`, `/t/${treeId}/tree`, `/t/${treeId}/search`].includes(i.to));
  const linkCls = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm ${isActive ? "bg-kumkum-100 font-semibold text-kumkum-900" : "text-ink hover:bg-parchment-deep"}`;

  return (
    <TreeContext.Provider value={ctx}>
      <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_1fr]">
        <a href="#main" className="sr-only-focusable absolute left-2 top-2 z-50 rounded bg-white px-3 py-2">
          {t("nav.skipToContent")}
        </a>
        <aside className="hidden border-r border-stone-200 bg-white/70 lg:block">
          <div className="sticky top-0 flex h-dvh flex-col gap-4 overflow-y-auto p-4">
            <BrandMark />
            <div className="rounded-lg bg-parchment-deep px-3 py-2">
              <p className="text-[11px] uppercase tracking-wider text-ink-muted">{t("nav.currentTree")}</p>
              <p className="truncate font-display font-semibold" title={ctx.tree.name}>
                {ctx.tree.name}
              </p>
              <NavLink to="/" className="text-xs text-kumkum-800 underline">
                {t("nav.switchTree")}
              </NavLink>
            </div>
            <nav aria-label={t("nav.treeNavigation")} className="flex flex-col gap-3">
              {groups.map((g) => (
                <div key={g.id}>
                  <p className="mb-1 px-2.5 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{g.label}</p>
                  <ul className="space-y-0.5">
                    {items
                      .filter((i) => i.group === g.id)
                      .map((i) => (
                        <li key={i.to}>
                          <NavLink to={i.to} end={i.end} className={linkCls}>
                            <i.icon className="size-4" aria-hidden />
                            {i.label}
                          </NavLink>
                        </li>
                      ))}
                  </ul>
                </div>
              ))}
            </nav>
            <div className="mt-auto flex flex-col gap-2 border-t border-stone-200 pt-3">
              <LanguageSwitcher />
              <UserMenu />
            </div>
          </div>
        </aside>

        <div className="min-w-0 pb-20 lg:pb-0">
          <header className="flex items-center justify-between gap-2 border-b border-stone-200 bg-white/80 px-4 py-2 backdrop-blur lg:hidden">
            <BrandMark />
            <div className="flex items-center gap-2">
              <LanguageSwitcher />
              <UserMenu />
            </div>
          </header>
          <main id="main" tabIndex={-1} className="mx-auto max-w-6xl px-4 py-5 lg:px-8 lg:py-8">
            <Outlet />
          </main>
        </div>

        <nav aria-label={t("nav.mobileNavigation")} className="fixed inset-x-0 bottom-0 z-40 border-t border-stone-200 bg-white lg:hidden">
          <ul className="grid grid-cols-5">
            {mobileMain.map((i) => (
              <li key={i.to}>
                <NavLink
                  to={i.to}
                  end={i.end}
                  className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-[11px] ${isActive ? "font-semibold text-kumkum-800" : "text-ink-muted"}`}
                >
                  <i.icon className="size-5" aria-hidden />
                  {i.label}
                </NavLink>
              </li>
            ))}
            <li>
              <button type="button" onClick={() => setMoreOpen(true)} className="flex w-full flex-col items-center gap-0.5 py-2 text-[11px] text-ink-muted" aria-haspopup="dialog">
                <MoreHorizontal className="size-5" aria-hidden />
                {t("nav.more")}
              </button>
            </li>
          </ul>
        </nav>
        <Dialog open={moreOpen} onClose={() => setMoreOpen(false)} title={ctx.tree.name}>
          <nav aria-label={t("nav.treeNavigation")}>
            {groups.map((g) => (
              <div key={g.id} className="mb-3">
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{g.label}</p>
                <ul className="grid grid-cols-2 gap-1">
                  {items
                    .filter((i) => i.group === g.id)
                    .map((i) => (
                      <li key={i.to}>
                        <NavLink to={i.to} end={i.end} className={linkCls} onClick={() => setMoreOpen(false)}>
                          <i.icon className="size-4" aria-hidden />
                          {i.label}
                        </NavLink>
                      </li>
                    ))}
                </ul>
              </div>
            ))}
            <NavLink to="/" className="text-sm text-kumkum-800 underline" onClick={() => setMoreOpen(false)}>
              {t("nav.switchTree")}
            </NavLink>
          </nav>
        </Dialog>
      </div>
    </TreeContext.Provider>
  );
}
