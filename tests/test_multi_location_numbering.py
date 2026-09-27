"""One number per article on several machines (v34.63, owner decision D6).

An article planned in several supply points (``Location_Shared``) has one
number: the KTC counter and the dimension-scheme variants advance once per
article (Listing, Code), and every copy shows the number of the article's
first row in numbering order. Invariant: a file whose articles are split over
several supply points gets exactly the same Article setup and numbers as the
same file with each article in one supply point. Replicate runs carry no flag
and keep their numbers, gaps included.
"""
import pandas as pd
import pytest

from engine.invariants import check_kromi_uniqueness
from engine.kromi_numbering import (
    augment_for_export,
    assign_kromi_numbers,
    assign_split_numbers,
    build_article_setup,
    numbering_omission_reason,
)
from engine.multi_location import SHARED_COL

KTC = "191"

# (code, description, tool class, system). Two Kanban drills share the
# dimension fingerprint (variants 00 and 01) and so do two KTC successors.
_ARTICLES = [
    ("A01", "Bohrer D5,0", "solid_carbide_drill", "KTC"),
    ("A02", "Bohrer D5,0 lang", "solid_carbide_drill", "Kanban"),
    ("A03", "Bohrer D5,0 kurz", "solid_carbide_drill", "Kanban"),
    ("A04", "Fraeser D12", "solid_end_mill", "KTC"),
    ("A05", "Fraeser D12 Z4", "solid_end_mill", "KTC"),
    ("A06", "Gewindebohrer M8", "tap", "Kanban"),
    ("A07", "Reibahle D6", "reamer", "KTC"),
]


def _rows(shared_codes=(), *, flag=True, sps=(1, 2)):
    rows = []
    for code, desc, tc, system in _ARTICLES:
        for sp in (sps if code in shared_codes else sps[:1]):
            rows.append({
                "Listing": "Tools", "Code": code, "Description": desc, "ToolClass": tc,
                "SystemCategory": system,
                "CabinetType": "Carousel" if system == "KTC" else "Kanban",
                "PackUnits": 1.0, "SupplyPoint": sp,
            })
    df = pd.DataFrame(rows)
    if flag:
        df[SHARED_COL] = df["Code"].isin(shared_codes)
    return df


_SHARED = ("A01", "A02", "A05", "A06")


def _by_code(frame):
    return dict(zip(frame["Code"], frame["Kromi_Art_No"]))


# ---- the invariant -----------------------------------------------------------------------

def test_the_article_setup_is_the_same_split_or_unsplit():
    split = build_article_setup(_rows(_SHARED), KTC)
    unsplit = build_article_setup(_rows(), KTC)
    pd.testing.assert_frame_equal(split, unsplit)


def test_the_result_numbers_are_the_same_split_or_unsplit():
    split = augment_for_export(_rows(_SHARED), KTC)
    unsplit = augment_for_export(_rows(), KTC)
    want = _by_code(unsplit)
    for code, number in zip(split["Code"], split["Kromi_Art_No"]):
        assert number == want[code], code


def test_every_copy_shows_one_number():
    split = augment_for_export(_rows(_SHARED), KTC)
    per_code = split.groupby("Code")["Kromi_Art_No"].nunique()
    assert (per_code == 1).all()


def test_the_counter_advances_once_per_ktc_article():
    split = assign_split_numbers(_rows(_SHARED, sps=(1, 2, 3)).assign(
        System=lambda d: d["SystemCategory"]), KTC)
    ktc = split[split["System"] == "KTC"]
    counters = {int(n[5:9]) for n in ktc["Kromi_Art_No"]}
    assert counters == set(range(1, ktc["Code"].nunique() + 1))


def test_the_article_setup_lists_each_article_once():
    setup = build_article_setup(_rows(_SHARED), KTC)
    customer = setup[setup["Property"] == "Customer property"]
    assert sorted(customer["Customer article No"]) == sorted(c for c, *_ in _ARTICLES)
    n_ktc = sum(1 for *_x, s in _ARTICLES if s == "KTC")
    assert (setup["Property"] == "KROMI property").sum() == n_ktc


def test_kanban_variants_advance_once_per_article():
    df = _rows(("A02", "A03")).query("SystemCategory == 'Kanban'")
    out = assign_kromi_numbers(df, KTC)
    nums = _by_code(out)
    assert nums["A02"][-3:-1] == "00" and nums["A03"][-3:-1] == "01"
    assert out.groupby("Code")["Kromi_Art_No"].nunique().max() == 1


def test_an_article_ktc_somewhere_takes_the_ktc_number_everywhere():
    # Defensive: the plan never leaves a shared article KTC and Kanban, but if
    # a frame did, the KTC copy decides (the counter runs first).
    df = _rows(("A06",))
    second = df.index[(df["Code"] == "A06") & (df["SupplyPoint"] == 2)][0]
    df.loc[second, ["SystemCategory", "CabinetType"]] = ["KTC", "Carousel"]
    out = augment_for_export(df, KTC)
    a06 = out[out["Code"] == "A06"]["Kromi_Art_No"].unique()
    assert len(a06) == 1 and a06[0][3:5] == "10"
    setup = build_article_setup(df, KTC)
    assert setup.loc[setup["Customer article No"] == "A06", "System"].tolist() == ["KTC", "KTC"]


def test_the_uniqueness_check_accepts_copies_of_one_article():
    out = augment_for_export(_rows(_SHARED), KTC)
    assert check_kromi_uniqueness(out) == []


def test_the_uniqueness_check_still_catches_two_articles_with_one_number():
    out = augment_for_export(_rows(_SHARED), KTC)
    a04 = out.index[out["Code"] == "A04"][0]
    out.loc[a04, "Kromi_Art_No"] = out.loc[out["Code"] == "A01", "Kromi_Art_No"].iloc[0]
    assert check_kromi_uniqueness(out)


def test_without_the_flag_duplicates_are_still_caught():
    out = augment_for_export(_rows(_SHARED), KTC).drop(columns=[SHARED_COL])
    assert check_kromi_uniqueness(out)


def test_the_omission_reason_is_none_for_a_split_frame():
    assert numbering_omission_reason(_rows(_SHARED), KTC) is None


# ---- Replicate is unchanged ---------------------------------------------------------------------

def test_replicate_numbers_are_unchanged_including_their_gaps():
    df = _rows(tuple(c for c, *_ in _ARTICLES), flag=False)
    out = augment_for_export(df, KTC)
    ktc = out[out["System"] == "KTC"]
    # one counter step per row: two copies of four KTC articles -> 1..8
    assert [int(n[5:9]) for n in ktc["Kromi_Art_No"]] == list(range(1, 9))
    setup = build_article_setup(df, KTC)
    pred = setup[(setup["Property"] == "Customer property") & (setup["System"] == "KTC")]
    # the sheet keeps the first occurrence's number: the counter shows gaps
    assert [int(n[5:9]) for n in pred["Kromi_Art_No"]] == [1, 3, 5, 7]


@pytest.mark.parametrize("flag", [False, True])
def test_a_frame_with_every_article_once_is_numbered_as_before(flag):
    df = _rows(flag=flag)
    base = augment_for_export(_rows(flag=False), KTC)
    assert _by_code(augment_for_export(df, KTC)) == _by_code(base)
