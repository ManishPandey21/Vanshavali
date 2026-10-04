import { useState } from "react";
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/utils";
import { GeoFields, geoDraftFrom, type GeoDraft } from "./GeoFields";

function Harness({ initial }: { initial: GeoDraft }) {
  const [value, setValue] = useState(initial);
  return <GeoFields value={value} onChange={setValue} showErrors={false} canPrivacy />;
}

describe("coordinate hints", () => {
  it("labels the example coordinates as examples, apart from the stored values", async () => {
    renderWithProviders(<Harness initial={{ ...geoDraftFrom(null), latitude: "25.5812", longitude: "83.5731", location_precision: "exact" }} />);
    const lat = screen.getByLabelText("Latitude");
    const lng = screen.getByLabelText("Longitude");
    expect(lat).toHaveValue("25.5812");
    expect(lng).toHaveValue("83.5731");
    // the hint is announced as the field's description and reads as an example
    expect(lat).toHaveAccessibleDescription("e.g. 25.3912");
    expect(lng).toHaveAccessibleDescription("e.g. 82.5712");
    // no bare number that could pass for a second set of coordinates
    expect(screen.queryByText("25.3912")).not.toBeInTheDocument();
    expect(screen.queryByText("82.5712")).not.toBeInTheDocument();
    // editing the value leaves the example alone (and the example never fills the field)
    await userEvent.setup().clear(lat);
    expect(lat).toHaveValue("");
    expect(lat).toHaveAccessibleDescription("e.g. 25.3912");
  });
});
