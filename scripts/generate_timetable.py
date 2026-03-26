"""
scripts/generate_timetable.py — Standalone CLI for timetable generation.

Generates timetables without needing the FastAPI server running.
Outputs Excel (.xlsx) and CSV ZIP to the outputs/ directory.

Usage:
    # Generate CSE timetables (default):
    python scripts/generate_timetable.py

    # Specify department and seed:
    python scripts/generate_timetable.py --dept "School of Management" --seed 42

    # Export only Excel:
    python scripts/generate_timetable.py --no-zip

    # Custom output directory:
    python scripts/generate_timetable.py --output-dir ./my_outputs

    # Print timetable to console (first section only):
    python scripts/generate_timetable.py --preview
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Schedulo — Standalone Timetable Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/generate_timetable.py\n"
            "  python scripts/generate_timetable.py --dept \"School of Management\" --seed 42\n"
            "  python scripts/generate_timetable.py --all-depts --preview\n"
        ),
    )
    parser.add_argument(
        "--dept", "--department",
        default="School of Computer Science & Engineering",
        metavar="DEPARTMENT",
        help="Full department name (default: School of Computer Science & Engineering)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducibility (default: random)",
    )
    parser.add_argument(
        "--output-dir", default=str(ROOT / "outputs"),
        metavar="DIR",
        help="Output directory for generated files (default: ./outputs)",
    )
    parser.add_argument(
        "--no-zip", action="store_true",
        help="Skip CSV ZIP export",
    )
    parser.add_argument(
        "--no-excel", action="store_true",
        help="Skip Excel export",
    )
    parser.add_argument(
        "--preview", action="store_true",
        help="Print the first section's timetable to console",
    )
    parser.add_argument(
        "--all-depts", action="store_true",
        help="Generate timetables for ALL departments (overrides --dept)",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build list of departments to process
    ALL_DEPARTMENTS = [
        "School of Computer Science & Engineering",
        "School of Management",
        "IILM Law School",
        "School of Hospitality & Services Management",
        "School of Design",
        "School of Psychology",
        "School of Journalism & Communication",
        "School of Liberal Arts & Social Sciences",
        "School of Biotechnology",
    ]

    departments = ALL_DEPARTMENTS if args.all_depts else [args.dept]

    print("\n=== Schedulo -- Timetable Generator ===")
    print("=" * 55)
    print(f"  Output directory : {output_dir}")
    print(f"  Random seed      : {args.seed if args.seed is not None else 'random'}")
    print(f"  Departments      : {len(departments)}")
    print()

    # Import scheduler
    try:
        from schedulo.scheduler_core.prototype_scheduler import PrototypeScheduler
    except ImportError as e:
        print(f"[ERROR] Import error: {e}")
        print("   Make sure you are running from the project root and .venv is active.")
        sys.exit(1)

    total_sections = 0
    generated_files: list[str] = []

    for dept in departments:
        _seed = args.seed
        scheduler = PrototypeScheduler(random_seed=_seed)

        print(f"[*] Generating: {dept}")
        start = time.time()

        try:
            timetables = scheduler.build_all(dept)
        except KeyError as e:
            print(f"   [SKIP] No sections found: {e}")
            continue
        except Exception as e:
            print(f"   [ERROR] {e}")
            continue

        elapsed_ms = int((time.time() - start) * 1000)
        n = len(timetables)
        total_sections += n

        if n == 0:
            print("   [WARN] No sections generated for this department -- check CSV data.")
            continue

        # Build a safe filename prefix from dept name
        safe_dept = (
            dept.replace("School of ", "")
                .replace("&", "and")
                .replace(" ", "_")
                .replace("/", "-")
        )
        ts = time.strftime("%Y%m%d_%H%M%S")
        file_prefix = f"timetable_{safe_dept}_{ts}"
        if _seed is not None:
            file_prefix += f"_seed{_seed}"

        # Excel export
        if not args.no_excel:
            xlsx_path = output_dir / f"{file_prefix}.xlsx"
            scheduler.to_excel(timetables, str(xlsx_path))
            generated_files.append(str(xlsx_path))

        # CSV ZIP export
        if not args.no_zip:
            zip_path = output_dir / f"{file_prefix}.zip"
            scheduler.to_csv_zip(timetables, str(zip_path))
            generated_files.append(str(zip_path))

        print(f"   [OK] {n} sections generated in {elapsed_ms}ms")

        # Preview: print first section as ASCII table
        if args.preview:
            first_sec = next(iter(timetables))
            df = timetables[first_sec]
            print(f"\n   [PREVIEW] Section {first_sec}")
            print("   " + "-" * 80)
            # Truncate cell text for display
            display_df = df.copy()
            for col in display_df.columns:
                display_df[col] = display_df[col].apply(
                    lambda x: str(x)[:18].replace("\n", " | ") if x else "—"
                )
            try:
                # Try tabulate for pretty output
                from tabulate import tabulate
                print(tabulate(
                    display_df,
                    headers=[""] + [p[:8] for p in df.columns],
                    tablefmt="simple",
                    showindex=True,
                ))
            except ImportError:
                # Fallback: plain pandas print
                print(display_df.to_string())
            print()

        print()

    # ── Summary ──────────────────────────────────────────────────────────────
    print("=" * 55)
    print(f"[DONE] {total_sections} sections generated across {len(departments)} department(s)")
    print(f"\nOutput files ({len(generated_files)} total):")
    for f in generated_files:
        size_kb = Path(f).stat().st_size // 1024 if Path(f).exists() else 0
        print(f"   {f}  ({size_kb} KB)")

    if not generated_files:
        print("   (no files generated)")


if __name__ == "__main__":
    main()
