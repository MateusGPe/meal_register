# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Defines the SQLAlchemy models for the database tables: students, reserve,
and session. Includes functions for data translation.
"""

import re
from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import (Mapped, declarative_base, mapped_column,
                            relationship)

Base = declarative_base()

TRANSLATE_DICT = str.maketrans("0123456789Xx", "abcdefghijkk")
REMOVE_IQ = re.compile(r"[Ii][Qq]\d0+")


def to_code(text: str) -> str:
    """
    Translates a given text by removing 'IQ' followed by digits and then
    applying a translation dictionary.

    Args:
        text (str): The input string to be translated.

    Returns:
        str: The translated string.
    """
    text = REMOVE_IQ.sub("", text)
    translated = text.translate(TRANSLATE_DICT)
    return " ".join(translated)


class Students(Base):
    """Represents the students table in the database."""
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    pront: Mapped[str] = mapped_column(String)
    nome: Mapped[str] = mapped_column(String)
    turma: Mapped[str] = mapped_column(String)

    reserves: Mapped[List["Reserve"]] = relationship(back_populates="student")

    def __init__(self, pront: str, nome: str, turma: str) -> None:
        """
        Initializes a new Students object.

        Args:
            pront (str): The student's registration number.
            nome (str): The student's name.
            turma (str): The student's class.
        """
        self.pront = pront
        self.nome = nome
        self.turma = turma
        self._keyid: Optional[str] = to_code(pront)

    @property
    def translate_id(self) -> str:
        """
        Returns the translated ID of the student.

        The ID is generated from the student's PRONT using the to_code function
        and stored in the _keyid attribute after the first access.

        Returns:
            str: The translated ID of the student.
        """
        if hasattr(self, "_keyid"):
            return self._keyid
        self._keyid = to_code(self.pront)
        return self._keyid

    __table_args__ = (
        UniqueConstraint(
            "pront", name="_pront_uc", sqlite_on_conflict="REPLACE"
        ),
    )

    def __repr__(self):
        """Returns a string representation of the Students object."""
        return f"<Students(pront='{self.pront}', nome='{self.nome}', turma='{self.turma}')>"


class Reserve(Base):
    """Represents the reserve table in the database."""
    __tablename__ = "reserve"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    prato: Mapped[Optional[str]] = mapped_column(String)
    data: Mapped[str] = mapped_column(String)
    snacks: Mapped[bool] = mapped_column(Boolean, default=False)
    reserved: Mapped[bool] = mapped_column(Boolean, default=False)
    session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("session.id"))
    registro_time: Mapped[Optional[str]] = mapped_column(String)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    canceled: Mapped[bool] = mapped_column(Boolean, default=False)

    student: Mapped["Students"] = relationship(back_populates="reserves")
    session: Mapped["Session"] = relationship(back_populates="reserves")

    __table_args__ = (
        UniqueConstraint(
            "session_id", "student_id", "data", "snacks", name="_all_uc",
            sqlite_on_conflict="REPLACE"
        ),
    )

    def __repr__(self):
        """Returns a string representation of the Reserve object."""
        return f"<Reserve(student_id={self.student_id}, prato='{self.prato}', "\
            f"data='{self.data}', snacks='{self.snacks}', reserved='{self.reserved}', "\
            f"session_id={self.session_id}, registro_time='{self.registro_time}', "\
            f"consumed='{self.consumed}', canceled='{self.canceled}')>"


class Session(Base):
    """Represents the session table in the database."""
    __tablename__ = "session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refeicao: Mapped[str] = mapped_column(String)
    periodo: Mapped[str] = mapped_column(String)
    data: Mapped[str] = mapped_column(String)
    hora: Mapped[str] = mapped_column(String)
    turmas: Mapped[str] = mapped_column(String)

    __table_args__ = (
        UniqueConstraint(
            'refeicao', 'periodo', 'data', 'hora', 'turmas', name="_all_uc",
            sqlite_on_conflict="REPLACE"
        ),
    )

    reserves: Mapped[List["Reserve"]] = relationship(back_populates="session")

    def __repr__(self):
        """Returns a string representation of the Session object."""
        return f"<Session(refeicao='{self.refeicao}', data='{self.data}', hora='{self.hora}')>"
