import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { PlaceCascade } from "./PlaceCascade";
import { PlacePicker, emptyPlace, type PlaceValue } from "../pickers";
import { placeFieldsFor } from "../../lib/lgd";
import type { GeoUnitOut } from "../../api/types";

const snapshot = { id: "2026-05", activated_at: null, attribution: "Source: Local Government Directory" };
const up: GeoUnitOut = { level: "state", lgd_code: "9", name_en: "Uttar Pradesh", name_local: "उत्तर प्रदेश", local_script: "Deva", sub_district_label: "tehsil", state_code: "9", ancestors: [] };
const pryj: GeoUnitOut = { level: "district", lgd_code: "9901", name_en: "Prayagraj", name_local: "प्रयागराज", local_script: "Deva", parent_level: "state", parent_lgd_code: "9", state_code: "9", district_code: "9901", sub_district_label: "tehsil", ancestors: [{ level: "state", lgd_code: "9", name_en: "Uttar Pradesh" }] };
const phulpur: GeoUnitOut = { level: "sub_district", lgd_code: "99001", name_en: "Phulpur", name_local: "फूलपुर", local_script: "Deva", state_code: "9", district_code: "9901", sub_district_code: "99001", sub_district_label: "tehsil", ancestors: [up, pryj] };
const rampur: GeoUnitOut = {
  level: "village",
  lgd_code: "9900001",
  name_en: "Rampur",
  name_local: "रामपुर",
  local_script: "Deva",
  state_code: "9",
  district_code: "9901",
  sub_district_code: "99001",
  sub_district_label: "tehsil",
  ancestors: [up, pryj, phulpur],
};
const page = (items: GeoUnitOut[]) => ({ items, next_cursor: null, snapshot });

/** Route fake API calls by path and query. */
function geoApi(extra: (url: URL) => unknown | undefined = () => undefined) {
  const calls: URL[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    calls.push(url);
    const special = extra(url);
    if (special !== undefined) return Promise.resolve(special as Response);
    const p = url.searchParams;
    if (url.pathname.endsWith("/geo/units")) {
      if (p.get("q")) return Promise.resolve(jsonResponse(page(p.get("q")!.startsWith("Alla") ? [{ ...pryj, match: { reason: "alias", text: "Allahabad" } }] : [rampur])));
      const level = p.get("level");
      if (level === "state") return Promise.resolve(jsonResponse(page([up])));
      if (level === "district") return Promise.resolve(jsonResponse(page([pryj])));
      if (level === "sub_district") return Promise.resolve(jsonResponse(page([phulpur])));
      if (level === "village") return Promise.resolve(jsonResponse(page([rampur])));
      return Promise.resolve(jsonResponse(page([])));
    }
    if (url.pathname.endsWith("/geo/pincodes/212402"))
      return Promise.resolve(jsonResponse({ pincode: "212402", offices: [{ office_name: "Phulpur S.O" }, { office_name: "Rampur B.O" }], states: [up], districts: [pryj], sub_districts: [], snapshot }));
    return Promise.resolve(jsonResponse({ error: { code: "not_found", message: "Not found" } }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("PlaceCascade", () => {
  it("renders nothing when the directory is switched off, so free-text fields stay", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({ error: { code: "not_found", message: "Not found" } }, 404)));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderWithProviders(<PlaceCascade onPick={vi.fn()} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelector("section")).toBeNull());
  });

  it("walks state → district → tehsil → village and picks only on the user's choice", async () => {
    geoApi();
    const onPick = vi.fn();
    renderWithProviders(<PlaceCascade onPick={onPick} />);
    await userEvent.click(await screen.findByRole("combobox", { name: "State or union territory" }));
    await userEvent.click(await screen.findByRole("option", { name: /Uttar Pradesh/ }));
    // the local-script name is marked up with its language
    const chosen = screen.getByRole("group", { name: "State or union territory" });
    expect(within(chosen).getByText("उत्तर प्रदेश")).toHaveAttribute("lang", "hi");
    await userEvent.click(screen.getByRole("combobox", { name: "District" }));
    await userEvent.click(await screen.findByRole("option", { name: /Prayagraj/ }));
    // Uttar Pradesh calls its sub-districts tehsils
    await userEvent.click(screen.getByRole("combobox", { name: "Tehsil" }));
    await userEvent.click(await screen.findByRole("option", { name: /Phulpur/ }));
    expect(onPick).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("combobox", { name: "Village or town" }));
    await userEvent.click(await screen.findByRole("option", { name: /Rampur/ }));
    expect(onPick).toHaveBeenCalledWith(rampur);
  });

  it("finds a district by its former name and says why it matched", async () => {
    geoApi();
    const onPick = vi.fn();
    renderWithProviders(<PlaceCascade onPick={onPick} />);
    await userEvent.type(await screen.findByRole("combobox", { name: "Search all villages and towns" }), "Allahabad");
    const opt = await screen.findByRole("option", { name: /Prayagraj/ });
    expect(opt).toHaveTextContent("also known as Allahabad");
    await userEvent.click(opt);
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ lgd_code: "9901" }));
  });

  it("a PIN code only suggests the district; it never picks a village", async () => {
    geoApi();
    const onPick = vi.fn();
    renderWithProviders(<PlaceCascade onPick={onPick} />);
    await userEvent.type(await screen.findByLabelText("PIN code"), "212402");
    await userEvent.click(await screen.findByRole("button", { name: "Use Prayagraj, Uttar Pradesh" }));
    expect(onPick).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: "District" })).toHaveTextContent("Prayagraj");
  });

  it("'My village is not listed' hands back the chosen district and state as text", async () => {
    geoApi();
    const onNotListed = vi.fn();
    renderWithProviders(<PlaceCascade onPick={vi.fn()} onNotListed={onNotListed} />);
    await userEvent.click(await screen.findByRole("combobox", { name: "State or union territory" }));
    await userEvent.click(await screen.findByRole("option", { name: /Uttar Pradesh/ }));
    await userEvent.click(screen.getByRole("button", { name: "My village is not listed" }));
    expect(onNotListed).toHaveBeenCalledWith({ state: up, district: null });
    expect(screen.getByText(/kept as text, without an LGD code/)).toBeInTheDocument();
  });

  it("shows the GODL-India attribution with the snapshot", async () => {
    geoApi();
    renderWithProviders(<PlaceCascade onPick={vi.fn()} />);
    expect(await screen.findByText(/Local Government Directory, Government of India; India Post \(data of 2026-05\)/)).toBeInTheDocument();
  });
});

describe("placeFieldsFor", () => {
  it("fills the place from the unit and its ancestors, with the local name in its script", () => {
    expect(placeFieldsFor(rampur)).toEqual({
      canonical_name: "Rampur",
      place_type: "village",
      lgd_code: "9900001",
      lgd_level: "village",
      district: "Prayagraj",
      state: "Uttar Pradesh",
      country: "India",
      local_names: [{ name: "रामपुर", language: "hi", script: "Deva" }],
    });
    expect(placeFieldsFor({ ...rampur, level: "urban_body", category: "Municipal Corporation" }).place_type).toBe("city");
  });
});

function PickerHarness({ onChange }: { onChange: (v: PlaceValue) => void }) {
  const [v, setV] = useState<PlaceValue>(emptyPlace());
  return (
    <PlacePicker
      treeId="tree-1"
      label="Birth place"
      value={v}
      suggestion={{ place_id: "p-1", place_label: "Rampur", reason: "Ancestral village of Sharma branch" }}
      onChange={(x) => {
        setV(x);
        onChange(x);
      }}
    />
  );
}

describe("PlacePicker ancestral-village suggestion (ADR-0019 §8)", () => {
  it("is offered, never filled, and can be accepted or dismissed", async () => {
    geoApi((url) => (url.pathname.includes("/places") ? jsonResponse({ items: [], next_cursor: null }) : undefined));
    const onChange = vi.fn();
    const { unmount } = renderWithProviders(<PickerHarness onChange={onChange} />);
    expect(screen.getByText(/Ancestral village of Sharma branch/)).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Use Rampur" }));
    expect(onChange).toHaveBeenCalledWith({ place_id: "p-1", place_label: "Rampur", place_as_recorded: "Rampur" });
    unmount();

    const onChange2 = vi.fn();
    renderWithProviders(<PickerHarness onChange={onChange2} />);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(/Ancestral village of Sharma branch/)).toBeNull();
    expect(onChange2).not.toHaveBeenCalled();
  });

  it("links a picked LGD unit to a new tree place carrying the code", async () => {
    const created: unknown[] = [];
    geoApi((url) => {
      if (url.pathname === "/api/v1/trees/tree-1/places") {
        return url.search ? jsonResponse({ items: [], next_cursor: null }) : undefined;
      }
      return undefined;
    });
    const base = (globalThis.fetch as unknown as { getMockImplementation: () => (input: RequestInfo | URL) => Promise<Response> }).getMockImplementation();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "POST" && String(input).endsWith("/trees/tree-1/places")) {
          created.push(JSON.parse(String(init.body)));
          return Promise.resolve(jsonResponse({ id: "new-place", canonical_name: "Rampur", hierarchy: [], place_type: "village", local_names: [], historical_names: [] }, 201));
        }
        return base(input);
      }),
    );
    const onChange = vi.fn();
    renderWithProviders(<PlacePicker treeId="tree-1" label="Birth place" value={emptyPlace()} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Find in the Local Government Directory" }));
    await userEvent.type(await screen.findByRole("combobox", { name: "Search all villages and towns" }), "Rampur");
    await userEvent.click(await screen.findByRole("option", { name: /Rampur/ }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ place_id: "new-place", place_label: "Rampur", place_as_recorded: "Rampur" }));
    expect(created).toEqual([expect.objectContaining({ lgd_code: "9900001", lgd_level: "village", district: "Prayagraj" })]);
  });
});

describe("adding a person to a branch", () => {
  it("sends the chosen branch with the new person", async () => {
    const { buildPersonCreate, emptyPersonDraft } = await import("../person/PersonForm");
    const d = emptyPersonDraft();
    d.names[0] = { ...d.names[0], given_name: "Aarav" };
    expect(buildPersonCreate({ ...d, branch_id: "b-1" }).branch_ids).toEqual(["b-1"]);
    expect(buildPersonCreate(d).branch_ids).toBeUndefined();
  });
});
