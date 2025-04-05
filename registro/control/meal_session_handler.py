# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
meal_session_handler.py

This module defines the `MealSessionHandler` class, which manages operations related to 
students, reservations, and meal consumption within a meal serving session. It provides 
methods to handle session information, filter students based on reservations and classes, 
mark students as served, and retrieve session-related data.

Classes:
    - MealSessionHandler: Handles the core logic for managing meal sessions, including 
      filtering students, tracking served meals, and interacting with the database.

Dependencies:
    - datetime: For handling date and time operations.
    - typing: For type annotations.
    - sqlalchemy: For database operations.
    - registro.control.generic_crud: Provides generic CRUD operations.
    - registro.control.utils: Utility functions for data processing.
    - registro.model.tables: Database table models for `Consumption`, `Group`, `Reserve`, 
      and `Student`.

Usage:
    The `MealSessionHandler` class is initialized with a SQLAlchemy database session and 
    provides methods to manage meal sessions, such as setting session information, filtering 
    students, marking students as served, and retrieving session data.
"""

from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import delete, insert, select

from registro.control.generic_crud import CRUD
from registro.control.utils import to_code
from registro.model.tables import Consumption, Group, Reserve, Student


class MealSessionHandler:
    """
    Handles operations related to students, reserves, and consumption
    within a meal serving session.
    """

    def __init__(self, database_session):
        """
        Initializes the MealSessionHandler.

        Args:
            database_session: The SQLAlchemy session used for database operations.
        """
        self.student_crud: CRUD[Student] = CRUD[Student](
            database_session, Student)
        # self.reserve_crud: CRUD[Reserve] = CRUD[Reserve](
        #     database_session, Reserve)
        self.consumption_crud: CRUD[Consumption] = CRUD[Consumption](
            database_session, Consumption)
        self._session_id: Optional[int] = None
        self._date: Optional[str] = None
        self._meal_type: Optional[str] = None
        self._turmas: Optional[List[str]] = None
        self._served_meals: List[Tuple] = []
        self._current_session_pronts: Set[str] = set()
        self._filtered_discentes: List[Dict] = []
        self._pront_to_reserve_id_map: Dict[str, int] = {}

    def set_session_info(self, session_id: Optional[int], date: Optional[str],
                         meal_type: Optional[str], turmas: Optional[List[str]]):
        """
        Sets the session information.

        Args:
            session_id (Optional[int]): The ID of the session.
            date (Optional[str]): The date of the session in 'YYYY-MM-DD' format.
            meal_type (Optional[str]): The type of meal (e.g., "lanche").
            turmas (Optional[List[str]]): A list of class names participating in the session.
        """
        self._session_id = session_id
        self._date = date
        self._meal_type = meal_type
        self._turmas = turmas

    def get_served_registers(self):
        """
        Retrieves the set of PRONTs of students who have been served in the current session.

        Returns:
            Set[str]: A set of PRONTs of served students.
        """
        return self._current_session_pronts

    def filter_students(self):
        """
        Loads reserves and filters students based on the selected classes.
        Includes students without reservations if 'SEM RESERVA' is selected.

        Returns:
            Optional[List[Dict]]: A list of dictionaries containing student information,
                                  or None if session information is incomplete.
        """
        if self._date is None or self._turmas is None:
            return None

        selected_turmas = set(self._turmas)
        filtered_students = []
        reserved_pronts = set()

        # Filter students with reservations
        self._filter_students_with_reservations(
            selected_turmas, filtered_students, reserved_pronts)

        # Add students without reservations if 'SEM RESERVA' is selected
        if 'SEM RESERVA' in selected_turmas:
            self._add_students_without_reservations(
                filtered_students, reserved_pronts, selected_turmas)

        self._filtered_discentes = filtered_students
        return self._filtered_discentes

    def _filter_students_with_reservations(
            self, selected_turmas: Set[str], filtered_students: List[Dict],
            reserved_pronts: Set[str]):
        """
        Filters students who have reservations based on the selected classes using a single query.

        Args:
            selected_turmas (Set[str]): The set of selected class names.
            filtered_students (List[Dict]): The list to append filtered student information.
            reserved_pronts (Set[str]): The set to add PRONTs of students with reservations.
        """
        is_snack = self._meal_type.lower() == "lanche"
        selected_classes_with_reserve = set(selected_turmas)
        if 'SEM RESERVA' in selected_classes_with_reserve:
            selected_classes_with_reserve.discard('SEM RESERVA')

        results = self.student_crud.get_session(
        ).query(
            Student.pront,
            Student.nome,
            Group.nome,
            Reserve.dish,
            Reserve.data,
            Student.id.label('student_id'),
            Reserve.id.label('reserve_id')
        ).join(Reserve, Reserve.student_id == Student.id).join(Student.groups).filter(
            Reserve.data == self._date,
            Reserve.snacks == is_snack,
            Group.nome.in_(selected_classes_with_reserve)
        ).all()

        processed_students = {}
        for student_item in results:
            pront = student_item[0]
            if pront not in processed_students:
                processed_students[pront] = {
                    "Pront": pront,
                    "Nome": student_item[1],
                    "Turma": [student_item[2]],
                    "Prato": student_item[3],
                    "Data": student_item[4],
                    "id": to_code(pront),
                    "Hora": None,
                    "reserve_id": student_item[6],
                    "student_id": student_item[5],
                }
                reserved_pronts.add(pront)
                self._pront_to_reserve_id_map[pront] = student_item[6]
            else:
                processed_students[pront]["Turma"].append(student_item[2])
                if processed_students[pront]["reserve_id"] is None:
                    processed_students[pront]["reserve_id"] = student_item[6]

                if processed_students[pront]["Prato"] == "Sem Reserva":
                    processed_students[pront]["Prato"] = student_item[3]

        for student_info in processed_students.values():
            student_info["Turma"] = ','.join(
                sorted(list(set(student_info["Turma"]))))
            filtered_students.append(student_info)

    def _add_students_without_reservations(
            self, filtered_students: List[Dict], reserved_pronts: Set[str],
            selected_turmas: Set[str]):
        """
        Adds students who do not have reservations and belong to the 'SEM RESERVA' class.

        Args:
            filtered_students (List[Dict]): The list to append student information.
            reserved_pronts (Set[str]): The set of PRONTs of students with reservations.
            selected_turmas (Set[str]): The set of selected class names.
        """
        results = self.student_crud.get_session().query(
            Student.pront,
            Student.nome,
            Group.nome,
            Student.id.label('student_id'),
        ).join(Reserve, Reserve.student_id == Student.id).join(Student.groups).filter(
            Group.nome.in_(selected_turmas),
            Student.pront.not_in(list(reserved_pronts))
        ).all()

        processed_students = {}
        for pront, nome, turma, student_id in results:
            if pront not in reserved_pronts:
                processed_students[pront] = {
                    "Pront": pront,
                    "Nome": nome,
                    "Turma": [turma],
                    "Prato": "Sem Reserva",
                    "Data": self._date,
                    "id": to_code(pront),
                    "Hora": None,
                    "reserve_id": None,
                    "student_id": student_id,
                }
            else:
                processed_students[pront]["Turma"].append(turma)

        for student_info in processed_students.values():
            student_info["Turma"] = ','.join(
                sorted(list(set(student_info["Turma"]))))
            filtered_students.append(student_info)

    def create_student(self, student: Tuple[str, str, str, str, str]) -> bool:
        """
        Marks a student as served in the current session.

        Args:
            student (Tuple[str, str, str, str, str]): A tuple containing student information:
                                                      (PRONT, Nome, Turma, Hora, Refeição).

        Returns:
            bool: True if the student was successfully marked as served, False otherwise.
        """
        pront = student[0]
        if pront in self._current_session_pronts:
            return False

        reserve_id = self._pront_to_reserve_id_map.get(pront)

        student_record = self.student_crud.read_filtered(pront=pront)
        if not student_record:
            return False  # Student not found

        consumption_data = {
            "student_id": student_record[0].id,
            "session_id": self._session_id,
            "consumption_time": datetime.now().strftime("%H:%M:%S"),
            "consumed_without_reservation": reserve_id is None,
            "reserve_id": reserve_id,
        }
        self.consumption_crud.create(consumption_data)

        self._served_meals.append(student)
        self._current_session_pronts.add(pront)
        return True

    def delete_student(self, student: Tuple[str, str, str, str, str]) -> bool:
        """
        Unmarks a student as served in the current session.

        Args:
            student (Tuple[str, str, str, str, str]): A tuple containing student information:
                                                      (PRONT, Nome, Turma, Hora, Refeição).

        Returns:
            bool: True if the student was successfully unmarked as served, False otherwise.
        """
        pront = student[0]
        if pront not in self._current_session_pronts:
            return False

        student_record = self.student_crud.read_filtered(pront=pront)
        if not student_record:
            return False  # Student not found

        consumption = self.consumption_crud.read_filtered(
            student_id=student_record[0].id, session_id=self._session_id
        )
        if consumption:
            self.consumption_crud.delete(consumption[0].id)

        self._served_meals.remove(student)
        self._current_session_pronts.remove(pront)
        return True

    def get_session_students(self):
        """
        Retrieves the list of filtered students for the current session.

        Returns:
            List[Dict]: A list of dictionaries containing filtered student information.
        """
        return self._filtered_discentes

    def get_served_students(self) -> List[Tuple[str, str, str, str, str]]:
        """
        Retrieves the list of students marked as served in the current session.

        Returns:
            List[Tuple[str, str, str, str, str]]: A list of tuples containing served student
            information: (PRONT, Nome, Turma, Hora, Refeição).
        """
        if self._session_id is None:
            return []

        served_consumptions: List[Consumption] = self.consumption_crud.read_filtered(
            session_id=self._session_id
        )

        if not served_consumptions:
            self._served_meals = []
            self._current_session_pronts = set()
            return self._served_meals

        student_ids: Set[int] = {consumption.student_id for consumption in served_consumptions}
        reserve_ids: Set[int] = {
            consumption.reserve_id for consumption in served_consumptions
            if consumption.reserve_id is not None}

        students: List[Student] = self.student_crud.get_session().query(Student).filter(
            Student.id.in_(list(student_ids)))

        reserves: List[Reserve] = self.student_crud.get_session().query(Reserve).filter(
            Reserve.id.in_(list(reserve_ids))) if reserve_ids else []

        student_map: Dict[int, Student] = {student.id: student for student in students}
        reserve_map: Dict[int, Reserve] = {reserve.id: reserve for reserve in reserves}

        served_students_data: List[Tuple[str, str, str, str, str]] = []
        served_pronts: Set[str] = set()

        for consumption in served_consumptions:
            student = student_map.get(consumption.student_id)
            if student:
                reserve = reserve_map.get(consumption.reserve_id)
                meal_type = reserve.dish if reserve else "Sem Reserva"
                served_students_data.append(
                    (student.pront, student.nome, ','.join(t.nome for t in student.groups if t),
                     consumption.consumption_time, meal_type)
                )
                served_pronts.add(student.pront)

        self._served_meals = served_students_data
        self._current_session_pronts = served_pronts
        return self._served_meals

    def set_students(self, served_update: List[Tuple[str, str, str, str, str]]):
        """
        Updates the list of served students for the current session.

        Args:
            served_update (List[Tuple[str, str, str, str, str]]): A list of tuples containing
            updated served student information: (PRONT, Nome, Turma, Hora, Refeição).
        """
        if self._session_id is None:
            return

        current_served_pronts: Set = {i[0] for i in self._served_meals}
        updated_served_pronts: Set = {i[0] for i in served_update}

        # Handle students who were unmarked as served
        unmarked_pronts = current_served_pronts.difference(
            updated_served_pronts)
        if unmarked_pronts:
            self.student_crud.get_session().execute(
                delete(Consumption).where(
                    Consumption.session_id == self._session_id,
                    Consumption.student_id.in_(
                        select(Student.id).where(
                            Student.pront.in_(unmarked_pronts))
                    )
                )
            )
            self.student_crud.get_session().commit()

        # Handle students who were marked as served
        marked_pronts = updated_served_pronts.difference(current_served_pronts)
        consumption_data_to_insert = []
        for pront in marked_pronts:
            student_data = next(
                item for item in served_update if item[0] == pront)
            pront, _, _, hora, _ = student_data
            student_record = self.student_crud.read_filtered(pront=pront)
            if student_record:
                reserve_id = self._pront_to_reserve_id_map.get(pront)
                consumption_data_to_insert.append({
                    "student_id": student_record[0].id,
                    "session_id": self._session_id,
                    "consumption_time": hora,
                    "consumed_without_reservation": reserve_id is None,
                    "reserve_id": reserve_id,
                })

        if consumption_data_to_insert:
            self.student_crud.get_session().execute(
                insert(Consumption).values(consumption_data_to_insert)
            )
            self.student_crud.get_session().commit()

        self._served_meals = served_update
        self._current_session_pronts = updated_served_pronts
        self.filter_students()
