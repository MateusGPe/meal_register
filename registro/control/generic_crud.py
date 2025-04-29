# ----------------------------------------------------------------------------
# File: registro/control/generic_crud.py (Refined Generic CRUD)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

import csv
import logging
from pathlib import Path
from typing import (Any, Callable, Dict, Generic, List, Optional, Self, Type,
                    TypeVar, Union)
from sqlalchemy import insert, select, update as sql_update, delete as sql_delete
from sqlalchemy.orm import Session as DBSession, declarative_base
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from registro.control.utils import load_csv_as_dict
logger = logging.getLogger(__name__)
MODEL = TypeVar('MODEL', bound=declarative_base())


class CRUD(Generic[MODEL]):

    def __init__(self: Self, session: DBSession, model: Type[MODEL]):
        if not isinstance(session, DBSession):
            raise TypeError("session must be a SQLAlchemy Session")

        if not hasattr(model, '__mapper__'):
            raise TypeError(f"model '{model.__name__}' must be a valid SQLAlchemy mapped class")
        self._db_session = session
        self._model = model
        try:

            mapper = model.__mapper__
            if not mapper.primary_key:
                raise ValueError(f"Model {model.__name__} does not have a primary key defined.")
            self._primary_key_name = mapper.primary_key[0].name
            self._primary_key_column = getattr(self._model, self._primary_key_name)
            logger.debug(f"CRUD initialized for model {model.__name__} with PK '{self._primary_key_name}'")
        except (AttributeError, IndexError, ValueError) as e:
            logger.error(f"Failed to determine primary key for model {model.__name__}: {e}")
            raise ValueError(f"Could not identify primary key for model {model.__name__}.") from e

    def _handle_db_error(self, operation: str, error: SQLAlchemyError, item_info: Any = None) -> None:
        log_msg = f"DB Error during '{operation}'"
        if item_info:

            info_repr = repr(item_info)
            if len(info_repr) > 200:
                info_repr = info_repr[:197] + '...'
            log_msg += f" (Info: {info_repr})"
        log_msg += f": {error}"

        logger.debug(f"DB Error Traceback during '{operation}':", exc_info=True)

        logger.error(log_msg)
        try:
            self._db_session.rollback()
            logger.info("DB Session rollback performed due to error.")
        except Exception as rb_exc:
            logger.error(f"Additional error during DB session rollback: {rb_exc}")

    def create(self: Self, data: Dict[str, Any]) -> Optional[MODEL]:
        try:
            db_item = self._model(**data)
            self._db_session.add(db_item)
            self._db_session.commit()
            self._db_session.refresh(db_item)
            logger.debug(
                f"Record created successfully for {self._model.__name__}: PK={getattr(db_item, self._primary_key_name, '?')}")
            return db_item
        except (SQLAlchemyError, TypeError) as e:
            self._handle_db_error("create", e, data)
            return None

    def read_one(self: Self, item_id: Union[int, str]) -> Optional[MODEL]:
        try:

            result = self._db_session.get(self._model, item_id)

            if result:
                logger.debug(f"Record found for {self._model.__name__} PK {item_id}")
            else:
                logger.debug(f"Record NOT found for {self._model.__name__} PK {item_id}")
            return result
        except SQLAlchemyError as e:
            self._handle_db_error("read_one", e, f"PK={item_id}")
            return None

    def read_filtered_one(self: Self, **filters: Any) -> Optional[MODEL]:
        try:
            stmt = select(self._model)
            for key, value in filters.items():

                if not hasattr(self._model, key):
                    raise AttributeError(f"Model {self._model.__name__} has no attribute '{key}' for filtering.")
                stmt = stmt.where(getattr(self._model, key) == value)
            stmt = stmt.limit(1)
            result = self._db_session.scalars(stmt).first()
            if result:
                logger.debug(f"Filtered record found for {self._model.__name__}: {filters}")
            else:
                logger.debug(f"No record found for {self._model.__name__} with filters: {filters}")
            return result
        except AttributeError as e:
            logger.error(f"Invalid filter attribute for {self._model.__name__}: {e}")
            return None
        except SQLAlchemyError as e:
            self._handle_db_error("read_filtered_one", e, filters)
            return None

    def read_filtered(self: Self, **filters: Any) -> List[MODEL]:
        try:
            skip = filters.pop('skip', 0)
            limit = filters.pop('limit', None)
            stmt = select(self._model)

            for key, value in filters.items():
                if not hasattr(self._model, key):
                    raise AttributeError(f"Model {self._model.__name__} has no attribute '{key}' for filtering.")

                if key.endswith('__in') and isinstance(value, (list, set)):
                    actual_key = key[:-4]
                    if not hasattr(self._model, actual_key):
                        raise AttributeError(
                            f"Model {self._model.__name__} has no attribute '{actual_key}' for '__in' filtering.")
                    stmt = stmt.where(getattr(self._model, actual_key).in_(value))
                else:
                    stmt = stmt.where(getattr(self._model, key) == value)

            if skip > 0:
                stmt = stmt.offset(skip)
            if limit is not None:
                stmt = stmt.limit(limit)

            results = self._db_session.scalars(stmt).all()
            logger.debug(
                f"{len(results)} records found for {self._model.__name__} with filters: {filters}, skip={skip}, limit={limit}")
            return results
        except AttributeError as e:
            logger.error(f"Invalid filter attribute for {self._model.__name__}: {e}")
            return []
        except SQLAlchemyError as e:
            self._handle_db_error("read_filtered", e, filters)
            return []

    def read_all(self: Self) -> List[MODEL]:
        try:
            stmt = select(self._model)
            results = self._db_session.scalars(stmt).all()
            logger.debug(f"{len(results)} total records found for {self._model.__name__} (read_all)")
            return results
        except SQLAlchemyError as e:
            self._handle_db_error("read_all", e)
            return []

    def read_all_ordered_by(self: Self, *order_by_columns: Any) -> List[MODEL]:
        try:
            stmt = select(self._model).order_by(*order_by_columns)
            results = self._db_session.scalars(stmt).all()
            logger.debug(f"{len(results)} ordered records found for {self._model.__name__}")
            return results
        except (SQLAlchemyError, AttributeError) as e:
            self._handle_db_error("read_all_ordered_by", e, order_by_columns)
            return []

    def update(self: Self, item_id: Union[int, str], data: Dict[str, Any]) -> Optional[MODEL]:
        try:

            item_to_update = self._db_session.get(self._model, item_id)
            if item_to_update:
                logger.debug(f"Attempting to update record {self._model.__name__} PK {item_id} with data: {data}")
                for key, value in data.items():
                    if hasattr(item_to_update, key):
                        setattr(item_to_update, key, value)
                    else:
                        logger.warning(
                            f"Attempting to update non-existent attribute '{key}' on {self._model.__name__} PK {item_id}. Ignored.")
                self._db_session.commit()
                self._db_session.refresh(item_to_update)
                logger.info(f"Record {self._model.__name__} PK {item_id} updated successfully.")
                return item_to_update
            else:
                logger.warning(f"Record {self._model.__name__} PK {item_id} not found for update.")
                return None
        except (SQLAlchemyError, TypeError) as e:
            self._handle_db_error("update", e, f"PK={item_id}, data={data}")
            return None

    def delete(self: Self, item_id: Union[int, str]) -> bool:
        try:

            item_to_delete = self._db_session.get(self._model, item_id)
            if item_to_delete:
                self._db_session.delete(item_to_delete)
                self._db_session.commit()
                logger.info(f"Record {self._model.__name__} PK {item_id} deleted successfully.")
                return True
            else:
                logger.warning(f"Record {self._model.__name__} PK {item_id} not found for deletion.")
                return False
        except SQLAlchemyError as e:

            if isinstance(e, IntegrityError):
                logger.error(
                    f"Integrity error deleting {self._model.__name__} PK {item_id} (likely FK constraint): {e}")
            self._handle_db_error("delete", e, f"PK={item_id}")
            return False

    def bulk_create(self: Self, rows_data: List[Dict[str, Any]]) -> bool:
        if not rows_data:
            logger.debug("bulk_create called with empty list.")
            return True
        try:

            self._db_session.execute(insert(self._model), rows_data)
            self._db_session.commit()
            logger.info(f"{len(rows_data)} records bulk created for {self._model.__name__}.")
            return True
        except (SQLAlchemyError, TypeError) as e:

            if isinstance(e, IntegrityError):
                logger.error(
                    f"Integrity error during bulk create for {self._model.__name__} (likely duplicate key): {e}")
            self._handle_db_error("bulk_create", e, f"{len(rows_data)} rows")
            return False

    def bulk_update(self: Self, rows_data: List[Dict[str, Any]]) -> bool:
        if not rows_data:
            logger.debug("bulk_update called with empty list.")
            return True
        updated_count = 0
        skipped_missing_pk = 0
        skipped_not_found = 0
        pk_name = self._primary_key_name

        try:
            for row_update_data in rows_data:
                item_id = row_update_data.get(pk_name)
                if item_id is None:
                    logger.warning(f"bulk_update: skipping row without primary key '{pk_name}': {row_update_data}")
                    skipped_missing_pk += 1
                    continue

                item_to_update = self._db_session.get(self._model, item_id)
                if item_to_update:
                    logger.debug(f"bulk_update: updating {self._model.__name__} PK {item_id}")
                    for key, value in row_update_data.items():
                        if key == pk_name:
                            continue
                        if hasattr(item_to_update, key):
                            setattr(item_to_update, key, value)
                        else:
                            logger.warning(
                                f"bulk_update: attribute '{key}' not found on {self._model.__name__} PK {item_id}. Ignored.")

                    updated_count += 1
                else:
                    logger.warning(f"bulk_update: record {self._model.__name__} PK {item_id} not found for update.")
                    skipped_not_found += 1

            self._db_session.commit()
            logger.info(
                f"bulk_update for {self._model.__name__} finished. Updated: {updated_count}, Skipped (Missing PK): {skipped_missing_pk}, Skipped (Not Found): {skipped_not_found}")
            return True
        except (SQLAlchemyError, TypeError, AttributeError) as e:

            self._handle_db_error("bulk_update", e, f"{len(rows_data)} rows attempted")
            return False

    def import_csv(self: Self, csv_file_path: Union[str, Path],
                   row_processor: Callable[[Dict[str, str]], Optional[Dict[str, Any]]] = lambda row: row,
                   adjust_keys_func: Optional[Callable[[Dict], Dict]] = None) -> bool:
        csv_path_str = str(csv_file_path)
        logger.info(f"Starting CSV import: {csv_path_str} for {self._model.__name__}")
        try:

            raw_rows = load_csv_as_dict(csv_path_str)
            if raw_rows is None:
                return False
            if not raw_rows:
                logger.info(f"CSV file '{csv_path_str}' is empty or contains only headers.")
                return True
            processed_rows: List[Dict[str, Any]] = []
            for i, raw_row in enumerate(raw_rows, start=1):
                try:

                    adjusted_row = adjust_keys_func(raw_row) if adjust_keys_func else raw_row

                    processed_row = row_processor(adjusted_row)

                    if isinstance(processed_row, dict) and processed_row:
                        processed_rows.append(processed_row)
                    elif processed_row is not None:
                        logger.warning(
                            f"Row processor returned non-dict, non-None value for CSV line {i+1}. Skipping row: {raw_row}")
                except Exception as proc_err:
                    logger.error(
                        f"Error processing CSV line {i+1} from '{csv_path_str}': {proc_err} | Row: {raw_row}", exc_info=True)

            if not processed_rows:
                logger.warning(f"No valid rows to import after processing CSV '{csv_path_str}'.")
                return True

            logger.info(f"Attempting to bulk insert {len(processed_rows)} processed records from CSV '{csv_path_str}'.")
            success = self.bulk_create(processed_rows)
            if success:
                logger.info(f"CSV import '{csv_path_str}' completed successfully.")
            else:
                logger.error(
                    f"Bulk create failed during CSV import from '{csv_path_str}'. Check previous logs for details.")
            return success
        except Exception as e:
            logger.exception(f"Unexpected error during CSV import '{csv_path_str}': {e}")
            return False

    def get_session(self: Self) -> DBSession:
        return self._db_session

    def commit(self: Self) -> None:
        try:
            self._db_session.commit()
            logger.debug("DB session committed successfully.")
        except SQLAlchemyError as e:
            self._handle_db_error("commit", e)

    def rollback(self: Self) -> None:
        try:
            self._db_session.rollback()
            logger.info("DB session rollback performed.")
        except Exception as e:
            logger.error(f"Error during DB session rollback: {e}")
