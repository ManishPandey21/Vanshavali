import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "subtle";
type Size = "sm" | "md";

const base =
  "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 whitespace-nowrap";
const variants: Record<Variant, string> = {
  primary: "bg-kumkum-700 text-white hover:bg-kumkum-800 shadow-sm",
  secondary: "border border-stone-400 bg-white text-ink hover:bg-parchment-deep",
  ghost: "text-kumkum-800 hover:bg-kumkum-50",
  subtle: "bg-parchment-deep text-ink hover:bg-haldi-100",
  danger: "bg-red-700 text-white hover:bg-red-800",
};
const sizes: Record<Size, string> = {
  sm: "px-2.5 py-1.5 text-xs min-h-8",
  md: "px-3.5 py-2 text-sm min-h-10",
};

export function buttonClass(variant: Variant = "primary", size: Size = "md", extra = "") {
  return `${base} ${variants[variant]} ${sizes[size]} ${extra}`;
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, className = "", children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={buttonClass(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export function ButtonLink({
  variant = "primary",
  size = "md",
  icon,
  className = "",
  children,
  ...rest
}: LinkProps & { variant?: Variant; size?: Size; icon?: ReactNode }) {
  return (
    <Link className={buttonClass(variant, size, className)} {...rest}>
      {icon}
      {children}
    </Link>
  );
}
