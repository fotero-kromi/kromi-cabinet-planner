"""pandas 3 readiness of technician overrides (v34.49, audit code quality).

Writing an override label ("high", "Override", ...) into an audit column that
arrived all-empty (float64) is a FutureWarning in pandas 2 and a TypeError in
pandas 3, which would break category and pack overrides after an upgrade.
Text writes now make the column text first; the resulting values are
identical to pandas 2's implicit upcast.
"""
import warnings

import numpy as np
import pandas as pd

from engine.overrides import apply_overrides, OVERRIDE_COLUMNS


def test_text_override_into_float_audit_column_is_warning_free():
    work = pd.DataFrame({
        "Code": ["A1"], "Listing": ["Tools"], "ProductCategory": ["other"],
        "ProductCategory_Source": [np.nan], "ProductCategory_Evidence": [np.nan],
        "ProductCategory_Confidence": [np.nan],
        "PackUnits": [1.0], "PackUnits_Source": [np.nan],
        "PackUnits_Evidence": [np.nan], "PackUnits_Confidence": [np.nan],
        "SizeCategory": ["M"], "SizeCategory_Source": [np.nan],
        "CabinetType": ["Helix"], "SystemCategory": ["KTC"],
        "VendMode": ["Vending"], "VendBlockReason": [np.nan],
    })
    ov = pd.DataFrame([{c: "" for c in OVERRIDE_COLUMNS}])
    ov.loc[0, ["code", "listing", "product_category_override",
               "pack_units_override", "size_category_override"]] = [
        "A1", "Tools", "drills", "10", "L"]
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        out, stats = apply_overrides(work, ov)
    assert out.loc[0, "ProductCategory"] == "drills"
    assert out.loc[0, "ProductCategory_Confidence"] == "high"
    assert out.loc[0, "PackUnits_Source"] == "Override"
    assert out.loc[0, "SizeCategory_Source"] == "Override"
    assert stats["rows_touched"] == 1
