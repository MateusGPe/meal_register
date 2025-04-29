# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# File: registro/control/session_metadata_manager.py (Gerenciador de Metadados da Sessão)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Gerencia os metadados da sessão ativa, incluindo a conexão com o banco de dados,
o carregamento/salvamento do estado da sessão (ID ativo), e a criação/atualização
de registros de sessão no banco de dados. Também inicializa a conexão com
planilhas Google (SpreadSheet).
"""
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLASession
from sqlalchemy.exc import SQLAlchemyError

# Importações locais
from registro.control.constants import DATABASE_URL, SESSION_PATH, NewSessionData, UI_TEXTS
from registro.control.generic_crud import CRUD
from registro.control.reserves import reserve_snacks_for_all  # Função auxiliar
from registro.control.sync_session import SpreadSheet  # Wrapper do gspread
from registro.control.utils import load_json, save_json  # Utilitários de arquivo
from registro.model.tables import Base, Group, Reserve, Session, Student  # Modelos DB

logger = logging.getLogger(__name__)


class SessionMetadataManager:
    """
    Gerencia a conexão com o banco de dados, os metadados da sessão ativa
    (ID, data, tipo, turmas) e a interação com o SpreadSheet.
    """

    def __init__(self):
        """
        Inicializa o gerenciador, estabelecendo a conexão com o banco de dados
        e criando as tabelas se necessário.

        Raises:
            SystemExit: Se a conexão com o banco de dados falhar.
        """
        logger.info("Inicializando SessionMetadataManager...")
        self.database_session: Optional[SQLASession] = None  # Inicializa como None
        try:
            # Cria a engine SQLAlchemy
            engine = create_engine(DATABASE_URL, echo=False)
            # Cria todas as tabelas definidas em Base.metadata (se não existirem)
            Base.metadata.create_all(engine)
            # Cria uma fábrica de sessões
            session_local_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            # Obtém uma instância de sessão do banco de dados
            self.database_session = session_local_factory()
            logger.info("Conexão com banco de dados e sessão estabelecidas.")
        except SQLAlchemyError as db_err:
            logger.critical(f"Falha na conexão/inicialização do banco de dados: {db_err}", exc_info=True)
            # Mensagem para o console caso o log não funcione/não seja visto
            print(f"ERRO CRÍTICO DE BANCO DE DADOS: {db_err}\nA aplicação não pode iniciar.", file=sys.stderr)
            sys.exit(1)  # Encerra a aplicação imediatamente
        except Exception as e:
            logger.critical(f"Erro inesperado durante configuração do banco de dados: {e}", exc_info=True)
            print(
                f"ERRO CRÍTICO durante configuração do banco de dados: {e}\nAplicação não pode iniciar.", file=sys.stderr)
            sys.exit(1)

        # Instancia o CRUD para o modelo Session
        self.session_crud: CRUD[Session] = CRUD[Session](self.database_session, Session)

        # Atributos para armazenar o estado da sessão ativa
        self._session_id: Optional[int] = None
        self._hora: Optional[str] = None
        self._turmas_selecionadas: List[str] = []
        self._date: Optional[str] = None  # Formato YYYY-MM-DD
        self._meal_type: Optional[str] = None  # 'lanche' ou 'almoço'

        # Instância do SpreadSheet (inicializada sob demanda)
        self._spread: Optional[SpreadSheet] = None

    def get_spreadsheet(self) -> Optional[SpreadSheet]:
        """
        Retorna a instância da classe SpreadSheet, inicializando-a se necessário.

        Returns:
            A instância SpreadSheet configurada ou None se a inicialização falhar.
        """
        if self._spread is None:
            logger.debug("Instância SpreadSheet requisitada mas não inicializada. Inicializando agora.")
            try:
                # Cria a instância (passa o caminho do config, se necessário)
                self._spread = SpreadSheet()  # Construtor pode receber config_file
                # Garante que a conexão interna foi estabelecida
                if not self._spread._ensure_initialized():
                    logger.error("Falha ao inicializar a instância SpreadSheet (conexão/auth falhou).")
                    self._spread = None  # Reseta para None se falhar
            except Exception as e:
                logger.exception(f"Erro ocorreu durante a inicialização do SpreadSheet: {e}")
                self._spread = None
        return self._spread

    def get_date(self) -> Optional[str]:
        """ Retorna a data da sessão ativa (YYYY-MM-DD). """
        return self._date

    def get_meal_type(self) -> Optional[str]:
        """ Retorna o tipo de refeição da sessão ativa ('lanche' ou 'almoço'). """
        return self._meal_type

    def get_time(self) -> Optional[str]:
        """ Retorna a hora da sessão ativa (HH:MM). """
        return self._hora

    def get_session_classes(self) -> List[str]:
        """ Retorna a lista de nomes das turmas selecionadas para a sessão ativa. """
        return self._turmas_selecionadas or []

    def get_session_info(self) -> Optional[Tuple[int, str, str, List[str]]]:
        """
        Retorna as informações completas da sessão ativa.

        Returns:
            Uma tupla (session_id, data, tipo_refeicao, lista_turmas) se uma
            sessão estiver ativa, ou None caso contrário.
        """
        if self._session_id is None:
            return None
        # Garante que os valores retornados não sejam None (usa string vazia como fallback)
        return (
            self._session_id,
            self._date or "",
            self._meal_type or "",
            self._turmas_selecionadas or []
        )

    def load_session(self, session_id: Optional[int] = None) -> Optional[Dict[str, int]]:
        """
        Carrega uma sessão específica ou a última sessão ativa salva no estado.
        Atualiza os atributos internos (`_session_id`, `_date`, etc.) e o
        arquivo de estado `session.json`.

        Args:
            session_id: O ID da sessão a ser carregada. Se None, tenta carregar
                        o ID do arquivo `session.json`.

        Returns:
            Um dicionário `{"session_id": id}` se uma sessão válida for carregada,
            ou None se nenhuma sessão for encontrada ou ocorrer um erro.
        """
        target_session_id: Optional[int] = None
        source: str = ""

        if session_id is not None:
            # Carregamento explícito por ID
            target_session_id = session_id
            source = f"ID explícito {target_session_id}"
            logger.info(f"Tentando carregar sessão usando {source}.")
        else:
            # Tenta carregar do arquivo de estado
            source = f"arquivo de estado ({SESSION_PATH})"
            logger.info(f"Tentando carregar ID da sessão do {source}.")
            session_state = load_json(str(SESSION_PATH))
            if session_state and isinstance(session_state.get("session_id"), int) and session_state["session_id"] > 0:
                target_session_id = session_state["session_id"]
                logger.info(f"ID de sessão {target_session_id} encontrado no arquivo de estado.")
            else:
                logger.info(f"Nenhum ID de sessão válido encontrado em {source}. Limpando sessão ativa.")
                self._clear_session_attributes()
                # Limpa o arquivo de estado se ele continha dados inválidos ou vazios
                if session_state is not None:
                    self._save_state_to_file(None)  # Salva None no arquivo
                return None  # Nenhuma sessão para carregar

        # Se não conseguimos determinar um ID alvo, não há sessão
        if target_session_id is None:
            self._clear_session_attributes()
            return None

        # --- Busca a sessão no banco de dados ---
        session_obj: Optional[Session] = None
        try:
            session_obj = self.session_crud.read_one(target_session_id)
        except Exception as e:
            logger.exception(f"Erro ao ler sessão ID {target_session_id} do banco de dados: {e}")
            self._clear_session_attributes()
            self._save_state_to_file(None)  # Limpa o estado se o DB falhar
            return None

        # --- Processa o resultado da busca ---
        if session_obj:
            # Sessão encontrada: atualiza atributos internos
            self._session_id = session_obj.id  # Garante que estamos usando o ID do objeto encontrado
            self._update_session_attributes(session_obj)
            # Salva o ID da sessão carregada no arquivo de estado
            if not self._save_state_to_file(self._session_id):
                # Loga um aviso, mas continua (a sessão está carregada em memória)
                logger.warning(f"Falha ao salvar ID {self._session_id} no arquivo de estado após carregar sessão.")
            logger.info(
                f"Sessão {self._session_id} ({self._meal_type} em {self._date}) carregada com sucesso via {source}.")
            return {"session_id": self._session_id}
        else:
            # Sessão não encontrada no DB (ID inválido?)
            logger.warning(f"ID de sessão {target_session_id} (de {source}) não encontrado no banco de dados.")
            self._clear_session_attributes()
            # Limpa o arquivo de estado se o ID era de lá e inválido
            if source.startswith("arquivo de estado"):
                self._save_state_to_file(None)
            return None

    def _clear_session_attributes(self):
        """ Limpa os atributos internos que definem a sessão ativa. """
        logger.debug("Limpando atributos internos da sessão.")
        self._session_id = None
        self._date = None
        self._meal_type = None
        self._hora = None
        self._turmas_selecionadas = []

    def _update_session_attributes(self, session_obj: Session):
        """
        Atualiza os atributos internos com base em um objeto Session carregado do DB.
        Realiza tratamento de erro para o campo 'groups' (JSON).
        """
        logger.debug(f"Atualizando atributos internos a partir do objeto Session ID: {session_obj.id}")
        self._session_id = session_obj.id  # Garante consistência
        self._meal_type = session_obj.refeicao.lower()  # Armazena em minúsculo
        self._date = session_obj.data  # YYYY-MM-DD
        self._hora = session_obj.hora  # HH:MM

        # Processa o campo 'groups' (JSON string)
        try:
            # Tenta decodificar o JSON (pode ser None ou string vazia)
            groups_list = json.loads(session_obj.groups or '[]')
            # Valida se o resultado é realmente uma lista
            if isinstance(groups_list, list):
                self._turmas_selecionadas = [str(item) for item in groups_list]  # Garante que itens são strings
            else:
                logger.warning(f"Tipo de dado inesperado para 'groups' na sessão {session_obj.id}. "
                               f"Esperado list, recebido {type(groups_list)}. Redefinindo para lista vazia.")
                self._turmas_selecionadas = []
        except json.JSONDecodeError:
            logger.error(f"Falha ao decodificar JSON 'groups' para sessão {session_obj.id}. "
                         f"Conteúdo: '{session_obj.groups}'. Redefinindo para lista vazia.")
            self._turmas_selecionadas = []
        except Exception as e:
            # Captura outros erros inesperados durante o processamento
            logger.exception(f"Erro inesperado ao processar 'groups' para sessão {session_obj.id}: {e}")
            self._turmas_selecionadas = []

    def save_session_state(self) -> bool:
        """ Salva o ID da sessão ativa atual no arquivo de estado JSON. """
        return self._save_state_to_file(self._session_id)

    def _save_state_to_file(self, session_id_to_save: Optional[int]) -> bool:
        """ Função interna para salvar o ID no arquivo session.json. """
        logger.debug(f"Salvando estado da sessão: session_id={session_id_to_save} para {SESSION_PATH}")
        # Usa a função utilitária save_json
        return save_json(str(SESSION_PATH), {"session_id": session_id_to_save})

    def set_session_classes(self, classes: List[str]) -> Optional[List[str]]:
        """
        Atualiza a lista de turmas associadas à sessão ativa no banco de dados.

        Args:
            classes: A nova lista de nomes de turmas.

        Returns:
            A lista de turmas atualizada se a operação for bem-sucedida,
            ou None se não houver sessão ativa ou ocorrer um erro.
        """
        if self._session_id is None:
            logger.error("Não é possível definir turmas da sessão: Nenhuma sessão ativa carregada.")
            return None

        logger.info(f"Tentando atualizar turmas para sessão ativa {self._session_id} para: {classes}")
        try:
            # Serializa a lista de turmas para JSON
            classes_json = json.dumps(classes)
        except TypeError as json_err:
            # Erro se a lista contiver tipos não serializáveis
            logger.error(f"Erro ao serializar lista de turmas para JSON para sessão {self._session_id}: {json_err}")
            return None

        try:
            # Atualiza o registro da sessão no banco de dados
            updated_session = self.session_crud.update(self._session_id, {"groups": classes_json})
            if updated_session:
                # Sucesso: atualiza o atributo interno e retorna a lista
                self._turmas_selecionadas = classes
                logger.info(f"Turmas atualizadas com sucesso para sessão {self._session_id}.")
                return self._turmas_selecionadas
            else:
                # CRUD.update retornou None (sessão não encontrada? Erro interno?)
                logger.error(
                    f"Falha ao atualizar turmas para sessão {self._session_id} no banco de dados (update retornou None).")
                # Tenta recarregar o estado original do DB para consistência
                self.load_session(self._session_id)
                return None
        except SQLAlchemyError as db_err:
            logger.exception(f"Erro de banco de dados ao atualizar turmas para sessão {self._session_id}: {db_err}")
            self.database_session.rollback()
            # Tenta recarregar o estado original
            self.load_session(self._session_id)
            return None
        except Exception as e:
            logger.exception(f"Erro inesperado ao definir turmas para sessão {self._session_id}: {e}")
            # Garante rollback em caso de erro inesperado
            try:
                self.database_session.rollback()
            except Exception:
                pass
            # Tenta recarregar o estado original
            self.load_session(self._session_id)
            return None

    def new_session(self, session_data: NewSessionData) -> bool:
        """
        Cria uma nova sessão de refeição no banco de dados.

        Verifica/cria reservas necessárias (especialmente para lanches) antes
        de criar o registro da sessão. Atualiza o estado interno para a nova
        sessão criada e salva no arquivo de estado.

        Args:
            session_data: Dicionário contendo os dados da nova sessão
                          (refeição, data, hora, turmas, lanche opcional).

        Returns:
            True se a sessão foi criada com sucesso, False caso contrário.
        """
        refeicao = session_data.get("refeição", "").lower()  # Garante minúsculo
        data = session_data.get("data")  # Esperado YYYY-MM-DD
        periodo = session_data.get("período", "")  # Opcional/legado?
        hora = session_data.get("hora")  # HH:MM
        groups = session_data.get("groups", [])
        lanche_nome = session_data.get("lanche")  # Nome do lanche específico

        # Validação básica dos dados obrigatórios
        if not all([refeicao in ["lanche", "almoço"], data, hora]):
            logger.error(f"Não é possível criar nova sessão: Dados obrigatórios ausentes "
                         f"(refeição, data, hora). Fornecido: {session_data}")
            return False

        logger.info(f"Tentando criar nova sessão: Refeição='{refeicao}', Data='{data}', Hora='{hora}'")

        # --- Verifica/Cria Reservas ---
        # Esta etapa é crucial, especialmente para lanches, onde pode criar reservas automaticamente.
        if not self._check_or_create_reserves(refeicao, data, lanche_nome):
            # A função _check_or_create_reserves já loga o motivo da falha
            logger.error("Pré-verificação/criação de reservas falhou. Abortando criação da sessão.")
            return False

        # --- Cria o Registro da Sessão ---
        try:
            # Serializa a lista de grupos para JSON
            groups_json = json.dumps(groups)
        except TypeError as json_err:
            logger.error(f"Erro ao serializar lista de grupos para JSON: {groups} - {json_err}")
            return False

        # Prepara os dados para a tabela Session
        new_session_db_data = {
            "refeicao": refeicao,
            "periodo": periodo,
            "data": data,
            "hora": hora,
            "groups": groups_json,
        }

        try:
            # Tenta criar o registro no banco de dados
            new_session_obj = self.session_crud.create(new_session_db_data)
            if new_session_obj and new_session_obj.id:
                # Sucesso: atualiza estado interno e salva no arquivo
                self._session_id = new_session_obj.id
                self._update_session_attributes(new_session_obj)
                self.save_session_state()  # Salva o ID da nova sessão como ativa
                logger.info(f"Nova sessão criada com sucesso. ID da sessão ativa: {self._session_id}")
                return True
            else:
                # create() retornou None ou objeto inválido
                logger.error("Falha ao criar registro da nova sessão no DB (create retornou None ou objeto inválido).")
                # Tenta rollback se o CRUD não fez
                self.database_session.rollback()
                return False
        except SQLAlchemyError as db_err:
            logger.exception(f"Erro de banco de dados ao criar nova sessão: {db_err}")
            self.database_session.rollback()
            # Verifica se foi erro de constraint única (sessão duplicada)
            if "UNIQUE constraint failed" in str(db_err):
                logger.warning("Criação da sessão falhou, provavelmente devido a uma sessão duplicada "
                               "existente para a mesma refeição/data/hora.")
            return False
        except Exception as e:
            logger.exception(f"Erro inesperado ao criar nova sessão: {e}")
            self.database_session.rollback()
            return False

    def _check_or_create_reserves(self, refeicao: str, data: str, snack_name: Optional[str]) -> bool:
        """
        Verifica a existência de reservas para a data e tipo de refeição.
        Se for uma sessão de lanche ('lanche') e não houver reservas, tenta
        criar reservas automaticamente para todos os alunos usando a função
        `reserve_snacks_for_all`.

        Args:
            refeicao: 'lanche' ou 'almoço'.
            data: Data da sessão (YYYY-MM-DD).
            snack_name: Nome do lanche (usado se precisar criar reservas).

        Returns:
            True se as reservas necessárias existem ou foram criadas com sucesso,
            False caso contrário.
        """
        is_snack_session = (refeicao == "lanche")
        logger.debug(f"Verificando reservas para: Refeição='{refeicao}', Data='{data}', É Lanche={is_snack_session}")

        try:
            # Query para verificar se existe *alguma* reserva válida para a data e tipo
            reserve_query = self.database_session.query(Reserve.id)\
                                .filter(Reserve.data == data,
                                        Reserve.snacks.is_(is_snack_session),  # Compara booleano
                                        Reserve.canceled.is_(False))  # Apenas reservas ativas
            # Executa a query de existência (mais eficiente que buscar todos)
            reserves_exist = self.database_session.query(reserve_query.exists()).scalar()

            logger.debug(f"Verificação de existência de reservas para {data} ({refeicao}): {reserves_exist}")

            if is_snack_session:
                # --- Lógica para Sessão de Lanche ---
                if not reserves_exist:
                    # Se não existem reservas de lanche, tenta criar automaticamente
                    logger.warning(
                        f"Nenhuma reserva de lanche encontrada para data {data}. Tentando criação automática.")
                    # Instancia CRUDs necessários para a função auxiliar
                    student_crud = CRUD[Student](self.database_session, Student)
                    reserve_crud = CRUD[Reserve](self.database_session, Reserve)
                    # Usa o nome do lanche fornecido ou um padrão
                    actual_snack_name = snack_name or UI_TEXTS.get("default_snack_name", "Lanche Padrão")
                    logger.info(f"Chamando reserve_snacks_for_all com Data='{data}', Prato='{actual_snack_name}'")
                    # Chama a função que faz o bulk insert
                    success = reserve_snacks_for_all(student_crud, reserve_crud, data, actual_snack_name)

                    if success:
                        # Verifica novamente se as reservas existem após a tentativa de criação
                        # (Importante pois bulk_create pode ignorar duplicatas e retornar sucesso)
                        reserves_now_exist = self.database_session.query(reserve_query.exists()).scalar()
                        if reserves_now_exist:
                            logger.info(f"Reservas de lanche automáticas criadas com sucesso para {data}.")
                            return True
                        else:
                            # Isso indica um problema: bulk_create retornou sucesso mas nada foi inserido?
                            logger.error(f"reserve_snacks_for_all retornou sucesso, mas nenhuma reserva de lanche "
                                         f"encontrada para {data} após tentativa de criação.")
                            return False
                    else:
                        # bulk_create falhou
                        logger.error(f"Criação automática de reservas de lanche falhou para {data}.")
                        return False
                else:
                    # Reservas de lanche já existem
                    logger.info(f"Reservas de lanche existentes encontradas para {data}.")
                    return True
            else:
                # --- Lógica para Sessão de Almoço ---
                if not reserves_exist:
                    # Almoço requer reservas existentes, não cria automaticamente
                    logger.error(f"Não é possível criar sessão de '{refeicao}' para {data}: "
                                 "Nenhuma reserva de almoço existente encontrada.")
                    return False
                else:
                    # Reservas de almoço existem
                    logger.info(f"Reservas de almoço existentes confirmadas para {data}.")
                    return True

        except SQLAlchemyError as db_err:
            logger.exception(f"Erro de banco de dados ao verificar/criar reservas para {data}: {db_err}")
            self.database_session.rollback()
            return False
        except Exception as e:
            logger.exception(f"Erro inesperado ao verificar/criar reservas para {data}: {e}")
            # Garante rollback em caso de erro
            try:
                self.database_session.rollback()
            except Exception:
                pass
            return False

    def close_db_session(self):
        """ Fecha a sessão do banco de dados SQLAlchemy. """
        if self.database_session:
            try:
                logger.info("Fechando sessão do banco de dados...")
                self.database_session.close()
                logger.info("Sessão do banco de dados fechada.")
            except SQLAlchemyError as db_err:
                logger.error(f"Erro ao fechar a sessão do banco de dados: {db_err}", exc_info=True)
            except Exception as e:
                logger.exception(f"Erro inesperado ao fechar sessão do banco de dados: {e}")
        else:
            logger.warning("Tentativa de fechar sessão DB, mas ela não estava inicializada.")
