import { useEffect, useRef, type CSSProperties, type ElementType, type ReactNode } from "react";

/**
 * Fades and lifts its content into place the first time it scrolls into view. The content is in
 * the page and visible from the start: it is only hidden once this script has armed it, and only
 * when IntersectionObserver exists and the visitor has not asked for reduced motion (the CSS lives
 * in index.css under [data-reveal]).
 */
export function Reveal({
  as: Tag = "div",
  delay = 0,
  className = "",
  children,
  ...rest
}: {
  as?: ElementType;
  delay?: number;
  className?: string;
  children: ReactNode;
} & Record<string, unknown>) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const box = el.getBoundingClientRect();
    if (box.top < window.innerHeight * 0.9) return; // already on screen: never hide what the reader sees
    el.dataset.reveal = "armed";
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          el.dataset.reveal = "shown";
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.12 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={className}
      style={{ "--reveal-delay": `${delay}ms` } as CSSProperties}
      {...rest}
    >
      {children}
    </Tag>
  );
}
