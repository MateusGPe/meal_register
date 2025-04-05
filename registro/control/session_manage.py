# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides classes for managing meal serving sessions.
"""

from typing import Any, Dict, List, Optional, Tuple

from registro.control.generic_crud import CRUD
from registro.control.meal_session_handler import MealSessionHandler
from registro.control.session_metadata_manager import SessionMetadataManager
from registro.model.tables import Group, Reserve, Student

class SessionManager:
    """
    Manages meal serving sessions by coordinating the MealSessionHandler
    and SessionMetadataManager.
    """

    def __init__(self, fn):
        """
        Initializes the SessionManager.

        Args:
            fn (str): The filename for storing session information.
        """
        self.metadata_manager = SessionMetadataManager(fn)
        self.meal_handler = MealSessionHandler(
            self.metadata_manager.database_session)
        self.student_crud: CRUD[Student] = CRUD[Student](
            self.metadata_manager.database_session, Student)

        self.reserve_crud: CRUD[Reserve] = CRUD[Reserve](
            self.metadata_manager.database_session, Reserve)
        self.turma_crud: CRUD[Group] = CRUD[Group](
            self.metadata_manager.database_session, Group)

    def get_spreadsheet(self):
        """Returns the SpreadSheet object."""
        return self.metadata_manager.get_spreadsheet()

    def get_date(self):
        """Returns the current session date."""
        return self.metadata_manager.get_date()

    def get_meal_type(self):
        """Returns the current session meal type."""
        return self.metadata_manager.get_meal_type()

    def get_time(self):
        """Returns the current session time."""
        return self.metadata_manager.get_time()

    def get_served_registers(self):
        """Returns the set of PRONTs of students served in the current session."""
        return self.meal_handler.get_served_registers()

    def filter_students(self):
        """
        Loads reserves and filters students based on selected classes.
        Returns:
            Optional[List[Dict]]: A list of student information.
        """
        session_info = self.metadata_manager.load_session()
        if session_info is None:
            return None
        self.meal_handler.set_session_info(
            *self.metadata_manager.get_session_info()
        )
        return self.meal_handler.filter_students()

    def create_student(self, student: Tuple[str, str, str, str, str]) -> bool:
        """
        Marks a student as served in the current session.
        """
        return self.meal_handler.create_student(student)

    def delete_student(self, student: Tuple[str, str, str, str, str]) -> bool:
        """
        Unmarks a student as served in the current session.
        """
        return self.meal_handler.delete_student(student)

    def load_session(self) -> Optional[dict]:
        """
        Loads session information from the session file.
        """
        return self.metadata_manager.load_session()

    def save_session(self) -> bool:
        """Saves the current session information to the session file."""
        return self.metadata_manager.save_session()

    def get_served_students(self) -> List[Tuple[str, str, str, str, str]]:
        """
        Retrieves the list of students marked as served in the current session
        from the database.
        """
        self.meal_handler.set_session_info(
            *self.metadata_manager.get_session_info()
        )
        return self.meal_handler.get_served_students()

    def get_session_classes(self):
        """Returns the list of classes selected for the current session."""
        return self.metadata_manager.get_session_classes()

    def set_students(self, served_update: List[Tuple[str, str, str, str, str]]):
        """
        Updates the list of served students for the current session.
        """
        self.meal_handler.set_session_info(
            *self.metadata_manager.get_session_info()
        )
        self.meal_handler.set_students(served_update)

    def new_session(self, session: Dict[str, Any]):
        """
        Creates a new serving session.
        """
        return self.metadata_manager.new_session(session)

    def set_session_classes(self, classes):
        """
        Sets the classes for the current session.
        """
        return self.metadata_manager.set_session_classes(classes)

    def get_session_students(self):
        """Returns the list of filtered students for the current session."""
        return self.meal_handler.get_session_students()
