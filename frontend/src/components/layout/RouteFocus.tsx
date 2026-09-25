import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

let lastPath: string | null = null;

/**
 * Single-page-app route changes, made accessible:
 * - every page gets a descriptive document title from its main heading (WCAG 2.4.2 Page Titled);
 * - after in-app navigation, focus moves to that heading (2.4.3 Focus Order), so keyboard and
 *   screen-reader users start at the new content instead of on a link that no longer exists, and the
 *   heading is announced.
 *
 * Only the path counts as a new page; search-param changes (tabs, filters) keep focus where it is.
 * Focus is never taken from an element the user moved to after the navigation started.
 */
export function RouteFocus() {
  const { pathname } = useLocation();
  const { t, i18n } = useTranslation();
  const appName = t("app.name");

  useEffect(() => {
    // Focus moves only on in-app navigation to a new path: not on first load, and not when the
    // effect re-runs for a language switch.
    const navigated = lastPath !== null && lastPath !== pathname;
    lastPath = pathname;
    const focusedAtNavigation = document.activeElement;
    let focused = !navigated;
    let frame = 0;

    const apply = () => {
      frame = 0;
      const h1 = document.querySelector<HTMLElement>("main h1") ?? document.querySelector<HTMLElement>("h1");
      const text = h1?.textContent?.replace(/\s+/g, " ").trim();
      if (!h1 || !text) return;
      const title = `${text} · ${appName}`;
      if (document.title !== title) document.title = title;
      if (focused) return;
      focused = true;
      const active = document.activeElement;
      const userMoved = active && active !== document.body && active !== focusedAtNavigation && document.body.contains(active);
      if (userMoved || active?.closest("[role=dialog]")) return;
      if (!h1.hasAttribute("tabindex")) h1.setAttribute("tabindex", "-1");
      h1.focus({ preventScroll: false });
    };

    apply();
    const observer = new MutationObserver(() => {
      if (!frame) frame = requestAnimationFrame(apply);
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => {
      observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
    };
  }, [pathname, appName, i18n.language]);

  return null;
}
