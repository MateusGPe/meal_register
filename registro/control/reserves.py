# ----------------------------------------------------------------------------
# File: registro/control/reserves.py (Refined Reserves Importer)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as SQLASession
from registro.control.generic_crud import CRUD
from registro.control.utils import adjust_keys, load_csv_as_dict
from registro.model.tables import Group, Reserve, Student
logger = logging.getLogger(__name__)
def import_students_csv(student_crud: CRUD[Student], group_crud: CRUD[Group],
                        csv_file_path: str) -> bool:
    logger.info(f"Starting student import from CSV: {csv_file_path}")
    try:
        raw_student_data = load_csv_as_dict(csv_file_path)
        if raw_student_data is None:
            logger.error(f"Failed to load student data from {csv_file_path}.")
            return False
        if not raw_student_data:
            logger.info(f"Student CSV file '{csv_file_path}' is empty. Nothing to import.")
            return True
        existing_students_pronts: Set[str] = {s.pront for s in student_crud.read_all()}
        existing_groups_names: Set[str] = {g.nome for g in group_crud.read_all()}
        logger.debug(
            f"Found {len(existing_students_pronts)} existing students and {len(existing_groups_names)} existing groups.")
        students_to_create: List[Dict[str, Any]] = []
        groups_to_create: Set[str] = set()
        student_group_associations: Set[Tuple[str, str]] = set()
        pronts_in_csv: Set[str] = set()
        for i, row_raw in enumerate(raw_student_data):
            try:
                row = adjust_keys(row_raw)
                pront = row.get('pront')
                nome = row.get('nome')
                group_name = row.get('turma')
                if not pront or not nome:
                    logger.warning(f"Skipping row {i+2} in student CSV: missing 'pront' or 'nome'. Data: {row_raw}")
                    continue
                if pront not in existing_students_pronts and pront not in pronts_in_csv:
                    student_data = {k: v for k, v in row.items() if k in ['pront', 'nome']}
                    students_to_create.append(student_data)
                    pronts_in_csv.add(pront)
                if group_name:
                    student_group_associations.add((pront, group_name))
                    if group_name not in existing_groups_names and group_name not in groups_to_create:
                        groups_to_create.add(group_name)
            except Exception as row_err:
                logger.error(f"Error processing row {i+2} of student CSV: {row_err}. Data: {row_raw}", exc_info=True)
        db_session = student_crud.get_session()
        try:
            if groups_to_create:
                logger.info(f"Creating {len(groups_to_create)} new groups...")
                group_data = [{'nome': name} for name in groups_to_create]
                if not group_crud.bulk_create(group_data):
                    raise RuntimeError("Failed to bulk create new groups.")
                logger.info("New groups created successfully.")
                existing_groups_names.update(groups_to_create)
            if students_to_create:
                logger.info(f"Creating {len(students_to_create)} new students...")
                if not student_crud.bulk_create(students_to_create):
                    raise RuntimeError("Failed to bulk create new students.")
                logger.info("New students created successfully.")
                existing_students_pronts.update(s['pront'] for s in students_to_create)
            if student_group_associations:
                logger.info(f"Associating {len(student_group_associations)} student-group links...")
                if not _associate_students_with_groups_refactored(db_session, student_crud, group_crud,
                                                                  student_group_associations):
                    raise RuntimeError("Failed to associate students with groups.")
                logger.info("Student-group associations completed.")
            logger.info(f"Student import from CSV '{csv_file_path}' completed successfully.")
            return True
        except (SQLAlchemyError, RuntimeError) as db_err:
            logger.error(f"Database error during student import: {db_err}. Rolling back transaction.", exc_info=True)
            db_session.rollback()
            return False
    except Exception as e:
        logger.exception(f"Unexpected error during student import from CSV '{csv_file_path}': {e}")
        return False
def _associate_students_with_groups_refactored(db_session: SQLASession,
                                               student_crud: CRUD[Student], group_crud: CRUD[Group],
                                               associations: Set[Tuple[str, str]]) -> bool:
    if not associations:
        logger.debug("No student-group associations to process.")
        return True
    try:
        pronts_to_fetch = {pront for pront, _ in associations}
        group_names_to_fetch = {gname for _, gname in associations}
        student_map: Dict[str, Student] = {s.pront: s for s in student_crud.read_all() if s.pront in pronts_to_fetch}
        group_map: Dict[str, Group] = {g.nome: g for g in group_crud.read_all() if g.nome in group_names_to_fetch}
        logger.debug(
            f"Fetched {len(student_map)} relevant students and {len(group_map)} relevant groups for association.")
        association_count = 0
        for pront, group_name in associations:
            student = student_map.get(pront)
            group = group_map.get(group_name)
            if student and group:
                if group not in student.groups:
                    student.groups.append(group)
                    association_count += 1
            elif not student:
                logger.warning(f"Cannot associate: Student with pront '{pront}' not found in fetched map.")
            elif not group:
                logger.warning(f"Cannot associate: Group with name '{group_name}' not found in fetched map.")
        if association_count > 0:
            db_session.commit()
            logger.info(f"{association_count} new student-group associations committed.")
        else:
            logger.info("No new student-group associations were needed.")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Database error during student-group association: {e}. Rolling back.", exc_info=True)
        db_session.rollback()
        return False
    except Exception as e:
        logger.exception(f"Unexpected error associating students to groups: {e}")
        db_session.rollback()
        return False
def import_reserves_csv(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                        csv_file_path: str) -> bool:
    logger.info(f"Starting reserves import from CSV: {csv_file_path}")
    try:
        raw_reserve_data = load_csv_as_dict(csv_file_path)
        if raw_reserve_data is None:
            logger.error(f"Failed to load reserve data from {csv_file_path}.")
            return False
        if not raw_reserve_data:
            logger.info(f"Reserves CSV file '{csv_file_path}' is empty. Nothing to import.")
            return True
        all_students_map: Dict[str, int] = {s.pront: s.id for s in student_crud.read_all()}
        if not all_students_map:
            logger.error("Cannot import reserves: No students found in the database.")
            return False
        logger.debug(f"Created lookup map for {len(all_students_map)} students.")
        reserves_to_insert: List[Dict[str, Any]] = []
        for i, row_raw in enumerate(raw_reserve_data):
            try:
                row = adjust_keys(row_raw)
                pront = row.get('pront')
                data = row.get('data')
                dish = row.get('dish')
                is_snack = str(row.get('snacks', 'false')).lower() in ['true', '1', 'sim', 'yes', 'lanche']
                is_canceled = str(row.get('canceled', 'false')).lower() in ['true', '1', 'sim', 'yes', 'cancelado']
                if not pront or not data:
                    logger.warning(f"Skipping row {i+2} in reserves CSV: missing 'pront' or 'data'. Data: {row_raw}")
                    continue
                student_id = all_students_map.get(pront)
                if student_id:
                    reserve_data = {
                        'student_id': student_id,
                        'data': data,
                        'dish': dish or 'Não Especificado',
                        'snacks': is_snack,
                        'canceled': is_canceled
                    }
                    reserves_to_insert.append(reserve_data)
                else:
                    logger.warning(
                        f"Skipping row {i+2} in reserves CSV: Student pront '{pront}' not found in database.")
            except Exception as row_err:
                logger.error(f"Error processing row {i+2} of reserves CSV: {row_err}. Data: {row_raw}", exc_info=True)
        if reserves_to_insert:
            logger.info(
                f"Attempting to bulk insert {len(reserves_to_insert)} processed reserves from '{csv_file_path}'.")
            success = reserve_crud.bulk_create(reserves_to_insert)
            if success:
                logger.info(f"Bulk insert of reserves from '{csv_file_path}' completed.")
                return True
            else:
                logger.error(f"Bulk insert of reserves failed (check CRUD logs). Rolling back.")
                reserve_crud.rollback()
                return False
        else:
            logger.info(f"No valid reserves found to import from '{csv_file_path}'.")
            return True
    except Exception as e:
        logger.exception(f"Unexpected error during reserves import from CSV '{csv_file_path}': {e}")
        return False
def reserve_snacks_for_all(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                           date: str, dish: str) -> bool:
    logger.info(f"Initiating bulk snack reservation for dish '{dish}' on date '{date}' for all students.")
    try:
        all_students = student_crud.read_all()
        if not all_students:
            logger.warning("No students found in the database to reserve snacks for.")
            return True
        reserves_to_insert = [{
            'student_id': student.id,
            'data': date,
            'dish': dish,
            'snacks': True,
            'canceled': False
        } for student in all_students]
        logger.info(f"Preparing {len(reserves_to_insert)} snack reservations for bulk insert...")
        success = reserve_crud.bulk_create(reserves_to_insert)
        if success:
            logger.info(
                f"Bulk snack reservations for '{date}' processed successfully (new ones inserted, duplicates ignored).")
            return True
        else:
            logger.error(f"Bulk insert failed during snack reservation for '{date}' (check CRUD logs). Rolling back.")
            reserve_crud.rollback()
            return False
    except SQLAlchemyError as e:
        logger.error(f"Database error during bulk snack reservation for '{date}': {e}. Rolling back.", exc_info=True)
        reserve_crud.rollback()
        return False
    except Exception as e:
        logger.exception(f"Unexpected error reserving snacks for '{date}': {e}")
        reserve_crud.rollback()
        return False
