# ----------------------------------------------------------------------------
# File: registro/control/session_metadata_manager.py (Controller/Service Layer - No changes from previous refactoring)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Fornece funcionalidade para gerenciar metadados de sessões de serviço de refeição.
Inclui classes e funções para interagir com os modelos Session e Group.
"""

import json
import sys
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLASession # Alias para evitar conflito de nome

from registro.control.constants import DATABASE_URL, SESSION_PATH
from registro.control.generic_crud import CRUD
from registro.control.reserves import reserve_snacks
from registro.control.sync_session import SpreadSheet
from registro.control.utils import load_json, save_json
from registro.model.tables import Base, Reserve, Session, Student, Group # Import Group

logger = logging.getLogger(__name__)

class SessionMetadataManager:
    """
    Gerencia metadados de sessões de serviço de refeição, incluindo carregar e salvar
    informações da sessão e interagir com os modelos Session e Group.
    """

    def __init__(self):
        """
        Inicializa o SessionMetadataManager.

        Configura a conexão com o banco de dados, inicializa as operações CRUD
        para o modelo Session e prepara atributos para os metadados da sessão.
        """
        try:
            engine = create_engine(DATABASE_URL)
            Base.metadata.create_all(engine) # Garante que as tabelas existam
            session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            self.database_session: SQLASession = session_local()
        except Exception as e: # pylint: disable=broad-except
            logger.exception("Falha ao conectar ou inicializar o banco de dados.")
            print(f"Erro crítico de banco de dados: {e}")
            sys.exit(1)

        self.session_crud: CRUD[Session] = CRUD[Session](self.database_session, Session)
        self._session_id: Optional[int] = None
        self._hora: Optional[str] = None
        self._turmas_selecionadas: Optional[List[str]] = None
        self._date: Optional[str] = None
        self._meal_type: Optional[str] = None
        self._spread: Optional[SpreadSheet] = None

    def get_spreadsheet(self) -> Optional[SpreadSheet]:
        """ Retorna o objeto SpreadSheet (lazy loaded). """
        if self._spread is None:
            try:
                self._spread = SpreadSheet()
            except Exception as e: # pylint: disable=broad-except
                logger.error(f"Erro ao inicializar SpreadSheet {type(e).__name__}: {e}")
                print(f"Erro ao inicializar SpreadSheet: {e}")
                return None
        return self._spread

    def get_date(self) -> Optional[str]: return self._date
    def get_meal_type(self) -> Optional[str]: return self._meal_type
    def get_time(self) -> Optional[str]: return self._hora
    def get_session_classes(self) -> List[str]: return self._turmas_selecionadas or []

    def load_session(self, session_id: Optional[int] = None) -> Optional[dict]:
        """ Carrega informações da sessão do arquivo de estado ou por ID. """
        loaded_session_info = None
        target_session_id = None

        if session_id is not None:
            target_session_id = session_id
            self._session_id = target_session_id
            if not self.save_session_state():
                 logger.warning(f"Falha ao salvar o estado da sessão para session_id: {target_session_id}")
            loaded_session_info = {"session_id": target_session_id}
        else:
            _session_state = load_json(SESSION_PATH)
            if _session_state and isinstance(_session_state.get("session_id"), int) and _session_state["session_id"] > 0:
                target_session_id = _session_state["session_id"]
                loaded_session_info = _session_state
            else:
                logger.info(f"session_id inválido ou ausente no arquivo de estado: {_session_state}")
                self._clear_session_attributes()
                return None

        if target_session_id is None:
            self._clear_session_attributes()
            return None

        session_obj = self.session_crud.read_one(target_session_id)
        if not session_obj:
            logger.warning(f"Sessão com ID {target_session_id} não encontrada no banco de dados.")
            self._clear_session_attributes()
            if self._session_id == target_session_id:
                 save_json(SESSION_PATH, {"session_id": None}) # Limpa estado se sessão não existe
            self._session_id = None
            return None

        self._session_id = session_obj.id
        self._update_session_attributes(session_obj)
        logger.info(f"Sessão {self._session_id} carregada com sucesso.")
        return loaded_session_info or {"session_id": self._session_id}

    def _clear_session_attributes(self):
        """ Limpa os atributos de metadados da sessão. """
        self._session_id = None
        self._date = None
        self._meal_type = None
        self._hora = None
        self._turmas_selecionadas = None

    def _update_session_attributes(self, session_obj: Session):
        """ Atualiza os atributos internos com base no objeto Session do DB. """
        self._meal_type = session_obj.refeicao
        self._date = session_obj.data
        self._hora = session_obj.hora
        try:
            groups_list = json.loads(session_obj.groups or '[]')
            self._turmas_selecionadas = groups_list if isinstance(groups_list, list) else []
            if not isinstance(groups_list, list):
                 logger.warning(f"Formato inesperado para 'groups' na session {session_obj.id}. Recebido {type(groups_list)}")
        except json.JSONDecodeError:
            logger.error(f"Erro ao decodificar JSON 'groups' para session {session_obj.id}: {session_obj.groups}")
            self._turmas_selecionadas = []

    def save_session_state(self) -> bool:
        """ Salva o ID da sessão atual no arquivo de estado SESSION_PATH. """
        session_id_to_save = self._session_id # Pode ser None
        if session_id_to_save is None:
             logger.warning("Tentativa de salvar estado da sessão sem um session_id ativo.")
        return save_json(SESSION_PATH, {"session_id": session_id_to_save})

    def set_session_classes(self, classes: List[str]) -> Optional[List[str]]:
        """ Define as turmas para a sessão ativa atual no DB e atualiza o estado interno. """
        if self._session_id is None:
            logger.error("Não é possível definir turmas: nenhuma sessão ativa carregada.")
            return None
        try:
            classes_json = json.dumps(classes)
            updated = self.session_crud.update(self._session_id, {"groups": classes_json})
            if updated:
                self._turmas_selecionadas = classes
                logger.info(f"Turmas atualizadas para session {self._session_id}: {classes}")
                return self._turmas_selecionadas
            else:
                logger.error(f"Falha ao atualizar turmas para session {self._session_id} no banco de dados.")
                return None
        except Exception as e: # pylint: disable=broad-except
            logger.exception(f"Erro ao definir turmas para session {self._session_id}: {e}")
            self.database_session.rollback()
            return None

    def new_session(self, session_data: Dict[str, Any]) -> bool:
        """ Cria uma nova sessão de serviço de refeição no DB e a define como ativa. """
        refeicao = session_data.get("refeição", "").lower()
        data = session_data.get("data")
        periodo = session_data.get("período", "")
        hora = session_data.get("hora")
        groups = session_data.get("groups", [])

        if not all([refeicao, data, hora]):
            logger.error(f"Dados insuficientes para criar nova sessão: {session_data}")
            return False

        # Verifica/cria reservas se necessário
        if not self._check_or_create_reserves(refeicao, data, session_data.get('lanche')):
            return False # Log ocorre dentro do método auxiliar

        # Prepara dados e cria sessão no DB
        new_session_db_data = {
            "refeicao": refeicao, "periodo": periodo, "data": data,
            "hora": hora, "groups": json.dumps(groups),
        }
        try:
            new_session_obj = self.session_crud.create(new_session_db_data)
            if new_session_obj:
                self._session_id = new_session_obj.id
                self._update_session_attributes(new_session_obj)
                self.save_session_state()
                logger.info(f"Nova sessão criada e definida como ativa: ID {self._session_id}")
                return True
            else:
                logger.error("Falha ao criar a nova sessão no DB (create retornou None).")
                self.database_session.rollback()
                return False
        except Exception as e: # pylint: disable=broad-except
            logger.exception(f"Erro ao criar nova sessão no DB: {e}")
            self.database_session.rollback()
            return False

    def _check_or_create_reserves(self, refeicao: str, data: str, snack_name: Optional[str]) -> bool:
        """ Verifica existência de reservas ou tenta criá-las para lanches. """
        reserve_query = self.database_session.query(Reserve).filter(Reserve.data == data)
        is_snack = refeicao == "lanche"
        reserves_exist = reserve_query.filter(Reserve.snacks.is_(is_snack)).count() > 0

        if is_snack:
            if not reserves_exist:
                logger.info(f"Nenhuma reserva de lanche encontrada para {data}. Tentando criar automaticamente.")
                try:
                    student_crud = CRUD[Student](self.database_session, Student)
                    reserve_crud = CRUD[Reserve](self.database_session, Reserve)
                    actual_snack_name = snack_name or 'Lanche Padrão'
                    reserve_snacks(student_crud, reserve_crud, data, actual_snack_name)
                    # Verifica novamente após tentativa de criação
                    if reserve_query.filter(Reserve.snacks.is_(True)).count() == 0:
                        logger.error(f"Falha ao criar reservas de lanche automaticamente para {data}.")
                        return False
                    logger.info(f"Reservas de lanche criadas automaticamente para {data}.")
                    return True # Reservas criadas
                except Exception as e: # pylint: disable=broad-except
                    logger.exception(f"Erro ao criar reservas de lanche para {data}: {e}")
                    self.database_session.rollback()
                    return False
            else:
                 return True # Reservas de lanche já existiam
        else: # Almoço
             if not reserves_exist:
                  logger.warning(f"Nenhuma reserva de almoço encontrada para {data}. Sessão não pode ser criada.")
                  return False
             else:
                  return True # Reservas de almoço existem

    def get_session_info(self) -> Optional[Tuple[int, str, str, List[str]]]:
        """ Recupera as informações da sessão ativa atual. """
        if self._session_id is None: return None
        return (
            self._session_id,
            self._date or "",
            self._meal_type or "",
            self._turmas_selecionadas or []
        )

    def close_db_session(self):
        """ Fecha a sessão do banco de dados SQLAlchemy. """
        if self.database_session:
            try:
                self.database_session.close()
                logger.info("Sessão do banco de dados fechada.")
            except Exception as e: # pylint: disable=broad-except
                 logger.error(f"Erro ao fechar a sessão do banco de dados: {e}")