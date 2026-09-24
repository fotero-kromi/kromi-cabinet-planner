// The form renders any list of setting descriptions; nothing is laid out by hand.
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SettingField } from "../../lib/settingFields";
import { initialSettings } from "../../lib/settings";
import { defaults } from "../../test/fixtures";
import { renderApp } from "../../test/render";
import { SettingsForm } from "./SettingsForm";

const FIELDS: SettingField[] = [
  { section: "planning", key: "helix_threshold", kind: "number", label: "Helix", group: "routing",
    advanced: false, step: 0.5, decimals: 4 },
  { section: "planning", key: "bulk_routing", kind: "checkbox", label: "Bulk", group: "vend",
    advanced: false },
  { section: "planning", key: "year_mode", kind: "select", label: "Years", group: "supply",
    advanced: false, labels: "year_mode" },
];

describe("the settings form", () => {
  it("renders only the groups that have fields, with the given fields", () => {
    renderApp(<SettingsForm fields={FIELDS} defaults={defaults} settings={initialSettings(defaults)}
                            stdSpecialMapped={false} opMode="" onChange={() => {}} />);
    expect(screen.getByText("Routing and sizing")).toBeInTheDocument();
    expect(screen.queryByText("Run setup")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Helix" })).toHaveValue("6");
    expect(screen.getByRole("checkbox", { name: "Bulk" })).not.toBeChecked();
    expect(screen.getByRole("combobox", { name: "Years" })).toHaveValue("Use all rows");
  });

  it("reports each change as new settings", async () => {
    const onChange = vi.fn();
    const { user } = renderApp(
      <SettingsForm fields={FIELDS} defaults={defaults} settings={initialSettings(defaults)}
                    stdSpecialMapped={false} opMode="" onChange={onChange} />);
    await user.click(screen.getByRole("checkbox", { name: "Bulk" }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ planning: expect.objectContaining({ bulk_routing: true }) }));
    await user.click(screen.getByRole("combobox", { name: "Years" }));
    await user.click(await screen.findByRole("option", { name: "Keep latest year only" }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ planning: expect.objectContaining({ year_mode: "latest_year_only" }) }));
  });
});
