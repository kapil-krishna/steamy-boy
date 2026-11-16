from steamy_boy.cli import reviews_summary
from steamy_boy.ingest import ReviewsResult


def result(**overrides) -> ReviewsResult:
    fields = {"pages": 58, "fetched": 5705, "written": 5705, "steam_total": 5705, "stored": 5700}
    return ReviewsResult(**(fields | overrides))


def test_summary_passes_r1_within_one_percent():
    assert "(0.1% gap): OK" in reviews_summary(result())


def test_summary_flags_a_gap_over_one_percent():
    assert "MORE THAN 1% OFF" in reviews_summary(result(stored=5000))


def test_summary_reports_deletions_and_skipped_deletions():
    assert "Marked 3 as deleted" in reviews_summary(result(marked_deleted=3))
    assert "none were marked deleted" in reviews_summary(result(deletion_skipped=True))


def test_summary_omits_the_r1_check_when_steam_gave_no_total():
    assert "gap" not in reviews_summary(result(steam_total=None))
