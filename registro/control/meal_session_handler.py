# ----------------------------------------------------------------------------
# File: registro/control/meal_session_handler.py (Controlador da Sessão de Refeição)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Gerencia a lógica de negócio relacionada a uma sessão de refeição específica,
incluindo filtragem de alunos elegíveis, registro e remoção de consumos,
e consulta de dados relacionados à sessão ativa.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# Importações SQLAlchemy
from sqlalchemy import case, delete, func
from sqlalchemy import or_ as sql_or
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as SQLASession
from sqlalchemy.orm import aliased

# Importações locais
from registro.control.constants import UI_TEXTS
from registro.control.generic_crud import CRUD
from registro.control.session_metadata_manager import SessionMetadata
from registro.control.utils import to_code
from registro.model.tables import Consumption, Group, Reserve, Student

logger = logging.getLogger(__name__)


class MealSessionHandler:
    """
    Manipula as operações de dados para uma sessão de refeição ativa.

    Responsável por:
    - Filtrar alunos elegíveis com base na data, tipo de refeição e turmas selecionadas.
    - Manter o estado dos alunos já servidos na sessão atual.
    - Registrar o consumo de refeição por aluno.
    - Remover registros de consumo.
    - Sincronizar o estado de consumo com uma fonte externa (ex: snapshot).
    - Fornecer detalhes dos alunos servidos e elegíveis.
    """

    def __init__(self, database_session: SQLASession):
        """
        Inicializa o manipulador da sessão de refeição.

        Args:
            database_session: A instância da sessão SQLAlchemy para interagir
                              com o banco de dados.

        Raises:
            ValueError: Se `database_session` for None.
        """
        if database_session is None:
            raise ValueError(
                "A sessão do banco de dados (database_session) não pode ser None."
            )
        self.db_session = database_session
        # Instâncias CRUD para cada modelo relevante
        self.student_crud: CRUD[Student] = CRUD[Student](self.db_session, Student)
        self.consumption_crud: CRUD[Consumption] = CRUD[Consumption](
            self.db_session, Consumption
        )

        # Atributos de estado da sessão atual
        self._session_id: Optional[int] = None
        self._date: Optional[str] = None  # Formato YYYY-MM-DD internamente
        self._meal_type: Optional[str] = None  # 'lanche' ou 'almoço' (minúsculo)

        # Turmas selecionadas para a sessão (separadas por tipo de reserva)
        self._turmas_com_reserva: Set[str] = set()
        self._turmas_sem_reserva: Set[str] = set()  # Identificadas por '#' no input

        # Caches internos para otimização
        self._served_pronts: Set[str] = (
            set()
        )  # Prontuários dos alunos já servidos nesta sessão
        self._filtered_students_cache: List[Dict[str, Any]] = (
            []
        )  # Cache dos alunos elegíveis filtrados
        self._pront_to_reserve_id_map: Dict[str, Optional[int]] = (
            {}
        )  # Cache ID reserva por prontuário
        self._pront_to_student_id_map: Dict[str, int] = (
            {}
        )  # Cache ID aluno por prontuário

    def set_session_info(
        self,
        session: SessionMetadata
    ):
        """
        Define o contexto da sessão de refeição ativa. Limpa caches internos.

        Args:
            session_id: O ID da sessão no banco de dados.
            date: A data da sessão (formato YYYY-MM-DD).
            meal_type: O tipo de refeição ('Lanche' ou 'Almoço').
            turmas: Lista de nomes de turmas selecionadas para esta sessão.
                    Turmas prefixadas com '#' são consideradas "sem reserva obrigatória".
        """
        logger.debug('Definindo informações da sessão: ID=%s, Data=%s, Refeição=%s, Grupos=%s',
                     session.session_id, session.date, session.meal_type, session.select_group)
        self._session_id = session.session_id
        self._date = session.date
        # Armazena o tipo de refeição em minúsculo para consistência interna
        self._meal_type = session.meal_type.lower() if session.meal_type else None

        # Processa a lista de turmas para separar com/sem reserva
        self._turmas_com_reserva = set()
        self._turmas_sem_reserva = set()
        if session.select_group:
            for t in session.select_group:
                # Limpa espaços e remove 'Vazio' (legado?)
                t_clean = t.replace("Vazio", "").strip()
                if not t_clean:
                    continue
                if t_clean.startswith("#"):
                    # Adiciona à lista sem reserva, removendo o '#'
                    self._turmas_sem_reserva.add(t_clean[1:])
                else:
                    self._turmas_com_reserva.add(t_clean)

        # Limpa caches sempre que o contexto da sessão muda
        self._clear_caches()
        logger.info('Contexto da sessão definido: ID=%s, Data=%s, Refeição=%s, GruposComReserva=%s,'
                    ' GruposSemReserva=%s', self._session_id, self._date, self._meal_type,
                    self._turmas_com_reserva, self._turmas_sem_reserva)

    def _clear_caches(self) -> None:
        """Limpa os caches internos de alunos filtrados, servidos e mapeamentos de ID."""
        logger.debug("Limpando caches internos.")
        self._filtered_students_cache = []
        self._served_pronts = set()
        self._pront_to_reserve_id_map = {}
        self._pront_to_student_id_map = {}

    def get_served_pronts(self) -> Set[str]:
        """
        Retorna o conjunto de prontuários dos alunos já servidos na sessão atual.
        Carrega do banco de dados se o cache estiver vazio.

        Returns:
            Um conjunto contendo os prontuários (strings) dos alunos servidos.
        """
        # Se o cache está vazio e temos uma sessão ativa, carrega do DB
        if not self._served_pronts and self._session_id is not None:
            self._load_served_pronts_from_db()
        return self._served_pronts

    def filter_eligible_students(self, not_served: bool = True) -> Optional[List[Dict[str, Any]]]:
        """
        Filtra e retorna a lista de alunos elegíveis para a sessão atual,
        com base na data, tipo de refeição e turmas selecionadas.

        A elegibilidade considera:
        - Alunos pertencentes às turmas selecionadas.
        - Se a turma exige reserva (`_turmas_com_reserva`), o aluno DEVE ter
          uma reserva válida (não cancelada) para a data e tipo de refeição.
        - Se a turma não exige reserva (`_turmas_sem_reserva`), o aluno é elegível
          independentemente de ter reserva ou não.
        - Alunos já servidos nesta sessão são EXCLUÍDOS implicitamente (pelo cache
            `_served_pronts`).

        Retorna o resultado do cache se já calculado, caso contrário, executa a
        query no banco de dados e popula os caches internos.

        Returns:
            Uma lista de dicionários, cada um representando um aluno elegível,
            contendo chaves como 'Pront', 'Nome', 'Turma', 'Prato', 'Data', etc.,
            ou None se ocorrer um erro ou a informação da sessão for incompleta.
            Retorna lista vazia se nenhum aluno elegível for encontrado.
        """
        # Validação prévia das informações necessárias da sessão
        if not all(
            [
                self._date,
                self._meal_type is not None,
                self._session_id is not None,
                (self._turmas_com_reserva or self._turmas_sem_reserva),
            ]
        ):
            logger.warning(
                "Não é possível filtrar alunos: Informações da sessão incompletas "
                "(data, refeição, id, turmas)."
            )
            return None

        # Se o cache já existe, retorna diretamente (otimização)
        if self._filtered_students_cache:
            logger.debug('Retornando alunos elegíveis do cache.')
            return self._filtered_students_cache
        logger.debug('Filtrando alunos elegíveis para a sessão (cache vazio)...')
        # Limpa caches (garantia, embora set_session_info já faça isso)
        self._clear_caches()
        # Carrega os prontuários já servidos para uso posterior (exclusão implícita)
        self._load_served_pronts_from_db()

        is_snack_session = self._meal_type == "lanche"

        # Cria aliases para as tabelas para clareza na query
        s, g, r = aliased(Student), aliased(Group), aliased(Reserve)

        try:
            # --- Construção da Query Principal ---
            query = (
                self.db_session.query(
                    s.pront,  # Prontuário do aluno
                    s.nome,  # Nome do aluno
                    func.group_concat(g.nome.distinct()).label(
                        "turmas_concat"
                    ),  # Concatena nomes das turmas do aluno
                    s.id.label("student_id"),  # ID interno do aluno
                    r.id.label("reserve_id"),  # ID da reserva (se houver)
                    r.dish.label("reserve_dish"),  # Prato da reserva (se houver)
                )
                .select_from(s)
                .join(s.groups.of_type(g))
                .outerjoin(
                    r,
                    (r.student_id == s.id)
                    & (r.data == self._date)
                    & (
                        r.snacks.is_(is_snack_session)
                    )  # Compara booleano (True para lanche)
                    & (r.canceled.is_(False)),
                )
            )  # Garante que a reserva está ativa

            # --- Condições de Filtragem (WHERE) ---
            # Constrói as condições com base nas turmas selecionadas
            conditions = []
            # 1. Turmas COM reserva obrigatória:
            if self._turmas_com_reserva:
                conditions.append(
                    (
                        g.nome.in_(self._turmas_com_reserva)
                    )  # Aluno pertence a uma turma COM reserva
                    & (
                        r.id.isnot(None)
                    )  # E DEVE ter uma reserva (JOIN foi bem-sucedido)
                )
            # 2. Turmas SEM reserva obrigatória:
            if self._turmas_sem_reserva:
                # Aluno pertence a uma turma SEM reserva (reserva é opcional)
                conditions.append(g.nome.in_(self._turmas_sem_reserva))

            # Aplica as condições ao filtro da query usando OR se ambas existirem
            if conditions:
                query = query.filter(
                    sql_or(*conditions) if len(conditions) > 1 else conditions[0]
                )
            else:
                # Se nenhuma turma foi selecionada (não deveria acontecer devido à
                #   validação anterior)
                logger.warning(
                    "Nenhuma turma selecionada para filtragem. Retornando lista vazia."
                )
                self._filtered_students_cache = []
                return self._filtered_students_cache

            # --- Agrupamento e Ordenação ---
            # Agrupa para evitar duplicação de alunos se ele pertencer a múltiplas turmas
            # que satisfaçam as condições. Inclui campos da reserva no group_by
            # para garantir que diferentes reservas (raro, mas possível?) não sejam colapsadas.
            query = query.group_by(s.id, s.pront, s.nome, r.id, r.dish).order_by(
                s.nome
            )  # Ordena por nome para a exibição

            # Executa a query
            results = query.all()
            logger.debug('Query executada, processando %s resultados brutos.', len(results))

            # --- Pós-Processamento dos Resultados ---
            # Agrega informações por aluno (caso um aluno esteja em múltiplas turmas elegíveis)
            processed_students: Dict[str, Dict[str, Any]] = {}
            for (
                pront,
                nome,
                turmas_str,
                student_id,
                reserve_id,
                reserve_dish,
            ) in results:
                # Popula caches de mapeamento ID <-> Prontuário
                self._pront_to_student_id_map[pront] = student_id
                self._pront_to_reserve_id_map[pront] = reserve_id  # Pode ser None

                # Se é a primeira vez que vemos este prontuário
                if pront not in processed_students:
                    processed_students[pront] = {
                        "Pront": pront,
                        "Nome": nome,
                        # Usa um set para acumular turmas sem duplicação
                        "Turma": set(turmas_str.split(",") if turmas_str else []),
                        # Define o prato baseado na existência da reserva
                        "Prato": (
                            reserve_dish
                            if reserve_id is not None
                            else UI_TEXTS.get("no_reservation_status", "Sem Reserva")
                        ),
                        "Data": self._date,  # Adiciona data da sessão
                        "lookup_key": to_code(pront),  # Chave ofuscada para UI
                        "Hora": None,  # Será preenchido no consumo
                        # Guarda IDs internos para operações futuras
                        "reserve_id": reserve_id,
                        "student_id": student_id,
                    }
                else:
                    # Se já vimos o aluno, apenas atualiza o conjunto de turmas
                    if turmas_str:
                        processed_students[pront]["Turma"].update(turmas_str.split(","))
                    # Se esta linha tem uma reserva e a anterior não tinha, atualiza prato/ID
                    # (Prioriza mostrar o status de 'Com Reserva' se houver)
                    if (
                        reserve_id is not None
                        and processed_students[pront]["reserve_id"] is None
                    ):
                        processed_students[pront]["reserve_id"] = reserve_id
                        processed_students[pront]["Prato"] = reserve_dish

            # Converte o dicionário processado de volta para lista, formatando as turmas
            self._filtered_students_cache = [
                # Junta as turmas (do set) em uma string ordenada e separada por vírgula
                {**info, "Turma": ",".join(sorted(list(info["Turma"])))}
                for pront, info in processed_students.items()
                # Exclui alunos que já foram servidos nesta sessão
                if pront not in self._served_pronts and not_served
            ]

            logger.info('%s alunos elegíveis (e não servidos) filtrados para a sessão %s.',
                        len(self._filtered_students_cache), self._session_id)
            return self._filtered_students_cache

        except SQLAlchemyError as e:
            logger.exception('Erro de banco de dados durante filtragem de alunos para'
                             ' sessão %s: %s', self._session_id, e)
            self.db_session.rollback()
            self._clear_caches()  # Limpa caches em caso de erro
            return None
        except Exception as e:
            logger.exception('Erro inesperado durante filtragem de alunos: %s', e)
            self._clear_caches()
            return None

    def _load_served_pronts_from_db(self) -> None:
        """Carrega os prontuários dos alunos servidos na sessão atual do DB para o cache
        `_served_pronts`."""
        if self._session_id is None:
            logger.debug('Não é possível carregar servidos: ID da sessão não definido.')
            self._served_pronts = set()
            return
        logger.debug('Carregando prontuários servidos do DB para sessão %s...', self._session_id)
        try:
            # Query simples para buscar prontuários da tabela Consumption para a sessão atual
            served_query = (
                self.db_session.query(Student.pront)
                .join(Consumption, Consumption.student_id == Student.id)
                .filter(Consumption.session_id == self._session_id)
            )

            # Executa a query e monta o conjunto de prontuários
            self._served_pronts = {pront for (pront,) in served_query.all()}
            logger.debug('Carregados %s prontuários servidos do DB para sessão %s.',
                         len(self._served_pronts), self._session_id)
        except SQLAlchemyError as e:
            logger.exception('Erro DB ao carregar PRONTs servidos para sessão %s: %s',
                             self._session_id, e)
            self.db_session.rollback()
            self._served_pronts = set()  # Limpa cache em caso de erro
        except Exception as e:
            logger.exception('Erro inesperado ao carregar PRONTs servidos: %s', e)
            self._served_pronts = set()

    def _get_or_find_student_details(
        self, pront: str
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Obtém o ID do aluno e o ID da reserva (se aplicável) para um dado prontuário.
        Primeiro tenta obter do cache, se não encontrar, busca no banco de dados.

        Args:
            pront: O prontuário do aluno.

        Returns:
            Uma tupla contendo (student_id, reserve_id). `reserve_id` pode ser None.
            Retorna (None, None) se o aluno não for encontrado ou ocorrer um erro.
        """
        student_id = self._pront_to_student_id_map.get(pront)
        reserve_id = self._pront_to_reserve_id_map.get(pront)

        # Se ambos IDs estão no cache, retorna diretamente
        if (
            student_id is not None
        ):  # reserve_id PODE ser None, então só checamos student_id
            return student_id, reserve_id

        # Cache miss: Busca no banco de dados
        logger.debug('Cache miss para detalhes do aluno %s. Consultando DB...', pront)
        try:
            # Busca o aluno pelo prontuário
            student_record = self.student_crud.read_filtered_one(pront=pront)
            if student_record:
                student_id = student_record.id
                # Busca a reserva correspondente (se houver) para a data e tipo de refeição
                reserve_record_id = (
                    self.db_session.query(Reserve.id)
                    .filter(
                        Reserve.student_id == student_id,
                        Reserve.data == self._date,
                        Reserve.snacks.is_(self._meal_type == "lanche"),
                        Reserve.canceled.is_(False),
                    )
                    .scalar()
                )  # Pega o ID diretamente, ou None se não encontrar

                reserve_id = reserve_record_id  # Pode ser None
                # Atualiza os caches com os dados encontrados
                self._pront_to_student_id_map[pront] = student_id
                self._pront_to_reserve_id_map[pront] = reserve_id
                logger.debug(
                    'Detalhes para %s encontrados no DB: student_id=%s, reserve_id=%s. '
                    'Caches atualizados.', pront, student_id, reserve_id)
                return (student_id, reserve_id)
                # Aluno não encontrado no banco de dados
            else:
                logger.warning('Aluno %s não encontrado no DB ao buscar detalhes.', pront)
                return (None, None)
        except SQLAlchemyError as e:
            logger.exception('Erro DB ao buscar detalhes para %s: %s', pront, e)
            self.db_session.rollback()
            return (None, None)
        except Exception as e:
            logger.exception('Erro inesperado ao buscar detalhes para %s: %s', pront, e)
            return (None, None)

    def record_consumption(self, student_info: Tuple[str, str, str, str, str]) -> bool:
        """
        Registra o consumo de uma refeição para um aluno na sessão atual.

        Args:
            student_info: Tupla contendo (pront, nome, turma, hora, prato_status).
                          Apenas o prontuário é estritamente necessário aqui.

        Returns:
            True se o consumo foi registrado com sucesso, False caso contrário
            (ex: sessão inativa, aluno não encontrado, já servido, erro DB).
        """
        if self._session_id is None:
            logger.error('Não é possível registrar consumo: Nenhuma sessão ativa.')
            return False

        pront = student_info[0]
        # Verifica se o aluno já consta como servido no cache desta sessão
        if pront in self._served_pronts:
            logger.warning('Consumo não registrado: %s já marcado como servido nesta sessão.',
                           pront)
            return False

        # Obtém os IDs necessários (do cache ou DB)
        student_id, reserve_id = self._get_or_find_student_details(pront)

        # Se não encontrou o aluno, não pode registrar
        if student_id is None:
            logger.error('Não é possível registrar consumo: Aluno %s não encontrado.', pront)
            return False

        # Prepara os dados para a tabela Consumption
        consumption_data = {
            "student_id": student_id,
            "session_id": self._session_id,
            "consumption_time": datetime.now().strftime(
                "%H:%M:%S"
            ),  # Hora atual do registro
            "consumed_without_reservation": (
                reserve_id is None
            ),  # True se não tinha reserva
            "reserve_id": reserve_id,  # ID da reserva (ou None)
        }

        try:
            # Tenta criar o registro de consumo usando o CRUD
            created_consumption = self.consumption_crud.create(consumption_data)
            if created_consumption:
                # Sucesso: Adiciona ao cache de servidos e loga
                self._served_pronts.add(pront)
                logger.info('Consumo registrado para %s na sessão %s.', pront, self._session_id)
                # Atualiza cache de alunos elegíveis (remove o aluno recém-registrado)
                self._filtered_students_cache = [
                    s for s in self._filtered_students_cache if s.get("Pront") != pront
                ]
                return True
            else:
                # CRUD.create pode retornar None se ocorrer erro interno e rollback
                logger.error(
                    "Falha ao criar registro de consumo para %s (CRUD retornou não-True)."
                    " Verificando status atual.", pront
                )
                self.db_session.rollback()  # Garante rollback se o CRUD não fez
                # Recarrega servidos do DB para verificar se já existe (concorrência?)
                self._load_served_pronts_from_db()
                if pront in self._served_pronts:
                    logger.warning(
                        'Registro de consumo para %s parece existir agora (possível condição de'
                        ' corrida ou conflito).', pront)
                    # Considera como "falha" porque a operação original não inseriu,
                    # mas o estado final é que o aluno está servido. A UI deve refletir isso.
                return False
        except SQLAlchemyError as e:
            # Erro durante a operação de criação no DB
            logger.exception('Erro ao registrar consumo para %s na sessão %s: %s',
                             pront, self._session_id, e)
            self.db_session.rollback()
            # Recarrega para garantir consistência do cache
            self._load_served_pronts_from_db()
            if pront in self._served_pronts:
                logger.warning('Registro de consumo falhou para %s, mas DB mostra status servido.',
                               pront)
            return False
        except Exception as e:
            # Outro erro inesperado
            logger.exception('Erro inesperado ao registrar consumo para %s: %s', pront, e)
            self.db_session.rollback()
            return False

    def delete_consumption(self, student_info: Tuple[str, str, str, str, str]) -> bool:
        """
        Remove o registro de consumo de um aluno na sessão atual.

        Args:
            student_info: Tupla contendo (pront, nome, turma, hora, prato_status).
                          Apenas o prontuário é estritamente necessário aqui.

        Returns:
            True se o consumo foi removido com sucesso, False caso contrário
            (ex: sessão inativa, aluno não servido, erro DB).
        """
        if self._session_id is None:
            logger.error('Não é possível deletar consumo: Nenhuma sessão ativa.')
            return False

        pront = student_info[0]
        # Verifica se o aluno realmente está no cache de servidos
        if pront not in self._served_pronts:
            logger.warning('Não é possível deletar consumo: %s não está marcado como servido'
                           ' nesta sessão (cache).', pront)
            # Tenta recarregar do DB para garantir
            self._load_served_pronts_from_db()
            if pront not in self._served_pronts:
                logger.warning('Confirmado que %s não está servido no DB. exclusão abortada.', pront)
                return False
            else:
                logger.warning('Inconsistência de cache detectada para %s ao deletar. Prosseguindo'
                               ' com ID do DB.', pront)

        # Obtém o ID do aluno (necessário para a query de exclusão)
        student_id, _ = self._get_or_find_student_details(pront)

        # Inconsistência grave: está no cache de servidos mas não acha o aluno no DB
        if student_id is None:
            logger.error('Inconsistência: %s no cache de servidos, mas aluno não encontrado'
                         ' no DB para exclusão.', pront)
            self._served_pronts.discard(pront)  # Remove do cache para corrigir
            return False

        try:
            # Cria a declaração de exclusão direta no banco
            delete_stmt = delete(Consumption).where(
                Consumption.student_id == student_id,
                Consumption.session_id == self._session_id,
            )
            # Executa a exclusão
            result = self.db_session.execute(delete_stmt)
            deleted_count = result.rowcount  # Número de linhas afetadas

            if deleted_count > 0:
                # Sucesso: commita a transação e atualiza o cache
                self.db_session.commit()
                self._served_pronts.discard(pront)
                logger.info('Registro de consumo deletado para %s na sessão %s (%s linha(s)).',
                            pront, self._session_id, deleted_count)
                # Força recarregamento da lista de elegíveis na próxima busca
                self._filtered_students_cache = []
                return True
            else:
                # Nenhuma linha foi deletada (registro não existia no DB?)
                self.db_session.rollback()
                logger.warning(
                    'Nenhum registro de consumo encontrado no DB para deletar para %s na'
                    ' sessão %s. Cache pode estar inconsistente.', pront, self._session_id)
                # Recarrega o cache de servidos para garantir consistência
                self._load_served_pronts_from_db()
                return False
        except SQLAlchemyError as e:
            logger.exception('Erro DB ao deletar consumo para %s na sessão %s: %s',
                             pront, self._session_id, e)
            self.db_session.rollback()
            return False
        except Exception as e:
            logger.exception('Erro inesperado ao deletar consumo para %s: %s', pront, e)
            self.db_session.rollback()
            return False

    def sync_consumption_state(
        self, target_served_snapshot: List[Tuple[str, str, str, str, str]]
    ):
        """
        Sincroniza o estado de consumo no banco de dados com um 'snapshot' alvo.
        Remove consumos do DB que não estão no snapshot e adiciona consumos
        do snapshot que não estão no DB para a sessão atual.

        Args:
            target_served_snapshot: Uma lista de tuplas, onde cada tupla representa
                                    um aluno que DEVE ser considerado como servido
                                    (pront, nome, turma, hora, prato_status).
                                    A hora pode ser usada para inserção.
        """
        if self._session_id is None:
            logger.error('Não é possível sincronizar estado de consumo: Nenhuma sessão ativa.')
            return
        logger.info('Iniciando sincronização de estado de consumo para sessão %s.',
                    self._session_id)

        # Conjunto de prontuários do snapshot alvo
        target_served_pronts: Set[str] = {item[0] for item in target_served_snapshot}
        # Cópia do conjunto de prontuários atualmente marcados como servidos (cache)
        current_served_pronts_cache: Set[str] = self._served_pronts.copy()

        # Alunos a remover do DB (estão no cache/DB atual mas não no snapshot)
        pronts_to_unmark = current_served_pronts_cache.difference(target_served_pronts)
        # Alunos a adicionar no DB (estão no snapshot mas não no cache/DB atual)
        pronts_to_mark = target_served_pronts.difference(current_served_pronts_cache)
        logger.debug('Sincronização necessária: Remover %s, Adicionar %s',
                     len(pronts_to_unmark), len(pronts_to_mark))
        try:
            # --- Remoção ---
            if pronts_to_unmark:
                logger.debug('Removendo %s alunos: %s', len(pronts_to_unmark), pronts_to_unmark)
                # Subquery para obter os IDs dos alunos a serem removidos
                student_ids_to_unmark_subquery = (
                    self.db_session.query(Student.id)
                    .filter(Student.pront.in_(pronts_to_unmark))
                    .scalar_subquery()
                )
                # Declaração de exclusão usando a subquery
                delete_stmt = delete(Consumption).where(
                    Consumption.session_id == self._session_id,
                    Consumption.student_id.in_(student_ids_to_unmark_subquery),
                )
                result_del = self.db_session.execute(delete_stmt)
                logger.info('%s registros de consumo removidos.', result_del.rowcount)

            # --- Adição ---
            if pronts_to_mark:
                logger.debug('Adicionando %s alunos: %s', len(pronts_to_mark), pronts_to_mark)
                consumption_data_to_insert = []
                # Cria um mapa do snapshot para buscar a hora do consumo original, se disponível
                snapshot_map = {item[0]: item for item in target_served_snapshot}

                for pront in pronts_to_mark:
                    # Obtém detalhes do aluno (ID, reserva ID)
                    student_id, reserve_id = self._get_or_find_student_details(pront)
                    if student_id is None:
                        logger.warning('Não é possível marcar %s como servido:'
                                       ' Aluno não encontrado. Pulando.', pront)
                        continue

                    # Obtém a hora do snapshot ou usa a hora atual como fallback
                    hora_consumo = (
                        snapshot_map[pront][3]
                        if pront in snapshot_map
                        else datetime.now().strftime("%H:%M:%S")
                    )

                    # Monta o dicionário para inserção
                    consumption_data_to_insert.append(
                        {
                            "student_id": student_id,
                            "session_id": self._session_id,
                            "consumption_time": hora_consumo,
                            "consumed_without_reservation": reserve_id is None,
                            "reserve_id": reserve_id,
                        }
                    )

                if consumption_data_to_insert:
                    logger.debug('Tentando inserção em lote de %s registros de consumo.',
                                 len(consumption_data_to_insert))
                    # Usa insert específico do SQLite para ignorar conflitos
                    # (registros já existentes). Isso evita erros se um registro foi criado
                    # entre o início da sync e a inserção.
                    insert_stmt = sqlite_insert(Consumption).values(
                        consumption_data_to_insert
                    )
                    # Ignora linhas que violariam a constraint UNIQUE(student_id, session_id)
                    insert_stmt = insert_stmt.on_conflict_do_nothing(
                        index_elements=[
                            "student_id",
                            "session_id",
                        ]  # Nome da constraint ou colunas
                    )
                    # rowcount pode ser 0 se todos já existiam
                    result_ins = self.db_session.execute(insert_stmt)
                    logger.info('Tentativa de inserção em lote concluída (linhas afetadas/'
                                'inseridas: %s).', result_ins.rowcount)

            # Commita as remoções e adições
            self.db_session.commit()
            # Atualiza o cache interno para refletir o estado do snapshot
            self._served_pronts = target_served_pronts
            # Limpa cache de elegíveis pois o estado mudou
            self._filtered_students_cache = []
            logger.info('Sincronização de estado de consumo concluída com sucesso para sessão %s.',
                        self._session_id)
        except SQLAlchemyError as e:
            logger.exception('Erro DB durante sincronização de estado de'
                             ' consumo para sessão %s: %s', self._session_id, e)
            self.db_session.rollback()
            # Recarrega o estado do DB em caso de falha para manter consistência
            self._load_served_pronts_from_db()
        except Exception as e:
            logger.exception('Erro inesperado durante sincronização de estado de consumo: %s', e)
            self.db_session.rollback()
            self._load_served_pronts_from_db()

    def get_eligible_students(self, not_served: bool = True) -> List[Dict[str, Any]]:
        """
        Retorna a lista cacheada de alunos elegíveis.
        Se o cache estiver vazio, dispara `filter_eligible_students` para preenchê-lo.

        Returns:
            A lista de dicionários dos alunos elegíveis. Pode estar vazia.
        """
        # Se o cache está vazio (primeira chamada ou após clear/sync)
        if not self._filtered_students_cache:
            logger.debug('Cache de alunos elegíveis vazio. Disparando filtro.')
            # Tenta preencher o cache. filter_eligible_students lida com erros internos.
            self.filter_eligible_students(not_served)
        # Retorna o conteúdo atual do cache (pode ser vazio se filtro falhou ou não encontrou nada)
        return self._filtered_students_cache

    def get_served_students_details(self) -> List[Tuple[str, str, str, str, str]]:
        """
        Consulta o banco de dados e retorna detalhes dos alunos servidos na sessão atual.
        Atualiza o cache `_served_pronts` como efeito colateral.

        Returns:
            Uma lista de tuplas, onde cada tupla contém:
            (pront, nome, turmas_concatenadas, hora_consumo, prato_ou_status_reserva).
            Retorna lista vazia se não houver alunos servidos ou ocorrer um erro.
        """
        if self._session_id is None:
            logger.warning('Não é possível obter detalhes de servidos: Nenhuma sessão ativa.')
            self._served_pronts = set()  # Garante que o cache está limpo
            return []
        logger.debug('Consultando DB para detalhes dos alunos servidos na sessão %s.',
                     self._session_id)
        try:
            # Aliases para clareza
            s, g, r, c = (
                aliased(Student),
                aliased(Group),
                aliased(Reserve),
                aliased(Consumption),
            )

            # Query para buscar detalhes dos alunos consumidos
            query = (
                self.db_session.query(
                    s.pront,  # Prontuário
                    s.nome,  # Nome
                    func.group_concat(g.nome.distinct()).label(
                        "turmas_concat"
                    ),  # Turmas (concatenadas)
                    c.consumption_time,  # Hora do consumo registrada
                    # Status: Prato da reserva se houver ID, senão texto padrão "Sem Reserva"
                    case(
                        (
                            c.reserve_id.isnot(None),
                            r.dish,
                        ),  # Condição: Se reserve_id não é nulo, usa r.dish
                        else_=UI_TEXTS.get(
                            "no_reservation_status", "Sem Reserva"
                        ),  # Senão, usa o texto padrão
                    ).label("prato_status"),
                )
                .select_from(c)
                .join(s, c.student_id == s.id)
                .join(s.groups.of_type(g))  # Junta Aluno com Turma (obrigatório)
                # Junta Consumo com Reserva (OPCIONAL, via reserve_id)
                .outerjoin(r, c.reserve_id == r.id)
                .filter(c.session_id == self._session_id)  # Filtra pela sessão atual
                # Agrupa para concatenar turmas e evitar duplicações por múltiplas turmas
                .group_by(
                    s.id, s.pront, s.nome, c.consumption_time, c.reserve_id, r.dish
                )
                # Ordena por hora de consumo descendente (mais recentes primeiro)
                .order_by(c.consumption_time.desc())
            )

            served_results = query.all()

            # Formata os resultados e atualiza o cache de prontuários servidos
            served_students_data = []
            current_served_pronts_db = set()  # Recalcula a partir do resultado da query
            for pront, nome, turmas_str, hora, prato_status in served_results:
                # Formata a string de turmas
                turmas_fmt = ",".join(
                    sorted(list(set(turmas_str.split(",") if turmas_str else [])))
                )
                served_students_data.append(
                    (pront, nome, turmas_fmt, hora, prato_status)
                )
                current_served_pronts_db.add(pront)

            # Atualiza o cache de prontuários servidos com o resultado fresco do DB
            self._served_pronts = current_served_pronts_db
            logger.info('%s detalhes de alunos servidos recuperados para sessão %s.',
                        len(served_students_data), self._session_id)
            return served_students_data

        except SQLAlchemyError as e:
            logger.exception('Erro DB ao recuperar detalhes de alunos servidos para sessão %s: %s',
                             self._session_id, e)
            self.db_session.rollback()
            self._served_pronts = set()  # Limpa cache em caso de erro
            return []
        except Exception as e:
            logger.exception('Erro inesperado ao recuperar detalhes de alunos servidos: %s', e)
            self._served_pronts = set()
            return []
