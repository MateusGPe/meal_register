# ----------------------------------------------------------------------------
# File: registro/control/session_manage.py (Controller Facade)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
import logging
from typing import Any, Dict, List, Optional, Tuple, Set
from registro.control.generic_crud import CRUD
from registro.control.meal_session_handler import MealSessionHandler
from registro.control.session_metadata_manager import SessionMetadataManager
from registro.model.tables import Group, Reserve, Session, Student
from registro.control.constants import NewSessionData
logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self):
        logger.info("Initializing SessionManager...")
        try:
            self.metadata_manager = SessionMetadataManager()
            self.meal_handler = MealSessionHandler(
                self.metadata_manager.database_session
            )
            self.student_crud: CRUD[Student] = CRUD[Student](
                self.metadata_manager.database_session, Student
            )
            self.reserve_crud: CRUD[Reserve] = CRUD[Reserve](
                self.metadata_manager.database_session, Reserve
            )
            self.turma_crud: CRUD[Group] = CRUD[Group](
                self.metadata_manager.database_session, Group
            )
            self.session_crud: CRUD[Session] = CRUD[Session](
                self.metadata_manager.database_session, Session
            )
            logger.info("SessionManager initialized successfully.")
        except Exception as e:
            logger.critical("Critical failure during SessionManager initialization.", exc_info=True)
            raise RuntimeError(f"Failed to initialize SessionManager: {e}") from e
    def get_spreadsheet(self) -> Optional[Any]:
        return self.metadata_manager.get_spreadsheet()
    def get_date(self) -> Optional[str]:
        return self.metadata_manager.get_date()
    def get_meal_type(self) -> Optional[str]:
        return self.metadata_manager.get_meal_type()
    def get_time(self) -> Optional[str]:
        return self.metadata_manager.get_time()
    def save_session_state(self) -> bool:
        return self.metadata_manager.save_session_state()
    def get_session_classes(self) -> List[str]:
        return self.metadata_manager.get_session_classes()
    def get_session_info(self) -> Optional[Tuple[int, str, str, List[str]]]:
        return self.metadata_manager.get_session_info()
    def load_session(self, session_id: Optional[int] = None) -> Optional[dict]:
        action = f"Loading session by ID: {session_id}" if session_id else "Loading session from state file"
        logger.info(action)
        session_info = self.metadata_manager.load_session(session_id)
        session_details = self.metadata_manager.get_session_info()
        if session_info and session_details:
            logger.info(f"Session {session_details[0]} loaded. Updating MealHandler context.")
            self.meal_handler.set_session_info(*session_details)
        elif session_info and not session_details:
            logger.error("Session state loaded, but failed to retrieve session details for MealHandler!")
            self.meal_handler.set_session_info(None, None, None, None)
        else:
            logger.warning("No session could be loaded.")
            self.meal_handler.set_session_info(None, None, None, None)
        return session_info
    def set_session_classes(self, classes: List[str]) -> Optional[List[str]]:
        logger.info(f"Attempting to set session classes to: {classes}")
        updated_classes = self.metadata_manager.set_session_classes(classes)
        session_details = self.metadata_manager.get_session_info()
        if updated_classes is not None and session_details:
            self.meal_handler.set_session_info(*session_details)
            logger.info("Session classes updated and MealHandler context refreshed.")
        elif updated_classes is not None and not session_details:
            logger.error("Session classes updated in DB, but failed to refresh MealHandler context!")
            return None
        else:
            logger.error("Failed to update session classes in SessionMetadataManager.")
        return updated_classes
    def new_session(self, session_data: NewSessionData) -> bool:
        logger.info(f"Attempting to create new session with data: {session_data}")
        success = self.metadata_manager.new_session(session_data)
        session_details = self.metadata_manager.get_session_info()
        if success and session_details:
            self.meal_handler.set_session_info(*session_details)
            logger.info(f"New session {session_details[0]} created and MealHandler context set.")
        elif success and not session_details:
            logger.error("New session created in DB, but failed to retrieve details to update MealHandler!")
            return False
        elif not success:
            logger.error("Failed to create new session via SessionMetadataManager.")
        return success
    def get_served_pronts(self) -> Set[str]:
        return self.meal_handler.get_served_pronts()
    def filter_eligible_students(self) -> Optional[List[Dict[str, Any]]]:
        return self.meal_handler.filter_eligible_students()
    def record_consumption(self, student_info: Tuple[str, str, str, str, str]) -> bool:
        return self.meal_handler.record_consumption(student_info)
    def delete_consumption(self, student_info: Tuple[str, str, str, str, str]) -> bool:
        return self.meal_handler.delete_consumption(student_info)
    def get_served_students_details(self) -> List[Tuple[str, str, str, str, str]]:
        return self.meal_handler.get_served_students_details()
    def get_eligible_students(self) -> List[Dict[str, Any]]:
        return self.meal_handler.get_eligible_students()
    def sync_consumption_state(self, served_update: List[Tuple[str, str, str, str, str]]):
        logger.debug(f"Initiating consumption state sync with {len(served_update)} target records.")
        session_details = self.metadata_manager.get_session_info()
        if session_details:
            current_handler_sid = self.meal_handler._session_id
            if current_handler_sid != session_details[0]:
                logger.warning(
                    f"MealHandler session context ({current_handler_sid}) differs from active session ({session_details[0]}). "
                    f"Forcing update before sync_consumption_state.")
                self.meal_handler.set_session_info(*session_details)
            self.meal_handler.sync_consumption_state(served_update)
        else:
            logger.error("Cannot sync consumption state: Active session information is unavailable.")
    def close_resources(self):
        logger.info("Closing SessionManager resources (delegating to metadata_manager)...")
        if self.metadata_manager:
            self.metadata_manager.close_db_session()
        else:
            logger.warning("MetadataManager not initialized, cannot close resources.")
        logger.info("SessionManager resources closed.")
