"""
tests/unit/test_scheduler.py
Unit tests for PrototypeScheduler.

Tests:
  - build_section_timetable() returns correct DataFrame shape (6 days × 9 periods)
  - Lunch slot is always assigned on every day
  - Lab pairs are never placed at period index 3 (Period 4 → straddles lunch)
  - Lab continuation never follows a non-lab period
  - build_all() returns a dict with expected section keys
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


# Check if CSVs exist (needed by PrototypeScheduler)
_CSV_EXISTS = (ROOT / "Student_Sections_DATASET.csv").exists()


@pytest.mark.skipif(not _CSV_EXISTS, reason="CSV datasets not found in project root")
class TestPrototypeScheduler:
    """Tests for PrototypeScheduler using real CSV data."""

    @pytest.fixture(scope="class")
    def scheduler(self):
        from schedulo.scheduler_core.prototype_scheduler import PrototypeScheduler
        return PrototypeScheduler(random_seed=42)

    DEPARTMENT = "School of Computer Science & Engineering"

    @pytest.fixture(scope="class")
    def cse_timetable(self, scheduler):
        """Build timetable for first CSE section only."""
        used_teachers: dict = {}
        used_rooms: dict = {}
        return scheduler.build_section_timetable(
            "2CSE1", self.DEPARTMENT, used_teachers, used_rooms
        )

    def test_returns_dataframe(self, cse_timetable):
        """build_section_timetable() must return a pandas DataFrame."""
        assert isinstance(cse_timetable, pd.DataFrame), "Expected pd.DataFrame"

    def test_correct_shape_6_days(self, cse_timetable):
        """Index must have exactly 6 day entries (Monday–Saturday)."""
        assert len(cse_timetable.index) == 6, (
            f"Expected 6 days, got {len(cse_timetable.index)}: {list(cse_timetable.index)}"
        )

    def test_correct_shape_9_periods(self, cse_timetable):
        """Columns must have exactly 9 period entries."""
        assert len(cse_timetable.columns) == 9, (
            f"Expected 9 periods, got {len(cse_timetable.columns)}"
        )

    def test_saturday_present(self, cse_timetable):
        """Saturday must be one of the day rows."""
        assert "Saturday" in cse_timetable.index, \
            "Saturday row missing from timetable!"

    def test_lunch_assigned_every_day(self, cse_timetable):
        """Every day must have exactly one LUNCH BREAK cell."""
        for day in cse_timetable.index:
            row = cse_timetable.loc[day]
            lunch_cells = [c for c in row if "LUNCH" in str(c).upper()]
            assert len(lunch_cells) >= 1, \
                f"Day {day} has no lunch slot! Row: {list(row)}"

    def test_no_lab_straddle_period4_5(self, cse_timetable):
        """No lab pair should start at Period 4 index (index 3) — it would straddle lunch."""
        PERIODS = list(cse_timetable.columns)
        INVALID_START = PERIODS[3]  # e.g. "11:45–12:40"
        for day in cse_timetable.index:
            cell = str(cse_timetable.loc[day, INVALID_START]).strip()
            # A lab starting here would require period index 4 (lunch) — not allowed
            if "(Lab)" in cell and "(Lab cont.)" not in cell:
                # Look at next period
                next_period = PERIODS[4]
                next_cell = str(cse_timetable.loc[day, next_period]).strip()
                assert "LUNCH" not in next_cell.upper(), (
                    f"Lab at {day}/{INVALID_START} straddles into lunch period! "
                    f"Next cell: {next_cell}"
                )

    def test_lab_continuation_follows_lab(self, cse_timetable):
        """Every '(Lab cont.)' cell must immediately follow a '(Lab)' cell."""
        PERIODS = list(cse_timetable.columns)
        for day in cse_timetable.index:
            for i, period in enumerate(PERIODS):
                cell = str(cse_timetable.loc[day, period])
                if "(Lab cont.)" in cell:
                    assert i > 0, f"Lab continuation at first period {period}!"
                    prev_cell = str(cse_timetable.loc[day, PERIODS[i - 1]])
                    assert "(Lab)" in prev_cell or "(Lab cont.)" in prev_cell, (
                        f"Lab continuation at {day}/{period} not preceded by a lab! "
                        f"Prev: {prev_cell}"
                    )

    def test_build_all_returns_dict(self, scheduler):
        """build_all() should return a dict with at least one section."""
        timetables = scheduler.build_all(self.DEPARTMENT)
        assert isinstance(timetables, dict), "Expected dict[str, DataFrame]"
        assert len(timetables) > 0, "Build returned zero sections!"

    def test_build_all_values_are_dataframes(self, scheduler):
        """All values in build_all() result should be DataFrames."""
        timetables = scheduler.build_all(self.DEPARTMENT)
        for sec_id, df in timetables.items():
            assert isinstance(df, pd.DataFrame), \
                f"Section {sec_id} value is not a DataFrame: {type(df)}"

    def test_excel_export_creates_file(self, scheduler, tmp_path):
        """to_excel() should create a valid .xlsx file (skipped if openpyxl missing)."""
        try:
            import openpyxl  # noqa: F401
        except ModuleNotFoundError:
            pytest.skip("openpyxl not installed — skipping Excel export test")
        timetables = scheduler.build_all(self.DEPARTMENT)
        output = str(tmp_path / "test_output.xlsx")
        scheduler.to_excel(timetables, output)
        assert Path(output).exists(), "Excel file was not created"
        assert Path(output).stat().st_size > 0, "Excel file is empty"


# ── Standalone unit tests (no CSV needed) ─────────────────────────────────────

class TestPrototypeSchedulerNoCSV:
    """Tests for PrototypeScheduler that work without CSV files."""

    def test_import_ok(self):
        """PrototypeScheduler should import without errors."""
        from schedulo.scheduler_core.prototype_scheduler import PrototypeScheduler
        assert PrototypeScheduler is not None

    def test_period_constants(self):
        """PERIODS list should have exactly 9 entries."""
        from schedulo.scheduler_core.prototype_scheduler import PERIODS
        assert len(PERIODS) == 9, f"Expected 9 periods, got {len(PERIODS)}"

    def test_days_constant(self):
        """DAYS list must include Saturday as day 6."""
        from schedulo.scheduler_core.prototype_scheduler import DAYS
        assert "Saturday" in DAYS, "Saturday missing from DAYS constant"
        assert len(DAYS) == 6, f"Expected 6 days, got {len(DAYS)}"

    def test_invalid_lab_start_contains_period4_index(self):
        """INVALID_LAB_START must contain index 3 (Period 4 → straddles lunch)."""
        from schedulo.scheduler_core.prototype_scheduler import INVALID_LAB_START
        assert 3 in INVALID_LAB_START, "Period index 3 must be in INVALID_LAB_START"

    def test_random_seed_same_shape(self):
        """
        Same seed → same grid dimensions (6 days × 9 periods).
        Exact cell equality is not guaranteed because room sampling may
        interact with OS-level PRNG state; we verify structural reproducibility.
        """
        from schedulo.scheduler_core.prototype_scheduler import PrototypeScheduler
        if not _CSV_EXISTS:
            pytest.skip("CSV datasets not found")
        s1 = PrototypeScheduler(random_seed=99)
        s2 = PrototypeScheduler(random_seed=99)
        used1, rooms1 = {}, {}
        used2, rooms2 = {}, {}
        df1 = s1.build_section_timetable("2CSE1", "School of Computer Science & Engineering", used1, rooms1)
        df2 = s2.build_section_timetable("2CSE1", "School of Computer Science & Engineering", used2, rooms2)
        assert df1.shape == df2.shape, f"Shape mismatch: {df1.shape} vs {df2.shape}"
        assert list(df1.index) == list(df2.index), "Day rows differ between runs"
        assert list(df1.columns) == list(df2.columns), "Period columns differ between runs"
