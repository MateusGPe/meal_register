# ----------------------------------------------------------------------------
# File: registro/model/tables.py (Database Models)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

from typing import List, Optional
from sqlalchemy import (Boolean, Column, ForeignKey, Integer, String, Table,
                        UniqueConstraint)
from sqlalchemy.orm import (Mapped, declarative_base, mapped_column,
                            relationship)
Base = declarative_base()
student_group_association = Table(
    "student_group_association",
    Base.metadata,

    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),

    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),


)


class Group(Base):
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    nome: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)

    students: Mapped[List["Student"]] = relationship(
        secondary=student_group_association, back_populates="groups", lazy="select"
    )

    def __repr__(self):
        return f"<Group(id={self.id}, nome='{self.nome}')>"


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    pront: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)

    nome: Mapped[str] = mapped_column(String, nullable=False, index=True)

    groups: Mapped[List["Group"]] = relationship(
        secondary=student_group_association, back_populates="students", lazy="select"
    )

    reserves: Mapped[List["Reserve"]] = relationship(back_populates="student")

    consumptions: Mapped[List["Consumption"]] = relationship(back_populates="student")

    def __repr__(self):
        return f"<Student(id={self.id}, pront='{self.pront}', nome='{self.nome}')>"


class Snack(Base):
    __tablename__ = "snack"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    def __repr__(self):
        return f"<Snack(id={self.id}, name='{self.name}')>"


class Reserve(Base):
    __tablename__ = "reserve"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)

    dish: Mapped[Optional[str]] = mapped_column(String)

    data: Mapped[str] = mapped_column(String, index=True)

    snacks: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    canceled: Mapped[bool] = mapped_column(Boolean, default=False)

    student: Mapped["Student"] = relationship(back_populates="reserves")

    consumption: Mapped[Optional["Consumption"]] = relationship(back_populates="reserve", uselist=False)

    __table_args__ = (

        UniqueConstraint("student_id", "data", "snacks", name="_student_date_mealtype_uc",



                         sqlite_on_conflict="IGNORE"),
    )

    def __repr__(self) -> str:
        return (f"<Reserve(id={self.id}, student_id={self.student_id}, dish='{self.dish}', "
                f"data='{self.data}', snacks={self.snacks}, canceled={self.canceled})>")


class Session(Base):
    __tablename__ = "session"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    refeicao: Mapped[str] = mapped_column(String, nullable=False)

    periodo: Mapped[str] = mapped_column(String)

    data: Mapped[str] = mapped_column(String, nullable=False, index=True)

    hora: Mapped[str] = mapped_column(String, nullable=False)

    groups: Mapped[str] = mapped_column(String)

    consumptions: Mapped[List["Consumption"]] = relationship(back_populates="session")

    __table_args__ = (

        UniqueConstraint('refeicao', 'periodo', 'data', 'hora', name="_session_datetime_meal_uc"),
    )

    def __repr__(self):
        groups_repr = (self.groups[:30] + '...') if len(self.groups or '') > 30 else (self.groups or '')
        return (f"<Session(id={self.id}, refeicao='{self.refeicao}', periodo='{self.periodo}', "
                f"data='{self.data}', hora='{self.hora}', groups='{groups_repr}')>")


class Consumption(Base):
    __tablename__ = "consumption"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)

    session_id: Mapped[int] = mapped_column(ForeignKey("session.id", ondelete="RESTRICT"), index=True)

    consumption_time: Mapped[str] = mapped_column(String, nullable=False)

    consumed_without_reservation: Mapped[bool] = mapped_column(Boolean, default=False)

    reserve_id: Mapped[Optional[int]] = mapped_column(ForeignKey("reserve.id", ondelete="RESTRICT"), index=True)

    student: Mapped["Student"] = relationship(back_populates="consumptions")

    session: Mapped["Session"] = relationship(back_populates="consumptions")

    reserve: Mapped[Optional["Reserve"]] = relationship(back_populates="consumption")

    __table_args__ = (

        UniqueConstraint("student_id", "session_id", name="_student_session_consumption_uc",


                         ),
    )

    def __repr__(self):
        return (f"<Consumption(id={self.id}, student_id={self.student_id}, session_id={self.session_id}, "
                f"time='{self.consumption_time}', no_reserve={self.consumed_without_reservation}, reserve_id={self.reserve_id})>")
