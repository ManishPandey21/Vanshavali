import { saveBlob } from "../api/client";

/** Serialise an on-screen chart SVG into a standalone file (fonts fall back to the system). */
export function svgMarkup(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const box = svg.viewBox.baseVal;
  if (box && box.width) {
    clone.setAttribute("width", String(box.width));
    clone.setAttribute("height", String(box.height));
  }
  // interactive-only attributes have no meaning in a file
  clone.querySelectorAll("[tabindex]").forEach((el) => el.removeAttribute("tabindex"));
  const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
  style.textContent = "text{font-family:'Noto Sans','Noto Sans Devanagari',Arial,sans-serif}";
  clone.insertBefore(style, clone.firstChild);
  return new XMLSerializer().serializeToString(clone);
}

export function downloadSvg(svg: SVGSVGElement, filename: string) {
  saveBlob(new Blob([svgMarkup(svg)], { type: "image/svg+xml" }), `${filename}.svg`);
}

export async function downloadPng(svg: SVGSVGElement, filename: string, scale = 2) {
  const markup = svgMarkup(svg);
  const box = svg.viewBox.baseVal;
  const width = (box?.width || svg.clientWidth || 800) * scale;
  const height = (box?.height || svg.clientHeight || 600) * scale;
  const url = URL.createObjectURL(new Blob([markup], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("render"));
      img.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(img, 0, 0, width, height);
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/png"));
    if (blob) saveBlob(blob, `${filename}.png`);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Clean print/PDF: the page's print stylesheet hides navigation and controls (.no-print). */
export function printChart() {
  window.print();
}
