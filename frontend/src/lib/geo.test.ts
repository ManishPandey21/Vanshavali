import { describe, expect, it } from "vitest";
import { boundsOf, formatCoords, gridLines, osmLink, parseCoordinate, projector } from "./geo";

describe("geo helpers", () => {
  it("fits points and keeps a minimum span", () => {
    const b = boundsOf([{ latitude: 25.39, longitude: 82.57 }])!;
    expect(b.maxLat - b.minLat).toBeGreaterThanOrEqual(2);
    const project = projector(b, 400, 300);
    const p = project({ latitude: 25.39, longitude: 82.57 });
    expect(p.x).toBeCloseTo(200, 0);
    expect(p.y).toBeCloseTo(150, 0);
  });

  it("projects north up and east right", () => {
    const b = boundsOf([{ latitude: 20, longitude: 75 }, { latitude: 28, longitude: 85 }], 0)!;
    const project = projector(b, 500, 500);
    const delhi = project({ latitude: 28.6, longitude: 77.2 });
    const varanasi = project({ latitude: 25.3, longitude: 83 });
    expect(delhi.y).toBeLessThan(varanasi.y);
    expect(delhi.x).toBeLessThan(varanasi.x);
    expect(gridLines(b).step).toBe(2);
  });

  it("formats and validates coordinates", () => {
    expect(formatCoords({ latitude: 25.3912, longitude: -82.5 })).toBe("25.391° N, 82.500° W");
    expect(osmLink({ latitude: 25.39, longitude: 82.57 })).toContain("mlat=25.39000");
    expect(parseCoordinate("", "lat")).toBeNull();
    expect(parseCoordinate("91", "lat")).toBe("invalid");
    expect(parseCoordinate("-179.5", "lng")).toBe(-179.5);
    expect(parseCoordinate("abc", "lng")).toBe("invalid");
  });
});
