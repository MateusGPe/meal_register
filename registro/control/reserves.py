# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides functions for importing student and reserve data from CSV files
and for reserving snacks for all students.
"""

import csv
from typing import Dict, List, Set

from sqlalchemy.exc import SQLAlchemyError

from registro.control.generic_crud import CRUD
from registro.control.utils import adjust_keys
from registro.model.tables import Reserve, Student, Turma


def import_reserves_csv(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                        csv_file_path: str) -> bool:
    """
    Imports reserve data from a CSV file into the database.

    This function reads student and reserve information from a CSV file,
    creates new student records if they don't exist, and creates corresponding
    reserve entries. It also handles cases where students might not have
    a reservation on a given date by creating a "Sem Reserva" entry.

    Args:
        student_crud (CRUD[Students]): CRUD object for interacting with the Students table.
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
                try:
                    row = adjust_keys(row)
                    pront = row['pront']
                    nome = row['nome']
                    turma = row['turma']
                    prato = row['prato']
                    data = row['data']

                    if pront not in new_students_data and pront not in existing_students_pronts:
                        new_students_data[pront] = {
                            'pront': pront, 'nome': nome, 'turma': turma}

                    csv_reserves_data.append({
                        'pront': pront, 'prato': prato, 'data': data, 'snacks': False,
                        'canceled': False})  # Added 'canceled' field
                except KeyError as e:
                    print(f"Missing key in row: {row}. Error: {e}")
                except csv.Error as e:
                    print(f"Error parsing CSV: {e}")
                except SQLAlchemyError as e:
                    print(f"Database error: {e}")

        if new_students_data:
            student_crud.bulk_create(list(new_students_data.values()))

        all_students_by_pront: Dict[str, Student] = {
            student.pront: student for student in student_crud.read_all()
        }

        reserves_to_insert: List[dict] = []
        for reserve_info in csv_reserves_data:
            pront = reserve_info['pront']
            if pront in all_students_by_pront:
                reserves_to_insert.append({
                    'prato': reserve_info.get('prato'),
                    'data': reserve_info['data'],
                    'snacks': False,
                    'canceled': reserve_info['canceled'],
                    'student_id': all_students_by_pront[pront].id})
            else:
                print(f"Warning: Student with pront '{pront}' not found"
                      " in the database for a reserve entry.")

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


def import_students_csv(student_crud: CRUD[Student], turma_crud: CRUD[Turma],
                        csv_file_path: str) -> bool:
    """
    Imports student data from a CSV file into the database, including turma information.

    This function reads student information (pront, nome, turma) from a CSV
    file, creates new student and turma records in the database if they don't
    already exist, and establishes the relationship between them.

    Args:
        db_session: The SQLAlchemy database session.
        student_crud (CRUD[Students]): CRUD object for interacting with the Students table.
        turma_crud (CRUD[Turma]): CRUD object for interacting with the Turmas table.
        csv_file_path (str): The path to the CSV file containing the student data.

    Returns:
        bool: True if the import was successful, False otherwise.
    """
    try:
        existing_students_pronts: Set[str] = {
            s.pront for s in student_crud.read_all()
        }
        existing_turmas_nomes: Set[str] = {
            t.nome for t in turma_crud.read_all()
        }
        new_students_data: Dict[str, Dict[str, str]] = {}
        new_turmas_nomes: Set[str] = set()

        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    row = adjust_keys(row)
                    pront = row['pront']
                    nome = row['nome']
                    turma_nome = row['turma']

                    if pront not in new_students_data and pront not in existing_students_pronts:
                        new_students_data[pront] = {
                            'pront': pront, 'nome': nome}
                        if turma_nome not in existing_turmas_nomes:
                            new_turmas_nomes.add(turma_nome)

                except KeyError as e:
                    print(f"Missing key in row: {row}. Error: {e}")
                except (TypeError, ValueError) as e:
                    print(f"Error processing row: {row}. Error: {e}")

        # Insert new turmas
        turmas_to_insert = [{'nome': nome} for nome in new_turmas_nomes]
        if turmas_to_insert:
            turma_crud.bulk_create(turmas_to_insert)
            turma_crud.commit()

        # Fetch all turmas (including the newly created ones)
        all_turmas_by_name: Dict[str, Turma] = {
            turma.nome: turma for turma in turma_crud.read_all()
        }

        # Insert new students and associate them with turmas
        students_to_insert = []
        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    row = adjust_keys(row)
                    pront = row['pront']
                    nome = row['nome']
                    turma_nome = row['turma']

                    if pront in new_students_data or pront in existing_students_pronts:
                        student = (student_crud.read_filtered(
                            pront=pront, limit=1) or [None])[0]

                        if not student:
                            student = Student(pront=pront, nome=nome)
                            students_to_insert.append(student)

                        if turma_nome in all_turmas_by_name:
                            turma = all_turmas_by_name[turma_nome]
                            if turma not in student.turmas:
                                student.turmas.append(turma)

                except KeyError as e:
                    print(f"Missing key in row: {row}. Error: {e}")
                except SQLAlchemyError as e:
                    student_crud.get_session().rollback()
                    print(
                        f"Database error during student-turma association: {e}")
                    return False

        if students_to_insert:
            student_crud.get_session().add_all(students_to_insert)
            student_crud.commit()

        print(
            f"Successfully imported students and turmas from {csv_file_path}")
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


def reserve_snacks(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                   data: str, prato: str) -> bool:
    """
    Reserves a specific snack for all students on a given date.

    Args:
        student_crud (CRUD[Students]): CRUD object for interacting with the Students table.
        reserve_crud (CRUD[Reserve]): CRUD object for interacting with the Reserve table.
        data (str): The date for which to reserve the snack (in 'YYYY-MM-DD' format).
        prato (str): The name of the snack to reserve.

    Returns:
        bool: True if the snack reservation was successful for all students, False otherwise.
    """
    try:
        students = student_crud.read_all()

        reserves_to_insert: List[dict] = []
        for student in students:
            reserves_to_insert.append({
                'prato': prato,
                'data': data,
                'snacks': True,
                'canceled': False,  # Added 'canceled' field
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
