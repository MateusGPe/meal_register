# ----------------------------------------------------------------------------
# File: registro/control/meal_session_handler.py (Controller/Service Layer - Refined with Helper)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
meal_session_handler.py

Este módulo define a classe `MealSessionHandler`, que gerencia operações relacionadas a
students, reservations e consumption de refeições dentro de uma sessão de serviço de refeição.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Any

# Importações SQLAlchemy
from sqlalchemy import delete, insert, select, func, case
from sqlalchemy.orm import aliased, Session as SQLASession
from sqlalchemy.dialects.sqlite import insert as sqlite_insert # Específico para SQLite ON CONFLICT

# Importações Locais
from registro.control.generic_crud import CRUD
from registro.control.utils import to_code
from registro.model.tables import Consumption, Group, Reserve, Student

logger = logging.getLogger(__name__)

class MealSessionHandler:
    """
    Lida com operações relacionadas a students, reserves e consumption
    dentro de uma sessão de serviço de refeição.
    """

    def __init__(self, database_session: SQLASession):
        """ Inicializa o MealSessionHandler. """
        if database_session is None:
             raise ValueError("database_session não pode ser None")
        self.db_session = database_session
        self.student_crud: CRUD[Student] = CRUD[Student](self.db_session, Student)
        self.consumption_crud: CRUD[Consumption] = CRUD[Consumption](self.db_session, Consumption)

        # Estado e Cache da Sessão
        self._session_id: Optional[int] = None
        self._date: Optional[str] = None
        self._meal_type: Optional[str] = None
        self._turmas_com_reserva: Set[str] = set()
        self._turmas_sem_reserva: Set[str] = set()
        self._served_pronts: Set[str] = set()
        self._filtered_students_cache: List[Dict[str, Any]] = []
        self._pront_to_reserve_id_map: Dict[str, Optional[int]] = {}
        self._pront_to_student_id_map: Dict[str, int] = {}

    def set_session_info(self, session_id: Optional[int], date: Optional[str],
                         meal_type: Optional[str], turmas: Optional[List[str]]):
        """ Define as informações da sessão atual e limpa caches relacionados. """
        self._session_id = session_id
        self._date = date
        self._meal_type = meal_type.lower() if meal_type else None

        self._turmas_com_reserva = set()
        self._turmas_sem_reserva = set()
        if turmas:
            for t in turmas:
                t_clean = t.replace('Vazio', '').strip()
                if not t_clean: continue
                if t_clean.startswith('#'): self._turmas_sem_reserva.add(t_clean[1:])
                else: self._turmas_com_reserva.add(t_clean)

        self._clear_caches()
        logger.debug(f"Info sessão definida: ID={self._session_id}, Data={self._date}, "
                     f"Refeição={self._meal_type}, Turmas c/Reserva={self._turmas_com_reserva}, "
                     f"Turmas s/Reserva={self._turmas_sem_reserva}")

    def _clear_caches(self):
        """ Limpa os caches internos de students filtrados e servidos. """
        self._filtered_students_cache = []
        self._served_pronts = set()
        self._pront_to_reserve_id_map = {}
        self._pront_to_student_id_map = {}

    def get_served_registers(self) -> Set[str]:
        """ Retorna o conjunto de PRONTs servidos na sessão atual (cache). """
        if not self._served_pronts and self._session_id is not None:
             self.get_served_students() # Carrega do DB se cache vazio
        return self._served_pronts

    def filter_students(self) -> Optional[List[Dict[str, Any]]]:
        """ Filtra e retorna a lista de students elegíveis para a sessão atual. """
        if not all([self._date, self._meal_type is not None, self._session_id is not None,
                   (self._turmas_com_reserva or self._turmas_sem_reserva)]):
            logger.warning("Info sessão incompleta para filtrar students.")
            return None

        self._clear_caches()
        self._load_served_pronts_from_db() # Recarrega quem já foi servido

        is_snack = self._meal_type == "lanche"
        s, g, r = aliased(Student), aliased(Group), aliased(Reserve)

        query = self.db_session.query(
            s.pront, s.nome, func.group_concat(g.nome.distinct()).label('turmas_concat'),
            s.id.label('student_id'), r.id.label('reserve_id'), r.dish.label('reserve_dish')
        ).select_from(s).join(s.groups.of_type(g))\
         .outerjoin(r, (r.student_id == s.id) & (r.data == self._date) &
                       (r.snacks.is_(is_snack)) & (r.canceled.is_(False)))

        conditions = []
        if self._turmas_com_reserva: conditions.append((g.nome.in_(self._turmas_com_reserva)) & (r.id.isnot(None)))
        if self._turmas_sem_reserva: conditions.append(g.nome.in_(self._turmas_sem_reserva))

        if conditions: query = query.filter(sqlalchemy.or_(*conditions) if len(conditions) > 1 else conditions[0])
        else:
            logger.warning("Nenhuma turma selecionada para filtragem.")
            self._filtered_students_cache = []
            return self._filtered_students_cache

        query = query.group_by(s.id, s.pront, s.nome, r.id, r.dish).order_by(s.nome)
        results = query.all()

        # Processa resultados e popula caches
        processed_students: Dict[str, Dict[str, Any]] = {}
        for pront, nome, turmas_str, student_id, reserve_id, reserve_dish in results:
            self._pront_to_student_id_map[pront] = student_id
            self._pront_to_reserve_id_map[pront] = reserve_id
            if pront not in processed_students:
                 processed_students[pront] = {
                    "Pront": pront, "Nome": nome, "Turma": set(turmas_str.split(',') if turmas_str else []),
                    "Prato": reserve_dish if reserve_id is not None else "Sem Reserva",
                    "Data": self._date, "id": to_code(pront), "Hora": None,
                    "reserve_id": reserve_id, "student_id": student_id,
                 }
            else:
                 if turmas_str: processed_students[pront]["Turma"].update(turmas_str.split(','))
                 if reserve_id is not None and processed_students[pront]["reserve_id"] is None:
                       processed_students[pront]["reserve_id"] = reserve_id
                       processed_students[pront]["Prato"] = reserve_dish

        # Formata saída final
        self._filtered_students_cache = [
             {**info, "Turma": ','.join(sorted(list(info["Turma"])))}
             for info in processed_students.values()
        ]
        logger.info(f"{len(self._filtered_students_cache)} students filtrados para sessão {self._session_id}.")
        return self._filtered_students_cache

    def _load_served_pronts_from_db(self):
        """ Carrega os PRONTs dos alunos já servidos nesta sessão do DB. """
        if self._session_id is None: self._served_pronts = set(); return
        try:
            served_query = self.db_session.query(Student.pront)\
                .join(Consumption, Consumption.student_id == Student.id)\
                .filter(Consumption.session_id == self._session_id)
            self._served_pronts = {pront for (pront,) in served_query.all()}
            logger.debug(f"Carregados {len(self._served_pronts)} PRONTs servidos do DB para sessão {self._session_id}.")
        except Exception as e:
            logger.exception(f"Erro ao carregar PRONTs servidos do DB para sessão {self._session_id}: {e}")
            self._served_pronts = set()

    # --- Helper Method ---
    def _get_or_find_student_details(self, pront: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Obtém student_id e reserve_id para um PRONT, usando cache ou buscando no DB.
        Atualiza os caches internos se buscar no DB.

        Returns:
            Tuple[Optional[int], Optional[int]]: (student_id, reserve_id) ou (None, None) se não encontrado.
        """
        student_id = self._pront_to_student_id_map.get(pront)
        reserve_id = self._pront_to_reserve_id_map.get(pront) # Pode já ser None do cache

        if student_id is None:
            # Não está no cache de student_id, busca student no DB
            student_record = self.student_crud.read_filtered_one(pront=pront)
            if student_record:
                student_id = student_record.id
                # Encontrou student, agora busca a reserva correspondente (se houver)
                reserve_record = self.db_session.query(Reserve.id).filter(
                    Reserve.student_id == student_id,
                    Reserve.data == self._date,
                    Reserve.snacks.is_(self._meal_type == "lanche"),
                    Reserve.canceled.is_(False)
                ).first()
                reserve_id = reserve_record[0] if reserve_record else None
                # Atualiza os caches para futuras consultas
                self._pront_to_student_id_map[pront] = student_id
                self._pront_to_reserve_id_map[pront] = reserve_id
                logger.debug(f"Detalhes de {pront} encontrados no DB: student_id={student_id}, reserve_id={reserve_id}")
            else:
                # Student não encontrado no DB
                logger.warning(f"Student {pront} não encontrado no DB ao buscar detalhes.")
                return None, None # Indica falha em encontrar o student

        # Retorna os IDs encontrados (do cache ou recém-buscados)
        return student_id, reserve_id

    # --- CRUD Operations for Consumption ---
    def create_student(self, student_info: Tuple[str, str, str, str, str]) -> bool:
        """ Marca um student como servido na sessão atual (registra consumo). """
        if self._session_id is None: logger.error("Não registrar consumo: sessão inativa."); return False
        pront = student_info[0]
        if pront in self._served_pronts: logger.warning(f"{pront} já servido."); return False

        student_id, reserve_id = self._get_or_find_student_details(pront)
        if student_id is None: return False # Student não encontrado

        consumption_data = {
            "student_id": student_id, "session_id": self._session_id,
            "consumption_time": datetime.now().strftime("%H:%M:%S"),
            "consumed_without_reservation": reserve_id is None, "reserve_id": reserve_id,
        }
        try:
            created = self.consumption_crud.create(consumption_data)
            if created:
                self._served_pronts.add(pront)
                logger.info(f"Student {pront} marcado como servido na sessão {self._session_id}.")
                return True
            else: # create retornou None ou False
                 logger.error(f"Falha ao criar registro de consumo para {pront} (CRUD retornou não-True).")
                 self.db_session.rollback() # Garante rollback se create não comitou
                 return False
        except Exception as e:
            logger.exception(f"Erro ao registrar consumo para {pront} na sessão {self._session_id}: {e}")
            self.db_session.rollback()
            # Verifica se o erro foi por constraint (já existe)
            self._load_served_pronts_from_db() # Recarrega estado real do DB
            if pront in self._served_pronts:
                 logger.warning(f"Registro de consumo para {pront} falhou, mas ele já consta como servido (provável race condition).")
                 return False # A *operação* falhou, mas o estado é 'servido'
            return False # Outro erro

    def delete_student(self, student_info: Tuple[str, str, str, str, str]) -> bool:
        """ Desmarca um student como servido na sessão atual (remove consumo). """
        if self._session_id is None: logger.error("Não remover consumo: sessão inativa."); return False
        pront = student_info[0]
        if pront not in self._served_pronts: logger.warning(f"{pront} não está servido."); return False

        student_id, _ = self._get_or_find_student_details(pront) # Só precisamos do student_id
        if student_id is None: return False # Student não encontrado

        try:
            result = self.db_session.execute(
                delete(Consumption).where(
                    Consumption.student_id == student_id,
                    Consumption.session_id == self._session_id
                )#.returning(Consumption.id) # returning não é padrão em todos DBs
            )
            deleted_count = result.rowcount
            if deleted_count > 0:
                self.db_session.commit()
                self._served_pronts.discard(pront)
                logger.info(f"Student {pront} desmarcado como servido na sessão {self._session_id}.")
                return True
            else:
                self.db_session.rollback()
                logger.warning(f"Nenhum registro de consumo encontrado para deletar para {pront} na sessão {self._session_id}.")
                self._load_served_pronts_from_db() # Garante que o cache reflete o DB
                return False
        except Exception as e:
            logger.exception(f"Erro ao remover consumo para {pront} na sessão {self._session_id}: {e}")
            self.db_session.rollback()
            return False

    def set_students(self, served_update: List[Tuple[str, str, str, str, str]]):
        """ Atualiza o estado de 'servido' dos students via operações bulk. """
        if self._session_id is None: logger.error("Não atualizar students: sessão inativa."); return
        logger.debug(f"Iniciando atualização (set_students) para sessão {self._session_id}.")

        target_served_pronts: Set[str] = {item[0] for item in served_update}
        current_served_pronts: Set[str] = self._served_pronts.copy()
        pronts_to_unmark = current_served_pronts.difference(target_served_pronts)
        pronts_to_mark = target_served_pronts.difference(current_served_pronts)

        try:
            # --- Desmarcar ---
            if pronts_to_unmark:
                logger.debug(f"Desmarcando {len(pronts_to_unmark)} students: {pronts_to_unmark}")
                student_ids_to_unmark = select(Student.id).where(Student.pront.in_(pronts_to_unmark))
                delete_stmt = delete(Consumption).where(
                    Consumption.session_id == self._session_id,
                    Consumption.student_id.in_(student_ids_to_unmark)
                )
                result_del = self.db_session.execute(delete_stmt)
                logger.info(f"{result_del.rowcount} registros de consumo removidos.")

            # --- Marcar ---
            if pronts_to_mark:
                logger.debug(f"Marcando {len(pronts_to_mark)} students: {pronts_to_mark}")
                consumption_data_to_insert = []
                for pront, _, _, hora, _ in served_update:
                    if pront in pronts_to_mark:
                        student_id, reserve_id = self._get_or_find_student_details(pront)
                        if student_id is None:
                             logger.warning(f"Student {pront} para marcar não encontrado. Ignorando.")
                             continue
                        consumption_data_to_insert.append({
                            "student_id": student_id, "session_id": self._session_id,
                            "consumption_time": hora, "consumed_without_reservation": reserve_id is None,
                            "reserve_id": reserve_id,
                        })
                if consumption_data_to_insert:
                    # Usa insert específico do dialeto para ON CONFLICT (ex: SQLite)
                    insert_stmt = sqlite_insert(Consumption).values(consumption_data_to_insert)
                    insert_stmt = insert_stmt.on_conflict_do_nothing(
                         index_elements=['student_id', 'session_id'] # Usa nome da constraint
                    )
                    # Para outros DBs (ex: PostgreSQL), usar a sintaxe apropriada
                    # from sqlalchemy.dialects.postgresql import insert as pg_insert
                    # insert_stmt = pg_insert(Consumption).values(...)
                    # insert_stmt = insert_stmt.on_conflict_do_nothing(...)
                    result_ins = self.db_session.execute(insert_stmt)
                    # rowcount pode ser 0 ou N com on_conflict_do_nothing, log é informativo
                    logger.info(f"Tentativa de inserir {len(consumption_data_to_insert)} registros de consumo (afetados: {result_ins.rowcount}).")

            # Comita todas as alterações (delete e insert)
            self.db_session.commit()
            self._served_pronts = target_served_pronts # Atualiza cache local
            logger.info("Atualização (set_students) concluída com sucesso.")

        except Exception as e:
            logger.exception(f"Erro durante atualização (set_students) para sessão {self._session_id}: {e}")
            self.db_session.rollback()
            self._load_served_pronts_from_db() # Recarrega cache do DB

    # --- Getters for Cached/Processed Data ---
    def get_session_students(self) -> List[Dict[str, Any]]:
        """ Retorna a lista de students filtrados para a sessão atual (cache). """
        if not self._filtered_students_cache:
            logger.debug("Cache de students filtrados vazio, tentando filtrar agora.")
            self.filter_students()
        return self._filtered_students_cache

    def get_served_students(self) -> List[Tuple[str, str, str, str, str]]:
        """ Recupera do DB a lista formatada de students servidos na sessão atual. """
        if self._session_id is None:
            logger.warning("Não obter servidos: sessão inativa."); self._served_pronts = set(); return []
        try:
            s, g, r, c = aliased(Student), aliased(Group), aliased(Reserve), aliased(Consumption)
            query = self.db_session.query(
                s.pront, s.nome, func.group_concat(g.nome.distinct()), c.consumption_time,
                case((c.reserve_id.isnot(None), r.dish), else_="Sem Reserva")
            ).select_from(c).join(s, c.student_id == s.id).join(s.groups.of_type(g))\
             .outerjoin(r, c.reserve_id == r.id).filter(c.session_id == self._session_id)\
             .group_by(s.id, s.pront, s.nome, c.consumption_time, c.reserve_id, r.dish)\
             .order_by(c.consumption_time.desc()) # Mais recentes primeiro

            served_results = query.all()
            served_students_data = []
            current_served_pronts = set()
            for pront, nome, turmas_str, hora, prato in served_results:
                turmas_fmt = ','.join(sorted(list(set(turmas_str.split(',') if turmas_str else []))))
                served_students_data.append((pront, nome, turmas_fmt, hora, prato))
                current_served_pronts.add(pront)

            self._served_pronts = current_served_pronts # Atualiza cache de PRONTs servidos
            logger.info(f"{len(served_students_data)} students servidos recuperados para sessão {self._session_id}.")
            return served_students_data
        except Exception as e:
            logger.exception(f"Erro ao recuperar students servidos da sessão {self._session_id}: {e}")
            self._served_pronts = set()
            return []