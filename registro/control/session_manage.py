# ----------------------------------------------------------------------------
# File: registro/control/session_manage.py (Fachada do Controlador de Sessão)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Ponto de entrada principal para a camada de controle relacionada à gestão
de sessões de refeição. Atua como uma fachada (Facade), coordenando as ações
entre `SessionMetadataManager` (metadados da sessão, DB, estado) e
`MealSessionHandler` (lógica da refeição ativa, elegibilidade, consumo).
"""
import logging
from typing import Any, Dict, List, Optional, Tuple, Set

# Importações locais dos componentes de controle
from registro.control.generic_crud import CRUD
from registro.control.meal_session_handler import MealSessionHandler
from registro.control.session_metadata_manager import SessionMetadata, SessionMetadataManager
from registro.model.tables import Group, Reserve, Session, Student  # Modelos DB
from registro.control.constants import NewSessionData  # Tipagem

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Coordena as operações relacionadas à sessão de refeição, delegando
    tarefas para os gerenciadores específicos de metadados e lógica de refeição.

    Fornece uma interface unificada para a camada de Visão (GUI).
    """

    def __init__(self):
        """
        Inicializa o SessionManager, criando instâncias dos gerenciadores
        de metadados e de lógica de refeição, e também instâncias CRUD
        necessárias.

        Raises:
            RuntimeError: Se a inicialização de `SessionMetadataManager` falhar
                          (geralmente devido a erro de banco de dados).
        """
        logger.info("Inicializando SessionManager...")
        try:
            # Cria o gerenciador de metadados (que inicializa o DB)
            self.metadata_manager = SessionMetadataManager()
            # Cria o manipulador da lógica de refeição, passando a sessão DB
            self.meal_handler = MealSessionHandler(
                self.metadata_manager.database_session
            )

            # Cria instâncias CRUD para acesso direto (se necessário) ou para
            # passar para outras funções (ex: sync)
            # A sessão DB é a mesma gerenciada pelo metadata_manager
            self.student_crud: CRUD[Student] = CRUD[Student](
                self.metadata_manager.database_session, Student
            )
            self.reserve_crud: CRUD[Reserve] = CRUD[Reserve](
                self.metadata_manager.database_session, Reserve
            )
            self.turma_crud: CRUD[Group] = CRUD[Group](
                self.metadata_manager.database_session, Group
            )
            self.session_crud: CRUD[Session] = CRUD[Session](
                self.metadata_manager.database_session, Session
            )

            logger.info("SessionManager inicializado com sucesso.")
        except Exception as e:
            # Captura qualquer erro durante a inicialização (principalmente do DB)
            logger.critical("Falha crítica durante a inicialização do SessionManager.", exc_info=True)
            # Relança o erro para que a aplicação principal possa tratá-lo
            raise RuntimeError(f"Falha ao inicializar SessionManager: {e}") from e

    # --- Métodos Delegados ao SessionMetadataManager ---

    def get_spreadsheet(self) -> Optional[Any]:
        """ Retorna a instância configurada do SpreadSheet (gspread wrapper). """
        return self.metadata_manager.get_spreadsheet()

    def get_date(self) -> Optional[str]:
        """ Retorna a data da sessão ativa (YYYY-MM-DD). """
        return self.metadata_manager.get_date()

    def get_meal_type(self) -> Optional[str]:
        """ Retorna o tipo de refeição da sessão ativa ('lanche' ou 'almoço'). """
        return self.metadata_manager.get_meal_type()

    def get_time(self) -> Optional[str]:
        """ Retorna a hora da sessão ativa (HH:MM). """
        return self.metadata_manager.get_time()

    def save_session_state(self) -> bool:
        """ Salva o ID da sessão ativa no arquivo de estado. """
        return self.metadata_manager.save_session_state()

    def get_session_classes(self) -> List[str]:
        """ Retorna a lista de nomes das turmas selecionadas para a sessão ativa. """
        return self.metadata_manager.get_session_classes()

    def get_session_info(self) -> Optional[SessionMetadata]:
        """ Retorna as informações completas da sessão ativa (id, data, tipo, turmas). """
        return self.metadata_manager.get_session_info()

    def load_session(self, session_id: Optional[int] = None) -> Optional[dict]:
        """
        Carrega uma sessão (por ID ou do estado salvo) e atualiza o contexto
        do MealSessionHandler.

        Args:
            session_id: O ID da sessão a carregar, ou None para usar o estado salvo.

        Returns:
            Dicionário `{"session_id": id}` se carregado com sucesso, None caso contrário.
        """
        acao = f"Carregando sessão por ID: {session_id}" if session_id else "Carregando sessão do arquivo de estado"
        logger.info(acao)

        # Delega o carregamento para o metadata_manager
        session_info_dict = self.metadata_manager.load_session(session_id)
        # Obtém os detalhes completos da sessão recém-carregada (se houver)
        session_details_tuple: Optional[SessionMetadata] = self.metadata_manager.get_session_info()

        # Atualiza o contexto do MealSessionHandler com os detalhes carregados
        if session_info_dict and session_details_tuple:
            logger.info("Sessão %s carregada. Atualizando contexto do MealHandler.",
                        session_details_tuple.session_id)
            self.meal_handler.set_session_info(session_details_tuple)
        elif session_info_dict and not session_details_tuple:
            # Caso raro: estado carregado mas detalhes não recuperados do DB?
            logger.error("Estado da sessão carregado, mas falha ao obter detalhes da sessão para MealHandler!")
            # Limpa o contexto do MealHandler
            self.meal_handler.set_session_info(SessionMetadata(-1, '', [], '', ''))
        else:
            # Nenhuma sessão carregada
            logger.warning("Nenhuma sessão pôde ser carregada.")
            # Limpa o contexto do MealHandler
            self.meal_handler.set_session_info(SessionMetadata(-1, '', [], '', ''))

        return session_info_dict  # Retorna o resultado do carregamento

    def set_session_classes(self, classes: List[str]) -> Optional[List[str]]:
        """
        Define as turmas para a sessão ativa e atualiza o contexto do MealSessionHandler.

        Args:
            classes: Lista de nomes das turmas (prefixo '#' indica sem reserva).

        Returns:
            A lista de turmas atualizada se sucesso, None caso contrário.
        """
        logger.info("Tentando definir turmas da sessão para: %s", classes)

        # Delega a atualização para o metadata_manager
        updated_classes = self.metadata_manager.set_session_classes(classes)
        # Obtém os detalhes atualizados da sessão
        session_details_tuple = self.metadata_manager.get_session_info()

        # Se a atualização no DB foi bem-sucedida e temos os detalhes
        if updated_classes is not None and session_details_tuple:
            # Atualiza o contexto do MealHandler
            self.meal_handler.set_session_info(session_details_tuple)
            logger.info("Turmas da sessão atualizadas e contexto do MealHandler refrescado.")
        elif updated_classes is not None and not session_details_tuple:
            # Caso raro: atualizou DB mas não conseguiu ler de volta?
            logger.error(
                "Turmas da sessão atualizadas no DB, mas falha ao"
                " atualizar contexto do MealHandler!")
            # Retorna None para indicar problema
            return None
        else:
            # Falha ao atualizar no metadata_manager (erro já logado lá)
            logger.error("Falha ao atualizar turmas da sessão via SessionMetadataManager.")
            # updated_classes já será None neste caso

        return updated_classes  # Retorna a lista (ou None se falhou)

    def new_session(self, session_data: NewSessionData) -> bool:
        """
        Cria uma nova sessão e atualiza o contexto do MealSessionHandler.

        Args:
            session_data: Dicionário com dados da nova sessão.

        Returns:
            True se a criação for bem-sucedida, False caso contrário.
        """
        logger.info("Tentando criar nova sessão com dados: %s", session_data)

        # Delega a criação para o metadata_manager
        success = self.metadata_manager.new_session(session_data)
        # Obtém os detalhes da sessão recém-criada (se sucesso)
        session_details_tuple = self.metadata_manager.get_session_info()

        # Se a criação foi bem-sucedida e temos os detalhes
        if success and session_details_tuple:
            # Atualiza o contexto do MealHandler
            self.meal_handler.set_session_info(session_details_tuple)
            logger.info("Nova sessão %d criada e contexto do MealHandler definido.",
                        session_details_tuple.session_id)
        elif success and not session_details_tuple:
            # Caso raro: criou no DB mas não conseguiu ler de volta?
            logger.error("Nova sessão criada no DB, mas falha ao obter detalhes"
                         " para atualizar MealHandler!")
            # Retorna False porque o estado está inconsistente
            return False
        elif not success:
            # Falha na criação (erro já logado pelo metadata_manager)
            logger.error("Falha ao criar nova sessão via SessionMetadataManager.")
            # success já será False

        return success

    # --- Métodos Delegados ao MealSessionHandler ---

    def get_served_pronts(self) -> Set[str]:
        """ Retorna o conjunto de prontuários já servidos na sessão ativa. """
        return self.meal_handler.get_served_pronts()

    def filter_eligible_students(self) -> Optional[List[Dict[str, Any]]]:
        """ Filtra e retorna a lista de alunos elegíveis para a sessão ativa. """
        return self.meal_handler.filter_eligible_students()

    def record_consumption(self, student_info: Tuple[str, str, str, str, str]) -> bool:
        """ Registra o consumo de um aluno na sessão ativa. """
        return self.meal_handler.record_consumption(student_info)

    def delete_consumption(self, student_info: Tuple[str, str, str, str, str]) -> bool:
        """ Remove o registro de consumo de um aluno na sessão ativa. """
        return self.meal_handler.delete_consumption(student_info)

    def get_served_students_details(self) -> List[Tuple[str, str, str, str, str]]:
        """ Retorna detalhes dos alunos já servidos na sessão ativa. """
        return self.meal_handler.get_served_students_details()

    def get_eligible_students(self) -> List[Dict[str, Any]]:
        """ Retorna a lista (cacheada ou recém-filtrada) de alunos elegíveis. """
        return self.meal_handler.get_eligible_students()

    def sync_consumption_state(self, served_update: List[Tuple[str, str, str, str, str]]):
        """
        Sincroniza o estado de consumo no DB com um snapshot externo.

        Garante que o MealSessionHandler esteja com o contexto da sessão
        correta antes de delegar a sincronização.

        Args:
            served_update: Lista de tuplas representando o estado desejado de alunos servidos.
        """
        logger.debug(
            "Iniciando sincronização de estado de consumo com %d registros alvo.",
            len(served_update))
        # Obtém a sessão ativa atual do metadata_manager
        session_details_tuple = self.metadata_manager.get_session_info()

        if session_details_tuple:
            active_session_id = session_details_tuple[0]
            # Verifica se o ID da sessão no MealHandler corresponde ao ID ativo
            current_handler_sid = self.meal_handler._session_id
            if current_handler_sid != active_session_id:
                # Se diferente, força a atualização do contexto do MealHandler
                logger.warning(
                    "Contexto de sessão do MealHandler (%s) difere da sessão ativa (%s). "
                    "Forçando atualização antes de sync_consumption_state.",
                    current_handler_sid, active_session_id)
                self.meal_handler.set_session_info(session_details_tuple)

            # Delega a sincronização para o MealSessionHandler
            self.meal_handler.sync_consumption_state(served_update)
        else:
            # Não há sessão ativa, não pode sincronizar
            logger.error("Não é possível sincronizar estado de consumo:"
                         " Informação da sessão ativa indisponível.")

    # --- Gerenciamento de Recursos ---

    def close_resources(self):
        """ Fecha recursos, principalmente a sessão do banco de dados. """
        logger.info("Fechando recursos do SessionManager (delegando para metadata_manager)...")
        if self.metadata_manager:
            # Delega o fechamento da sessão DB para o metadata_manager
            self.metadata_manager.close_db_session()
        else:
            logger.warning("MetadataManager não inicializado, não é possível fechar recursos.")
        logger.info("Recursos do SessionManager fechados.")
