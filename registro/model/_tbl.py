# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Defines the SQLAlchemy models for the database tables: students, reserve,
and session. Includes functions for data translation.
"""
from typing import List, Optional

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import (Mapped, declarative_base, mapped_column,
                            relationship)

Base = declarative_base()

student_group_association = Table(
    "student_group_association",
    Base.metadata,
    Column("student_id", Integer, ForeignKey("students.id"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id"), primary_key=True),
)




class Group(Base):
    """Represents the groups (classes/groups) table."""
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    students: Mapped[List["Student"]] = relationship(
        secondary=student_group_association,
        back_populates="groups",
        lazy="select"
    )

    def __repr__(self):
        """Returns a string representation of the Group object."""
        return f"<Group(nome='{self.nome!r}')>"


class MealConsumption(Base):
    """Represents the consumption of meals."""
    __tablename__ = "meal_consumption"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"))
    session_id: Mapped[int] = mapped_column(
        ForeignKey("session.id", ondelete="RESTRICT"))
    consumption_time: Mapped[str] = mapped_column(String)
    consumed_without_reservation: Mapped[bool] = mapped_column(Boolean, default=False)
    reserve_id: Mapped[int] = mapped_column(
        ForeignKey("reserve.id", ondelete="RESTRICT"))

    student: Mapped["Student"] = relationship(back_populates="meal_consumptions")
    session: Mapped["Session"] = relationship(back_populates="meal_consumptions")
    reserve: Mapped["Reserve"] = relationship(back_populates="meal_consumption")

    __table_args__ = (
        UniqueConstraint("student_id", "session_id",
                         name="_student_session_meal_consumption_uc"),
    )

    def __repr__(self):
        return (f"<MealConsumption(student_id={self.student_id}, session_id={self.session_id}, "
                f"consumption_time='{self.consumption_time!r}')>")


class SnackConsumption(Base):
    """Represents the consumption of snacks."""
    __tablename__ = "snack_consumption"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"))
    session_id: Mapped[int] = mapped_column(
        ForeignKey("session.id", ondelete="RESTRICT"))
    consumption_time: Mapped[str] = mapped_column(String)
    consumed_without_reservation: Mapped[bool] = mapped_column(Boolean, default=True)
    snack_id: Mapped[int] = mapped_column(
        ForeignKey("snack.id", ondelete="RESTRICT"))
    reserve_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reserve.id", ondelete="RESTRICT"), nullable=True)

    student: Mapped["Student"] = relationship(back_populates="snack_consumptions")
    session: Mapped["Session"] = relationship(back_populates="snack_consumptions")
    snack: Mapped["Snack"] = relationship()

    __table_args__ = (
        UniqueConstraint("student_id", "session_id",
                         name="_student_session_snack_consumption_uc"),
    )

    def __repr__(self):
        return (f"<SnackConsumption(student_id={self.student_id}, session_id={self.session_id}, "
                f"consumption_time='{self.consumption_time!r}', snack_id={self.snack_id})>")


class Student(Base):
    """Represents the students table in the database."""
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    pront: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String, nullable=False)

    groups: Mapped[List["Group"]] = relationship(
        secondary=student_group_association,
        back_populates="students",
        lazy="select"
    )

    reserves: Mapped[List["Reserve"]] = relationship(back_populates="student")
    meal_consumptions: Mapped[List["MealConsumption"]] = relationship(back_populates="student")
    snack_consumptions: Mapped[List["SnackConsumption"]] = relationship(back_populates="student")

    def __repr__(self):
        """Returns a string representation of the Student object."""
        return f"<Student(pront='{self.pront!r}', nome='{self.nome!r}')>"


class Session(Base):
    """Represents the session table in the database."""
    __tablename__ = "session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refeicao: Mapped[str] = mapped_column(String)
    periodo: Mapped[str] = mapped_column(String)
    data: Mapped[str] = mapped_column(String)
    hora: Mapped[str] = mapped_column(String)
    groups: Mapped[str] = mapped_column(String)

    meal_consumptions: Mapped[List["MealConsumption"]] = relationship(back_populates="session")
    snack_consumptions: Mapped[List["SnackConsumption"]] = relationship(back_populates="session")

    __table_args__ = (
        UniqueConstraint(
            'refeicao', 'periodo', 'data', 'hora', name="_all_uc",
            
        ),
    )

    def __repr__(self):
        """Returns a string representation of the Session object."""
        return (f"<Session(refeicao='{self.refeicao!r}', periodo='{self.periodo!r}', "
                f"data='{self.data!r}', hora='{self.hora!r}', groups='{self.groups!r}')>")


class Reserve(Base):
    """Represents the reserve table in the database."""
    __tablename__ = "reserve"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"))
    dish: Mapped[Optional[str]] = mapped_column(String)
    data: Mapped[str] = mapped_column(String)
    snacks: Mapped[bool] = mapped_column(Boolean, default=False)
    canceled: Mapped[bool] = mapped_column(Boolean, default=False)

    student: Mapped["Student"] = relationship(back_populates="reserves")
    meal_consumption: Mapped[Optional["MealConsumption"]] = relationship(
        back_populates="reserve", uselist=False)

    __table_args__ = (
        UniqueConstraint(
            "student_id", "data", "snacks", name="_pront_uc", sqlite_on_conflict="IGNORE"
        ),
    )

    def __repr__(self) -> str:
        """Returns a string representation of the Reserve object."""
        return (
            f"<Reserve(student_id={self.student_id}, dish={self.dish!r}, "
            f"data={self.data!r}, snacks={self.snacks!r}, canceled={self.canceled!r})>"
        )
