import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { PlaceCascade, placeTypeFor, unitTrail } from "./PlaceCascade";
import { GeoSnapshotsPage } from "../../pages/admin/GeoSnapshotsPage";
import type { GeoUnit } from "../../api/types";

const snapshot = { source: "lgd", label: "2026-10", licence: "GODL-India", attribution: "Local Government Directory" };
const u = (level: string, code: string, name_en: string, name_local: string | null, path: [string, string, string][] = [], extra: object = {}) => ({
  level,
  code,
  name_en,
  name_local,
  local_script: "Deva",
  local_term: null,
  category: null,
  alt_names: [],
  former_names: [],
  status: "current",
  valid_to: null,
  successor_codes: [],
  path: path.map(([level, code, name_en]) => ({ level, code, name_en })),
  ...extra,
});
const UP = u("state", "909", "Uttar Pradesh", "उत्तर प्रदेश");
const VNS = u("district", "90187", "Varanasi", "वाराणसी", [["state", "909", "Uttar Pradesh"]]);
const PINDRA = u("subdistrict", "90901", "Pindra", "पिंडरा", [["state", "909", "Uttar Pradesh"], ["district", "90187", "Varanasi"]], { local_term: "Tehsil" });
const BABATPUR = u("village", "9100001", "Babatpur", "बाबतपुर", [
  ["state", "909", "Uttar Pradesh"],
  ["district", "90187", "Varanasi"],
  ["subdistrict", "90901", "Pindra"],
]);
const page = (items: unknown[]) => ({ items, next_cursor: null, snapshot });

function routeGeo(extra: Record<string, unknown> = {}) {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://x");
    const p = url.searchParams;
    for (const [k, v] of Object.entries(extra)) if (url.pathname.includes(k)) return Promise.resolve(jsonResponse(v));
    if (url.pathname.endsWith("/geo/units")) {
      if (p.get("q") && !p.get("parent_code")) return Promise.resolve(jsonResponse(page(p.get("q")!.startsWith("बाब") || p.get("q")!.startsWith("bab") ? [BABATPUR] : [])));
      if (p.get("parent_code") === "909") return Promise.resolve(jsonResponse(page([VNS])));
      if (p.get("parent_code") === "90187" && p.get("level") === "subdistrict") return Promise.resolve(jsonResponse(page([PINDRA])));
      if (p.get("parent_code") === "90187") return Promise.resolve(jsonResponse(page([])));
      if (p.get("parent_code") === "90901") return Promise.resolve(jsonResponse(page([BABATPUR])));
      return Promise.resolve(jsonResponse(page([UP])));
    }
    if (url.pathname.includes("/geo/pincodes/221006"))
      return Promise.resolve(jsonResponse({ pin: "221006", offices: [{ office_name: "Babatpur B.O", office_type: "B.O.", units: [BABATPUR] }], snapshot }));
    return Promise.resolve(jsonResponse({ error: { code: "not_found", message: "Not found" } }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("PlaceCascade", () => {
  it("finds a village by its Hindi name and shows where it is", async () => {
    routeGeo();
    const onPick = vi.fn();
    renderWithProviders(<PlaceCascade linked={null} onPick={onPick} onUnlink={() => {}} />, { tree: null });
    const box = await screen.findByRole("combobox", { name: /Search a village/ });
    await userEvent.type(box, "बाब");
    const opt = await screen.findByRole("option", { name: /Babatpur/ });
    expect(opt).toHaveTextContent("Pindra, Varanasi, Uttar Pradesh");
    await userEvent.click(opt);
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ level: "village", code: "9100001" }));
    expect(screen.getByText(/Source: Local Government Directory \(snapshot 2026-10\)/)).toBeInTheDocument();
  });

  it("walks state → district → tehsil (the state's own word) → village", async () => {
    routeGeo();
    const onPick = vi.fn();
    renderWithProviders(<PlaceCascade linked={null} onPick={onPick} onUnlink={() => {}} />, { tree: null });
    await userEvent.click(await screen.findByText("Or choose step by step"));
    await userEvent.selectOptions(await screen.findByLabelText("State / UT"), "909");
    const district = screen.getByLabelText("District");
    await waitFor(() => expect(within(district).getByRole("option", { name: /Varanasi/ })).toBeInTheDocument());
    await userEvent.selectOptions(district, "90187");
    const tehsil = await screen.findByLabelText("Tehsil");
    await waitFor(() => expect(within(tehsil).getByRole("option", { name: /Pindra/ })).toBeInTheDocument());
    await userEvent.selectOptions(tehsil, "90901");
    await userEvent.click(screen.getByRole("combobox", { name: "Village or town" }));
    await userEvent.click(await screen.findByRole("option", { name: /Babatpur/ }));
    expect(onPick).toHaveBeenLastCalledWith(expect.objectContaining({ code: "9100001" }));
    // a higher level can be linked too (e.g. only the tehsil is known)
    await userEvent.click(screen.getByRole("button", { name: "Use Tehsil Pindra" }));
    expect(onPick).toHaveBeenLastCalledWith(expect.objectContaining({ code: "90901" }));
  });

  it("suggests the places a PIN serves without picking one", async () => {
    routeGeo();
    const onPick = vi.fn();
    renderWithProviders(<PlaceCascade linked={null} onPick={onPick} onUnlink={() => {}} />, { tree: null });
    await userEvent.type(await screen.findByLabelText("PIN code"), "22100x6");
    expect(screen.getByLabelText("PIN code")).toHaveValue("221006");
    expect(await screen.findByText(/Babatpur B.O/)).toBeInTheDocument();
    expect(screen.getByText(/A PIN can cover several villages/)).toBeInTheDocument();
    expect(onPick).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /Babatpur/ }));
    expect(onPick).toHaveBeenCalledOnce();
  });

  it("shows the link and lets the family remove it", async () => {
    routeGeo();
    const onUnlink = vi.fn();
    renderWithProviders(<PlaceCascade linked={BABATPUR as GeoUnit} onPick={() => {}} onUnlink={onUnlink} />, { tree: null });
    expect(await screen.findByRole("status")).toHaveTextContent("Linked to: Babatpur");
    await userEvent.click(screen.getByRole("button", { name: "Remove link" }));
    expect(onUnlink).toHaveBeenCalled();
  });

  it("disappears when the directory is switched off or empty, leaving free text", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ error: { code: "not_found", message: "Not found" } }, 404)));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderWithProviders(<PlaceCascade linked={null} onPick={() => {}} onUnlink={() => {}} />, { tree: null });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("maps levels to place types and formats trails", () => {
    expect(placeTypeFor("village")).toBe("village");
    expect(placeTypeFor("subdistrict")).toBe("tehsil");
    expect(placeTypeFor("ulb")).toBe("town");
    expect(unitTrail(BABATPUR as GeoUnit)).toBe("Pindra, Varanasi, Uttar Pradesh");
  });
});

describe("GeoSnapshotsPage", () => {
  const snap = (extra: object) => ({
    id: "s1",
    source: "lgd",
    label: "2026-10",
    status: "validated",
    source_url: null,
    downloaded_on: "2026-10-15",
    licence: "GODL-India",
    attribution: "LGD",
    files: [{ name: "units.csv", sha256: "ab".repeat(32), bytes: 1234, rows: 14 }],
    report: { counts: { village: 5 }, error_count: 0, errors: [], warning_count: 1, warnings: ["line 5: something"], diff: { previous: "2026-07", added: { village: 1 }, retired: { village: 2 }, samples: { retired: ["village 1 Phulpur"] } } },
    staged_by: "ops",
    approved_by_name: null,
    approved_at: null,
    activated_by_name: null,
    activated_at: null,
    created_at: "2026-11-06T00:00:00Z",
    approved_by_me: false,
    ...extra,
  });

  it("shows the report and only the next allowed actions; the approver cannot activate", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse([snap({}), snap({ id: "s2", label: "2026-11", status: "approved", approved_by_me: true })]))),
    );
    renderWithProviders(<GeoSnapshotsPage />, { tree: null });
    const v = await screen.findByRole("article", { name: /LGD units · 2026-10/ });
    expect(within(v).getByText("Validated")).toBeInTheDocument();
    expect(within(v).getByRole("rowheader", { name: "Retired" }).nextSibling).toHaveTextContent("village 2");
    expect(within(v).getByText("Compared with snapshot 2026-07.")).toBeInTheDocument();
    expect(within(v).getByRole("button", { name: "Approve 2026-10" })).toBeEnabled();
    expect(within(v).queryByRole("button", { name: /Activate/ })).toBeNull();
    const a = screen.getByRole("article", { name: /2026-11/ });
    expect(within(a).getByRole("button", { name: "Activate 2026-11" })).toBeDisabled();
    expect(within(a).getByText(/another administrator must activate it/)).toBeInTheDocument();
  });

  it("asks for a reason before approving", async () => {
    const fetchMock = vi.fn((_: RequestInfo | URL, init?: RequestInit) =>
      Promise.resolve(jsonResponse(init?.method === "POST" ? snap({ status: "approved" }) : [snap({})])),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<GeoSnapshotsPage />, { tree: null });
    await userEvent.click(await screen.findByRole("button", { name: "Approve 2026-10" }));
    const dialog = await screen.findByRole("dialog", { name: "Approve LGD units 2026-10" });
    const go = within(dialog).getByRole("button", { name: "Approve" });
    expect(go).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Counts match the source");
    await userEvent.click(go);
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/s1/approve") && JSON.parse(String(init?.body)).reason === "Counts match the source")).toBe(true),
    );
  });
});
