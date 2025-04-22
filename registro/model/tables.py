# ----------------------------------------------------------------------------
# File: registro/model/tables.py (Model - No changes from previous refactoring)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Define os modelos SQLAlchemy para as tabelas do banco de dados: students, reserve,
session, group, snack, e consumption. Inclui associações e representações.
"""
from typing import List, Optional

from sqlalchemy import (Boolean, Column, ForeignKey, Integer, String, Table,
                        UniqueConstraint)
from sqlalchemy.orm import (Mapped, declarative_base, mapped_column,
                            relationship)

Base = declarative_base()

# Tabela de associação para a relação muitos-para-muitos entre Student e Group
student_group_association = Table(
    "student_group_association",
    Base.metadata,
    Column("student_id", Integer, ForeignKey("students.id"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id"), primary_key=True),
)

# pylint: disable=too-few-public-methods
class Group(Base):
    """Representa a tabela groups (turmas/grupos) no banco de dados."""
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    students: Mapped[List["Student"]] = relationship(
        secondary=student_group_association, back_populates="groups", lazy="select"
    )
    def __repr__(self): return f"<Group(nome='{self.nome!r}')>"

# pylint: disable=too-few-public-methods
class Student(Base):
    """Representa a tabela students no banco de dados."""
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    pront: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    groups: Mapped[List["Group"]] = relationship(
        secondary=student_group_association, back_populates="students", lazy="select"
    )
    reserves: Mapped[List["Reserve"]] = relationship(back_populates="student")
    consumptions: Mapped[List["Consumption"]] = relationship(back_populates="student")
    def __repr__(self): return f"<Student(pront='{self.pront!r}', nome='{self.nome!r}')>"

# pylint: disable=too-few-public-methods
class Snack(Base):
    """Representa a tabela snack (lanches disponíveis)."""
    __tablename__ = "snack"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    def __repr__(self): return f"<Snack(name='{self.name!r}')>"

# pylint: disable=too-few-public-methods
class Reserve(Base):
    """Representa a tabela reserve no banco de dados."""
    __tablename__ = "reserve"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    dish: Mapped[Optional[str]] = mapped_column(String)
    data: Mapped[str] = mapped_column(String)
    snacks: Mapped[bool] = mapped_column(Boolean, default=False)
    canceled: Mapped[bool] = mapped_column(Boolean, default=False)
    student: Mapped["Student"] = relationship(back_populates="reserves")
    consumption: Mapped[Optional["Consumption"]] = relationship(back_populates="reserve", uselist=False)
    __table_args__ = (UniqueConstraint("student_id", "data", "snacks", name="_pront_uc", sqlite_on_conflict="IGNORE"),)
    def __repr__(self) -> str:
        return (f"<Reserve(id={self.id}, student_id={self.student_id}, dish={self.dish!r}, data={self.data!r}, "
                f"snacks={self.snacks!r}, canceled={self.canceled!r})>")

# pylint: disable=too-few-public-methods
class Session(Base):
    """Representa a tabela session no banco de dados."""
    __tablename__ = "session"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refeicao: Mapped[str] = mapped_column(String)
    periodo: Mapped[str] = mapped_column(String)
    data: Mapped[str] = mapped_column(String)
    hora: Mapped[str] = mapped_column(String)
    groups: Mapped[str] = mapped_column(String)
    consumptions: Mapped[List["Consumption"]] = relationship(back_populates="session")
    __table_args__ = (UniqueConstraint('refeicao', 'periodo', 'data', 'hora', name="_all_uc"),)
    def __repr__(self):
        return (f"<Session(id={self.id}, refeicao='{self.refeicao!r}', periodo='{self.periodo!r}', data='{self.data!r}', "
                f"hora='{self.hora!r}', groups='{self.groups!r}')>")

# pylint: disable=too-few-public-methods
class Consumption(Base):
    """Representa a tabela consumption (registros de consumo) no banco de dados."""
    __tablename__ = "consumption"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id", ondelete="RESTRICT"))
    consumption_time: Mapped[str] = mapped_column(String)
    consumed_without_reservation: Mapped[bool] = mapped_column(Boolean, default=False)
    reserve_id: Mapped[Optional[int]] = mapped_column(ForeignKey("reserve.id", ondelete="RESTRICT"))
    student: Mapped["Student"] = relationship(back_populates="consumptions")
    session: Mapped["Session"] = relationship(back_populates="consumptions")
    reserve: Mapped[Optional["Reserve"]] = relationship(back_populates="consumption")
    __table_args__ = (UniqueConstraint("student_id", "session_id", name="_student_session_consumption_uc"),)
    def __repr__(self):
        return (f"<Consumption(id={self.id}, student_id={self.student_id}, session_id={self.session_id}, "
                f"time='{self.consumption_time!r}', no_reserve={self.consumed_without_reservation}, reserve_id={self.reserve_id})>")