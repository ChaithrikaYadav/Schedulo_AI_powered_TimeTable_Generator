# scripts/clean_subjects_table.py
# One-time cleanup: remove duplicate subjects and wrong-department subjects
# from the existing subjects table in schedulo.db.
#
# Run once from the project root:
#   python scripts/clean_subjects_table.py

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "schedulo.db"

# Hospitality subjects that were incorrectly tagged as CSE (department_id=1)
HOSPITALITY_SUBJECTS = [
    "Bakery & Confectionery Lab", "F&B Service Lab", "Bar Operations Lab",
    "Bakery Advanced Lab", "Food Production Lab", "Basics of Food Production",
    "Front Office Management", "Housekeeping Operations", "Resort Management",
    "Tourism Geography", "Gastronomy", "Industrial Exposure Training",
    "Wine Studies", "Nutrition & Hygiene", "Culinary Art", "Hotel Accounting",
    "Food & Beverage Service", "French Language for Hospitality",
    "Food Cost Control", "Hospitality Law", "Hospitality Ethics",
]

# Management subjects that were incorrectly tagged as CSE (department_id=1)
MANAGEMENT_SUBJECTS = [
    "Business Economics", "Business Law", "Financial Management",
    "Financial Accounting", "Corporate Finance", "Taxation Laws",
    "Marketing Management", "Human Resource Management",
    "Banking & Insurance", "Entrepreneurship Development",
    "Organizational Behavior", "Consumer Behavior", "Retail Management",
    "CRM Systems", "Supply Chain Management", "E-Commerce",
    "Advertising & Sales", "Internship Project",
]

WRONG_CSE_SUBJECTS = HOSPITALITY_SUBJECTS + MANAGEMENT_SUBJECTS


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    cur  = conn.cursor()

    # ── Step 1: Remove wrong-department subjects from CSE (department_id=1) ──
    placeholders = ",".join("?" * len(WRONG_CSE_SUBJECTS))
    cur.execute(
        f"DELETE FROM subjects WHERE department_id=1 AND name IN ({placeholders})",
        WRONG_CSE_SUBJECTS,
    )
    removed_wrong = cur.rowcount
    print(f"Removed {removed_wrong} wrong-department subjects from CSE (dept_id=1)")

    # ── Step 2: Remove duplicate subjects (keep the row with the lowest id) ──
    cur.execute("""
        DELETE FROM subjects
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM subjects
            GROUP BY name, department_id, subject_type
        )
    """)
    removed_dups = cur.rowcount
    print(f"Removed {removed_dups} duplicate subject rows")

    # ── Step 3: Verify ────────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM subjects")
    total = cur.fetchone()[0]
    cur.execute(
        f"SELECT COUNT(*) FROM subjects WHERE department_id=1 AND name IN ({placeholders})",
        WRONG_CSE_SUBJECTS,
    )
    remaining_wrong = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT name, department_id, subject_type
            FROM subjects
            GROUP BY name, department_id, subject_type
            HAVING COUNT(*) > 1
        )
    """)
    remaining_dups = cur.fetchone()[0]

    conn.commit()
    conn.close()

    print(f"\n✅ subjects table cleanup complete.")
    print(f"   Total rows remaining : {total}")
    print(f"   Wrong-dept remaining : {remaining_wrong}  (should be 0)")
    print(f"   Duplicate groups     : {remaining_dups}  (should be 0)")


if __name__ == "__main__":
    main()
