/** Small, dependency-free geo helpers for the tile-free map preview (ADR-0017 §maps). */

export interface LatLng {
  latitude: number;
  longitude: number;
}

export interface Bounds {
  minLat: number;
  maxLat: number;
  minLng: number;
  maxLng: number;
}

export function boundsOf(points: LatLng[], padDeg = 0.5): Bounds | null {
  if (!points.length) return null;
  let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
  for (const p of points) {
    minLat = Math.min(minLat, p.latitude);
    maxLat = Math.max(maxLat, p.latitude);
    minLng = Math.min(minLng, p.longitude);
    maxLng = Math.max(maxLng, p.longitude);
  }
  // at least ~2° across so a single village is not drawn at infinite zoom
  const padLat = Math.max(padDeg, (2 - (maxLat - minLat)) / 2);
  const padLng = Math.max(padDeg, (2 - (maxLng - minLng)) / 2);
  return { minLat: minLat - padLat, maxLat: maxLat + padLat, minLng: minLng - padLng, maxLng: maxLng + padLng };
}

/** Equirectangular projection corrected for latitude (good enough at district/state scale). */
export function projector(b: Bounds, width: number, height: number) {
  const midLat = ((b.minLat + b.maxLat) / 2) * (Math.PI / 180);
  const kx = Math.cos(midLat);
  const spanX = (b.maxLng - b.minLng) * kx;
  const spanY = b.maxLat - b.minLat;
  const scale = Math.min(width / spanX, height / spanY);
  const offX = (width - spanX * scale) / 2;
  const offY = (height - spanY * scale) / 2;
  return (p: LatLng) => ({
    x: offX + (p.longitude - b.minLng) * kx * scale,
    y: offY + (b.maxLat - p.latitude) * scale,
  });
}

export function gridLines(b: Bounds): { lats: number[]; lngs: number[]; step: number } {
  const span = Math.max(b.maxLat - b.minLat, b.maxLng - b.minLng);
  const step = span > 40 ? 10 : span > 15 ? 5 : span > 6 ? 2 : span > 2 ? 1 : 0.5;
  const range = (lo: number, hi: number) => {
    const out: number[] = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(Number(v.toFixed(2)));
    return out;
  };
  return { lats: range(b.minLat, b.maxLat), lngs: range(b.minLng, b.maxLng), step };
}

export function formatCoords(p: LatLng): string {
  const ns = p.latitude >= 0 ? "N" : "S";
  const ew = p.longitude >= 0 ? "E" : "W";
  return `${Math.abs(p.latitude).toFixed(3)}° ${ns}, ${Math.abs(p.longitude).toFixed(3)}° ${ew}`;
}

/** Link the user may choose to follow; nothing is sent to a third party unless they click it. */
export function osmLink(p: LatLng, zoom = 12): string {
  return `https://www.openstreetmap.org/?mlat=${p.latitude.toFixed(5)}&mlon=${p.longitude.toFixed(5)}#map=${zoom}/${p.latitude.toFixed(5)}/${p.longitude.toFixed(5)}`;
}

export function parseCoordinate(raw: string, kind: "lat" | "lng"): number | null | "invalid" {
  const v = raw.trim();
  if (!v) return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return "invalid";
  const limit = kind === "lat" ? 90 : 180;
  return Math.abs(n) <= limit ? n : "invalid";
}
