# ----------------------------------------------------------------------------
# File: registro/model/tables.py (Modelos do Banco de Dados)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Define os modelos de dados SQLAlchemy que representam as tabelas do banco de
dados da aplicação de registro de refeições. Inclui tabelas para Alunos,
Grupos (Turmas), Reservas, Sessões de Refeição e Consumos.
"""
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    Text,
)  # Text pode ser melhor para 'groups' JSON
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

# Base declarativa para os modelos SQLAlchemy
Base = declarative_base()

# --- Tabela de Associação Aluno <-> Grupo (Muitos-para-Muitos) ---
# Define a tabela que liga alunos a grupos (turmas)
student_group_association = Table(
    "student_group_association",  # Nome da tabela no banco de dados
    Base.metadata,
    # Coluna para chave estrangeira referenciando 'students.id'
    # ON DELETE CASCADE: Se um aluno for deletado, suas associações são removidas.
    Column(
        "student_id",
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    # Coluna para chave estrangeira referenciando 'groups.id'
    # ON DELETE CASCADE: Se um grupo for deletado, suas associações são removidas.
    Column(
        "group_id",
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

# --- Modelos de Tabela ---


class Group(Base):
    """Representa um grupo (turma) de alunos."""

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nome do grupo (turma), deve ser único e é indexado para buscas rápidas
    nome: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )

    # Relacionamento Muitos-para-Muitos com Student, usando a tabela de associação
    # `back_populates` cria a referência bidirecional com Student.groups
    # `lazy="select"`: Carrega a lista de alunos apenas quando acessada explicitamente.
    students: Mapped[List["Student"]] = relationship(
        secondary=student_group_association, back_populates="groups", lazy="select"
    )

    def __repr__(self) -> str:
        """Retorna uma representação textual do objeto Group."""
        return f"<Group(id={self.id}, nome='{self.nome}')>"


class Student(Base):
    """Representa um aluno cadastrado no sistema."""

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Prontuário do aluno, deve ser único e é indexado
    pront: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    # Nome completo do aluno, indexado para buscas
    nome: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Relacionamento Muitos-para-Muitos com Group
    groups: Mapped[List["Group"]] = relationship(
        secondary=student_group_association, back_populates="students", lazy="select"
    )
    # Relacionamento Um-para-Muitos com Reserve (um aluno pode ter várias reservas)
    # `cascade="all, delete-orphan"`: Se o aluno for deletado, suas reservas também serão.
    reserves: Mapped[List["Reserve"]] = relationship(
        back_populates="student", lazy="select", cascade="all, delete-orphan"
    )
    # Relacionamento Um-para-Muitos com Consumption (um aluno pode ter vários consumos)
    # `cascade="all, delete-orphan"`: Se o aluno for deletado, seus consumos também serão.
    consumptions: Mapped[List["Consumption"]] = relationship(
        back_populates="student", lazy="select", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Retorna uma representação textual do objeto Student."""
        return f"<Student(id={self.id}, pront='{self.pront}', nome='{self.nome[:30]}...')>"


# Modelo Snack removido conforme análise anterior (não estava sendo usado e lanches.json é usado)
# class Snack(Base):
#     __tablename__ = "snack"
#     id: Mapped[int] = mapped_column(Integer, primary_key=True)
#     name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
#     def __repr__(self):
#         return f"<Snack(id={self.id}, name='{self.name}')>"


class Reserve(Base):
    """Representa uma reserva de refeição feita por um aluno para uma data específica."""

    __tablename__ = "reserve"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Chave estrangeira para Student.id
    # ON DELETE RESTRICT: Impede a exclusão de um aluno se ele tiver reservas associadas
    # (pode ser alterado para CASCADE se a regra de negócio permitir)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )
    # Nome do prato reservado (pode ser None/NULL se não especificado ou não aplicável)
    dish: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Data da reserva (formato YYYY-MM-DD), indexada para buscas
    data: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    # Indica se a reserva é para lanche (True) ou almoço (False)
    snacks: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    # Indica se a reserva foi cancelada
    canceled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relacionamento Muitos-para-Um com Student
    student: Mapped["Student"] = relationship(
        back_populates="reserves", lazy="joined"
    )  # 'joined' pode ser útil aqui
    # Relacionamento Um-para-Um (opcional) com Consumption
    # Uma reserva pode ou não ter um consumo associado
    consumption: Mapped[Optional["Consumption"]] = relationship(
        back_populates="reserve", uselist=False, lazy="select"
    )

    # Constraint de unicidade: um aluno não pode ter duas reservas ativas
    # (não canceladas) para a mesma data e mesmo tipo de refeição (lanche/almoço).
    # IMPORTANTE: Adicionar `canceled` à constraint se reservas canceladas puderem coexistir
    # com ativas para o mesmo dia/tipo. Se cancelada significa "não existe mais",
    # a constraint atual está ok.
    # `sqlite_on_conflict="IGNORE"`: Instrução específica para SQLite. Se tentar
    # inserir uma linha que viola a constraint, a inserção é silenciosamente ignorada.
    # Para outros DBs, o comportamento padrão é lançar um IntegrityError.
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "data",
            "snacks",
            name="_student_date_mealtype_uc",
            sqlite_on_conflict="IGNORE",
        ),  # IGNORA inserções duplicadas no SQLite
    )

    def __repr__(self) -> str:
        """Retorna uma representação textual do objeto Reserve."""
        status = (
            "Cancelada" if self.canceled else ("Lanche" if self.snacks else "Almoço")
        )
        return (
            f"<Reserve(id={self.id}, student={self.student_id}, data='{self.data}', "
            f"tipo='{status}', prato='{self.dish}')>"
        )


class Session(Base):
    """Representa uma sessão de serviço de refeição ocorrida em um momento específico."""

    __tablename__ = "session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Tipo de refeição ('lanche' ou 'almoço')
    refeicao: Mapped[str] = mapped_column(String(50), nullable=False)
    # Período (ex: 'Manhã', 'Tarde' - uso pode ser opcional/legado)
    periodo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Data da sessão (YYYY-MM-DD), indexada
    data: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    # Hora de início da sessão (HH:MM)
    hora: Mapped[str] = mapped_column(String(5), nullable=False)
    # Armazena a lista de turmas participantes como uma string JSON.
    # Usar `Text` pode ser mais apropriado se a lista for muito longa.
    groups: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relacionamento Um-para-Muitos com Consumption
    # Uma sessão pode ter vários consumos registrados
    # `cascade="all, delete-orphan"`: Se a sessão for deletada, os consumos associados também serão.
    consumptions: Mapped[List["Consumption"]] = relationship(
        back_populates="session", lazy="select", cascade="all, delete-orphan"
    )

    # Constraint de unicidade: Não deve haver duas sessões com a mesma
    # combinação de refeição, período(opcional?), data e hora.
    # Ajustar se 'periodo' não for relevante para unicidade.
    __table_args__ = (
        UniqueConstraint("refeicao", "data", "hora", name="_session_datetime_meal_uc"),
        # Adicionar 'periodo' se ele for mandatório e parte da chave única:
        # UniqueConstraint('refeicao', 'periodo', 'data', 'hora',
        # name="_session_datetime_meal_period_uc"),
    )

    def __repr__(self) -> str:
        """Retorna uma representação textual do objeto Session."""
        groups_repr = (
            (self.groups[:30] + "...")
            if self.groups and len(self.groups) > 30
            else (self.groups or "[]")
        )
        return (
            f"<Session(id={self.id}, refeicao='{self.refeicao}', "
            f"data='{self.data}', hora='{self.hora}', groups='{groups_repr}')>"
        )


class Consumption(Base):
    """Representa o registro de consumo de uma refeição por um aluno em uma sessão específica."""

    __tablename__ = "consumption"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Chave estrangeira para Student.id
    # ON DELETE RESTRICT: Impede deletar aluno se houver consumo registrado
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )
    # Chave estrangeira para Session.id
    # ON DELETE RESTRICT: Impede deletar sessão se houver consumo registrado
    session_id: Mapped[int] = mapped_column(
        ForeignKey("session.id", ondelete="RESTRICT"), index=True
    )
    # Hora exata do registro do consumo (HH:MM:SS)
    consumption_time: Mapped[str] = mapped_column(String(8), nullable=False)
    # Indica se o consumo ocorreu sem uma reserva correspondente
    consumed_without_reservation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Chave estrangeira (opcional) para Reserve.id
    # Liga o consumo à reserva específica, se houver.
    # ON DELETE RESTRICT: Impede deletar reserva se estiver ligada a um consumo
    reserve_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("reserve.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    # Relacionamento Muitos-para-Um com Student
    student: Mapped["Student"] = relationship(
        back_populates="consumptions", lazy="joined"
    )  # 'joined' pode ser útil
    # Relacionamento Muitos-para-Um com Session
    session: Mapped["Session"] = relationship(
        back_populates="consumptions", lazy="joined"
    )  # 'joined' pode ser útil
    # Relacionamento Muitos-para-Um (opcional) com Reserve
    reserve: Mapped[Optional["Reserve"]] = relationship(
        back_populates="consumption", lazy="select"
    )

    # Constraint de unicidade: Um aluno só pode ter um registro de consumo por sessão.
    # `sqlite_on_conflict="IGNORE"`: Ignora tentativas de inserir consumo duplicado no SQLite.
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "session_id",
            name="_student_session_consumption_uc",
            sqlite_on_conflict="IGNORE",
        ),  # IGNORA duplicatas no SQLite
    )

    def __repr__(self) -> str:
        """Retorna uma representação textual do objeto Consumption."""
        reserve_info = (
            f"reserve_id={self.reserve_id}"
            if self.reserve_id
            else f"sem_reserva={self.consumed_without_reservation}"
        )
        return (
            f"<Consumption(id={self.id}, student={self.student_id}, session={self.session_id}, "
            f"time='{self.consumption_time}', {reserve_info})>"
        )
