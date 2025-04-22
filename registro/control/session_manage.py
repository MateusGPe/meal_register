# ----------------------------------------------------------------------------
# File: registro/control/session_manage.py (Controller Facade - No changes from previous refactoring)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Fornece a classe `SessionManager` que atua como um facade (controlador principal)
para gerenciar sessões de serviço de refeição, coordenando os handlers
`MealSessionHandler` e `SessionMetadataManager`.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Set

# Importações locais
from registro.control.generic_crud import CRUD
from registro.control.meal_session_handler import MealSessionHandler
from registro.control.session_metadata_manager import SessionMetadataManager
from registro.model.tables import Group, Reserve, Student, Session  # Import Session

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Gerencia sessões de serviço de refeição coordenando MealSessionHandler
    e SessionMetadataManager. Atua como o Controller principal na arquitetura MVC.
    """

    def __init__(self):
        """ Inicializa o SessionManager. """
        logger.info("Inicializando SessionManager...")
        try:
            self.metadata_manager = SessionMetadataManager()
            self.meal_handler = MealSessionHandler(
                self.metadata_manager.database_session)
            # CRUDs para acesso direto, se necessário pela View ou outras partes
            self.student_crud: CRUD[Student] = CRUD[Student](
                self.metadata_manager.database_session, Student)
            self.reserve_crud: CRUD[Reserve] = CRUD[Reserve](
                self.metadata_manager.database_session, Reserve)
            self.turma_crud: CRUD[Group] = CRUD[Group](
                self.metadata_manager.database_session, Group)
            self.session_crud: CRUD[Session] = CRUD[Session](
                self.metadata_manager.database_session, Session)
            logger.info("SessionManager inicializado com sucesso.")
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Falha ao inicializar SessionManager.")
            raise RuntimeError(
                f"Erro crítico na inicialização do SessionManager: {e}") from e

    # --- Delegação para SessionMetadataManager ---
    def get_spreadsheet(
        self) -> Any: return self.metadata_manager.get_spreadsheet()

    def get_date(
        self) -> Optional[str]: return self.metadata_manager.get_date()

    def get_meal_type(
        self) -> Optional[str]: return self.metadata_manager.get_meal_type()

    def get_time(
        self) -> Optional[str]: return self.metadata_manager.get_time()

    def save_session_state(
        self) -> bool: return self.metadata_manager.save_session_state()

    def get_session_classes(
        self) -> List[str]: return self.metadata_manager.get_session_classes()

    def load_session(self, session_id: Optional[int] = None) -> Optional[dict]:
        """ Carrega sessão e atualiza o MealHandler. """
        logger.info(
            f"Tentando carregar sessão: {'ID '+str(session_id) if session_id else 'do arquivo'}")
        session_info = self.metadata_manager.load_session(session_id)
        # Pega detalhes *após* carregar
        session_details = self.metadata_manager.get_session_info()
        if session_info and session_details:
            logger.info(
                f"Sessão {session_details[0]} carregada. Atualizando MealHandler.")
            self.meal_handler.set_session_info(*session_details)
        elif session_info and not session_details:
            logger.warning(
                "Sessão carregada, mas falha ao obter detalhes para MealHandler.")
            self.meal_handler.set_session_info(
                None, None, None, None)  # Limpa handler
        else:
            logger.warning("Nenhuma sessão foi carregada.")
            self.meal_handler.set_session_info(
                None, None, None, None)  # Limpa handler
        return session_info

    def set_session_classes(self, classes: List[str]) -> Optional[List[str]]:
        """ Define turmas e atualiza o MealHandler. """
        logger.info(f"Definindo turmas da sessão: {classes}")
        updated_classes = self.metadata_manager.set_session_classes(classes)
        # Pega detalhes *após* definir
        session_details = self.metadata_manager.get_session_info()
        if updated_classes is not None and session_details:
            self.meal_handler.set_session_info(*session_details)
            logger.debug("MealHandler atualizado com as novas turmas.")
        elif updated_classes is not None and not session_details:
            logger.warning(
                "Turmas definidas, mas falha ao obter detalhes para MealHandler.")
        return updated_classes

    def new_session(self, session_data: Dict[str, Any]) -> bool:
        """ Cria nova sessão e atualiza o MealHandler. """
        logger.info(f"Criando nova sessão com dados: {session_data}")
        success = self.metadata_manager.new_session(session_data)
        # Pega detalhes *após* criar
        session_details = self.metadata_manager.get_session_info()
        if success and session_details:
            self.meal_handler.set_session_info(*session_details)
            logger.info("Nova sessão criada e MealHandler atualizado.")
            self.filter_students()  # Força filtragem inicial
        elif success and not session_details:
            logger.error(
                "Nova sessão criada, mas falha ao obter detalhes para MealHandler.")
            return False  # Considera falha se não puder atualizar handler
        elif not success:
            logger.error("Falha ao criar nova sessão via MetadataManager.")
        return success

    # --- Delegação para MealSessionHandler ---
    def get_served_registers(
        self) -> Set[str]: return self.meal_handler.get_served_registers()

    def filter_students(
        self) -> Optional[List[Dict[str, Any]]]: return self.meal_handler.filter_students()

    def create_student(self, i: Tuple[str, str, str, str, str]
                       ) -> bool: return self.meal_handler.create_student(i)

    def delete_student(self, i: Tuple[str, str, str, str, str]
                       ) -> bool: return self.meal_handler.delete_student(i)

    def get_served_students(
        self) -> List[Tuple[str, str, str, str, str]]: return self.meal_handler.get_served_students()

    def get_session_students(
        self) -> List[Dict[str, Any]]: return self.meal_handler.get_session_students()

    def set_students(self, served_update: List[Tuple[str, str, str, str, str]]):
        """ Atualiza students servidos, garantindo que MealHandler tem o contexto certo. """
        logger.debug(
            f"Chamando set_students com {len(served_update)} registros.")
        session_details = self.metadata_manager.get_session_info()
        if session_details:
            # Garante que o handler tem a info mais recente ANTES de chamar set_students
            # Embora set_session_info limpe caches, set_students não depende deles,
            # mas sim dos atributos _session_id, _date, _meal_type que são definidos.
            current_handler_sid = self.meal_handler._session_id
            if current_handler_sid != session_details[0]:
                logger.warning(
                    f"Atualizando info do MealHandler ({current_handler_sid} -> {session_details[0]}) antes de set_students.")
                self.meal_handler.set_session_info(*session_details)
            # Chama a atualização
            self.meal_handler.set_students(served_update)
        else:
            logger.error(
                "Não é possível chamar set_students: informações da sessão indisponíveis.")

    # --- Gerenciamento de Recursos ---
    def close_resources(self):
        """ Fecha recursos abertos, como a sessão do banco de dados. """
        logger.info("Fechando recursos do SessionManager...")
        if self.metadata_manager:
            self.metadata_manager.close_db_session()
        logger.info("Recursos do SessionManager fechados.")
