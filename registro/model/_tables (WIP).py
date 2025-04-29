# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Defines the SQLAlchemy models for a student meal/snack reservation system.
Includes tables for students, groups, snacks, reservations, sessions,
and consumption records.
"""
import datetime
from typing import List, Optional

from sqlalchemy import (Boolean, Column, Date, DateTime, ForeignKey, Integer,
                        String, Table, Time, UniqueConstraint)
from sqlalchemy.orm import (Mapped, declarative_base, mapped_column,
                            relationship)

# Define the base class for declarative models
Base = declarative_base()

# --- Association Tables ---

# Many-to-many relationship between Students and Groups
student_group_association = Table(
    "student_group_association",
    Base.metadata,
    Column("student_id", Integer, ForeignKey(
        "students.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey(
        "groups.id", ondelete="CASCADE"), primary_key=True),
)

# Many-to-many relationship between Sessions and Groups
# A session can be applicable to multiple groups, and a group can attend multiple sessions.
session_group_association = Table(
    "session_group_association",
    Base.metadata,
    Column("session_id", Integer, ForeignKey(
        "sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey(
        "groups.id", ondelete="CASCADE"), primary_key=True),
)

# --- Model Classes ---

# pylint: disable=too-few-public-methods


class Group(Base):
    """Represents a group or class of students."""
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Consistent naming: 'name' instead of 'nome'
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Name of the group or class")

    # Relationship to Students (many-to-many)
    students: Mapped[List["Student"]] = relationship(
        secondary=student_group_association,
        back_populates="groups",
        lazy="select"  # 'select' is often a good default loading strategy
    )
    # Relationship to Sessions (many-to-many)
    sessions: Mapped[List["Session"]] = relationship(
        secondary=session_group_association,
        back_populates="applicable_groups",
        lazy="select"
    )

    def __repr__(self):
        """Returns a string representation of the Group object."""
        return f"<Group(id={self.id}, name='{self.name!r}')>"

# pylint: disable=too-few-public-methods


class Student(Base):
    """Represents a student in the system."""
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Renamed 'pront' to 'registration_id' for clarity. Add comment if 'pront' has specific meaning.
    registration_id: Mapped[str] = mapped_column(String(
        50), unique=True, nullable=False, comment="Unique student registration identifier")
    # Consistent naming: 'name' instead of 'nome'
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Full name of the student")

    # Relationship to Groups (many-to-many)
    groups: Mapped[List["Group"]] = relationship(
        secondary=student_group_association,
        back_populates="students",
        lazy="select"
    )
    # Relationship to Reserves (one-to-many)
    reserves: Mapped[List["Reserve"]] = relationship(
        back_populates="student",
        # If a student is deleted, their reservations are also deleted
        cascade="all, delete-orphan"
    )
    # Relationship to Consumptions (one-to-many)
    consumptions: Mapped[List["Consumption"]] = relationship(
        back_populates="student",
        # If a student is deleted, their consumption records are also deleted
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        """Returns a string representation of the Student object."""
        return f"<Student(id={self.id}, registration_id='{self.registration_id!r}', name='{self.name!r}')>"


# pylint: disable=too-few-public-methods
class Snack(Base):
    """Represents a type of snack available for reservation or consumption."""
    __tablename__ = "snacks"  # Changed table name to plural for consistency

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Name of the snack")
    # Consider adding more fields like description, price, nutritional info, etc.

    def __repr__(self):
        """Returns a string representation of the Snack object."""
        return f"<Snack(id={self.id}, name='{self.name!r}')>"

# pylint: disable=too-few-public-methods


class Reserve(Base):
    """Represents a student's reservation for a meal or snack."""
    __tablename__ = "reserves"  # Changed table name to plural for consistency

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        # Changed ondelete to CASCADE
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False
    )
    # Use Date type for dates
    reservation_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False, comment="Date for which the reservation is made")
    # Optional: Link to a specific dish/meal item if needed
    # dish_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dishes.id")) # Example if you add a Dish table
    dish_description: Mapped[Optional[str]] = mapped_column(
        String(255), comment="Description of the main dish reserved, if applicable")

    # Renamed 'snacks' to 'is_snack_reservation' for clarity.
    # If multiple specific snacks can be reserved, a many-to-many relationship with Snack table is better.
    is_snack_reservation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="True if this reservation is for snacks, False if for a main meal")
    canceled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="True if the reservation has been canceled")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), comment="Timestamp when the reservation was created")
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc), comment="Timestamp when the reservation was last updated")

    # Relationship to Student (many-to-one)
    student: Mapped["Student"] = relationship(back_populates="reserves")
    # Relationship to Consumption (one-to-one)
    consumption: Mapped[Optional["Consumption"]] = relationship(
        back_populates="reserve",
        uselist=False,  # Ensures it's a one-to-one relationship
        # If reservation is deleted, linked consumption is deleted
        cascade="all, delete-orphan"
    )

    # Consider adding a relationship to Session if reservations are tied to specific sessions

    __table_args__ = (
        UniqueConstraint(
            "student_id", "reservation_date", "is_snack_reservation",
            name="uq_student_date_snack_type",  # More descriptive constraint name
            # Consider using RAISE or handling conflicts in application logic instead of IGNORE
            # sqlite_on_conflict="IGNORE"
        ),
    )

    def __repr__(self) -> str:
        """Returns a string representation of the Reserve object."""
        return (
            f"<Reserve(id={self.id}, student_id={self.student_id}, date={self.reservation_date!r}, "
            f"is_snack={self.is_snack_reservation!r}, canceled={self.canceled!r})>"
        )

# pylint: disable=too-few-public-methods


class Session(Base):
    """Represents a specific meal/snack distribution session."""
    __tablename__ = "sessions"  # Changed table name to plural for consistency

    id: Mapped[int] = mapped_column(primary_key=True)
    # Consistent naming and clarity
    meal_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Type of meal (e.g., Lunch, Dinner, Snack)")
    period: Mapped[Optional[str]] = mapped_column(String(
        50), comment="Associated period (e.g., Morning, Afternoon), if applicable")
    # Use Date and Time types
    session_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False, comment="Date of the session")
    start_time: Mapped[datetime.time] = mapped_column(
        Time, nullable=False, comment="Start time of the session")
    end_time: Mapped[Optional[datetime.time]] = mapped_column(
        Time, comment="End time of the session")

    # Relationship to Groups (many-to-many) - Replaces the 'groups' string column
    applicable_groups: Mapped[List["Group"]] = relationship(
        secondary=session_group_association,
        back_populates="sessions",
        lazy="select"
    )
    # Relationship to Consumptions (one-to-many)
    consumptions: Mapped[List["Consumption"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan"  # If session is deleted, consumptions are deleted
    )

    __table_args__ = (
        UniqueConstraint(
            'meal_type', 'session_date', 'start_time',
            name="uq_session_time",  # More descriptive constraint name
            # Consider RAISE or handling conflicts in application logic
            # sqlite_on_conflict="REPLACE" # REPLACE can be dangerous, might orphan data
        ),
    )

    def __repr__(self):
        """Returns a string representation of the Session object."""
        return (f"<Session(id={self.id}, meal='{self.meal_type!r}', date='{self.session_date!r}', "
                f"start='{self.start_time!r}')>")

# pylint: disable=too-few-public-methods


class Consumption(Base):
    """Represents a record of a student consuming a meal or snack during a session."""
    __tablename__ = "consumptions"  # Changed table name to plural for consistency

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        # Keep RESTRICT if you want to prevent student deletion if consumptions exist
        ForeignKey("students.id", ondelete="RESTRICT"),
        nullable=False
    )
    session_id: Mapped[int] = mapped_column(
        # Keep RESTRICT to prevent session deletion if consumptions exist
        ForeignKey("sessions.id", ondelete="RESTRICT"),
        nullable=False
    )
    # Use DateTime for precise timing
    consumption_time: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.datetime.now(datetime.timezone.utc), comment="Timestamp when the consumption occurred")
    consumed_without_reservation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="True if the student consumed without a prior reservation")
    # Link to the specific reservation if applicable
    reserve_id: Mapped[Optional[int]] = mapped_column(
        # Use SET NULL: if reservation is deleted, consumption record remains but link is removed
        ForeignKey("reserves.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationship to Student (many-to-one)
    student: Mapped["Student"] = relationship(back_populates="consumptions")
    # Relationship to Session (many-to-one)
    session: Mapped["Session"] = relationship(back_populates="consumptions")
    # Relationship to Reserve (many-to-one, potentially null)
    reserve: Mapped[Optional["Reserve"]] = relationship(
        back_populates="consumption")

    __table_args__ = (
        UniqueConstraint(
            "student_id", "session_id",
            name="uq_student_session_consumption"  # More descriptive constraint name
        ),
    )

    def __repr__(self):
        """Returns a string representation of the Consumption object."""
        return (f"<Consumption(id={self.id}, student_id={self.student_id}, session_id={self.session_id}, "
                f"time='{self.consumption_time!r}', no_reserve={self.consumed_without_reservation})>")
