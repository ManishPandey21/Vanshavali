import { Link, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LogOut, TreePine, UserCircle } from "lucide-react";
import { useLogout, useMe } from "../../api/hooks/auth";
import { LanguageSwitcher } from "./LanguageSwitcher";

export function BrandMark({ to = "/" }: { to?: string }) {
  const { t } = useTranslation();
  return (
    <Link to={to} className="flex items-center gap-2 rounded-md">
      <span className="grid size-9 place-items-center rounded-lg bg-kumkum-700 text-white shadow-sm">
        <TreePine className="size-5" aria-hidden />
      </span>
      <span className="leading-tight">
        <span className="block font-display text-lg font-bold text-kumkum-900">{t("app.name")}</span>
        <span className="block text-[11px] text-ink-muted" lang="hi">
          वंशावली
        </span>
      </span>
    </Link>
  );
}

export function UserMenu() {
  const { t } = useTranslation();
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  if (!me.data) return null;
  return (
    <div className="flex items-center gap-2">
      <Link to="/account" className="hidden items-center gap-1.5 rounded-md px-2 py-1 text-sm text-ink hover:bg-parchment-deep sm:inline-flex">
        <UserCircle className="size-4" aria-hidden />
        <span className="max-w-[10rem] truncate">{me.data.display_name}</span>
      </Link>
      <button
        type="button"
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm text-kumkum-800 hover:bg-kumkum-50"
        onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
      >
        <LogOut className="size-4" aria-hidden />
        <span className="hidden sm:inline">{t("auth.logout")}</span>
        <span className="sr-only sm:hidden">{t("auth.logout")}</span>
      </button>
    </div>
  );
}

/** Top-level chrome for non-tree pages (tree list, account). */
export function AppShell() {
  const { t } = useTranslation();
  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only-focusable absolute left-2 top-2 z-50 rounded bg-white px-3 py-2">
        {t("nav.skipToContent")}
      </a>
      <header className="border-b border-stone-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <BrandMark />
          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            <UserMenu />
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
