"""The new app end to end, as a user runs it: the Docker setup on port 8080,
a real browser, the synthetic standard scenario (tools/synthetic_golden.py).

The downloaded workbook must have the Streamlit app's digest from
tests/golden/synthetic_manifest.json; that is the parity oracle through every
layer: screens, API, planning service, PostgreSQL and the export.
"""
from __future__ import annotations

import json
import re
import urllib.request

from playwright.sync_api import Page, expect

from engine.build_info import BUILD
from tools import synthetic_golden as sg

#: tools/synthetic_golden.py SCENARIOS["standard"]: the mapping (screen labels)...
STANDARD_MAPPING = {
    "Code": "Article No", "Description": "Description",
    "Consumption pcs": "Consumption 12 months", "ProductCategory": "Category",
    "Description_2": "Description 2", "SupplierCode": "Supplier article no",
    "PackUnits": "Pack unit",
}
OPTIONAL_UNMAPPED = [
    "SizeCategory", "Year", "Program / Area", "Restocking yes/no", "Site", "Standard / Special",
    "Package dimensions", "Regrind YES/NO", "System type available", "Current stock pcs",
]
#: ... and the controls it changes, with the run scope of the golden gate.
STANDARD_SETTINGS = {
    "Helix threshold (packs per month)": "1", "Empty-cabinet threshold (%)": "50",
    "Customer": "Synthetic", "Site": "Golden",
}


def test_the_app_and_its_api_share_one_address(base_url):
    health = json.load(urllib.request.urlopen(f"{base_url}/api/v1/health", timeout=10))
    assert health == {"status": "ok", "build": BUILD, "database": "ok"}
    with urllib.request.urlopen(f"{base_url}/", timeout=10) as r:
        assert "<title>Kromi Cabinet Planner</title>" in r.read().decode("utf-8")


def test_the_standard_scenario_gives_the_streamlit_workbook(page: Page, base_url, tmp_path):
    problems: list[str] = []
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(str(e)))

    catalog = tmp_path / "synthetic_catalog.xlsx"
    catalog.write_bytes(sg.catalog_bytes(sg.build_catalog()))

    page.goto(base_url)
    expect(page.get_by_text(f"Engine {BUILD}")).to_be_visible()

    # 1. Upload
    page.get_by_label("Excel file").set_input_files(str(catalog))

    # 2. Sheet and columns
    page.get_by_role("combobox", name="Tools sheet", exact=True).click()
    page.get_by_role("option", name=sg.SHEET, exact=True).click()
    expect(page.get_by_text(re.compile(r"^First 20 of \d+ rows$"))).to_be_visible()
    for label in OPTIONAL_UNMAPPED:
        clear = page.get_by_role("button", name=f"Clear {label}", exact=True)
        if clear.count():
            clear.click()
    for label, column in STANDARD_MAPPING.items():
        box = page.get_by_role("combobox", name=label, exact=True)
        if box.input_value() != column:
            box.click()
            page.get_by_role("option", name=column, exact=True).click()
    for label in OPTIONAL_UNMAPPED:
        expect(page.get_by_role("combobox", name=label, exact=True)).to_have_value("")
    next_button = page.get_by_role("button", name="Next", exact=True)
    expect(next_button).to_be_enabled()
    next_button.click()

    # 3. Settings
    for label, value in STANDARD_SETTINGS.items():
        page.get_by_role("textbox", name=label, exact=True).fill(value)
    page.get_by_role("button", name="Run planning", exact=True).click()

    # 4. Run and results
    download_link = page.get_by_role("link", name="Download result workbook")
    expect(download_link).to_be_visible(timeout=120_000)
    totals = page.get_by_role("region", name="Totals")
    expect(totals).to_contain_text("Total cabinets")
    expect(page.get_by_text("SYN-00001", exact=True)).to_be_visible()
    with page.expect_download() as info:
        download_link.click()
    workbook = tmp_path / "result.xlsx"
    info.value.save_as(workbook)

    expected = sg.load_manifest()["scenarios"]["standard"]["workbook"]["sha256"]
    assert sg.workbook_digest(workbook.read_bytes()) == expected
    assert problems == []
