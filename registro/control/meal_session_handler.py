# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>


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
            database_session: The SQLAlchemy session.
        """
        self.database_session = database_session
        self.student_crud: CRUD[Student] = CRUD[Student](
            self.database_session, Student)
        self.reserve_crud: CRUD[Reserve] = CRUD[Reserve](
            self.database_session, Reserve)
        self.consumption_crud: CRUD[Consumption] = CRUD[Consumption](
            self.database_session, Consumption)
        self._session_id: Optional[int] = None
        self._date: Optional[str] = None
        self._meal_type: Optional[str] = None
        self._turmas: Optional[List[str]] = None
        self._served_meals: List[Tuple] = []
        self._current_session_pronts: Set[str] = set()
        self._filtered_discentes: List[Dict] = []
        self._pront_to_reserve_id_map: Dict[str, int] = {}
        self._snacks: bool = False

    def set_session_info(self, session_id: Optional[int], date: Optional[str],
                         meal_type: Optional[str], turmas: Optional[List[str]]):
        """Sets the session information."""
        self._session_id = session_id
        self._date = date
        self._meal_type = meal_type
        self._turmas = turmas
        self._snacks = self._meal_type.lower() == "lanche" if self._meal_type else False

    def get_served_registers(self):
        """Returns the set of PRONTs of students served in the current session."""
        return self._current_session_pronts

    def filter_students(self):
        """
        Loads reserves and filters students based on selected classes,
        including students without reservations if 'SEM RESERVA' is selected.
        Returns:
            Optional[List[Dict]]: A list of student information.
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

        results = self.database_session.query(
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
        for pront, nome, turma, dish, data, student_id, reserve_id in results:
            if pront not in processed_students:
                processed_students[pront] = {
                    "Pront": pront,
                    "Nome": nome,
                    "Turma": [turma],
                    "Prato": dish,
                    "Data": data,
                    "id": to_code(pront),
                    "Hora": None,
                    "reserve_id": reserve_id,
                    "student_id": student_id,
                }
                reserved_pronts.add(pront)
                self._pront_to_reserve_id_map[pront] = reserve_id
            else:
                processed_students[pront]["Turma"].append(turma)
                if processed_students[pront]["reserve_id"] is None:
                    processed_students[pront]["reserve_id"] = reserve_id

                if processed_students[pront]["Prato"] == "Sem Reserva":
                    processed_students[pront]["Prato"] = dish

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
        """
        results = self.database_session.query(
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
            student (Tuple): A tuple containing student information:
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
            student (Tuple): A tuple containing student information:
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
        """Returns the list of filtered students for the current session."""
        return self._filtered_discentes

    def get_served_students(self) -> List[Tuple[str, str, str, str, str]]:
        """
        Retrieves the list of students marked as served in the current session
        from the database.
        """
        if self._session_id is None:
            return []

        served_consumptions = self.consumption_crud.read_filtered(
            session_id=self._session_id
        )

        served_students_data: List[Tuple[str, str, str, str, str]] = []
        served_pronts: Set[str] = set()

        for consumption in served_consumptions:
            student = self.student_crud.read_one(consumption.student_id)
            if student:
                reserve = self.reserve_crud.read_one(
                    consumption.reserve_id) if consumption.reserve_id else None
                meal_type = reserve.dish if reserve else "Sem Reserva"
                served_students_data.append(
                    (student.pront, student.nome, ','.join(t.nome for t in student.groups),
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
            served_update (List[Tuple]): A list of tuples, where each tuple
                                            contains information about a served student.
        """
        if self._session_id is None:
            return

        current_served_pronts: Set = {i[0] for i in self._served_meals}
        updated_served_pronts: Set = {i[0] for i in served_update}

        # Handle students who were unmarked as served
        unmarked_pronts = current_served_pronts.difference(
            updated_served_pronts)
        if unmarked_pronts:
            self.database_session.execute(
                delete(Consumption).where(
                    Consumption.session_id == self._session_id,
                    Consumption.student_id.in_(
                        select(Student.id).where(
                            Student.pront.in_(unmarked_pronts))
                    )
                )
            )
            self.database_session.commit()

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
            self.database_session.execute(
                insert(Consumption).values(consumption_data_to_insert)
            )
            self.database_session.commit()

        self._served_meals = served_update
        self._current_session_pronts = updated_served_pronts
        self.filter_students()
