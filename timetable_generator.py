
import pandas as pd
import numpy as np
import random
from difflib import get_close_matches

# =======================
# Load all datasets
# =======================
room = pd.read_csv("Room_Dataset.csv")
section = pd.read_csv("Student_Sections_DATASET.csv")
subjects = pd.read_csv("Subjects_Dataset.csv")
teachers = pd.read_csv("Teachers_Dataset.csv")

# =======================
# Clean data
# =======================
def _s(x):
    if pd.isna(x):
        return ""
    return str(x).strip()

subjects["Department"] = subjects["Department"].map(_s)
teachers["Department"] = teachers["Department"].map(_s)

# Filter department
DEPARTMENT_NAME = "School of Computer Science & Engineering"
engineering_subjects = subjects[subjects["Department"] == DEPARTMENT_NAME]

# =======================
# Define structure
# =======================
Day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
periods = [
    "9:00–9:55", "9:55–10:50", "10:50–11:45", "11:45–12:40",
    "12:40–1:35", "1:35–2:30", "2:30–3:25", "3:25–4:20", "4:20–5:15"
]

# =======================
# Build teacher-subject map
# =======================
teacher_subject_map = {}

for col in ["Teacher ID", "Teacher Name", "Main Subject", "Backup Subject", "Can Take Labs"]:
    if col not in teachers.columns:
        teachers[col] = ""

def as_bool_for_lab(x):
    x = str(x).strip().lower()
    return x in {"yes", "y", "true", "1"}

for _, row in teachers.iterrows():
    if _s(row["Department"]) == DEPARTMENT_NAME:
        teach_id = _s(row["Teacher ID"])
        teacher_name = _s(row["Teacher Name"])
        main_subject = _s(row.get("Main Subject", ""))
        backup_subject = _s(row.get("Backup Subject", ""))
        can_take_lab = as_bool_for_lab(row.get("Can Take Labs", ""))
        room_type = "Lab" if can_take_lab else "Classroom"

        for subj in [main_subject, backup_subject]:
            if subj:
                teacher_subject_map.setdefault(subj, []).append({
                    "Teacher ID": teach_id,
                    "Teacher Name": teacher_name,
                    "Type": room_type
                })

print(f"\n✅ Teacher–Subject map built with {len(teacher_subject_map)} subjects")

# =======================
# Timetable generation
# =======================
def build_timetable(department=DEPARTMENT_NAME):
    if "Department" not in section.columns or "Section_ID" not in section.columns:
        raise KeyError("❌ Student_Sections_DATASET.csv must have 'Department' and 'Section_ID' columns")

    if "Semester" not in section.columns:
        raise KeyError("❌ Student_Sections_DATASET.csv must have a 'Semester' column")

    sections = section[section["Department"] == department]["Section_ID"].unique()
    print(f"\n📘 Generating timetable for {len(sections)} sections under {department}...")

    timetable = {}
    used_teachers = {}

    for sec in sections:
        # find semester
        semester = section.loc[section["Section_ID"] == sec, "Semester"].values[0]

        df = pd.DataFrame("", index=Day, columns=periods)
       
        # Choose ONE lunch slot for entire section
        lunch_slot = random.choice(["12:40–1:35", "1:35–2:30"])
        # Assign lunch for all days
        for day in Day:
            df.loc[day, lunch_slot] = "Lunch Break 🍴"
        subj_list = list(engineering_subjects["Subject Name"])
        np.random.shuffle(subj_list)

        # random 5-6 subjects for section (simulating semester load)
        subj_list = subj_list[:random.randint(5, 8)]

        teacher_assignments = {}
        for subj in subj_list:
            match = get_close_matches(subj.lower(), [s.lower() for s in teacher_subject_map.keys()], n=1, cutoff=0.6)
            if match:
                matched_key = next(k for k in teacher_subject_map.keys() if k.lower() == match[0])
                teacher_assignments[subj] = random.choice(teacher_subject_map[matched_key])
            else:
                teacher_assignments[subj] = {
                    "Teacher ID": f"T{random.randint(100,999)}",
                    "Teacher Name": "TBA",
                    "Type": "Classroom"
                }

        # assign classes across week
        for subj, teach in teacher_assignments.items():
            weekly_classes = random.randint(2, 6)  # based on credits roughly
            assigned_slots = 0
            attempts = 0

            while assigned_slots < weekly_classes and attempts < 50:
                attempts += 1
                d = random.choice(Day)
                p_idx = random.randint(0, len(periods) - 1)


                # Lunch break (skip)
                if periods[p_idx] == lunch_slot:
                    continue

                # Avoid teacher conflict
                if teach["Teacher ID"] in used_teachers.get((d, periods[p_idx]), []):
                    continue

                # If lab, reserve 2 consecutive slots
                if teach["Type"] == "Lab" and p_idx < len(periods) - 1:
                    if df.loc[d, periods[p_idx]] == "" and df.loc[d, periods[p_idx + 1]] == "":
                        available_rooms = room[room["Type"] == "Lab"]
                        if not available_rooms.empty:
                            selected_room = available_rooms.sample(1)["Room ID"].values[0]
                            df.loc[d, periods[p_idx]] = f"{subj} (Lab)\n{teach['Teacher Name']}\nRoom {selected_room}"
                            df.loc[d, periods[p_idx + 1]] = f"{subj} (Lab)\n{teach['Teacher Name']}\nRoom {selected_room}"
                            used_teachers.setdefault((d, periods[p_idx]), []).append(teach["Teacher ID"])
                            used_teachers.setdefault((d, periods[p_idx + 1]), []).append(teach["Teacher ID"])
                            assigned_slots += 2
                else:
                    # Regular class
                    if df.loc[d, periods[p_idx]] == "":
                        available_rooms = room[room["Type"] == "Classroom"]
                        if not available_rooms.empty:
                            selected_room = available_rooms.sample(1)["Room ID"].values[0]
                            df.loc[d, periods[p_idx]] = f"{subj}\n{teach['Teacher Name']}\nRoom {selected_room}"
                            used_teachers.setdefault((d, periods[p_idx]), []).append(teach["Teacher ID"])
                            assigned_slots += 1


        timetable[sec] = df

    return timetable


# =======================
# Run and print
# =======================
if __name__ == "__main__":
    tt = build_timetable(DEPARTMENT_NAME)
    for sec, df in tt.items():
        print(f"\n===== Timetable for {sec} =====")
        print(df)
