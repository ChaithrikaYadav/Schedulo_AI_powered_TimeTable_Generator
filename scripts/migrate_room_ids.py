# scripts/migrate_room_ids.py
# One-time migration: backfill room_id FK in all existing timetable_slots
# by resolving the room string in cell_display_line3 against the rooms table.
#
# Run once from the project root:
#   python scripts/migrate_room_ids.py

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "schedulo.db"


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    cur  = conn.cursor()

    # Build room lookup: room_id_string → rooms.id
    cur.execute("SELECT id, room_id FROM rooms")
    room_map: dict[str, int] = {row[1]: row[0] for row in cur.fetchall()}
    print(f"Loaded {len(room_map)} rooms from rooms table.")

    # Find all slots where room_id is NULL but cell_display_line3 has a value
    cur.execute("""
        SELECT id, cell_display_line3
        FROM timetable_slots
        WHERE room_id IS NULL
          AND cell_display_line3 IS NOT NULL
          AND cell_display_line3 != ''
          AND slot_type NOT IN ('LUNCH', 'FREE', 'Lunch', 'Free')
    """)
    rows = cur.fetchall()
    print(f"Found {len(rows)} slots with NULL room_id and a room string in cell_display_line3.")

    updated = 0
    unresolved: list[str] = []
    for slot_id, room_str in rows:
        room_pk = room_map.get(room_str)
        if room_pk:
            cur.execute(
                "UPDATE timetable_slots SET room_id=? WHERE id=?",
                (room_pk, slot_id)
            )
            updated += 1
        else:
            unresolved.append(room_str)

    conn.commit()
    conn.close()

    print(f"✅ Backfilled room_id for {updated} slots out of {len(rows)} checked.")
    if unresolved:
        unique_unresolved = sorted(set(unresolved))
        print(f"⚠️  {len(unique_unresolved)} unique room strings could NOT be resolved:")
        for r in unique_unresolved[:20]:
            print(f"   {r!r}")


if __name__ == "__main__":
    main()
