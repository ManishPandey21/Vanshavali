import { ImageOff } from "lucide-react";
import { useDocumentImage } from "../../api/hooks/documents";

/** A vault photo through a signed, short-lived URL (never a public link). */
export function PhotoThumb({ treeId, documentId, alt, variant = "thumbnail", className = "" }: { treeId: string; documentId: string; alt: string; variant?: "thumbnail" | "preview"; className?: string }) {
  const img = useDocumentImage(treeId, documentId, variant);
  if (img.data) return <img src={img.data} alt={alt} className={`object-cover ${className}`} loading="lazy" />;
  return (
    <div className={`flex items-center justify-center bg-parchment-deep text-ink-muted ${className}`} role="img" aria-label={alt}>
      {img.isError ? <ImageOff className="size-6" aria-hidden /> : <span className="size-5 animate-pulse rounded-full bg-stone-300" aria-hidden />}
    </div>
  );
}
