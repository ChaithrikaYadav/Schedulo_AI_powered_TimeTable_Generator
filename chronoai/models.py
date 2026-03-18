"""
models.py — SQLAlchemy ORM models for ChronoAI.
All table definitions match the schema in PART 2 Section 2.3 of the spec.
Column comment references show exact CSV header mappings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from sqlalchemy import JSON
except ImportError:
    from sqlalchemy import Text as JSON  # SQLite fallback

from chronoai.database import Base


# ─────────────────────────────────────────────────────────────────
# Department
# ─────────────────────────────────────────────────────────────────
class Department(Base):
    """University department registry."""

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)          # e.g. "School of Computer Science & Engineering"
    short_code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)  # e.g. "CSE"
    faculty_count: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    faculty: Mapped[list["Faculty"]] = relationship("Faculty", back_populates="department")
    subjects: Mapped[list["Subject"]] = relationship("Subject", back_populates="department")
    sections: Mapped[list["Section"]] = relationship("Section", back_populates="department")
    timetables: Mapped[list["Timetable"]] = relationship("Timetable", back_populates="department")


# ─────────────────────────────────────────────────────────────────
# Faculty (merged from Teachers_Dataset.csv + faculty_dataset_final.csv)
# ─────────────────────────────────────────────────────────────────
class Faculty(Base):
    """Combined faculty record from both teacher CSV files."""

    __tablename__ = "faculty"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[Optional[str]] = mapped_column(String(20), unique=True)     # "Teacher ID" col — e.g. "T-CSE-001"
    name: Mapped[str] = mapped_column(Text, nullable=False)                         # "Teacher Name" col
    faculty_name: Mapped[Optional[str]] = mapped_column(Text)                       # "Faculty_Name" from faculty_dataset_final.csv
    department_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("departments.id"))
    main_subject: Mapped[Optional[str]] = mapped_column(Text)                       # "Main Subject" col
    backup_subject: Mapped[Optional[str]] = mapped_column(Text)                     # "Backup Subject" col
    subject_handled: Mapped[Optional[str]] = mapped_column(Text)                    # "Subject_Handled" from faculty_dataset_final.csv
    max_classes_per_week: Mapped[Optional[int]] = mapped_column(Integer)            # "Max Classes/Week" col
    preferred_slots: Mapped[Optional[str]] = mapped_column(String(50))              # Morning|Afternoon|No 1st Period|Any
    can_take_labs: Mapped[Optional[bool]] = mapped_column(Boolean)                  # "Can Take Labs": Yes→True
    can_be_coordinator: Mapped[Optional[bool]] = mapped_column(Boolean)             # "Can Be Class Coordinator"
    available_days: Mapped[Optional[str]] = mapped_column(JSON)                     # {"Monday": true, "Saturday": false, ...}
    unavailable_slots: Mapped[Optional[str]] = mapped_column(JSON)                  # [[day, period], ...]
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="faculty")
    subject_assignments: Mapped[list["SubjectAssignment"]] = relationship("SubjectAssignment", back_populates="faculty")
    conversations: Mapped[list["ChatbotConversation"]] = relationship("ChatbotConversation", back_populates="faculty")


# ─────────────────────────────────────────────────────────────────
# Subject (merged from Subjects_Dataset.csv + course_dataset_final.csv)
# ─────────────────────────────────────────────────────────────────
class Subject(Base):
    """Subject catalogue with weekly period calculation."""

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)                         # "Subject Name" / "Subject" col
    department_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("departments.id"))
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)           # Theory|Lab|Project
    credits: Mapped[Optional[float]] = mapped_column(Numeric(3, 1))                 # float from course_dataset_final.csv
    weekly_periods: Mapped[Optional[int]] = mapped_column(Integer)                  # derived: Theory→credits, Lab→2, Project→1
    requires_consecutive_lab: Mapped[bool] = mapped_column(Boolean, default=False)  # True when subject_type='Lab'
    lab_duration_periods: Mapped[int] = mapped_column(Integer, default=1)           # 2 for all Lab types
    semester: Mapped[Optional[str]] = mapped_column(String(20))                     # inferred from section data

    # Relationships
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="subjects")
    subject_assignments: Mapped[list["SubjectAssignment"]] = relationship("SubjectAssignment", back_populates="subject")


# ─────────────────────────────────────────────────────────────────
# Room (from Room_Dataset.csv — 132 rooms)
# ─────────────────────────────────────────────────────────────────
class Room(Base):
    """Physical room / lab registry."""

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)   # "Room ID" col: "ENG-101"
    building: Mapped[str] = mapped_column(String(20), nullable=False)               # "Building" col: ENG|SVH|...
    floor: Mapped[Optional[int]] = mapped_column(Integer)                           # "Floor" col
    room_number: Mapped[Optional[str]] = mapped_column(String(30))                  # "Room Number" col
    room_type: Mapped[str] = mapped_column(String(20), nullable=False)              # Classroom|Lab|Special
    department: Mapped[Optional[str]] = mapped_column(Text)                         # "Department" col
    capacity: Mapped[int] = mapped_column(Integer, default=60)                      # default 60
    has_projector: Mapped[bool] = mapped_column(Boolean, default=True)
    has_computers: Mapped[Optional[bool]] = mapped_column(Boolean)                  # True for Lab type rooms

    # Relationships
    sections: Mapped[list["Section"]] = relationship("Section", back_populates="primary_room")
    timetable_slots: Mapped[list["TimetableSlot"]] = relationship("TimetableSlot", back_populates="room")


# ─────────────────────────────────────────────────────────────────
# Section (from Student_Sections_DATASET.csv — 117 sections)
# ─────────────────────────────────────────────────────────────────
class Section(Base):
    """Student section registry."""

    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # "Section_ID" col: "2CSE1"
    department_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("departments.id"))
    duration_years: Mapped[Optional[int]] = mapped_column(Integer)                    # "Duration (Years)" col
    semester: Mapped[Optional[str]] = mapped_column(String(20))                       # "Semester" col: "Sem 1"
    strength: Mapped[Optional[int]] = mapped_column(Integer)                          # "Strength" col (40–60)
    program: Mapped[Optional[str]] = mapped_column(Text)                              # "Program" col: "B.Tech CSE"
    primary_room_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("rooms.id"))
    group_a_count: Mapped[Optional[int]] = mapped_column(Integer)                     # approx strength // 2
    group_b_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="sections")
    primary_room: Mapped[Optional["Room"]] = relationship("Room", back_populates="sections")
    subject_assignments: Mapped[list["SubjectAssignment"]] = relationship("SubjectAssignment", back_populates="section")
    timetable_slots: Mapped[list["TimetableSlot"]] = relationship("TimetableSlot", back_populates="section")


# ─────────────────────────────────────────────────────────────────
# SubjectAssignment — links Subject + Faculty + Section
# ─────────────────────────────────────────────────────────────────
class SubjectAssignment(Base):
    """Maps a subject to a faculty member and section for a given timetable cycle."""

    __tablename__ = "subject_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id"))
    faculty_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("faculty.id"))
    section_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sections.id"))
    group_designation: Mapped[Optional[str]] = mapped_column(String(5))              # NULL | G1 | G2
    is_elective: Mapped[bool] = mapped_column(Boolean, default=False)
    elective_group_code: Mapped[Optional[str]] = mapped_column(String(10))           # E-2, E-3, etc.
    weekly_periods_required: Mapped[Optional[int]] = mapped_column(Integer)          # from subject.weekly_periods

    # Relationships
    subject: Mapped[Optional["Subject"]] = relationship("Subject", back_populates="subject_assignments")
    faculty: Mapped[Optional["Faculty"]] = relationship("Faculty", back_populates="subject_assignments")
    section: Mapped[Optional["Section"]] = relationship("Section", back_populates="subject_assignments")
    timetable_slots: Mapped[list["TimetableSlot"]] = relationship("TimetableSlot", back_populates="subject_assignment")


# ─────────────────────────────────────────────────────────────────
# Timetable — root record per generation run
# ─────────────────────────────────────────────────────────────────
class Timetable(Base):
    """A complete timetable generation run."""

    __tablename__ = "timetables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(Text)
    department_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("departments.id"))
    academic_year: Mapped[Optional[str]] = mapped_column(String(10))                 # e.g. "2025-26"
    semester: Mapped[Optional[str]] = mapped_column(String(20))                      # Sem 1|Sem 3|...
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")                 # DRAFT|GENERATING|COMPLETED|FAILED
    generation_params: Mapped[Optional[str]] = mapped_column(JSON)                   # GA params, random seed, etc.
    ga_fitness_score: Mapped[Optional[float]] = mapped_column(Float)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    generation_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="timetables")
    slots: Mapped[list["TimetableSlot"]] = relationship("TimetableSlot", back_populates="timetable", cascade="all, delete-orphan")
    conflict_logs: Mapped[list["ConflictLog"]] = relationship("ConflictLog", back_populates="timetable")
    ml_training_data: Mapped[list["MLTrainingData"]] = relationship("MLTrainingData", back_populates="timetable")


# ─────────────────────────────────────────────────────────────────
# TimetableSlot — individual (day, period) assignment
# ─────────────────────────────────────────────────────────────────
class TimetableSlot(Base):
    """A single day+period slot within a timetable."""

    __tablename__ = "timetable_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timetable_id: Mapped[int] = mapped_column(Integer, ForeignKey("timetables.id", ondelete="CASCADE"))
    section_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sections.id"))
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)                # 0=Monday … 5=Saturday
    day_name: Mapped[str] = mapped_column(String(15), nullable=False)                # "Monday" … "Saturday"
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)              # 1–9
    period_label: Mapped[str] = mapped_column(String(20), nullable=False)            # "9:00–9:55" etc.
    subject_assignment_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subject_assignments.id"))
    room_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("rooms.id"))
    slot_type: Mapped[str] = mapped_column(String(20), nullable=False)               # THEORY|LAB|PROJECT|LUNCH|FREE
    is_lab_continuation: Mapped[bool] = mapped_column(Boolean, default=False)        # True for 2nd period of lab pair
    lab_group: Mapped[Optional[str]] = mapped_column(String(5))                      # G1|G2|None
    cell_display_line1: Mapped[Optional[str]] = mapped_column(Text)                  # Subject name
    cell_display_line2: Mapped[Optional[str]] = mapped_column(Text)                  # Faculty name
    cell_display_line3: Mapped[Optional[str]] = mapped_column(Text)                  # Room ID
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    timetable: Mapped["Timetable"] = relationship("Timetable", back_populates="slots")
    section: Mapped[Optional["Section"]] = relationship("Section", back_populates="timetable_slots")
    subject_assignment: Mapped[Optional["SubjectAssignment"]] = relationship("SubjectAssignment", back_populates="timetable_slots")
    room: Mapped[Optional["Room"]] = relationship("Room", back_populates="timetable_slots")
    conflict_logs_as_slot1: Mapped[list["ConflictLog"]] = relationship("ConflictLog", foreign_keys="ConflictLog.slot_1_id", back_populates="slot_1")
    conflict_logs_as_slot2: Mapped[list["ConflictLog"]] = relationship("ConflictLog", foreign_keys="ConflictLog.slot_2_id", back_populates="slot_2")


# ─────────────────────────────────────────────────────────────────
# ConflictLog
# ─────────────────────────────────────────────────────────────────
class ConflictLog(Base):
    """Records detected scheduling conflicts with their resolution status."""

    __tablename__ = "conflict_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timetable_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("timetables.id"))
    conflict_type: Mapped[Optional[str]] = mapped_column(String(10))                 # CF-01 through CF-09
    severity: Mapped[Optional[str]] = mapped_column(String(20))                      # CRITICAL|HIGH|MEDIUM|LOW|INFO
    description: Mapped[Optional[str]] = mapped_column(Text)
    slot_1_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("timetable_slots.id"))
    slot_2_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("timetable_slots.id"))
    auto_fixable: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resolution_method: Mapped[Optional[str]] = mapped_column(String(20))             # SWAP|REASSIGN|MANUAL|AUTO

    # Relationships
    timetable: Mapped[Optional["Timetable"]] = relationship("Timetable", back_populates="conflict_logs")
    slot_1: Mapped[Optional["TimetableSlot"]] = relationship("TimetableSlot", foreign_keys=[slot_1_id], back_populates="conflict_logs_as_slot1")
    slot_2: Mapped[Optional["TimetableSlot"]] = relationship("TimetableSlot", foreign_keys=[slot_2_id], back_populates="conflict_logs_as_slot2")


# ─────────────────────────────────────────────────────────────────
# ChatbotConversation
# ─────────────────────────────────────────────────────────────────
class ChatbotConversation(Base):
    """Persistent chat session record for ChronoBot."""

    __tablename__ = "chatbot_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timetable_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("timetables.id"))
    faculty_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("faculty.id"))
    session_id: Mapped[str] = mapped_column(String(100), unique=True)
    messages: Mapped[Optional[str]] = mapped_column(JSON, default="[]")              # [{role, content, timestamp}]
    last_modification: Mapped[Optional[str]] = mapped_column(JSON)                   # last applied change for undo
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    faculty: Mapped[Optional["Faculty"]] = relationship("Faculty", back_populates="conversations")


# ─────────────────────────────────────────────────────────────────
# MLTrainingData
# ─────────────────────────────────────────────────────────────────
class MLTrainingData(Base):
    """Stores features and quality metadata for ML model training."""

    __tablename__ = "ml_training_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timetable_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("timetables.id"))
    features: Mapped[Optional[str]] = mapped_column(JSON)                            # engineered feature dict
    quality_score: Mapped[Optional[float]] = mapped_column(Float)
    conflict_count: Mapped[Optional[int]] = mapped_column(Integer)
    generation_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    ga_generations_run: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    timetable: Mapped[Optional["Timetable"]] = relationship("Timetable", back_populates="ml_training_data")
