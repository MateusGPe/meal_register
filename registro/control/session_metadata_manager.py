# ----------------------------------------------------------------------------
# File: registro/control/session_metadata_manager.py (Controller/Service Layer)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLASession
from sqlalchemy.exc import SQLAlchemyError
from registro.control.constants import DATABASE_URL, SESSION_PATH, NewSessionData
from registro.control.generic_crud import CRUD
from registro.control.reserves import reserve_snacks_for_all
from registro.control.sync_session import SpreadSheet
from registro.control.utils import load_json, save_json
from registro.model.tables import Base, Group, Reserve, Session, Student
logger = logging.getLogger(__name__)

class SessionMetadataManager:
    def __init__(self):
        logger.info("Initializing SessionMetadataManager...")
        try:
            engine = create_engine(DATABASE_URL, echo=False)
            Base.metadata.create_all(engine)
            session_local_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            self.database_session: SQLASession = session_local_factory()
            logger.info("Database connection and session established.")
        except SQLAlchemyError as db_err:
            logger.critical(f"Database connection/initialization failed: {db_err}", exc_info=True)
            print(f"CRITICAL DATABASE ERROR: {db_err}\nApplication cannot start.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            logger.critical(f"Unexpected error during database setup: {e}", exc_info=True)
            print(f"CRITICAL ERROR during database setup: {e}\nApplication cannot start.", file=sys.stderr)
            sys.exit(1)
        self.session_crud: CRUD[Session] = CRUD[Session](self.database_session, Session)
        self._session_id: Optional[int] = None
        self._hora: Optional[str] = None
        self._turmas_selecionadas: List[str] = []
        self._date: Optional[str] = None
        self._meal_type: Optional[str] = None
        self._spread: Optional[SpreadSheet] = None
    def get_spreadsheet(self) -> Optional[SpreadSheet]:
        if self._spread is None:
            logger.debug("SpreadSheet instance requested but not initialized. Initializing now.")
            try:
                self._spread = SpreadSheet()
                if not self._spread._ensure_initialized():
                    logger.error("Failed to initialize SpreadSheet instance.")
                    self._spread = None
            except Exception as e:
                logger.exception(f"Error occurred while initializing SpreadSheet: {e}")
                self._spread = None
        return self._spread
    def get_date(self) -> Optional[str]:
        return self._date
    def get_meal_type(self) -> Optional[str]:
        return self._meal_type
    def get_time(self) -> Optional[str]:
        return self._hora
    def get_session_classes(self) -> List[str]:
        return self._turmas_selecionadas or []
    def get_session_info(self) -> Optional[Tuple[int, str, str, List[str]]]:
        if self._session_id is None:
            return None
        return (
            self._session_id,
            self._date or "",
            self._meal_type or "",
            self._turmas_selecionadas or []
        )
    def load_session(self, session_id: Optional[int] = None) -> Optional[Dict[str, int]]:
        loaded_session_info: Optional[Dict[str, int]] = None
        target_session_id: Optional[int] = None
        source: str = ""
        if session_id is not None:
            target_session_id = session_id
            source = f"explicit ID {target_session_id}"
            logger.info(f"Attempting to load session using {source}.")
            self._session_id = target_session_id
            if not self.save_session_state():
                logger.warning(f"Failed to save session state file for attempted session ID: {target_session_id}")
        else:
            source = f"state file ({SESSION_PATH})"
            logger.info(f"Attempting to load session ID from {source}.")
            session_state = load_json(str(SESSION_PATH))
            if session_state and isinstance(session_state.get("session_id"), int) and session_state["session_id"] > 0:
                target_session_id = session_state["session_id"]
                logger.info(f"Found session ID {target_session_id} in state file.")
            else:
                logger.info(f"No valid session ID found in {source}. Clearing active session.")
                self._clear_session_attributes()
                if session_state is not None:
                    save_json(str(SESSION_PATH), {"session_id": None})
                return None
        if target_session_id is None:
            self._clear_session_attributes()
            return None
        session_obj: Optional[Session] = None
        try:
            session_obj = self.session_crud.read_one(target_session_id)
        except Exception as e:
            logger.exception(f"Error reading session ID {target_session_id} from database: {e}")
            self._clear_session_attributes()
            save_json(str(SESSION_PATH), {"session_id": None})
            return None
        if session_obj:
            self._session_id = session_obj.id
            self._update_session_attributes(session_obj)
            loaded_session_info = {"session_id": self._session_id}
            if not self.save_session_state():
                logger.warning(f"Failed to update session state file for loaded session ID: {self._session_id}")
            logger.info(f"Session {self._session_id} loaded successfully from {source}.")
            return loaded_session_info
        else:
            logger.warning(f"Session ID {target_session_id} (from {source}) not found in the database.")
            self._clear_session_attributes()
            save_json(str(SESSION_PATH), {"session_id": None})
            return None
    def _clear_session_attributes(self):
        logger.debug("Clearing internal session attributes.")
        self._session_id = None
        self._date = None
        self._meal_type = None
        self._hora = None
        self._turmas_selecionadas = []
    def _update_session_attributes(self, session_obj: Session):
        logger.debug(f"Updating internal attributes from Session object ID: {session_obj.id}")
        self._meal_type = session_obj.refeicao
        self._date = session_obj.data
        self._hora = session_obj.hora
        try:
            groups_list = json.loads(session_obj.groups or '[]')
            if isinstance(groups_list, list):
                self._turmas_selecionadas = groups_list
            else:
                logger.warning(
                    f"Unexpected data type for 'groups' in session {session_obj.id}. Expected list, got {type(groups_list)}. Resetting to empty.")
                self._turmas_selecionadas = []
        except json.JSONDecodeError:
            logger.error(
                f"Failed to decode JSON 'groups' for session {session_obj.id}. Content: '{session_obj.groups}'. Resetting to empty.")
            self._turmas_selecionadas = []
        except Exception as e:
            logger.exception(f"Unexpected error processing 'groups' for session {session_obj.id}: {e}")
            self._turmas_selecionadas = []
    def save_session_state(self) -> bool:
        session_id_to_save = self._session_id
        logger.debug(f"Saving session state: session_id={session_id_to_save} to {SESSION_PATH}")
        return save_json(str(SESSION_PATH), {"session_id": session_id_to_save})
    def set_session_classes(self, classes: List[str]) -> Optional[List[str]]:
        if self._session_id is None:
            logger.error("Cannot set session classes: No active session loaded.")
            return None
        logger.info(f"Attempting to update classes for active session {self._session_id} to: {classes}")
        try:
            classes_json = json.dumps(classes)
            updated_session = self.session_crud.update(self._session_id, {"groups": classes_json})
            if updated_session:
                self._turmas_selecionadas = classes
                logger.info(f"Successfully updated classes for session {self._session_id}.")
                return self._turmas_selecionadas
            else:
                logger.error(
                    f"Failed to update classes for session {self._session_id} in database (update returned None).")
                return None
        except json.JSONDecodeError as json_err:
            logger.error(f"Error serializing class list to JSON for session {self._session_id}: {json_err}")
            return None
        except SQLAlchemyError as db_err:
            logger.exception(f"Database error updating classes for session {self._session_id}: {db_err}")
            self.database_session.rollback()
            return None
        except Exception as e:
            logger.exception(f"Unexpected error setting classes for session {self._session_id}: {e}")
            self.database_session.rollback()
            return None
    def new_session(self, session_data: NewSessionData) -> bool:
        refeicao = session_data.get("refeição", "").lower()
        data = session_data.get("data")
        periodo = session_data.get("período", "")
        hora = session_data.get("hora")
        groups = session_data.get("groups", [])
        lanche_nome = session_data.get("lanche")
        if not all([refeicao in ["lanche", "almoço"], data, hora]):
            logger.error(
                f"Cannot create new session: Missing required data (refeição, data, hora). Provided: {session_data}")
            return False
        logger.info(f"Attempting to create new session: Meal='{refeicao}', Date='{data}', Time='{hora}'")
        if not self._check_or_create_reserves(refeicao, data, lanche_nome):
            return False
        try:
            groups_json = json.dumps(groups)
        except TypeError as json_err:
            logger.error(f"Error serializing group list to JSON: {groups} - {json_err}")
            return False
        new_session_db_data = {
            "refeicao": refeicao,
            "periodo": periodo,
            "data": data,
            "hora": hora,
            "groups": groups_json,
        }
        try:
            new_session_obj = self.session_crud.create(new_session_db_data)
            if new_session_obj and new_session_obj.id:
                self._session_id = new_session_obj.id
                self._update_session_attributes(new_session_obj)
                self.save_session_state()
                logger.info(f"New session created successfully. Active session ID: {self._session_id}")
                return True
            else:
                logger.error("Failed to create new session record in DB (create returned None or invalid object).")
                self.database_session.rollback()
                return False
        except SQLAlchemyError as db_err:
            logger.exception(f"Database error creating new session: {db_err}")
            self.database_session.rollback()
            if "UNIQUE constraint failed" in str(db_err):
                logger.warning(
                    "Session creation failed, likely due to a duplicate session existing for the same meal/period/date/time.")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error creating new session: {e}")
            self.database_session.rollback()
            return False
    def _check_or_create_reserves(self, refeicao: str, data: str, snack_name: Optional[str]) -> bool:
        is_snack_session = (refeicao == "lanche")
        logger.debug(f"Checking reservations for: Meal='{refeicao}', Date='{data}', IsSnack={is_snack_session}")
        try:
            reserve_query = self.database_session.query(Reserve.id)\
                                .filter(Reserve.data == data,
                                        Reserve.snacks.is_(is_snack_session),
                                        Reserve.canceled.is_(False))
            reserves_exist = self.database_session.query(reserve_query.exists()).scalar()
            logger.debug(f"Reservations exist check for {data} ({refeicao}): {reserves_exist}")
            if is_snack_session:
                if not reserves_exist:
                    logger.warning(f"No snack reservations found for date {data}. Attempting automatic creation.")
                    student_crud = CRUD[Student](self.database_session, Student)
                    reserve_crud = CRUD[Reserve](self.database_session, Reserve)
                    actual_snack_name = snack_name if snack_name else 'Lanche Padrão'
                    logger.info(f"Calling reserve_snacks_for_all with Date='{data}', Dish='{actual_snack_name}'")
                    success = reserve_snacks_for_all(student_crud, reserve_crud, data, actual_snack_name)
                    if success:
                        reserves_now_exist = self.database_session.query(reserve_query.exists()).scalar()
                        if reserves_now_exist:
                            logger.info(f"Automatic snack reservations created successfully for {data}.")
                            return True
                        else:
                            logger.error(
                                f"reserve_snacks_for_all reported success, but no snack reserves found for {data} after creation attempt.")
                            return False
                    else:
                        logger.error(f"Automatic creation of snack reservations failed for {data}.")
                        return False
                else:
                    logger.info(f"Existing snack reservations found for {data}.")
                    return True
            else:
                if not reserves_exist:
                    logger.error(f"Cannot create 'Almoço' session for {data}: No existing lunch reservations found.")
                    return False
                else:
                    logger.info(f"Existing lunch reservations confirmed for {data}.")
                    return True
        except SQLAlchemyError as db_err:
            logger.exception(f"Database error checking/creating reservations for {data}: {db_err}")
            self.database_session.rollback()
            return False
        except Exception as e:
            logger.exception(f"Unexpected error checking/creating reservations for {data}: {e}")
            try:
                self.database_session.rollback()
            except Exception:
                pass
            return False
    def close_db_session(self):
        if self.database_session:
            try:
                logger.info("Closing database session...")
                self.database_session.close()
                logger.info("Database session closed.")
            except SQLAlchemyError as db_err:
                logger.error(f"Error closing the database session: {db_err}", exc_info=True)
            except Exception as e:
                logger.exception(f"Unexpected error closing database session: {e}")
        else:
            logger.warning("Attempted to close DB session, but it was not initialized.")
