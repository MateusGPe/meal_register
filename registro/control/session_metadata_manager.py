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
from registro.model.tables import Base, Group, Reserve, Session, Student


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
                print(
                    f"Error initializing SpreadSheet {type(e).__name__}: {e}")
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

    def new_session(self, session_info: Dict[str, Any]) -> bool:
        """
        Creates a new meal serving session and handles related reserves.

        Args:
            session_info (Dict[str, Any]): A dictionary containing the new session's information.
                                           Expected keys: "refeição", "data", "período", "hora",
                                                          "lanche" (if refeição is lanche), "groups".

        Returns:
            bool: True if the session was created successfully, False otherwise.
        """
        db: Session = self.database_session  # Get session once

        try:
            refeicao = session_info["refeição"].lower()
            data = session_info["data"]
            self._date = data  # Store date if needed by other methods

            session_data = {
                "refeicao": refeicao,
                "periodo": session_info["período"],
                "data": data,
                "hora": session_info["hora"],
                # Use .get for safety
                "snack_name": session_info.get("lanche", '') if refeicao == "lanche" else '',
                "groups": json.dumps(session_info["groups"]),
            }

            # Create the base session object first (but don't commit yet)
            # Assuming session_crud.create adds to the session but doesn't commit
            session_ = self.session_crud.create(
                session_data, commit=False)  # Pass commit=False if possible
            if not session_:
                # Handle case where session creation itself failed before commit
                print("Error: Failed to create session object in memory.")
                # db.rollback() # No need to rollback if nothing was flushed yet
                return False

            self._session_id = session_.id  # Store session ID if needed

            if refeicao == "almoço":
                # Filter for existing *lunch* reserves for this date without a session
                lunch_reserve_filter = (
                    Reserve.snacks.is_(False),
                    Reserve.data == data,
                    Reserve.session_id.is_(None)
                )

                # Check if there are any reserves to assign
                reserves_to_update = db.query(Reserve).filter(
                    *lunch_reserve_filter).all()

                if not reserves_to_update:
                    print(
                        f"Warning: No unassigned lunch reserves found for date {data}. Session created but no reserves linked.")
                    # Decide if this is an error or just a warning.
                    # If it's an error and session shouldn't be created:
                    # db.rollback() # Rollback session creation
                    # return False
                    # If it's okay to have a session without reserves: proceed.

                # Update existing lunch reserves to link them to this new session
                db.query(Reserve).filter(*lunch_reserve_filter).update(
                    {"session_id": session_.id},
                    synchronize_session=False  # Important for bulk updates
                )
                print(f"Updated {len(reserves_to_update)} lunch reserves.")

            elif refeicao == "lanche":
                # Filter for existing *snack* reserves for this date without a session
                snack_reserve_filter = (
                    Reserve.snacks.is_(True),
                    Reserve.data == data,
                    Reserve.session_id.is_(None)
                )

                # Check if unassigned snack reserves already exist
                existing_snack_reserves_count = db.query(
                    Reserve).filter(*snack_reserve_filter).count()

                if existing_snack_reserves_count > 0:
                    # If reserves exist, just link them (optional, depending on requirements)
                    # If you want to link *existing* unassigned snack reserves:
                    db.query(Reserve).filter(*snack_reserve_filter).update(
                        {"session_id": session_.id},
                        synchronize_session=False
                    )
                    print(
                        f"Updated {existing_snack_reserves_count} existing snack reserves.")
                    # If you *don't* want to link existing ones automatically, remove the update above.

                else:
                    # No existing unassigned snack reserves found, create new ones for students in groups
                    # Instantiate CRUD helpers here if needed
                    reserve_crud = CRUD[Reserve](db, Reserve)

                    # Ensure it's a set for efficient lookup
                    target_groups = set(session_info["groups"])
                    if not target_groups:
                        print(
                            f"Warning: No groups specified for snack session {session_.id}. No reserves created.")
                    else:
                        # Find students in the specified groups
                        students_in_groups = (
                            db.query(Student)
                            # Assumes relationship named 'groups'
                            .join(Student.groups)
                            # Assumes Group model has 'nome'
                            .filter(Group.nome.in_(target_groups))
                            .all()
                        )

                        print(
                            f"Found {len(students_in_groups)} students in groups {target_groups} for snack session.")

                        if students_in_groups:
                            reserves_to_insert: List[Dict[str, Any]] = []
                            # Get snack name
                            snack_name = session_data["snack_name"]
                            for student in students_in_groups:
                                reserves_to_insert.append({
                                    'dish': snack_name,  # Use the actual snack name
                                    'data': data,
                                    'snacks': True,
                                    'canceled': False,
                                    'student_id': student.id,
                                    'session_id': session_.id  # Link to the new session
                                })

                            # Use bulk insert for efficiency
                            # Assuming reserve_crud.bulk_create uses session.bulk_insert_mappings or similar
                            reserve_crud.bulk_create(
                                reserves_to_insert, commit=False)  # Pass commit=False
                            print(
                                f"Bulk created {len(reserves_to_insert)} new snack reserves.")
                        else:
                            print(
                                f"Warning: No students found in the specified groups {target_groups}. No reserves created.")

            # --- Commit Transaction ---
            # All operations succeeded up to this point, now commit everything.
            db.commit()
            print(
                f"Session {session_.id} ({refeicao}) and related reserves committed successfully.")

            # --- Post-Commit Actions ---
            # These should ideally happen *after* the transaction is successful
            self._update_session(session_)  # Update internal state if needed
            self.save_session()  # Save other state if needed

            return True

        except Exception as e:
            print(f"Error creating session: {e}")
            if db:  # Check if db session was obtained
                db.rollback()  # Roll back any changes if an error occurred
            return False

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
