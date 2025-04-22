# ----------------------------------------------------------------------------
# File: registro/control/generic_crud.py (Refined Generic CRUD)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Fornece uma classe CRUD (Create, Read, Update, Delete) genérica para interagir
com modelos SQLAlchemy.

A classe `CRUD` simplifica operações comuns de banco de dados, fornecendo métodos
para criar, ler (único, filtrado, todos), atualizar e deletar registros. Inclui
também funcionalidade para criação e atualização em massa.
"""

import csv
import logging
from typing import (Any, Callable, Dict, Generic, List, Optional, Self, Type,
                    TypeVar, Union)

# Importações SQLAlchemy
from sqlalchemy import insert, select, update as sql_update, delete as sql_delete # Renomeia update/delete
from sqlalchemy.orm import Session as DBSession, declarative_base
from sqlalchemy.exc import SQLAlchemyError, IntegrityError # Erros específicos do SQLAlchemy

# Importações locais
from registro.control.utils import load_csv_as_dict # Para import_csv

logger = logging.getLogger(__name__)

# Tipo genérico para o modelo SQLAlchemy
MODEL = TypeVar('MODEL', bound=declarative_base())

class CRUD(Generic[MODEL]):
    """
    Classe base genérica para operações CRUD em modelos SQLAlchemy.
    """
    def __init__(self: Self, session: DBSession, model: Type[MODEL]):
        """
        Inicializa o objeto CRUD.

        Args:
            session (DBSession): A sessão SQLAlchemy a ser usada.
            model (Type[MODEL]): A classe do modelo SQLAlchemy.
        """
        if not isinstance(session, DBSession):
            raise TypeError("session must be a SQLAlchemy Session")
        if not hasattr(model, '__mapper__'):
             raise TypeError("model must be a valid SQLAlchemy mapped class")

        self._db_session = session
        self._model = model
        try:
            # Determina o nome da chave primária dinamicamente
            self._primary_key_name = model.__mapper__.primary_key[0].name
            self._primary_key_column = getattr(self._model, self._primary_key_name)
            logger.debug(f"CRUD inicializado para modelo {model.__name__} com PK '{self._primary_key_name}'")
        except (AttributeError, IndexError):
            logger.error(f"Não foi possível determinar a chave primária para o modelo {model.__name__}")
            raise ValueError(f"Modelo {model.__name__} não parece ter uma chave primária definida.")


    def _handle_db_error(self, operation: str, error: SQLAlchemyError, item_info: Any = None):
        """ Loga erros do DB e faz rollback. """
        log_msg = f"Erro de DB durante '{operation}'"
        if item_info: log_msg += f" (Info: {item_info})"
        log_msg += f": {error}"
        # Loga a exceção completa no nível de DEBUG para detalhes
        logger.debug(f"DB Error Traceback during '{operation}':", exc_info=True)
        # Loga mensagem de erro concisa no nível ERROR
        logger.error(log_msg)
        try:
            self._db_session.rollback()
            logger.info("Rollback da sessão DB realizado devido a erro.")
        except Exception as rb_exc: # pylint: disable=broad-except
             logger.error(f"Erro adicional durante o rollback da sessão DB: {rb_exc}")

    # --- Métodos CRUD Básicos ---

    def create(self: Self, data: Dict[str, Any]) -> Optional[MODEL]:
        """
        Cria um novo registro no banco de dados.

        Args:
            data (Dict[str, Any]): Dicionário com dados para o novo registro.

        Returns:
            Optional[MODEL]: A instância do modelo criada, ou None em caso de erro.
        """
        try:
            db_item = self._model(**data)
            self._db_session.add(db_item)
            self._db_session.commit() # Commit após adicionar
            self._db_session.refresh(db_item) # Atualiza o objeto com dados do DB (ex: ID gerado)
            logger.debug(f"Registro criado com sucesso para {self._model.__name__}: {db_item}")
            return db_item
        except (SQLAlchemyError, TypeError) as e: # Captura erros DB e erros de tipo (ex: dados inválidos)
            self._handle_db_error("create", e, data)
            return None

    def read_one(self: Self, item_id: Union[int, str]) -> Optional[MODEL]:
        """
        Lê um registro único pelo valor da sua chave primária.

        Args:
            item_id (Union[int, str]): O valor da chave primária.

        Returns:
            Optional[MODEL]: A instância do modelo se encontrada, None caso contrário ou erro.
        """
        try:
            stmt = select(self._model).where(self._primary_key_column == item_id)
            result = self._db_session.scalar(stmt)
            if result: logger.debug(f"Registro encontrado para {self._model.__name__} ID {item_id}")
            else: logger.debug(f"Registro NÃO encontrado para {self._model.__name__} ID {item_id}")
            return result
        except SQLAlchemyError as e:
            self._handle_db_error("read_one", e, f"ID={item_id}")
            return None

    def read_filtered_one(self: Self, **filters: Any) -> Optional[MODEL]:
        """
        Lê o *primeiro* registro que corresponde aos filtros fornecidos.

        Args:
            **filters: Pares chave=valor para filtrar (ex: nome='teste').

        Returns:
            Optional[MODEL]: A primeira instância encontrada, None se nenhuma for encontrada ou erro.
        """
        try:
            where_clause = [getattr(self._model, key) == value for key, value in filters.items()]
            stmt = select(self._model).where(*where_clause).limit(1) # Adiciona limit(1)
            result = self._db_session.scalar(stmt)
            if result: logger.debug(f"Registro filtrado encontrado para {self._model.__name__}: {filters}")
            else: logger.debug(f"Nenhum registro encontrado para {self._model.__name__} com filtros: {filters}")
            return result
        except AttributeError as e: # Erro se a chave do filtro não for um atributo do modelo
            logger.error(f"Atributo de filtro inválido para {self._model.__name__}: {e}")
            return None
        except SQLAlchemyError as e:
            self._handle_db_error("read_filtered_one", e, filters)
            return None

    def read_filtered(self: Self, **filters: Any) -> List[MODEL]:
        """
        Lê múltiplos registros baseados em filtros, com skip/limit opcionais.

        Args:
            **filters: Pares chave=valor para filtrar. Pode incluir 'skip' e 'limit'.

        Returns:
            List[MODEL]: Lista de instâncias do modelo correspondentes (pode ser vazia).
        """
        try:
            skip = filters.pop('skip', 0) # Padrão 0 se não fornecido
            limit = filters.pop('limit', None)
            stmt = select(self._model)
            # Aplica filtros where
            where_clause = [getattr(self._model, key) == value for key, value in filters.items()]
            if where_clause: stmt = stmt.where(*where_clause)
            # Aplica offset (skip) e limit
            if skip > 0: stmt = stmt.offset(skip)
            if limit is not None: stmt = stmt.limit(limit)
            # Executa e retorna todos os resultados
            results = self._db_session.scalars(stmt).all()
            logger.debug(f"{len(results)} registros encontrados para {self._model.__name__} com filtros: {filters}")
            return results
        except AttributeError as e:
            logger.error(f"Atributo de filtro inválido para {self._model.__name__}: {e}")
            return []
        except SQLAlchemyError as e:
            self._handle_db_error("read_filtered", e, filters)
            return []

    def read_all(self: Self) -> List[MODEL]:
        """
        Lê todos os registros da tabela do modelo.

        Returns:
            List[MODEL]: Lista de todas as instâncias do modelo.
        """
        try:
            results = self._db_session.scalars(select(self._model)).all()
            logger.debug(f"{len(results)} registros encontrados para {self._model.__name__} (read_all)")
            return results
        except SQLAlchemyError as e:
            self._handle_db_error("read_all", e)
            return []

    def read_all_ordered_by(self: Self, *order_by_columns: Any) -> List[MODEL]:
        """
        Lê todos os registros da tabela, ordenados pelas colunas especificadas.

        Args:
            *order_by_columns: Colunas SQLAlchemy para ordenar (ex: Model.name, Model.date.desc()).

        Returns:
            List[MODEL]: Lista ordenada de todas as instâncias.
        """
        try:
            stmt = select(self._model).order_by(*order_by_columns)
            results = self._db_session.scalars(stmt).all()
            logger.debug(f"{len(results)} registros ordenados encontrados para {self._model.__name__}")
            return results
        except SQLAlchemyError as e:
            self._handle_db_error("read_all_ordered_by", e, order_by_columns)
            return []

    def update(self: Self, item_id: Union[int, str], data: Dict[str, Any]) -> Optional[MODEL]:
        """
        Atualiza um registro existente pela sua chave primária.

        Args:
            item_id (Union[int, str]): O valor da chave primária do registro a atualizar.
            data (Dict[str, Any]): Dicionário com os campos e novos valores.

        Returns:
            Optional[MODEL]: A instância do modelo atualizada, ou None se não encontrado ou erro.
        """
        try:
            # Abordagem 1: Buscar e atualizar objeto (ORM-style)
            item_to_update = self.read_one(item_id) # Usa read_one para buscar
            if item_to_update:
                logger.debug(f"Atualizando registro {self._model.__name__} ID {item_id} com dados: {data}")
                for key, value in data.items():
                     if hasattr(item_to_update, key): # Verifica se o atributo existe
                          setattr(item_to_update, key, value)
                     else:
                          logger.warning(f"Tentando atualizar atributo inexistente '{key}' em {self._model.__name__}. Ignorando.")
                self._db_session.commit()
                self._db_session.refresh(item_to_update) # Atualiza objeto com estado pós-commit
                return item_to_update
            else:
                logger.warning(f"Registro {self._model.__name__} ID {item_id} não encontrado para atualização.")
                return None
            # Abordagem 2: Update direto (Core-style - mais eficiente para muitos updates sem carregar objetos)
            # stmt = sql_update(self._model)\
            #        .where(self._primary_key_column == item_id)\
            #        .values(**data)\
            #        .execution_options(synchronize_session="fetch") # Sincroniza sessão ORM
            # result = self._db_session.execute(stmt)
            # if result.rowcount > 0:
            #      self._db_session.commit()
            #      logger.info(f"Registro {self._model.__name__} ID {item_id} atualizado diretamente.")
            #      return self.read_one(item_id) # Recarrega para retornar objeto atualizado
            # else: ... (não encontrado)

        except (SQLAlchemyError, TypeError) as e:
            self._handle_db_error("update", e, f"ID={item_id}, data={data}")
            return None

    def delete(self: Self, item_id: Union[int, str]) -> bool:
        """
        Deleta um registro pela sua chave primária.

        Args:
            item_id (Union[int, str]): O valor da chave primária.

        Returns:
            bool: True se deletado com sucesso, False caso contrário.
        """
        try:
            # Abordagem 1: Buscar e deletar objeto (ORM-style)
            item_to_delete = self.read_one(item_id)
            if item_to_delete:
                self._db_session.delete(item_to_delete)
                self._db_session.commit()
                logger.info(f"Registro {self._model.__name__} ID {item_id} deletado com sucesso.")
                return True
            else:
                logger.warning(f"Registro {self._model.__name__} ID {item_id} não encontrado para deleção.")
                return False
            # Abordagem 2: Delete direto (Core-style)
            # stmt = sql_delete(self._model).where(self._primary_key_column == item_id)
            # result = self._db_session.execute(stmt)
            # if result.rowcount > 0:
            #     self._db_session.commit()
            #     return True
            # else: ... (não encontrado)

        except SQLAlchemyError as e:
            self._handle_db_error("delete", e, f"ID={item_id}")
            return False

    # --- Métodos em Massa ---

    def bulk_create(self: Self, rows_data: List[Dict[str, Any]]) -> bool:
        """
        Cria múltiplos registros em massa. Mais eficiente que criar um por um.
        Usa `insert()` do SQLAlchemy Core.

        Args:
            rows_data (List[Dict[str, Any]]): Lista de dicionários, cada um para um novo registro.

        Returns:
            bool: True se a operação foi bem-sucedida (ou sem dados), False em caso de erro.
        """
        if not rows_data:
            logger.debug("bulk_create chamado com lista vazia.")
            return True # Operação vazia é considerada sucesso

        try:
            # Usa insert() do Core para performance
            self._db_session.execute(insert(self._model), rows_data)
            self._db_session.commit()
            logger.info(f"{len(rows_data)} registros criados em massa para {self._model.__name__}.")
            return True
        except (SQLAlchemyError, TypeError) as e:
            self._handle_db_error("bulk_create", e, f"{len(rows_data)} rows")
            return False

    def bulk_update(self: Self, rows_data: List[Dict[str, Any]]) -> bool:
        """
        Atualiza múltiplos registros em massa.
        *Importante*: Esta implementação busca cada objeto e o atualiza (ORM-style).
        Para performance extrema com muitos registros, considere `session.bulk_update_mappings`
        ou updates diretos via Core API se seu caso de uso permitir.

        Args:
            rows_data (List[Dict[str, Any]]): Lista de dicionários. Cada dict DEVE conter
                a chave primária (`self._primary_key_name`) e os campos a atualizar.

        Returns:
            bool: True se todos os updates (para IDs encontrados) foram aplicados, False se erro.
        """
        if not rows_data:
            logger.debug("bulk_update chamado com lista vazia.")
            return True

        updated_count = 0
        skipped_count = 0
        pk_name = self._primary_key_name

        try:
            with self._db_session.begin_nested(): # Usa savepoint para tratar erros por lote
                for row_update_data in rows_data:
                    item_id = row_update_data.get(pk_name)
                    if item_id is None:
                        logger.warning(f"bulk_update: pulando linha sem chave primária '{pk_name}': {row_update_data}")
                        skipped_count += 1
                        continue

                    # Tenta buscar o objeto existente
                    item_to_update = self._db_session.get(self._model, item_id) # session.get é eficiente para busca por PK

                    if item_to_update:
                        logger.debug(f"bulk_update: atualizando {self._model.__name__} ID {item_id}")
                        for key, value in row_update_data.items():
                            if key != pk_name and hasattr(item_to_update, key):
                                setattr(item_to_update, key, value)
                            elif key != pk_name:
                                 logger.warning(f"bulk_update: atributo inexistente '{key}' em {self._model.__name__}. Ignorando.")
                        updated_count += 1
                        # O commit é feito no final do bloco try
                    else:
                        logger.warning(f"bulk_update: registro {self._model.__name__} ID {item_id} não encontrado para update.")
                        skipped_count += 1

            self._db_session.commit() # Comita todas as alterações bem-sucedidas
            logger.info(f"bulk_update para {self._model.__name__} concluído. Atualizados: {updated_count}, Pulados: {skipped_count}")
            return True
        except (SQLAlchemyError, TypeError, AttributeError) as e:
            self._handle_db_error("bulk_update", e, f"{len(rows_data)} rows attempt")
            return False

    def import_csv(self: Self, csv_file_path: str,
                   row_processor: Callable[[Dict[str, str]], Dict[str, Any]] = lambda row: row,
                   adjust_keys_func: Optional[Callable[[Dict], Dict]] = None) -> bool:
        """
        Importa dados de um arquivo CSV, processa as linhas e cria registros em massa.

        Args:
            csv_file_path (str): Caminho para o arquivo CSV.
            row_processor (Callable): Função opcional para transformar cada linha (dict)
                                      antes da inserção. Recebe dict, retorna dict.
            adjust_keys_func (Callable): Função opcional para ajustar/normalizar as chaves
                                        de cada linha lida do CSV (ex: utils.adjust_keys).

        Returns:
            bool: True se importado com sucesso, False caso contrário.
        """
        logger.info(f"Iniciando importação do CSV: {csv_file_path} para {self._model.__name__}")
        try:
            # Usa helper para carregar CSV como lista de dicionários
            raw_rows = load_csv_as_dict(csv_file_path)
            if raw_rows is None: # Erro na leitura do CSV já logado por load_csv_as_dict
                return False
            if not raw_rows:
                 logger.info(f"Arquivo CSV '{csv_file_path}' está vazio ou contém apenas cabeçalho.")
                 return True # Considera sucesso se o arquivo estiver vazio

            processed_rows = []
            for i, raw_row in enumerate(raw_rows):
                 try:
                      # 1. Ajusta chaves (opcional)
                      adjusted_row = adjust_keys_func(raw_row) if adjust_keys_func else raw_row
                      # 2. Processa a linha (transforma valores, etc.)
                      processed_row = row_processor(adjusted_row)
                      if processed_row: # Ignora se o processador retornar None/False/{}
                           processed_rows.append(processed_row)
                 except Exception as proc_err: # Captura erro no processamento da linha
                      logger.error(f"Erro ao processar linha {i+1} do CSV '{csv_file_path}': {proc_err} | Linha: {raw_row}", exc_info=True)
                      # Decide se continua ou aborta (aqui continua, apenas loga)

            if not processed_rows:
                 logger.warning(f"Nenhuma linha válida para importar após processamento do CSV '{csv_file_path}'.")
                 return True # Sucesso, mas nada a importar

            # Cria os registros em massa
            logger.info(f"Tentando inserir {len(processed_rows)} registros processados do CSV '{csv_file_path}'.")
            success = self.bulk_create(processed_rows)
            if success: logger.info(f"Importação do CSV '{csv_file_path}' concluída com sucesso.")
            else: logger.error(f"Falha no bulk_create durante importação do CSV '{csv_file_path}'.")
            return success

        except Exception as e: # Captura erros gerais da importação
            logger.exception(f"Erro inesperado durante importação do CSV '{csv_file_path}': {e}")
            return False

    # --- Métodos de Sessão ---
    def get_session(self: Self) -> DBSession:
        """ Retorna a sessão SQLAlchemy associada a este CRUD. """
        return self._db_session

    def commit(self: Self):
        """ Comita a transação atual na sessão DB. """
        try:
            self._db_session.commit()
            logger.debug("Sessão DB commitada com sucesso.")
        except SQLAlchemyError as e:
            self._handle_db_error("commit", e)

    def rollback(self: Self):
        """ Faz rollback da transação atual na sessão DB. """
        try:
            self._db_session.rollback()
            logger.info("Rollback da sessão DB realizado.")
        except Exception as e: # pylint: disable=broad-except
             logger.error(f"Erro durante rollback da sessão DB: {e}")