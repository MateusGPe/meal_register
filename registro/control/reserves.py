# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides functions for importing student and reserve data from CSV files
and for reserving snacks for all students.
"""

import csv
from typing import Dict, List, Set, Tuple

from sqlalchemy.exc import SQLAlchemyError

from registro.control.generic_crud import CRUD
from registro.control.utils import adjust_keys
from registro.model.tables import Group, Reserve, Student


def _process_reserves(csv_reserves_data: Dict[str, str],
                      all_students_by_pront: Dict[str, Student]) -> Dict[str, str]:
    """
    Processes reserve data from a CSV file and prepares it for insertion.

    Args:
        csv_reserves_data (Dict[str, str]): Reserve data extracted from the CSV file.
        all_students_by_pront (Dict[str, Student]): Mapping of student 'pront' to Student objects.

    Returns:
        Dict[str, str]: A list of dictionaries representing reserves to be inserted.
    """
    reserves_to_insert: List[dict] = []
    for reserve_info in csv_reserves_data:
        pront = reserve_info['pront']
        if pront in all_students_by_pront:
            reserves_to_insert.append({
                'dish': reserve_info.get('dish'),
                'data': reserve_info['data'],
                'snacks': False,
                'canceled': reserve_info['canceled'],
                'student_id': all_students_by_pront[pront].id})
        else:
            print(f"Warning: Student with pront '{pront}' not found"
                  " in the database for a reserve entry.")
    return reserves_to_insert


def _process_reserve_row(
        row: Dict[str, str],
        new_students_data: Dict[str, Dict[str, str]],
        csv_reserves_data: List[Dict[str, str]],
        existing_students_pronts: Set[str]):
    """
    Processes a single row of reserve data from the CSV file.

    Args:
        row (Dict[str, str]): A single row of data from the CSV file.
        new_students_data (Dict[str, Dict[str, str]]): Dictionary to store new student data.
        csv_reserves_data (List[Dict[str, str]]): List to store reserve data from the CSV.
        existing_students_pronts (Set[str]): Set of existing student 'pront' values.

    Raises:
        KeyError: If a required key is missing in the row.
        csv.Error: If there is an error parsing the CSV file.
        SQLAlchemyError: If there is a database error.
    """
    try:
        row = adjust_keys(row)
        pront = row['pront']
        nome = row['nome']
        turma = row['turma']
        dish = row['dish']
        data = row['data']
        if pront not in new_students_data and pront not in existing_students_pronts:
            new_students_data[pront] = {
                'pront': pront, 'nome': nome, 'turma': turma}
        csv_reserves_data.append({
            'pront': pront, 'dish': dish, 'data': data, 'snacks': False,
            'canceled': False})
    except KeyError as e:
        print(f"Missing key in row: {row}. Error: {e}")
    except csv.Error as e:
        print(f"Error parsing CSV: {e}")
    except SQLAlchemyError as e:
        print(f"Database error: {e}")


def import_reserves_csv(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                        csv_file_path: str) -> bool:
    """
    Imports reserve data from a CSV file into the database.

    This function reads student and reserve information from a CSV file,
    creates new student records if they don't exist, and creates corresponding
    reserve entries. If a student does not have a reservation on a given date,
    a "Sem Reserva" entry is created.

    Args:
        student_crud (CRUD[Student]): CRUD object for interacting with the Students table.
        reserve_crud (CRUD[Reserve]): CRUD object for interacting with the Reserve table.
        csv_file_path (str): The path to the CSV file containing the reserve data.

    Returns:
        bool: True if the import was successful, False otherwise.
    """
    try:
        existing_students_pronts: Set[str] = {
            s.pront for s in student_crud.read_all()
        }
        new_students_data: Dict[str, Dict[str, str]] = {}
        csv_reserves_data: List[Dict[str, str]] = []

        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                _process_reserve_row(
                    row, new_students_data,
                    csv_reserves_data,
                    existing_students_pronts)
        if new_students_data:
            student_crud.bulk_create(list(new_students_data.values()))

        all_students_by_pront: Dict[str, Student] = {
            student.pront: student for student in student_crud.read_all()
        }

        reserves_to_insert: List[dict] = _process_reserves(
            csv_reserves_data, all_students_by_pront)

        if reserves_to_insert:
            reserve_crud.bulk_create(reserves_to_insert)
            reserve_crud.commit()

        print(f"Successfully imported data from {csv_file_path}")
        return True

    except FileNotFoundError:
        print(f"File not found: {csv_file_path}")
        return False
    except csv.Error as e:
        print(f"Error parsing CSV: {e}")
        return False
    except SQLAlchemyError as e:
        student_crud.rollback()
        print(f"Database error: {e}")
        return False
    except (TypeError, ValueError) as e:
        print(f"Invalid data: {e}")
        return False


def _get_existing_students_groups(student_crud: CRUD[Student],
                                  turma_crud: CRUD[Group]
                                  ) -> Tuple[Set[str], Set[str]]:
    """
    Retrieves existing student 'pront' values and group names from the database.

    Args:
        student_crud (CRUD[Student]): CRUD object for interacting with the Students table.
        turma_crud (CRUD[Group]): CRUD object for interacting with the Groups (Turmas) table.

    Returns:
        Tuple[Set[str], Set[str]]: A tuple containing sets of student 'pront'
                                    values and group names.
    """
    student_pronts = {s.pront for s in student_crud.read_all()}
    group_names = {t.nome for t in turma_crud.read_all()}
    return student_pronts, group_names


def _find_new_students_groups(csv_file_path: str,
                              existing_students: Set[str],
                              existing_groups: Set[str]
                              ) -> Tuple[Dict[str, Dict[str, str]], Set[str]]:
    """
    Identifies new students and groups from the CSV file.

    Args:
        csv_file_path (str): The path to the CSV file containing student data.
        existing_students (Set[str]): Set of existing student 'pront' values.
        existing_groups (Set[str]): Set of existing group names.

    Returns:
        Tuple[Dict[str, Dict[str, str]], Set[str]]: A dictionary of new students and a
                                                    set of new groups.
    """
    new_students: Dict[str, Dict[str, str]] = {}
    new_groups: Set[str] = set()

    try:
        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    row = adjust_keys(row)
                    pront = row['pront']
                    nome = row['nome']
                    turma_nome = row['turma']

                    if pront not in new_students and pront not in existing_students:
                        new_students[pront] = {'pront': pront, 'nome': nome}

                    if turma_nome not in existing_groups:
                        new_groups.add(turma_nome)

                except KeyError as e:
                    print(f"Missing key in row: {row}. Error: {e}")
                except (TypeError, ValueError) as e:
                    print(f"Error processing row: {row}. Error: {e}")
    except FileNotFoundError:
        print(f"File not found: {csv_file_path}")
        return {}, set()
    except csv.Error as e:
        print(f"Error parsing CSV: {e}")
        return {}, set()
    return new_students, new_groups


def _add_new_groups(turma_crud: CRUD[Group], new_groups: Set[str]) -> None:
    """
    Adds new groups to the database.

    Args:
        turma_crud (CRUD[Group]): CRUD object for interacting with the Groups (Turmas) table.
        new_groups (Set[str]): Set of new group names to be added.
    """
    groups_to_insert = [{'nome': nome} for nome in new_groups]
    if groups_to_insert:
        turma_crud.bulk_create(groups_to_insert)
        turma_crud.commit()


def _add_students_to_groups(student_crud: CRUD[Student],
                            turma_crud: CRUD[Group],
                            csv_file_path: str,
                            new_students: Dict[str, Dict[str, str]],
                            existing_students: Set[str]) -> bool:
    """
    Adds students to the database and associates them with groups.

    Args:
        student_crud (CRUD[Student]): CRUD object for interacting with the Students table.
        turma_crud (CRUD[Group]): CRUD object for interacting with the Groups (Turmas) table.
        csv_file_path (str): The path to the CSV file containing student data.
        new_students (Dict[str, Dict[str, str]]): Dictionary of new student data.
        existing_students (Set[str]): Set of existing student 'pront' values.

    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    try:
        all_groups: Dict[str, Group] = {
            turma.nome: turma for turma in turma_crud.read_all()
        }
        students_to_add: List[Student] = []

        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            for row in csv.DictReader(csvfile):
                try:
                    row = adjust_keys(row)
                    pront = row['pront']
                    nome = row['nome']
                    turma_nome = row['turma']

                    if pront in new_students or pront in existing_students:
                        student = (student_crud.read_filtered(
                            pront=pront, limit=1) or [None])[0]

                        if not student:
                            student = Student(pront=pront, nome=nome)
                            students_to_add.append(student)

                        if turma_nome in all_groups and student:
                            turma = all_groups[turma_nome]
                            if turma not in student.groups:
                                student.groups.append(turma)

                except KeyError as e:
                    print(f"Missing key in row: {row}. Error: {e}")
                except SQLAlchemyError as e:
                    student_crud.get_session().rollback()
                    print(
                        f"Database error during student-turma association: {e}")
                    return False

        if students_to_add:
            student_crud.get_session().add_all(students_to_add)
            student_crud.commit()
        return True
    except FileNotFoundError:
        print(f"File not found: {csv_file_path}")
        return False
    except csv.Error as e:
        print(f"Error parsing CSV: {e}")
        return False
    except SQLAlchemyError as e:
        student_crud.get_session().rollback()
        print(f"Database error: {e}")
        return False
    except (TypeError, ValueError) as e:
        print(f"Invalid data: {e}")
        return False


def import_students_csv(student_crud: CRUD[Student], turma_crud: CRUD[Group],
                        csv_file_path: str) -> bool:
    """
    Imports student data from a CSV file into the database, including group (turma) information.

    This function reads student information (pront, nome, turma) from a CSV
    file, creates new student and group records in the database if they don't
    already exist, and establishes the relationship between them.

    Args:
        student_crud (CRUD[Student]): CRUD object for interacting with the Students table.
        turma_crud (CRUD[Group]): CRUD object for interacting with the Groups (Turmas) table.
        csv_file_path (str): The path to the CSV file containing the student data.

    Returns:
        bool: True if the import was successful, False otherwise.
    """
    try:
        existing_students, existing_groups = _get_existing_students_groups(
            student_crud, turma_crud)

        new_students, new_groups = _find_new_students_groups(
            csv_file_path, existing_students, existing_groups
        )

        _add_new_groups(turma_crud, new_groups)

        if not _add_students_to_groups(
            student_crud, turma_crud, csv_file_path, new_students, existing_students
        ):
            return False

        print(
            f"Successfully imported students and groups from {csv_file_path}")
        return True

    except Exception as e:  # pylint: disable=broad-except
        print(f"An unexpected error occurred {type(e).__name__}: {e}")
        return False


def reserve_snacks(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                   data: str, dish: str) -> bool:
    """
    Reserves a specific snack for all students on a given date.

    This function creates a reserve entry for each student in the database
    for the specified snack and date.

    Args:
        student_crud (CRUD[Student]): CRUD object for interacting with the Students table.
        reserve_crud (CRUD[Reserve]): CRUD object for interacting with the Reserve table.
        data (str): The date for which to reserve the snack (in 'YYYY-MM-DD' format).
        dish (str): The name of the snack to reserve.

    Returns:
        bool: True if the snack reservation was successful for all students, False otherwise.
    """
    try:
        students = student_crud.read_all()

        reserves_to_insert: List[dict] = []
        for student in students:
            reserves_to_insert.append({
                'dish': dish,
                'data': data,
                'snacks': True,
                'canceled': False,
                'student_id': student.id
            })
        reserve_crud.bulk_create(reserves_to_insert)
        reserve_crud.commit()
        return True
    except SQLAlchemyError as e:
        reserve_crud.rollback()
        print(f"Database error: {e}")
        return False
    except (TypeError, ValueError) as e:
        print(f"Invalid data: {e}")
        return False
