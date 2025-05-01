# ----------------------------------------------------------------------------
# File: registro/control/generic_crud.py (CRUD Genérico Refinado)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Fornece uma classe genérica para operações CRUD (Create, Read, Update, Delete)
em modelos SQLAlchemy, incluindo operações em lote e importação de CSV.
"""
import logging
from pathlib import Path
from typing import (Any, Callable, Dict, Generic, List, Optional, Self, Sequence, Type,
                    TypeVar, Union)

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import declarative_base

from registro.control.utils import load_csv_as_dict

logger = logging.getLogger(__name__)

# Tipo genérico para o modelo SQLAlchemy
Base = Type[declarative_base()]
MODEL = TypeVar('MODEL', bound=Base)


class CRUD(Generic[MODEL]):
    """
    Classe genérica que encapsula operações CRUD básicas e em lote para um
    modelo SQLAlchemy específico.
    """

    def __init__(self: Self, session: DBSession, model: Type[MODEL]):
        """
        Inicializa o objeto CRUD.

        Args:
            session: A instância da sessão SQLAlchemy a ser usada para as operações.
            model: A classe do modelo SQLAlchemy mapeado.

        Raises:
            TypeError: Se `session` não for uma DBSession ou `model` não for
                       uma classe SQLAlchemy mapeada válida.
            ValueError: Se o modelo não tiver uma chave primária definida ou
                        se não for possível identificá-la.
        """
        if not isinstance(session, DBSession):
            raise TypeError("O argumento 'session' deve ser uma Sessão SQLAlchemy (DBSession).")
        # Verifica se o modelo é uma classe mapeada (tem __mapper__)
        if not hasattr(model, '__mapper__'):
            raise TypeError(f"O modelo '{model.__name__
                                         }' deve ser uma classe SQLAlchemy mapeada válida.")

        self._db_session = session
        self._model = model

        try:
            # Obtém o mapper do modelo para introspecção
            mapper = self._model.__mapper__  # type: ignore
            # Verifica se há uma chave primária definida
            if not mapper.primary_key:
                raise ValueError(f"O modelo {model.__name__}"
                                 " não possui uma chave primária definida.")
            # Assume que a primeira coluna da chave primária é a principal (comum)
            self._primary_key_name = mapper.primary_key[0].name
            self._primary_key_column = getattr(self._model, self._primary_key_name)
            logger.debug("CRUD inicializado para o modelo %s com PK %s",
                         model.__name__, self._primary_key_name)
        except (AttributeError, IndexError, ValueError) as e:
            logger.error("Falha ao determinar a chave primária para o modelo %s: %s",
                         model.__name__, {e})
            raise ValueError("Não foi possível identificar a chave"
                             f" primária para o modelo {model.__name__}.") from e

    def _handle_db_error(self: Self, operation: str,
                         error: SQLAlchemyError | AttributeError | TypeError,
                         item_info: Any = None) -> None:
        """
        Trata e loga erros do SQLAlchemy, realizando rollback da sessão.

        Args:
            operation: Nome da operação que causou o erro (ex: "create", "update").
            error: A exceção SQLAlchemy capturada.
            item_info: Informações adicionais sobre o item sendo processado (opcional).
        """
        log_msg = f"Erro de DB durante '{operation}'"
        if item_info:
            try:
                # Tenta obter uma representação curta e segura do item
                info_repr = repr(item_info)
                if len(info_repr) > 200:
                    info_repr = info_repr[:197] + '...'  # Trunca representações longas
                log_msg += f" (Info: {info_repr})"
            except Exception:
                log_msg += " (Erro ao obter info do item)"
        log_msg += f": {error}"

        # Log detalhado com traceback em DEBUG
        logger.debug("Traceback do erro de DB durante '%s':", operation, exc_info=True)
        # Log do erro principal em ERROR
        logger.error(log_msg)

        try:
            # Tenta reverter a transação atual
            self._db_session.rollback()
            logger.info("Rollback da sessão DB realizado devido ao erro.")
        except Exception as rb_exc:
            # Loga erro adicional se o rollback falhar
            logger.error("Erro adicional durante o rollback da sessão DB: %s", rb_exc)

    def create(self: Self, data: Dict[str, Any]) -> Optional[MODEL]:
        """
        Cria um novo registro no banco de dados.

        Args:
            data: Um dicionário contendo os dados para o novo registro.

        Returns:
            O objeto do modelo criado e persistido, ou None se ocorrer um erro.
        """
        try:
            # Cria a instância do modelo com os dados fornecidos
            db_item = self._model(**data)  # type: ignore
            self._db_session.add(db_item)
            self._db_session.commit()
            # Atualiza o objeto com dados do DB (ex: ID gerado)
            self._db_session.refresh(db_item)
            pk_value = getattr(db_item, self._primary_key_name, '?')
            logger.debug("Registro criado com sucesso para %s: PK=%s",
                         self._model.__name__, pk_value)
            return db_item
        except (SQLAlchemyError, TypeError) as e:
            # TypeError pode ocorrer se dados inválidos forem passados ao construtor
            self._handle_db_error("create", e, data)
            return None

    def read_one(self: Self, item_id: Union[int, str]) -> Optional[MODEL]:
        """
        Lê um registro específico pelo seu ID (chave primária).

        Args:
            item_id: O ID (chave primária) do registro a ser lido.

        Returns:
            O objeto do modelo encontrado, ou None se não existir ou ocorrer um erro.
        """
        try:
            # Usa session.get() que é otimizado para busca por PK
            result = self._db_session.get(self._model, item_id)
            if result:
                logger.debug("Registro encontrado para %s PK = %s",
                             self._model.__name__, item_id)
            else:
                logger.debug("Registro NÃO encontrado para %s PK = %s",
                             self._model.__name__, item_id)
            return result
        except SQLAlchemyError as e:
            self._handle_db_error("read_one", e, f"PK={item_id}")
            return None

    def read_filtered_one(self: Self, **filters: Any) -> Optional[MODEL]:
        """
        Lê o primeiro registro que corresponde aos filtros fornecidos.

        Args:
            **filters: Pares chave-valor representando os filtros (ex: nome="Teste").

        Returns:
            O primeiro objeto do modelo encontrado que corresponde aos filtros,
            ou None se nenhum for encontrado ou ocorrer um erro.
        """
        try:
            stmt = select(self._model)
            for key, value in filters.items():
                # Verifica se o atributo existe no modelo antes de filtrar
                if not hasattr(self._model, key):
                    raise AttributeError(
                        f"Modelo {self._model.__name__} não possui o atributo '{key}' para filtro.")
                stmt = stmt.where(getattr(self._model, key) == value)

            # Limita a 1 resultado e busca o primeiro
            stmt = stmt.limit(1)
            result = self._db_session.scalars(stmt).first()

            if result:
                logger.debug("Registro filtrado encontrado para %s: %s",
                             self._model.__name__, filters)
            else:
                logger.debug("Nenhum registro encontrado para %s com filtros: %s",
                             self._model.__name__, filters)
            return result
        except AttributeError as e:
            # Erro específico se um atributo de filtro for inválido
            logger.error("Atributo de filtro inválido para %s: %s", self._model.__name__, e)
            return None
        except SQLAlchemyError as e:
            self._handle_db_error("read_filtered_one", e, filters)
            return None

    def read_filtered(self: Self, **filters: Any) -> Sequence[MODEL]:
        """
        Lê todos os registros que correspondem aos filtros fornecidos.
        Suporta filtros especiais como `skip`, `limit`, e `field__in=[...]`.

        Args:
            **filters: Pares chave-valor representando os filtros.
                       Filtros especiais:
                       - `skip`: (int) Número de registros a pular (offset).
                       - `limit`: (int) Número máximo de registros a retornar.
                       - `nome_do_campo__in`: (List | Set) Filtra onde o
                            campo está na lista/conjunto.

        Returns:
            Uma lista de objetos do modelo encontrados, ou uma lista vazia se
            nenhum for encontrado ou ocorrer um erro.
        """
        try:
            # Extrai parâmetros de paginação dos filtros
            skip = filters.pop('skip', 0)
            limit = filters.pop('limit', None)

            stmt = select(self._model)
            for key, value in filters.items():
                # Tratamento para filtro 'IN'
                if key.endswith('__in') and isinstance(value, (list, set)):
                    actual_key = key[:-4]  # Remove o sufixo '__in'
                    # **CORREÇÃO**: Verifica se a chave REAL (sem o sufixo) existe no modelo
                    if not hasattr(self._model, actual_key):
                        raise AttributeError(
                            f"Modelo {self._model.__name__} não possui o atributo "
                            f"'{actual_key}' para filtro '__in'.")
                    # Aplica o filtro 'IN'
                    stmt = stmt.where(getattr(self._model, actual_key).in_(value))
                else:
                    # Filtro de igualdade normal
                    if not hasattr(self._model, key):
                        raise AttributeError(
                            f"Modelo {self._model.__name__} não possui o atributo"
                            f" '{key}' para filtro.")
                    stmt = stmt.where(getattr(self._model, key) == value)

            # Aplica paginação (offset e limit)
            if skip > 0:
                stmt = stmt.offset(skip)
            if limit is not None:
                stmt = stmt.limit(limit)

            # Executa a query e retorna todos os resultados
            results = self._db_session.scalars(stmt).all()
            logger.debug(
                "%s registros encontrados para %s com filtros: %s, skip=%s, limit=%s",
                len(results), self._model.__name__, filters, skip, limit)
            return results  # Retorna lista vazia se não houver resultados
        except AttributeError as e:
            logger.error("Atributo de filtro inválido para %s: %s", self._model.__name__, e)
            return []
        except SQLAlchemyError as e:
            self._handle_db_error("read_filtered", e, filters)
            return []

    def read_all(self: Self) -> Sequence[MODEL]:
        """
        Lê todos os registros da tabela associada ao modelo.

        Returns:
            Uma lista contendo todos os objetos do modelo, ou uma lista vazia
            se a tabela estiver vazia ou ocorrer um erro.
        """
        try:
            stmt = select(self._model)
            results = self._db_session.scalars(stmt).all()
            logger.debug("%s registros totais encontrados para %s (read_all)",
                         len(results), self._model.__name__)
            return results
        except SQLAlchemyError as e:
            self._handle_db_error("read_all", e)
            return []

    def read_all_ordered_by(self: Self, *order_by_columns: Any) -> Sequence[MODEL]:
        """
        Lê todos os registros da tabela, ordenados pelas colunas especificadas.

        Args:
            *order_by_columns: Colunas SQLAlchemy para usar na ordenação
                               (ex: Model.nome, Model.data.desc()).

        Returns:
            Uma lista ordenada de objetos do modelo, ou uma lista vazia se
            ocorrer um erro.
        """
        try:
            # Cria a query com ordenação
            stmt = select(self._model).order_by(*order_by_columns)
            results = self._db_session.scalars(stmt).all()
            logger.debug("%s registros ordenados encontrados para %s",
                         len(results), self._model.__name__)
            return results
        except (SQLAlchemyError, AttributeError) as e:  # AttributeError se coluna inválida
            self._handle_db_error("read_all_ordered_by", e, order_by_columns)
            return []

    def update(self: Self, item_id: Union[int, str], data: Dict[str, Any]) -> Optional[MODEL]:
        """
        Atualiza um registro existente pelo seu ID.

        Args:
            item_id: O ID (chave primária) do registro a ser atualizado.
            data: Um dicionário contendo os campos e novos valores a serem atualizados.

        Returns:
            O objeto do modelo atualizado, ou None se o registro não for
            encontrado ou ocorrer um erro.
        """
        try:
            # Busca o item pelo ID
            item_to_update = self._db_session.get(self._model, item_id)
            if item_to_update:
                logger.debug("Tentando atualizar registro %s PK %s com dados: %s",
                             self._model.__name__, item_id, data)
                # Itera sobre os dados a serem atualizados
                for key, value in data.items():
                    # Verifica se o atributo existe antes de tentar setar
                    if hasattr(item_to_update, key):
                        setattr(item_to_update, key, value)
                    else:
                        logger.warning(
                            "Tentativa de atualizar atributo inexistente '%s'"
                            " em %s PK %s. Ignorado.",
                            key, self._model.__name__, item_id)
                # Persiste as alterações
                self._db_session.commit()
                # Atualiza o objeto com dados do DB (se houver triggers, etc.)
                self._db_session.refresh(item_to_update)
                logger.info("Registro %s PK %s atualizado com sucesso.",
                            self._model.__name__, item_id)
                return item_to_update
            else:
                logger.warning("Registro %s PK %s não encontrado para atualização.",
                               self._model.__name__, item_id)
                return None
        except (SQLAlchemyError, TypeError) as e:
            self._handle_db_error("update", e, f"PK={item_id}, data={data}")
            return None

    def delete(self: Self, item_id: Union[int, str]) -> bool:
        """
        Deleta um registro específico pelo seu ID.

        Args:
            item_id: O ID (chave primária) do registro a ser deletado.

        Returns:
            True se o registro foi deletado com sucesso, False caso contrário
            (não encontrado ou erro).
        """
        try:
            # Busca o item pelo ID
            item_to_delete = self._db_session.get(self._model, item_id)
            if item_to_delete:
                self._db_session.delete(item_to_delete)
                self._db_session.commit()
                logger.info("Registro %s PK %s deletado com sucesso.",
                            self._model.__name__, item_id)
                return True
            else:
                logger.warning("Registro %s PK %s não encontrado para deleção.",
                               self._model.__name__, item_id)
                return False
        except SQLAlchemyError as e:
            # Log específico para erros de integridade (ex: FK constraint)
            if isinstance(e, IntegrityError):
                logger.error(
                    "Erro de integridade ao deletar %s PK %s (provável FK constraint): %s",
                    self._model.__name__, item_id, e)
            # Chama o handler geral de erro
            self._handle_db_error("delete", e, f"PK={item_id}")
            return False

    def bulk_create(self: Self, rows_data: List[Dict[str, Any]]) -> bool:
        """
        Cria múltiplos registros em lote (bulk insert). Mais eficiente que
        criar um por um. Assume que os dados são válidos e não duplicados.

        Args:
            rows_data: Uma lista de dicionários, onde cada dicionário contém
                       os dados para um novo registro.

        Returns:
            True se a operação em lote foi bem-sucedida (ou lista vazia),
            False se ocorreu um erro.
        """
        if not rows_data:
            logger.debug("bulk_create chamado com lista vazia.")
            return True
        try:
            # Usa a sintaxe core do SQLAlchemy para bulk insert
            self._db_session.execute(insert(self._model), rows_data)
            self._db_session.commit()
            logger.info("%s registros criados em lote para %s.",
                        len(rows_data), self._model.__name__)
            return True
        except (SQLAlchemyError, TypeError) as e:
            # Log específico para erro de integridade (chave duplicada é comum aqui)
            if isinstance(e, IntegrityError):
                logger.error(
                    "Erro de integridade durante bulk create para %s"
                    " (provável chave duplicada): %s",
                    self._model.__name__, e)
            self._handle_db_error("bulk_create", e, f"{len(rows_data)} linhas")
            return False

    def bulk_update(self: Self, rows_data: List[Dict[str, Any]]) -> bool:
        """
        Atualiza múltiplos registros em lote. Carrega cada registro individualmente
        e aplica as atualizações. Menos eficiente que `bulk_create`, mas mais
        seguro que `bulk_update` direto no DB (permite validações do ORM).

        Args:
            rows_data: Uma lista de dicionários. Cada dicionário DEVE conter a
                       chave primária (com o nome correto) e os campos a serem
                       atualizados para um registro específico.

        Returns:
            True se a operação foi concluída (mesmo que com erros parciais),
            False se ocorreu um erro grave que impediu o commit.
        """
        if not rows_data:
            logger.debug("bulk_update chamado com lista vazia.")
            return True

        updated_count = 0
        skipped_missing_pk = 0
        skipped_not_found = 0
        pk_name = self._primary_key_name

        try:
            # Itera sobre cada dicionário de atualização
            for row_update_data in rows_data:
                # Obtém o ID do item a partir do dicionário
                item_id = row_update_data.get(pk_name)
                if item_id is None:
                    logger.warning("bulk_update: pulando linha sem chave primária '%s': %s",
                                   pk_name, row_update_data)
                    skipped_missing_pk += 1
                    continue

                # Busca o item no DB pelo ID
                # Usar get() é mais eficiente e seguro aqui
                item_to_update = self._db_session.get(self._model, item_id)

                if item_to_update:
                    logger.debug("bulk_update: atualizando %s PK %s", self._model.__name__, item_id)
                    # Aplica as atualizações contidas no dicionário
                    for key, value in row_update_data.items():
                        if key == pk_name:  # Não tenta atualizar a própria PK
                            continue
                        if hasattr(item_to_update, key):
                            setattr(item_to_update, key, value)
                        else:
                            logger.warning(
                                "bulk_update: atributo '%s' não encontrado em %s PK %s. Ignorado.",
                                key, self._model.__name__, item_id)
                    updated_count += 1
                else:
                    # Loga se o item com o ID fornecido não foi encontrado
                    logger.warning(
                        "bulk_update: registro %s PK %s não encontrado para atualização.",
                        self._model.__name__, item_id)
                    skipped_not_found += 1

            # Commita todas as alterações feitas na sessão
            self._db_session.commit()
            logger.info("bulk_update para %s finalizado. Atualizados: %s, "
                        "Pulados (Sem PK): %s, Pulados (Não encontrados): %s",
                        self._model.__name__, updated_count,
                        skipped_missing_pk, skipped_not_found)
            return True  # Retorna True mesmo que alguns itens não tenham sido encontrados
        except (SQLAlchemyError, TypeError, AttributeError) as e:
            # AttributeError pode ocorrer se tentarmos setar um atributo inexistente e a
            # checagem falhar
            self._handle_db_error("bulk_update", e, f"{len(rows_data)} linhas tentadas")
            return False

    def import_csv(
            self: Self, csv_file_path: Union[str, Path],
            row_processor: Callable[[Dict[str, str]], Optional[Dict[str, Any]]] =
            lambda row: row,
            adjust_keys_func: Optional[Callable[[Dict], Dict]] = None) -> bool:
        """
        Importa dados de um arquivo CSV para o banco de dados usando `bulk_create`.

        Args:
            csv_file_path: Caminho para o arquivo CSV.
            row_processor: Uma função opcional que recebe um dicionário (linha do CSV
                           com chaves ajustadas) e retorna um dicionário processado
                           para inserção, ou None para pular a linha.
            adjust_keys_func: Uma função opcional (como `utils.adjust_keys`) para
                              normalizar as chaves do dicionário lido do CSV antes
                              de passá-lo para `row_processor`.

        Returns:
            True se a importação for bem-sucedida (ou o arquivo estiver vazio),
            False se ocorrer um erro durante o carregamento, processamento ou
            inserção no banco de dados.
        """
        csv_path_str = str(csv_file_path)
        logger.info("Iniciando importação CSV: %s para %s", csv_path_str, self._model.__name__)
        try:
            # Carrega o CSV como lista de dicionários
            raw_rows = load_csv_as_dict(csv_path_str)
            if raw_rows is None:  # Erro ao carregar o arquivo
                return False
            if not raw_rows:
                logger.info("Arquivo CSV '%s' está vazio ou contém apenas cabeçalhos.",
                            csv_path_str)
                return True  # Considera sucesso se não há o que importar

            processed_rows: List[Dict[str, Any]] = []
            # Itera sobre as linhas brutas do CSV
            for i, raw_row in enumerate(raw_rows, start=1):  # start=1 para logar linha 2 em diante
                try:
                    # Ajusta as chaves se a função foi fornecida
                    adjusted_row = adjust_keys_func(raw_row) if adjust_keys_func else raw_row
                    # Processa a linha usando a função fornecida
                    processed_row = row_processor(adjusted_row)

                    # Adiciona à lista se o processador retornou um dicionário válido
                    if isinstance(processed_row, dict) and processed_row:
                        processed_rows.append(processed_row)
                    elif processed_row is not None:
                        # Loga aviso se o processador retornou algo inesperado (não None e não dict)
                        logger.warning("Processador de linha retornou valor não-dict e"
                                       " não-None para linha CSV %s. Pulando linha: %s",
                                       i+1, raw_row)
                except Exception as proc_err:
                    # Loga erro se o processador de linha falhar
                    logger.error(
                        "Erro ao processar linha CSV %s de '%s': %s | Linha: %s", i+1,
                        csv_path_str, proc_err, raw_row, exc_info=True)

            if not processed_rows:
                logger.warning("Nenhuma linha válida para importar após processar CSV '%s'.",
                               csv_path_str)
                return True  # Sucesso se não há linhas válidas

            logger.info(
                "Tentando inserir em lote %s registros processados do CSV '%s'.",
                len(processed_rows), csv_path_str)
            # Tenta a inserção em lote
            success = self.bulk_create(processed_rows)
            if success:
                logger.info("Importação CSV '%s' concluída com sucesso.", csv_path_str)
            else:
                # Erro já foi logado por bulk_create
                logger.error(
                    "Falha no bulk create durante importação CSV de '%s'."
                    " Verifique logs anteriores.",
                    csv_path_str)
            return success
        except Exception as e:
            logger.exception("Erro inesperado durante importação CSV '%s': %s", csv_path_str, e)
            return False

    def get_session(self: Self) -> DBSession:
        """ Retorna a instância da sessão SQLAlchemy usada pelo CRUD. """
        return self._db_session

    def commit(self: Self) -> None:
        """ Realiza o commit da transação atual na sessão DB. """
        try:
            self._db_session.commit()
            logger.debug("Sessão DB commitada com sucesso.")
        except SQLAlchemyError as e:
            # Trata o erro e faz rollback automaticamente
            self._handle_db_error("commit", e)

    def rollback(self: Self) -> None:
        """ Realiza o rollback da transação atual na sessão DB. """
        try:
            self._db_session.rollback()
            logger.info("Rollback da sessão DB realizado.")
        except Exception as e:
            logger.error("Erro durante o rollback da sessão DB: %s", e)
