# ----------------------------------------------------------------------------
# File: registro/control/meal_session_handler.py (Controller/Service Layer)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Any
from sqlalchemy import delete, func, case, or_ as sql_or
from sqlalchemy.orm import aliased, Session as SQLASession
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from registro.control.generic_crud import CRUD
from registro.control.utils import to_code
from registro.model.tables import Consumption, Group, Reserve, Student
logger = logging.getLogger(__name__)
class MealSessionHandler:
    def __init__(self, database_session: SQLASession):
        if database_session is None:
            raise ValueError("database_session cannot be None")
        self.db_session = database_session
        self.student_crud: CRUD[Student] = CRUD[Student](
            self.db_session, Student)
        self.consumption_crud: CRUD[Consumption] = CRUD[Consumption](
            self.db_session, Consumption)
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
        logger.debug(
            f"Setting session info: ID={session_id}, Date={date}, Meal={meal_type}, Groups={turmas}")
        self._session_id = session_id
        self._date = date
        self._meal_type = meal_type.lower() if meal_type else None
        self._turmas_com_reserva = set()
        self._turmas_sem_reserva = set()
        if turmas:
            for t in turmas:
                t_clean = t.replace('Vazio', '').strip()
                if not t_clean:
                    continue
                if t_clean.startswith('#'):
                    self._turmas_sem_reserva.add(t_clean[1:])
                else:
                    self._turmas_com_reserva.add(t_clean)
        self._clear_caches()
        logger.info(f"Session context set: ID={self._session_id}, Date={self._date}, "
                    f"Meal={self._meal_type}, ReservedGroups={self._turmas_com_reserva}, "
                    f"NonReservedGroups={self._turmas_sem_reserva}")
    def _clear_caches(self):
        logger.debug("Clearing internal caches.")
        self._filtered_students_cache = []
        self._served_pronts = set()
        self._pront_to_reserve_id_map = {}
        self._pront_to_student_id_map = {}
    def get_served_pronts(self) -> Set[str]:
        if not self._served_pronts and self._session_id is not None:
            self._load_served_pronts_from_db()
        return self._served_pronts
    def filter_eligible_students(self) -> Optional[List[Dict[str, Any]]]:
        if not all([self._date, self._meal_type is not None, self._session_id is not None,
                   (self._turmas_com_reserva or self._turmas_sem_reserva)]):
            logger.warning(
                "Cannot filter students: Incomplete session information.")
            return None
        logger.debug("Filtering eligible students for the session...")
        self._clear_caches()
        self._load_served_pronts_from_db()
        is_snack_session = self._meal_type == "lanche"
        s, g, r = aliased(Student), aliased(Group), aliased(Reserve)
        try:
            query = self.db_session.query(
                s.pront, s.nome, func.group_concat(
                    g.nome.distinct()).label('turmas_concat'),
                s.id.label('student_id'), r.id.label(
                    'reserve_id'), r.dish.label('reserve_dish')
            ).select_from(s)\
             .join(s.groups.of_type(g)) \
             .outerjoin(r, (r.student_id == s.id) & (r.data == self._date) &
                           (r.snacks.is_(is_snack_session)) & (r.canceled.is_(False)))
            conditions = []
            if self._turmas_com_reserva:
                conditions.append(
                    (g.nome.in_(self._turmas_com_reserva)) & (r.id.isnot(None)))
            if self._turmas_sem_reserva:
                conditions.append(g.nome.in_(self._turmas_sem_reserva))
            if conditions:
                query = query.filter(sql_or(*conditions)
                                     if len(conditions) > 1 else conditions[0])
            else:
                logger.warning("No groups selected for filtering.")
                self._filtered_students_cache = []
                return self._filtered_students_cache
            query = query.group_by(s.id, s.pront, s.nome,
                                   r.id, r.dish).order_by(s.nome)
            results = query.all()
            logger.debug(
                f"Query executed, processing {len(results)} raw results.")
            processed_students: Dict[str, Dict[str, Any]] = {}
            for pront, nome, turmas_str, student_id, reserve_id, reserve_dish in results:
                self._pront_to_student_id_map[pront] = student_id
                self._pront_to_reserve_id_map[pront] = reserve_id
                if pront not in processed_students:
                    processed_students[pront] = {
                        "Pront": pront,
                        "Nome": nome,
                        "Turma": set(turmas_str.split(',') if turmas_str else []),
                        "Prato": reserve_dish if reserve_id is not None else "Sem Reserva",
                        "Data": self._date,
                        "lookup_key": to_code(pront),
                        "Hora": None,
                        "reserve_id": reserve_id,
                        "student_id": student_id,
                    }
                else:
                    if turmas_str:
                        processed_students[pront]["Turma"].update(
                            turmas_str.split(','))
                    if reserve_id is not None and processed_students[pront]["reserve_id"] is None:
                        processed_students[pront]["reserve_id"] = reserve_id
                        processed_students[pront]["Prato"] = reserve_dish
            self._filtered_students_cache = [
                {**info, "Turma": ','.join(sorted(list(info["Turma"])))}
                for info in processed_students.values()
            ]
            logger.info(
                f"{len(self._filtered_students_cache)} eligible students filtered for session {self._session_id}.")
            return self._filtered_students_cache
        except SQLAlchemyError as e:
            logger.exception(
                f"Database error during student filtering for session {self._session_id}: {e}")
            self.db_session.rollback()
            self._clear_caches()
            return None
        except Exception as e:
            logger.exception(f"Unexpected error during student filtering: {e}")
            return None
    def _load_served_pronts_from_db(self):
        if self._session_id is None:
            self._served_pronts = set()
            return
        try:
            served_query = self.db_session.query(Student.pront)\
                .join(Consumption, Consumption.student_id == Student.id)\
                .filter(Consumption.session_id == self._session_id)
            self._served_pronts = {pront for (pront,) in served_query.all()}
            logger.debug(
                f"Loaded {len(self._served_pronts)} served PRONTs from DB for session {self._session_id}.")
        except SQLAlchemyError as e:
            logger.exception(
                f"DB error loading served PRONTs for session {self._session_id}: {e}")
            self.db_session.rollback()
            self._served_pronts = set()
        except Exception as e:
            logger.exception(f"Unexpected error loading served PRONTs: {e}")
            self._served_pronts = set()
    def _get_or_find_student_details(self, pront: str) -> Tuple[Optional[int], Optional[int]]:
        student_id = self._pront_to_student_id_map.get(pront)
        reserve_id = self._pront_to_reserve_id_map.get(
            pront)
        if student_id is None:
            logger.debug(
                f"Cache miss for student details of {pront}. Querying DB.")
            try:
                student_record = self.student_crud.read_filtered_one(
                    pront=pront)
                if student_record:
                    student_id = student_record.id
                    reserve_record = self.db_session.query(Reserve.id).filter(
                        Reserve.student_id == student_id,
                        Reserve.data == self._date,
                        Reserve.snacks.is_(self._meal_type == "lanche"),
                        Reserve.canceled.is_(False)
                    ).scalar()
                    reserve_id = reserve_record
                    self._pront_to_student_id_map[pront] = student_id
                    self._pront_to_reserve_id_map[pront] = reserve_id
                    logger.debug(
                        f"Details for {pront} found in DB: student_id={student_id}, reserve_id={reserve_id}. Caches updated.")
                else:
                    logger.warning(
                        f"Student {pront} not found in DB while fetching details.")
                    return None, None
            except SQLAlchemyError as e:
                logger.exception(f"DB error fetching details for {pront}: {e}")
                self.db_session.rollback()
                return None, None
            except Exception as e:
                logger.exception(
                    f"Unexpected error fetching details for {pront}: {e}")
                return None, None
        return student_id, reserve_id
    def record_consumption(self, student_info: Tuple[str, str, str, str, str]) -> bool:
        if self._session_id is None:
            logger.error("Cannot record consumption: No active session.")
            return False
        pront = student_info[0]
        if pront in self._served_pronts:
            logger.warning(
                f"Consumption not recorded: {pront} already marked as served in this session.")
            return False
        student_id, reserve_id = self._get_or_find_student_details(pront)
        if student_id is None:
            logger.error(
                f"Cannot record consumption: Student {pront} not found.")
            return False
        consumption_data = {
            "student_id": student_id,
            "session_id": self._session_id,
            "consumption_time": datetime.now().strftime("%H:%M:%S"),
            "consumed_without_reservation": reserve_id is None,
            "reserve_id": reserve_id,
        }
        try:
            created_consumption = self.consumption_crud.create(
                consumption_data)
            if created_consumption:
                self._served_pronts.add(pront)
                logger.info(
                    f"Consumption recorded for {pront} in session {self._session_id}.")
                return True
            else:
                logger.error(
                    f"Failed to create consumption record for {pront} (CRUD returned non-True). Checking current status.")
                self.db_session.rollback()
                self._load_served_pronts_from_db()
                if pront in self._served_pronts:
                    logger.warning(
                        f"Consumption record for {pront} appears to exist now (possible race condition or conflict).")
                return False
        except SQLAlchemyError as e:
            logger.exception(
                f"Error recording consumption for {pront} in session {self._session_id}: {e}")
            self.db_session.rollback()
            self._load_served_pronts_from_db()
            if pront in self._served_pronts:
                logger.warning(
                    f"Consumption recording failed for {pront}, but DB shows served status.")
            return False
        except Exception as e:
            logger.exception(
                f"Unexpected error recording consumption for {pront}: {e}")
            self.db_session.rollback()
            return False
    def delete_consumption(self, student_info: Tuple[str, str, str, str, str]) -> bool:
        if self._session_id is None:
            logger.error("Cannot delete consumption: No active session.")
            return False
        pront = student_info[0]
        if pront not in self._served_pronts:
            logger.warning(
                f"Cannot delete consumption: {pront} is not marked as served in this session.")
            return False
        student_id, _ = self._get_or_find_student_details(pront)
        if student_id is None:
            logger.error(
                f"Inconsistency: {pront} in served cache, but student not found for deletion.")
            self._served_pronts.discard(pront)
            return False
        try:
            delete_stmt = delete(Consumption).where(
                Consumption.student_id == student_id,
                Consumption.session_id == self._session_id
            )
            result = self.db_session.execute(delete_stmt)
            deleted_count = result.rowcount
            if deleted_count > 0:
                self.db_session.commit()
                self._served_pronts.discard(pront)
                logger.info(
                    f"Consumption record deleted for {pront} in session {self._session_id} ({deleted_count} row(s)).")
                return True
            else:
                self.db_session.rollback()
                logger.warning(
                    f"No consumption record found in DB to delete for {pront} in session {self._session_id}. Cache might be inconsistent.")
                self._load_served_pronts_from_db()
                return False
        except SQLAlchemyError as e:
            logger.exception(
                f"DB error deleting consumption for {pront} in session {self._session_id}: {e}")
            self.db_session.rollback()
            return False
        except Exception as e:
            logger.exception(
                f"Unexpected error deleting consumption for {pront}: {e}")
            self.db_session.rollback()
            return False
    def sync_consumption_state(self, target_served_snapshot: List[Tuple[str, str, str, str, str]]):
        if self._session_id is None:
            logger.error("Cannot sync consumption state: No active session.")
            return
        logger.info(
            f"Starting consumption state sync for session {self._session_id}.")
        target_served_pronts: Set[str] = {item[0]
                                          for item in target_served_snapshot}
        current_served_pronts: Set[str] = self._served_pronts.copy()
        pronts_to_unmark = current_served_pronts.difference(
            target_served_pronts)
        pronts_to_mark = target_served_pronts.difference(current_served_pronts)
        logger.debug(
            f"Sync needed: Unmark {len(pronts_to_unmark)}, Mark {len(pronts_to_mark)}")
        try:
            if pronts_to_unmark:
                logger.debug(
                    f"Unmarking {len(pronts_to_unmark)} students: {pronts_to_unmark}")
                student_ids_to_unmark_subquery = self.db_session.query(Student.id)\
                                                     .filter(Student.pront.in_(pronts_to_unmark))\
                                                     .scalar_subquery()
                delete_stmt = delete(Consumption).where(
                    Consumption.session_id == self._session_id,
                    Consumption.student_id.in_(student_ids_to_unmark_subquery)
                )
                result_del = self.db_session.execute(delete_stmt)
                logger.info(
                    f"{result_del.rowcount} consumption records removed.")
            if pronts_to_mark:
                logger.debug(
                    f"Marking {len(pronts_to_mark)} students: {pronts_to_mark}")
                consumption_data_to_insert = []
                snapshot_map = {
                    item[0]: item for item in target_served_snapshot}
                for pront in pronts_to_mark:
                    student_id, reserve_id = self._get_or_find_student_details(
                        pront)
                    if student_id is None:
                        logger.warning(
                            f"Cannot mark {pront}: Student not found. Skipping.")
                        continue
                    hora_consumo = snapshot_map[pront][3] if pront in snapshot_map else datetime.now(
                    ).strftime("%H:%M:%S")
                    consumption_data_to_insert.append({
                        "student_id": student_id,
                        "session_id": self._session_id,
                        "consumption_time": hora_consumo,
                        "consumed_without_reservation": reserve_id is None,
                        "reserve_id": reserve_id,
                    })
                if consumption_data_to_insert:
                    logger.debug(
                        f"Attempting bulk insert of {len(consumption_data_to_insert)} consumption records.")
                    insert_stmt = sqlite_insert(Consumption).values(
                        consumption_data_to_insert)
                    insert_stmt = insert_stmt.on_conflict_do_nothing(
                        index_elements=['student_id', 'session_id']
                    )
                    result_ins = self.db_session.execute(insert_stmt)
                    logger.info(
                        f"Bulk insert attempt completed (affected rows: {result_ins.rowcount}).")
            self.db_session.commit()
            self._served_pronts = target_served_pronts
            logger.info(
                f"Consumption state sync completed successfully for session {self._session_id}.")
        except SQLAlchemyError as e:
            logger.exception(
                f"DB error during consumption state sync for session {self._session_id}: {e}")
            self.db_session.rollback()
            self._load_served_pronts_from_db()
        except Exception as e:
            logger.exception(
                f"Unexpected error during consumption state sync: {e}")
            self.db_session.rollback()
            self._load_served_pronts_from_db()
    def get_eligible_students(self) -> List[Dict[str, Any]]:
        if not self._filtered_students_cache:
            logger.debug(
                "Eligible students cache is empty. Triggering filter.")
            self.filter_eligible_students()
        return self._filtered_students_cache
    def get_served_students_details(self) -> List[Tuple[str, str, str, str, str]]:
        if self._session_id is None:
            logger.warning(
                "Cannot get served students details: No active session.")
            self._served_pronts = set()
            return []
        logger.debug(
            f"Querying DB for details of served students in session {self._session_id}.")
        try:
            s, g, r, c = aliased(Student), aliased(
                Group), aliased(Reserve), aliased(Consumption)
            query = self.db_session.query(
                s.pront,
                s.nome,
                func.group_concat(g.nome.distinct()).label(
                    'turmas_concat'),
                c.consumption_time,
                case(
                    (c.reserve_id.isnot(None), r.dish),
                    else_="Sem Reserva"
                ).label('prato_status')
            ).select_from(c)\
                .join(s, c.student_id == s.id)\
                .join(s.groups.of_type(g)) \
                .outerjoin(r, c.reserve_id == r.id) \
                .filter(c.session_id == self._session_id)\
                .group_by(s.id, s.pront, s.nome, c.consumption_time, c.reserve_id, r.dish) \
                .order_by(c.consumption_time.desc())
            served_results = query.all()
            served_students_data = []
            current_served_pronts = set()
            for pront, nome, turmas_str, hora, prato_status in served_results:
                turmas_fmt = ','.join(
                    sorted(list(set(turmas_str.split(',') if turmas_str else []))))
                served_students_data.append(
                    (pront, nome, turmas_fmt, hora, prato_status))
                current_served_pronts.add(pront)
            self._served_pronts = current_served_pronts
            logger.info(
                f"{len(served_students_data)} served student details retrieved for session {self._session_id}.")
            return served_students_data
        except SQLAlchemyError as e:
            logger.exception(
                f"DB error retrieving served students details for session {self._session_id}: {e}")
            self.db_session.rollback()
            self._served_pronts = set()
            return []
        except Exception as e:
            logger.exception(
                f"Unexpected error retrieving served students details: {e}")
            self._served_pronts = set()
            return []
