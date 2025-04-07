# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Module description.

This module provides functionality for managing meal serving session metadata.
It includes classes and functions for interacting with the Session and Group models.
"""

import json
import sys
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from registro.control.constants import DATABASE_URL, SESSION_PATH
from registro.control.generic_crud import CRUD
from registro.control.reserves import reserve_snacks
from registro.control.sync_session import SpreadSheet
from registro.control.utils import load_json, save_json
from registro.model.tables import Base, Reserve, Session, Student


class SessionMetadataManager:
    """
    Manages meal serving session metadata, including loading and saving
    session information and interacting with the Session and Group models.
    """

    def __init__(self):
        """
        Initializes the SessionMetadataManager.

        This sets up the database connection, initializes the CRUD operations
        for the Session model, and prepares attributes for session metadata.
        """
        engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(engine)

        self.database_session = sessionmaker(
            autocommit=False, autoflush=False, bind=engine)()

        self.session_crud: CRUD[Session] = CRUD[Session](
            self.database_session, Session)

        self._session_id: Optional[int] = None
        self._hora: Optional[str] = None
        self._turmas: Optional[List[str]] = None
        self._date: Optional[str] = None
        self._meal_type: Optional[str] = None

        self._spread: Optional[SpreadSheet] = None

    def get_spreadsheet(self):
        """
        Returns the SpreadSheet object.

        If the object has not been initialized, this method attempts to create a new instance.
        If the initialization fails, the program exits with an error.

        Returns:
            SpreadSheet: The SpreadSheet object.
        """
        if self._spread is None:
            try:
                self._spread = SpreadSheet()
            except Exception as e:  # pylint: disable=broad-except
                print(f"Error initializing SpreadSheet {type(e).__name__}: {e}")
                sys.exit(1)
        return self._spread

    def get_date(self):
        """
        Retrieves the current session date.

        Returns:
            Optional[str]: The current session date, or None if not set.
        """
        return self._date

    def get_meal_type(self):
        """
        Retrieves the current session meal type.

        Returns:
            Optional[str]: The current session meal type, or None if not set.
        """
        return self._meal_type

    def get_time(self):
        """
        Retrieves the current session time.

        Returns:
            Optional[str]: The current session time, or None if not set.
        """
        return self._hora

    def load_session(self, session_id: Optional[int] = None) -> Optional[dict]:
        """
        Loads session information from the session file.

        Returns:
            Optional[dict]: A dictionary containing the loaded session information,
                            or None if the file cannot be loaded or the session ID is invalid.
        """
        if session_id:
            _session_info = {"session_id": session_id}
            self._session_id = session_id
            self.save_session()
        else:
            _session_info = load_json(SESSION_PATH)

            if _session_info is None:
                return None

        self._session_id = _session_info.get("session_id", -1)

        if self._session_id == -1:
            self._session_id = None
            return None

        session_ = self.session_crud.read_one(self._session_id)

        if not session_:
            return None

        self._date = session_.data
        self._meal_type = session_.refeicao
        self._update_session(session_)
        return _session_info

    def _update_session(self, session_: Session):
        """
        Updates the SessionMetadataManager's attributes based on the provided Session object.

        Args:
            session_ (Session): The Session object retrieved from the database.
        """
        self._meal_type = session_.refeicao
        self._date = session_.data
        self._hora = session_.hora
        self._turmas = json.loads(session_.groups)

    def save_session(self) -> bool:
        """
        Saves the current session information to the session file.

        Returns:
            bool: True if the session information was saved successfully, False otherwise.
        """
        return save_json(SESSION_PATH, {"session_id": self._session_id})

    def get_session_classes(self):
        """
        Retrieves the list of classes selected for the current session.

        Returns:
            List[str]: A list of class names, or an empty list if no classes are set.
        """
        return self._turmas or []

    def set_session_classes(self, classes):
        """
        Sets the classes for the current session.

        Args:
            classes (List[str]): A list of class names.

        Returns:
            Optional[List[str]]: The updated list of classes, or None if
            the session cannot be found.
        """
        session_ = self.session_crud.read_one(self._session_id)

        if not session_:
            return None

        session_.groups = json.dumps(classes)
        self.session_crud.update(session_.id, {"groups": session_.groups})
        self._turmas = classes
        return self._turmas

    def new_session(self, session: Dict[str, Any]):
        """
        Creates a new meal serving session.

        Args:
            session (Dict[str, Any]): A dictionary containing the new session's information.

        Returns:
            bool: True if the session was created successfully, False otherwise.
        """
        refeicao = session["refeição"].lower()
        data = session["data"]
        self._date = data

        reserves = self.session_crud.get_session().query(Reserve).filter(
            Reserve.snacks == False, Reserve.data == data  # pylint: disable=singleton-comparison
        ).count()
        if refeicao == "almoço":
            if reserves == 0:
                return False
        elif refeicao == "lanche":
            snacks_reserves_count = self.session_crud.get_session().query(Reserve).filter(
                Reserve.snacks == True, Reserve.data == data  # pylint: disable=singleton-comparison
            ).count()

            if snacks_reserves_count == 0:
                student_crud = CRUD[Student](
                    self.session_crud.get_session(), Student)
                reserve_crud = CRUD[Reserve](
                    self.session_crud.get_session(), Reserve)
                reserve_snacks(student_crud, reserve_crud,
                               data, session['lanche'])

        session_data = {
            "refeicao": refeicao,
            "periodo": session["período"],
            "data": session["data"],
            "hora": session["hora"],
            "groups": json.dumps(session["groups"]),
        }
        session_ = self.session_crud.create(session_data)
        self._session_id = session_.id

        self._update_session(session_)
        self.save_session()
        return True

    def get_session_info(self) -> Tuple[int, str, str, List[str]]:
        """
        Retrieves the current session information.

        Returns:
            Tuple[int, str, str, List[str]]: A tuple containing the session ID, date,
                                             meal type, and list of selected classes.
        """
        return (
            self._session_id,
            self._date,
            self._meal_type,
            self._turmas
        )
