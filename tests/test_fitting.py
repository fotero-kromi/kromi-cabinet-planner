"""Tests for engine.fitting — dimensional fit checking.

Compartment reference dimensions (from engine.constants):
  Helix coil : clear Ø64 mm ring, pitch <= 52 mm, usable length <= 520 mm
  Carousel   : rect 87 x 68 x 195 ; pie 87->6 x 50 x 195
  Locker A   : 180 x 500 x 140
  Locker B   : 180 x 500 x {140, 295}   (split cabinet)
  Locker C   : 180 x 500 x 62.5
"""

from engine import fitting as fit
from engine.dimensions import PackageDims, extract_package_dims as ex


def _pkg(*dims, evidence="parsed:3d", is_diameter=False):
    """Build a PackageDims directly for precise geometry tests."""
    return PackageDims(values_mm=list(dims), evidence=evidence, is_diameter=is_diameter)


# ---- _box_fits: orientation-free rectangular fit ----

class TestBoxFits:
    def test_exact_fit(self):
        assert fit._box_fits([180, 500, 140], [180, 500, 140]) is True

    def test_one_mm_over_rejected(self):
        assert fit._box_fits([181, 500, 140], [180, 500, 140]) is False

    def test_orientation_independent(self):
        # Same package, dims given in a different order — still fits.
        assert fit._box_fits([140, 180, 500], [500, 180, 140]) is True

    def test_clearly_too_big(self):
        assert fit._box_fits([600, 600, 600], [180, 500, 140]) is False


# ---- _normalize_package: padding 1-D / 2-D packages ----

class TestNormalizePackage:
    def test_three_dims_sorted(self):
        assert fit._normalize_package(_pkg(40, 200, 40)) == [200, 40, 40]

    def test_two_dims_padded_with_smaller(self):
        # Ø25 x 180 -> 180 x 25 x 25 (square cross-section bounding the round)
        assert fit._normalize_package(_pkg(25, 180)) == [180, 25, 25]

    def test_one_dim_becomes_cube(self):
        assert fit._normalize_package(_pkg(50)) == [50, 50, 50]

    def test_empty_returns_none(self):
        assert fit._normalize_package(PackageDims()) is None


# ---- Helix fit ----

class TestHelixFit:
    def test_small_box_fits(self):
        assert fit._fits_helix([200, 40, 40]) is True

    def test_thin_long_drill_fits(self):
        # 180 long, 25 cross-section, 25 thick -> all within limits
        assert fit._fits_helix([180, 25, 25]) is True

    def test_too_wide_for_ring_rejected(self):
        # cross-section 70 > 64 mm clear ring
        assert fit._fits_helix([200, 70, 30]) is False

    def test_too_thick_for_pitch_rejected(self):
        # thinnest dim 55 > 52 mm widest pitch
        assert fit._fits_helix([200, 60, 55]) is False

    def test_too_long_rejected(self):
        # 600 > 520 mm usable coil length
        assert fit._fits_helix([600, 40, 40]) is False

    def test_at_limits_fits(self):
        # exactly at the bounds
        assert fit._fits_helix([520, 64, 52]) is True


# ---- Carousel fit ----

class TestCarouselFit:
    def test_fits_rect_slot(self):
        # 80 x 60 x 150 within 87 x 68 x 195
        assert fit._fits_carousel([150, 80, 60]) is True

    def test_too_wide_rejected(self):
        # 90 > 87 mm widest carousel opening
        assert fit._fits_carousel([150, 90, 60]) is False

    def test_too_deep_rejected(self):
        # 200 > 195 mm radial depth
        assert fit._fits_carousel([200, 60, 50]) is False

    def test_at_rect_limits(self):
        assert fit._fits_carousel([195, 87, 68]) is True


# ---- Locker fit (incl. split B model) ----

class TestLockerFit:
    def test_locker_a_fits_medium(self):
        assert fit._fits_locker([480, 170, 120], "Locker A") is True

    def test_locker_a_too_tall_rejected(self):
        # 280 height exceeds A's 140 box (in every orientation)
        assert fit._fits_locker([480, 280, 170], "Locker A") is False

    def test_locker_c_short_only(self):
        # C boxes are 62.5 mm tall — a 120 mm item won't fit
        assert fit._fits_locker([480, 170, 120], "Locker C") is False

    def test_locker_c_fits_flat(self):
        assert fit._fits_locker([480, 170, 60], "Locker C") is True

    def test_locker_b_tall_box_fits(self):
        # B has a 295 mm box -> a 280 mm tall item fits
        assert fit._fits_locker([480, 280, 170], "Locker B") is True

    def test_unknown_model_false(self):
        assert fit._fits_locker([100, 100, 100], "Locker Z") is False


# ---- check_fit: end-to-end recommendation ----

class TestCheckFit:
    def test_small_item_recommends_helix(self):
        r = fit.check_fit(ex("40x40x30"))
        assert r.recommended == "Helix"
        assert r.fits_anywhere is True

    def test_medium_recommends_carousel(self):
        # 80 wide exceeds Helix ring -> Carousel is smallest fit
        r = fit.check_fit(ex("80x60x150"))
        assert r.recommended == "Carousel"
        assert r.fits["Helix"] is False

    def test_tall_recommends_locker_b(self):
        r = fit.check_fit(ex("170x480x280"))
        assert r.recommended == "Locker B"

    def test_oversize_fits_nowhere(self):
        r = fit.check_fit(ex("300x600x400"))
        assert r.recommended is None
        assert r.fits_anywhere is False
        assert r.evidence.startswith("no-fit")

    def test_no_dims_returns_no_dims(self):
        r = fit.check_fit(ex("no dimensions"))
        assert r.evidence == "no-dims"
        assert r.recommended is None

    def test_evidence_carries_source(self):
        r = fit.check_fit(ex("Ø25 x 180"))
        assert "diameter" in r.evidence


# ---- fit_disposition: validate current routing + suggest ----

class TestFitDisposition:
    def test_ok_when_fits_current(self):
        d = fit.fit_disposition("Helix", ex("40x40x30"))
        assert d["status"] == "ok"
        assert d["fits_current"] is True

    def test_misfit_suggests_alternative(self):
        # Item assigned to Helix but 80 mm wide doesn't fit -> misfit, suggest Carousel
        d = fit.fit_disposition("Helix", ex("80x60x150"))
        assert d["status"] == "misfit"
        assert d["fits_current"] is False
        assert d["recommended"] == "Carousel"

    def test_misfit_with_no_alternative(self):
        d = fit.fit_disposition("Locker B", ex("300x600x400"))
        assert d["status"] == "misfit"
        assert d["recommended"] is None

    def test_no_dims_keeps_heuristic(self):
        d = fit.fit_disposition("Helix", ex(""))
        assert d["status"] == "no-dims"
        assert d["recommended"] is None

    def test_current_cabinet_preserved_in_output(self):
        d = fit.fit_disposition("Carousel", ex("80x60x150"))
        assert d["current"] == "Carousel"


# ---- Realistic end-to-end scenarios ----

class TestRealisticScenarios:
    def test_typical_insert_box(self):
        # Small insert carton: fits Helix (most efficient)
        r = fit.check_fit(ex("60x40x20"))
        assert r.recommended == "Helix"

    def test_boxed_endmill(self):
        # 200 mm boxed end mill, 30 mm square -> Helix (200<520, 30<64, 30<52)
        r = fit.check_fit(ex("200x30x30"))
        assert r.recommended == "Helix"

    def test_large_drill_in_long_box(self):
        # 350 mm long, 55 mm cross-section: 55<64 ring but 55>52 pitch -> not Helix
        # Carousel: 350 > 195 depth -> no. Locker: 350<500, 55<140 -> Locker
        r = fit.check_fit(ex("350x55x55"))
        assert r.recommended in ("Locker C", "Locker A", "Locker B")
        assert r.fits["Helix"] is False
        assert r.fits["Carousel"] is False
