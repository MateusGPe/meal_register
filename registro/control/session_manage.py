# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides a class for managing meal serving sessions, including loading
reserves, tracking served students, and exporting session data.
"""

import json
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import xlsxwriter
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from registro.control.generic_crud import CRUD
from registro.control.reserves import reserve_snacks
from registro.control.sync_session import SpreadSheet
from registro.control.utils import (SESSION, get_documments_path, load_json,
                                    save_json, to_code)
from registro.model.tables import Base, Reserve, Session, Students, Consumption

TRANSLATE_DICT = str.maketrans("0123456789Xx", "abcdefghijkk")
REMOVE_IQ = re.compile(r"[Ii][Qq]\d0+")

INTEGRATE_CLASSES = [
    "1º A - MAC",
    "2º A - MAC",
    "1º A - MEC",
    "1º B - MEC",
    "2º A - MEC",
    "2º B - MEC",
    "3º A - MEC",
    "3º B - MEC",
]
OTHERS = ["SEM RESERVA"]

ANYTHING = INTEGRATE_CLASSES + OTHERS


class SessionManager:
    """
    Manages meal serving sessions, including loading reserves, tracking served
    students, and exporting session data to a spreadsheet.
    """

    def __init__(self, fn):
        """
        Initializes the SessionManager.

        Args:
            fn (str): The filename for storing session information.
        """
        self.filename = fn
        self.engine = create_engine("sqlite:///./config/registro.db")
        Base.metadata.create_all(self.engine)

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine)

        self.database_session = session_local()

        self.student_crud: CRUD[Students] = CRUD[Students](
            self.database_session, Students)

        self.reserve_crud: CRUD[Reserve] = CRUD[Reserve](
            self.database_session, Reserve)

        self.session_crud: CRUD[Session] = CRUD[Session](
            self.database_session, Session)

        self.consumption_crud: CRUD[Consumption] = CRUD[Consumption](
            self.database_session, Consumption)

        self._session_id: Optional[int] = None
        self._periodo: Optional[str] = None
        self._hora: Optional[str] = None
        self._turmas: Optional[List[str]] = None
        self._date: Optional[str] = None
        self._meal_type: Optional[str] = None

        self._served_meals: List[Tuple] = []
        self._session_info: Optional[dict] = None

        self._current_session_pronts: Set[str] = set()

        try:
            self._spread: SpreadSheet = SpreadSheet()
        except Exception:  # pylint: disable=broad-except
            sys.exit(1)

        self._all_reserves: List[Dict] = []
        self._filtered_discentes: List[Dict] = []
        self._xls_saved: str = ""
        self._pront_to_reserve_id_map: Dict[str, int] = {}
        self._snacks: bool = False

    def get_spreadsheet(self):
        """Returns the SpreadSheet object."""
        return self._spread

    def get_date(self):
        """Returns the current session date."""
        return self._date

    def get_meal_type(self):
        """Returns the current session meal type."""
        return self._meal_type

    def load_reserves(self):
        """
        Loads the reserves for the current session from the database.

        Returns:
            Optional[List[Dict]]: A list of student reserve information or None if
                                   the session info cannot be loaded.
        """
        if not self._session_info and not self.load_session():
            return None

        is_snack = self._meal_type.lower() == "lanche"

        reserves = self.reserve_crud.read_filtered(
            data=self._date, snacks=is_snack
        )

        self._all_reserves = []
        for reserve in reserves:
            student = self.student_crud.read_one(reserve.student_id)
            if student:
                self._all_reserves.append(
                    {
                        "Pront": student.pront,
                        "Nome": student.nome,
                        "Turma": student.turma,
                        "Prato": reserve.prato,
                        "Data": reserve.data,
                        "id": to_code(student.pront),
                        "Hora": None,  # Consumption time will be set later
                        "reserve_id": reserve.id,
                        "student_id": student.id,
                    }
                )
                self._pront_to_reserve_id_map[student.pront] = reserve.id

        if self._all_reserves is None:
            return None

        return self.filter_students()

    def get_served_registers(self):
        """Returns the set of PRONTs of students served in the current session."""
        return self._current_session_pronts

    def filter_students(self):
        """
        Filters the loaded reserves based on the selected classes for the session.

        Returns:
            List[Dict]: A list of student reserve information filtered by class.
        """
        if self._all_reserves is None or self._turmas is None:
            print(
                "Error: Required data (self._all_reserves) is not loaded.",
                file=sys.stderr,
            )
            return []

        selected_turmas = set(self._turmas)
        self._filtered_discentes = []

        reserved = 'SEM RESERVA' not in selected_turmas
        selected_turmas.discard("SEM RESERVA")

        for student_data in self._all_reserves:
            turma = student_data.get("Turma")
            meal = student_data.get('Prato')

            if meal.upper() == "SEM RESERVA" and reserved:
                continue

            if turma in selected_turmas:
                self._filtered_discentes.append(student_data)

        return self._filtered_discentes

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

        consumption_data = {
            "student_id": self.student_crud.read_filtered(pront=pront)[0].id,
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

        student_record = self.student_crud.read_filtered(pront=pront)[0]
        consumption = self.consumption_crud.read_filtered(
            student_id=student_record.id, session_id=self._session_id
        )
        if consumption:
            self.consumption_crud.delete(consumption[0].id)

        self._served_meals.remove(student)
        self._current_session_pronts.remove(pront)
        return True

    def load_session(self) -> Optional[dict]:
        """
        Loads session information from the session file.

        Returns:
            Optional[dict]: A dictionary containing the loaded session information
                             or None if the file cannot be loaded or the session ID
                             is invalid.
        """
        self._session_info = load_json(self.filename)

        if self._session_info is None:
            return None

        self._session_id = self._session_info.get("session_id", -1)

        if self._session_id == -1:
            self._session_id = None
            return None

        session_ = self.session_crud.read_one(self._session_id)

        if not session_:
            return None

        self._date = session_.data
        self._snacks = session_.refeicao == "lanche"
        self._update_session(session_, [])
        return self._session_info

    def _update_session(self, session_: Session, discentes_: List[Any]):
        """
        Updates the SessionManager's attributes based on the provided Session object.

        Args:
            session_ (Session): The Session object from the database.
            discentes_ (List[Any]): A list of served students (not currently used).
        """
        self._meal_type = session_.refeicao
        self._periodo = session_.periodo
        self._date = session_.data
        self._hora = session_.hora
        self._turmas = json.loads(session_.turmas)
        self._served_meals = discentes_

    def get_sheet_path(self):
        """Returns the path to the exported spreadsheet."""
        return self._xls_saved

    def get_session_students(self):
        """Returns the list of filtered students for the current session."""
        return self._filtered_discentes

    def export_sheet(self):
        """
        Exports the served students data to an Excel spreadsheet.

        Returns:
            bool: True if the export was successful, False otherwise.
        """
        self.save_session()
        try:
            name = f"{self._meal_type} {str(self._date.replace(
                '/', '-'))} {str(self._hora.replace(':', '.'))}"

            self._xls_saved = os.path.join(get_documments_path(), name+'.xlsx')

            workbook = xlsxwriter.Workbook(self._xls_saved)
            worksheet = workbook.add_worksheet(name)

            header = ["Matrícula", "Data", "Nome", "Turma", "Refeição", "Hora"]
            row = 0

            for hcol, item in enumerate(header):
                worksheet.write(row, hcol, item)

            for item in self._served_meals:
                row += 1
                worksheet.write(row, 0, item[0])
                worksheet.write(row, 1, self._date)
                worksheet.write(row, 2, item[1])
                worksheet.write(row, 3, item[2])
                worksheet.write(row, 4, item[4])
                worksheet.write(row, 5, item[3])

        except (IOError, ValueError) as e:
            print(f"Error: {e}")
            return False
        workbook.close()

        return True

    def save_session(self) -> bool:
        """Saves the current session information to the session file."""
        return save_json(self.filename, self._session_info)

    def get_served_students(self) -> List[Tuple[str, str, str, str, str]]:
        """
        Retrieves the list of students marked as served in the current session
        from the database.
        """
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
                meal_type = self._meal_type  # Assuming meal type is consistent for the session
                served_students_data.append(
                    (student.pront, student.nome, student.turma,
                     consumption.consumption_time, meal_type)
                )
                served_pronts.add(student.pront)

        self._served_meals = served_students_data
        self._current_session_pronts = served_pronts
        return self._served_meals

    def get_session_classes(self):
        """Returns the list of classes selected for the current session."""
        return self._turmas or []

    def set_students(self, served_update: List[Tuple[str, str, str, str, str]]):
        """
        Updates the list of served students for the current session.

        Args:
            served_update (List[Tuple]): A list of tuples, where each tuple
                                         contains information about a served student.
        """
        current_served_pronts: Set = {i[0] for i in self._served_meals}
        updated_served_pronts: Set = {i[0] for i in served_update}

        # Handle students who were unmarked as served
        unmarked_pronts = current_served_pronts.difference(
            updated_served_pronts)
        for pront in unmarked_pronts:
            student = self.student_crud.read_filtered(pront=pront)[0]
            consumption = self.consumption_crud.read_filtered(
                student_id=student.id, session_id=self._session_id
            )
            if consumption:
                self.consumption_crud.delete(consumption[0].id)

        # Handle students who were marked as served
        marked_pronts = updated_served_pronts.difference(current_served_pronts)
        for pront in marked_pronts:
            student_data = next(
                item for item in served_update if item[0] == pront)
            pront, nome, turma, hora, refeicao = student_data
            student = self.student_crud.read_filtered(pront=pront)[0]
            reserve_id = self._pront_to_reserve_id_map.get(pront)
            consumption_data = {
                "student_id": student.id,
                "session_id": self._session_id,
                "consumption_time": hora,
                "consumed_without_reservation": reserve_id is None,
                "reserve_id": reserve_id,
            }
            self.consumption_crud.create(consumption_data)

        self._served_meals = served_update
        self._current_session_pronts = updated_served_pronts
        self.load_reserves()

    def new_session(self, session: SESSION):
        """
        Creates a new serving session.

        Args:
            session (SessionDict): A dictionary containing the new session's information.

        Returns:
            bool: True if the session was created successfully, False otherwise.
        """
        refeicao = session["refeição"].lower()
        data = session["data"]
        self._date = data

        self._snacks = False
        reserves = self.reserve_crud.read_filtered(snacks=False, data=data)
        if refeicao == "almoço":
            if len(reserves) == 0:
                return False
        elif refeicao == "lanche":
            self._snacks = True
            reserves = self.reserve_crud.read_filtered(
                snacks=True, data=data
            )
            if len(reserves) == 0:
                reserve_snacks(self.student_crud,
                               self.reserve_crud, data, session['lanche'])
                reserves = self.reserve_crud.read_filtered(
                    snacks=True, data=data
                )

        session_data = {
            "refeicao": refeicao,
            "periodo": session["período"],
            "data": session["data"],
            "hora": session["hora"],
            "turmas": json.dumps(session["turmas"]),
        }
        session_ = self.session_crud.create(session_data)
        self._session_id = session_.id

        self._update_session(session_, [])
        self._session_info = {"session_id": session_.id}
        self.save_session()
        return True

    def set_session_classes(self, classes):
        """
        Sets the classes for the current session.

        Args:
            classes (List[str]): A list of class names.

        Returns:
            Optional[List[str]]: The updated list of classes or None if the
                                  session cannot be found.
        """
        session_ = self.session_crud.read_one(self._session_id)

        if not session_:
            return None

        session_.turmas = json.dumps(classes)
        self.session_crud.update(session_.id, {"turmas": session_.turmas})
        self._turmas = classes
        return self._turmas
