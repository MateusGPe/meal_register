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

student_turma_association = Table(
    "student_turma_association",
    Base.metadata,
    Column("student_id", Integer, ForeignKey("students.id"), primary_key=True),
    Column("turma_id", Integer, ForeignKey("turmas.id"), primary_key=True),
)

# pylint: disable=too-few-public-methods


class Turma(Base):
    """Represents the turmas (classes/groups) table."""
    __tablename__ = "turmas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    students: Mapped[List["Student"]] = relationship(
        secondary=student_turma_association,
        back_populates="turmas",
        lazy="select"
    )

    def __repr__(self):
        """Returns a string representation of the Turma object."""
        return f"<Turma(nome='{self.nome!r}')>"

# pylint: disable=too-few-public-methods


class Student(Base):
    """Represents the students table in the database."""
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    pront: Mapped[str] = mapped_column(String, unique=True)
    nome: Mapped[str] = mapped_column(String)

    turmas: Mapped[List["Turma"]] = relationship(
        secondary=student_turma_association,
        back_populates="students",
        lazy="select"
    )

    reserves: Mapped[List["Reserve"]] = relationship(back_populates="student")
    consumptions: Mapped[List["Consumption"]
                         ] = relationship(back_populates="student")

    def __repr__(self):
        """Returns a string representation of the Student object."""
        return f"<Student(pront='{self.pront!r}', nome='{self.nome!r}')>"


# class Student(Base):
#     """Represents the students table in the database."""
#     __tablename__ = "students"

#     id: Mapped[int] = mapped_column(primary_key=True)
#     pront: Mapped[str] = mapped_column(String)
#     nome: Mapped[str] = mapped_column(String)
#     turma: Mapped[str] = mapped_column(String)

#     reserves: Mapped[List["Reserve"]] = relationship(back_populates="student")
#     consumptions: Mapped[List["Consumption"]
#                          ] = relationship(back_populates="student")

#     __table_args__ = (
#         UniqueConstraint(
#             "pront", name="_pront_uc", sqlite_on_conflict="REPLACE"
#         ),
#     )

#     def __repr__(self):
#         """Returns a string representation of the Student object."""
#         return f"<Student(pront='{self.pront!r}', nome='{self.nome!r}', turma='{self.turma!r}')>"

# pylint: disable=too-few-public-methods


class Reserve(Base):
    """Represents the reserve table in the database."""
    __tablename__ = "reserve"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"))
    prato: Mapped[Optional[str]] = mapped_column(String)
    data: Mapped[str] = mapped_column(String)
    snacks: Mapped[bool] = mapped_column(Boolean, default=False)
    canceled: Mapped[bool] = mapped_column(Boolean, default=False)

    student: Mapped["Student"] = relationship(back_populates="reserves")
    consumption: Mapped[Optional["Consumption"]] = relationship(back_populates="reserve",
                                                                uselist=False)

    __table_args__ = (
        UniqueConstraint(
            "student_id", "data", "snacks", name="_pront_uc", sqlite_on_conflict="REPLACE"
        ),
    )

    def __repr__(self) -> str:
        """Returns a string representation of the Reserve object."""
        return (
            f"<Reserve(student_id={self.student_id}, prato={self.prato!r}, "
            f"data={self.data!r}, snacks={self.snacks!r}, canceled={self.canceled!r})>"
        )

# pylint: disable=too-few-public-methods


class Session(Base):
    """Represents the session table in the database."""
    __tablename__ = "session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refeicao: Mapped[str] = mapped_column(String)
    periodo: Mapped[str] = mapped_column(String)
    data: Mapped[str] = mapped_column(String)
    hora: Mapped[str] = mapped_column(String)
    turmas: Mapped[str] = mapped_column(String)

    consumptions: Mapped[List["Consumption"]
                         ] = relationship(back_populates="session")

    __table_args__ = (
        UniqueConstraint(
            'refeicao', 'periodo', 'data', 'hora', name="_all_uc",
            sqlite_on_conflict="REPLACE"
        ),
    )

    def __repr__(self):
        """Returns a string representation of the Session object."""
        return (f"<Session(refeicao='{self.refeicao!r}', periodo='{self.periodo!r}', "
                f"data='{self.data!r}', hora='{self.hora!r}', turmas='{self.turmas!r}')>")

# pylint: disable=too-few-public-methods


class Consumption(Base):
    """Represents the consumption table in the database."""
    __tablename__ = "consumption"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"))
    session_id: Mapped[int] = mapped_column(
        ForeignKey("session.id", ondelete="RESTRICT"))
    consumption_time: Mapped[str] = mapped_column(String)
    consumed_without_reservation: Mapped[bool] = mapped_column(
        Boolean, default=False)
    reserve_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reserve.id", ondelete="RESTRICT"))  # Opcional

    student: Mapped["Student"] = relationship(back_populates="consumptions")
    session: Mapped["Session"] = relationship(back_populates="consumptions")
    reserve: Mapped[Optional["Reserve"]] = relationship(
        back_populates="consumption")

    __table_args__ = (
        UniqueConstraint("student_id", "session_id",
                         name="_student_session_consumption_uc"),
    )

    def __repr__(self):
        """Returns a string representation of the Consumption object."""
        return (f"<Consumption(student_id={self.student_id}, session_id={self.session_id}, "
                f"consumption_time='{self.consumption_time!r}', "
                f"consumed_without_reservation={self.consumed_without_reservation})>")
