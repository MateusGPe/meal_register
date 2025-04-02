# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides a generic CRUD (Create, Read, Update, Delete) class for interacting with SQLAlchemy models.

The `CRUD` class simplifies common database operations by providing methods to create,
read (single, filtered, and all), update, and delete records. It also includes
functionality for bulk creation and updating, as well as importing data from CSV files.
"""

import csv
import logging
from typing import (Any, Callable, Dict, Generic, List, Optional, Self, Type,
                    TypeVar)

from sqlalchemy import insert, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import declarative_base
from sqlalchemy.exc import DBAPIError

logger = logging.getLogger(__name__)

MODEL = TypeVar('MODEL', bound=declarative_base)


class CRUD(Generic[MODEL]):
    """
    Base class for performing Create, Read, Update, and Delete operations on database models using
    SQLAlchemy.

    Provides common methods for interacting with a database table represented by a SQLAlchemy model.
    """

    def __init__(self: Self, session: DBSession, model: Type[MODEL]):
        """
        Initializes the CRUD object with a database session and a SQLAlchemy model.

        Args:
            session (DBSession): The SQLAlchemy database session to use for operations.
            model (Type[MODEL]): The SQLAlchemy model class representing the database table.
        """
        self._db_session = session
        self._model = model
        _primary_key_name = model.__mapper__.primary_key[0].name
        self._primary_key_column = getattr(self._model, _primary_key_name)

    def create(self: Self, data: Dict) -> Optional[MODEL]:
        """
        Creates a new record in the database.

        Args:
            data (Dict): A dictionary containing the data for the new record.

        Returns:
            Optional[MODEL]: The newly created database model instance, or None if an error occurs.
        """
        try:
            db_item = self._model(**data)
            self._db_session.add(db_item)
            self._db_session.commit()
            self._db_session.refresh(db_item)
            return db_item
        except DBAPIError as e:
            self._db_session.rollback()
            logger.error("Error creating record: %s", e)
            return None

    def commit(self: Self) -> None:
        """
        Commits the current transaction to the database.
        """
        try:
            self._db_session.commit()
        except DBAPIError as e:
            self._db_session.rollback()
            logger.error("Error committing transaction: %s", e)

    def rollback(self: Self) -> None:
        """
        Rolls back the current transaction, discarding any changes.
        """
        try:
            self._db_session.rollback()
        except DBAPIError as e:
            logger.error("Error rolling back transaction: %s", e)

    def read_one(self: Self, item_id: int) -> Optional[MODEL]:
        """
        Reads a single record from the database based on its primary key.

        Args:
            item_id (int): The value of the primary key of the record to retrieve.

        Returns:
            Optional[MODEL]: The database model instance if found, otherwise None.
        """
        try:
            return self._db_session.scalar(select(self._model)
                                           .where(self._primary_key_column == item_id))
        except DBAPIError as e:
            logger.error("Error reading record with ID %s: %s", item_id, e)
            return None

    def read(self: Self, **kwargs: Dict[str, Any]) -> Optional[MODEL]:
        """
        Reads a single record from the database based on specified keyword arguments.

        Args:
            **kwargs (Dict[str, Any]): Keyword arguments representing the fields and values to
                                       filter by.

        Returns:
            Optional[MODEL]: The database model instance if found, otherwise None.
        """
        try:
            filters = [getattr(self._model, key) ==
                       value for key, value in kwargs.items()]
            return self._db_session.scalar(select(self._model).where(*filters))
        except AttributeError as e:
            logger.error("Invalid filter attribute: %s", e)
            return None
        except DBAPIError as e:
            logger.error("Error reading record with filters %s: %s", kwargs, e)
            return None

    def read_filtered(self: Self, **filters: Any) -> List[MODEL]:
        """
        Reads multiple records from the database based on specified filters, with optional skip and
        limit.

        Args:
            **filters (Any): Keyword arguments representing the fields and values to filter by.
                             Can also include 'skip' and 'limit' for pagination.

        Returns:
            List[MODEL]: A list of database model instances matching the filters.
        """
        try:
            skip = filters.pop('skip', None)
            limit = filters.pop('limit', None)

            stmt = select(self._model)

            if skip:
                stmt = stmt.offset(skip)

            if limit:
                stmt = stmt.limit(limit)

            where_clause = [getattr(self._model, key) ==
                            value for key, value in filters.items()]
            if where_clause:
                stmt = stmt.where(*where_clause)

            return self._db_session.scalars(stmt).all()
        except AttributeError as e:
            logger.error("Invalid filter attribute: %s", e)
            return []
        except DBAPIError as e:
            logger.error("Error reading filtered records: %s", e)
            return []

    def read_all(self: Self) -> List[MODEL]:
        """
        Reads all records from the database table.

        Returns:
            List[MODEL]: A list containing all database model instances.
        """
        return self._db_session.scalars(select(self._model)).all()

    def update(self: Self, item_id: int, row: Dict) -> Optional[MODEL]:
        """
        Updates an existing record in the database based on its primary key.

        Args:
            item_id (int): The value of the primary key of the record to update.
            row (Dict): A dictionary containing the fields and values to update.

        Returns:
            Optional[MODEL]: The updated database model instance if found, otherwise None.
        """
        try:
            item_to_update = self._db_session.scalar(
                select(self._model).where(self._primary_key_column == item_id))
            if item_to_update:
                for key, value in row.items():
                    setattr(item_to_update, key, value)
                self._db_session.commit()
                self._db_session.refresh(item_to_update)
                return item_to_update
            logger.warning(
                "Record with ID %s not found for update.", item_id)
            return None
        except DBAPIError as e:
            self._db_session.rollback()
            logger.error("Error updating record with ID %s: %s", item_id, e)
            return None

    def delete(self: Self, item_id: int) -> bool:
        """
        Deletes a record from the database based on its primary key.

        Args:
            item_id (int): The value of the primary key of the record to delete.

        Returns:
            bool: True if the record was successfully deleted, False otherwise.
        """
        try:
            item_to_delete = self._db_session.scalar(
                select(self._model).where(self._primary_key_column == item_id))
            if item_to_delete:
                self._db_session.delete(item_to_delete)
                self._db_session.commit()
                return True

            logger.warning(
                "Record with ID %s not found for deletion.", item_id)
            return False
        except DBAPIError as e:
            self._db_session.rollback()
            logger.error("Error deleting record with ID %s: %s", item_id, e)
            return False

    def bulk_create(self: Self, rows: List[Dict]) -> bool:
        """
        Creates multiple new records in the database in a single operation.

        Args:
            rows (List[Dict]): A list of dictionaries, where each dictionary represents
                               a new record.

        Returns:
            bool: True if the records were successfully created, False otherwise.
        """
        try:
            self._db_session.execute(insert(self._model), rows)
            self._db_session.commit()
            return True
        except DBAPIError as e:
            self._db_session.rollback()
            logger.error("Error during bulk insert: %s", e)
            return False

    def import_csv(self: Self, csv_file: str,
                   value_processor: Callable[[dict], dict] = lambda v: v) -> bool:
        """
        Imports data from a CSV file into the database.

        Args:
            csv_file (str): The path to the CSV file to import.
            value_processor (Callable[[dict], dict], optional): An optional function to
                process each row read from the CSV before creating the database record.
                Defaults to an identity function.

        Returns:
            bool: True if the data was successfully imported, False otherwise.
        """
        try:
            with open(csv_file, "r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                rows = [value_processor(row) for row in reader]
                return self.bulk_create(rows)
        except FileNotFoundError:
            logger.error("CSV file not found: %s", csv_file)
            return False
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Error importing CSV file %s: %s", csv_file, e)
            return False

    def bulk_update(self: Self, rows: List[Dict]) -> bool:
        """
        Updates multiple existing records in the database in a single operation.

        Args:
            rows (List[Dict]): A list of dictionaries, where each dictionary contains the
                primary key and the fields to update for an existing record.

        Returns:
            bool: True if the records were successfully updated, False otherwise.
        """
        try:
            for row in rows:
                item_id = row.get(self._primary_key_column.name)
                if item_id is None:
                    logger.warning(
                        "Skipping row due to missing primary key: %s", row)
                    continue

                item_to_update = self._db_session.scalar(
                    select(self._model).where(self._primary_key_column == item_id))

                if item_to_update:
                    for key, value in row.items():
                        if key != self._primary_key_column.name:
                            setattr(item_to_update, key, value)
                else:
                    logger.warning(
                        "Skipping update for ID %s as it does not exist.", item_id)

            self._db_session.commit()
            return True
        except DBAPIError as e:
            self._db_session.rollback()
            logger.error("Database error during bulk update: %s", e)
            return False
        except ValueError as e:
            logger.error("Invalid data during bulk update: %s", e)
            return False

    def get_session(self: Self):
        """
        Retrieves the current database session.

        Returns:
            Session: The SQLAlchemy database session instance used for database operations.
        """
        return self._db_session
