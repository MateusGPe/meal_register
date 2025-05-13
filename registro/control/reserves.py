# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# File: registro/control/reserves.py (Importador de Reservas e Alunos)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Funções para importar dados de alunos e reservas a partir de arquivos CSV
para o banco de dados, gerenciando a criação de novos registros e associações.
Inclui lógica de busca por similaridade (fuzzy matching) para reservas órfãs.
"""
from datetime import datetime
import logging
from typing import Dict, List, Sequence, Set, Tuple, Optional, Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as SQLASession
# Importa fuzzywuzzy para busca por similaridade
try:
    from fuzzywuzzy import fuzz
    FUZZYWUZZY_AVAILABLE = True
except ImportError:
    FUZZYWUZZY_AVAILABLE = False
    # Define um objeto fuzz dummy se a biblioteca não estiver instalada

    class DummyFuzz:
        def ratio(self, _, __):
            return 0

        def token_set_ratio(self, _, __):
            return 0
    fuzz = DummyFuzz()

# Importações locais
from registro.control.constants import UI_TEXTS, PRONTUARIO_CLEANUP_REGEX
from registro.control.generic_crud import CRUD
from registro.control.utils import adjust_keys, load_csv_as_dict
from registro.model.tables import Group, Reserve, Student

logger = logging.getLogger(__name__)

# --- Constantes para Fuzzy Matching ---
# Limiar de similaridade para considerar um match fuzzy válido (0-100)
FUZZY_MATCH_THRESHOLD = 85
# Pesos para combinar scores de nome e prontuário
NAME_WEIGHT = 0.60
PRONT_WEIGHT = 0.40


# ============================================================================
# Importação de Alunos
# ============================================================================

def _process_student_csv_rows(
    raw_student_data: List[Dict[str, str]],
    existing_students_pronts: Set[str],
    existing_groups_names: Set[str]
) -> Tuple[List[Dict[str, Any]], Set[str], Set[Tuple[str, str]], Set[str]]:
    """
    Processa as linhas do CSV de alunos para identificar novos alunos,
    novos grupos e associações necessárias.

    Args:
        raw_student_data: Lista de dicionários lida do CSV.
        existing_students_pronts: Conjunto de prontuários existentes no DB.
        existing_groups_names: Conjunto de nomes de grupos existentes no DB.

    Returns:
        Uma tupla contendo:
        - students_to_create: Lista de dicts para novos alunos.
        - groups_to_create: Conjunto de nomes de novos grupos.
        - student_group_associations: Conjunto de tuplas (pront, group_name).
        - pronts_in_current_batch: Conjunto de prontuários adicionados neste lote.
    """
    students_to_create: List[Dict[str, Any]] = []
    groups_to_create: Set[str] = set()
    student_group_associations: Set[Tuple[str, str]] = set()
    pronts_in_current_batch: Set[str] = set()

    for i, row_raw in enumerate(raw_student_data):
        try:
            row = adjust_keys(row_raw)
            pront = row.get('pront')
            nome = row.get('nome')
            group_name = row.get('turma')

            if not pront or not nome:
                logger.warning(
                    "Pulando linha %d do CSV de alunos: 'pront' ou 'nome' ausente. Dados: %s",
                    i + 2, row_raw)
                continue

            # Verifica se o aluno é novo neste lote e no DB
            if pront not in existing_students_pronts and pront not in pronts_in_current_batch:
                student_data = {k: v for k, v in row.items() if k in [
                    'pront', 'nome']}
                students_to_create.append(student_data)
                pronts_in_current_batch.add(pront)

            # Verifica se o grupo é novo e adiciona associação
            if group_name:
                student_group_associations.add((pront, group_name))
                if group_name not in existing_groups_names and group_name not in groups_to_create:
                    groups_to_create.add(group_name)

        except Exception as row_err:
            logger.error("Erro ao processar linha %d do CSV de alunos: %s. Dados: %s",
                         i + 2, row_err, row_raw, exc_info=True)

    return students_to_create, groups_to_create, student_group_associations, pronts_in_current_batch


def _perform_student_db_operations(
    student_crud: CRUD[Student],
    group_crud: CRUD[Group],
    students_to_create: List[Dict[str, Any]],
    groups_to_create: Set[str],
    student_group_associations: Set[Tuple[str, str]]
) -> bool:
    """
    Executa as operações de banco de dados para criar grupos, alunos e associações.

    Args:
        student_crud: Instância CRUD para Student.
        group_crud: Instância CRUD para Group.
        students_to_create: Lista de dicts para novos alunos.
        groups_to_create: Conjunto de nomes de novos grupos.
        student_group_associations: Conjunto de tuplas (pront, group_name).

    Returns:
        True se todas as operações foram bem-sucedidas, False caso contrário.
    """
    db_session = student_crud.get_session()
    try:
        # 1. Cria Grupos Novos
        if groups_to_create:
            logger.info("Criando %d novos grupos...", len(groups_to_create))
            group_data = [{'nome': name} for name in groups_to_create]
            if not group_crud.bulk_create(group_data):
                raise RuntimeError("Falha ao criar novos grupos em lote.")
            logger.info("Novos grupos criados com sucesso.")

        # 2. Cria Alunos Novos
        if students_to_create:
            logger.info("Criando %d novos alunos...", len(students_to_create))
            if not student_crud.bulk_create(students_to_create):
                raise RuntimeError("Falha ao criar novos alunos em lote.")
            logger.info("Novos alunos criados com sucesso.")

        # 3. Associa Alunos a Grupos
        if student_group_associations:
            logger.info("Associando %d links aluno-grupo...",
                        len(student_group_associations))
            if not _associate_students_with_groups_refactored(
                    db_session, student_crud, group_crud, student_group_associations):
                raise RuntimeError("Falha ao associar alunos aos grupos.")
            logger.info("Associações aluno-grupo concluídas.")

        return True

    except (SQLAlchemyError, RuntimeError) as db_err:
        logger.error(
            "Erro de banco de dados ou falha durante operações"
            " de importação de alunos: %s. Revertendo.",
            db_err, exc_info=True)
        db_session.rollback()
        return False


def import_students_csv(student_crud: CRUD[Student], group_crud: CRUD[Group],
                        csv_file_path: str) -> bool:
    """
    Orquestra a importação de dados de alunos de um arquivo CSV.

    Carrega o CSV, processa as linhas para identificar dados novos e
    executa as operações necessárias no banco de dados.

    Args:
        student_crud: Instância CRUD para o modelo Student.
        group_crud: Instância CRUD para o modelo Group.
        csv_file_path: Caminho para o arquivo CSV de alunos.

    Returns:
        True se a importação completa for bem-sucedida, False caso contrário.
    """
    logger.info("Iniciando importação de alunos do CSV: %s", csv_file_path)
    try:
        raw_student_data = load_csv_as_dict(csv_file_path)
        if raw_student_data is None:
            logger.error(
                "Falha ao carregar dados de alunos de %s.", csv_file_path)
            return False
        if not raw_student_data:
            logger.info(
                "Arquivo CSV de alunos '%s' está vazio. Nada a importar.", csv_file_path)
            return True

        # Coleta dados existentes do DB
        existing_students_pronts: Set[str] = {
            s.pront for s in student_crud.read_all()}
        existing_groups_names: Set[str] = {
            g.nome for g in group_crud.read_all()}
        logger.debug("Encontrados %d alunos e %d grupos existentes no DB.",
                     len(existing_students_pronts), len(existing_groups_names))

        # Processa as linhas do CSV
        (students_to_create, groups_to_create, student_group_associations, _
         ) = _process_student_csv_rows(raw_student_data, existing_students_pronts,
                                       existing_groups_names)

        # Executa operações no DB
        if not _perform_student_db_operations(student_crud, group_crud, students_to_create,
                                              groups_to_create, student_group_associations):
            return False  # Erro já logado e rollback feito em _perform_student_db_operations

        logger.info(
            "Importação de alunos do CSV '%s' concluída com sucesso.", csv_file_path)
        return True

    except Exception as e:
        logger.exception(
            "Erro inesperado durante importação de alunos do CSV '%s': %s", csv_file_path, e)
        # Tenta garantir rollback em caso de erro não previsto
        try:
            student_crud.rollback()
        except Exception:
            pass
        return False


# ============================================================================
# Associação Aluno-Grupo (Helper)
# ============================================================================

def _associate_students_with_groups_refactored(db_session: SQLASession,
                                               student_crud: CRUD[Student], group_crud: CRUD[Group],
                                               associations: Set[Tuple[str, str]]) -> bool:
    """
    Associa alunos existentes aos seus grupos (turmas) correspondentes.
    (Função mantida da iteração anterior, com logs ajustados)

    Args:
        db_session: A sessão SQLAlchemy ativa.
        student_crud: Instância CRUD para Student.
        group_crud: Instância CRUD para Group.
        associations: Um conjunto de tuplas `(prontuario_aluno, nome_grupo)`.

    Returns:
        True se as associações foram processadas com sucesso, False se ocorrer um erro.
    """
    if not associations:
        logger.debug("Nenhuma associação aluno-grupo para processar.")
        return True
    try:
        pronts_to_fetch = {pront for pront, _ in associations}
        group_names_to_fetch = {gname for _, gname in associations}
        student_map: Dict[str, Student] = {
            s.pront: s for s in student_crud.read_filtered(pront__in=list(pronts_to_fetch))}
        group_map: Dict[str, Group] = {g.nome: g for g in group_crud.read_filtered(
            nome__in=list(group_names_to_fetch))}
        logger.debug("Buscados %d alunos e %d grupos relevantes para associação.", len(
            student_map), len(group_map))

        association_count = 0
        for pront, group_name in associations:
            student = student_map.get(pront)
            group = group_map.get(group_name)
            if student and group:
                if group not in student.groups:
                    student.groups.append(group)
                    association_count += 1
                    logger.debug(
                        "Associando aluno %s ao grupo %s.", pront, group_name)
            elif not student:
                logger.warning(
                    "Não é possível associar: Aluno com prontuário '%s'"
                    " não encontrado no mapa buscado.", pront)
            elif not group:
                logger.warning(
                    "Não é possível associar: Grupo com nome '%s' não encontrado no mapa buscado.",
                    group_name)

        if association_count > 0:
            db_session.commit()
            logger.info(
                "%d commits realizados para novas associações aluno-grupo.", association_count)
        else:
            logger.info("Nenhuma nova associação aluno-grupo foi necessária.")
        return True
    except SQLAlchemyError as e:
        logger.error(
            "Erro de banco de dados durante associação aluno-grupo: %s. Revertendo.",
            e, exc_info=True)
        db_session.rollback()
        return False
    except Exception as e:
        logger.exception("Erro inesperado ao associar alunos a grupos: %s", e)
        db_session.rollback()
        return False


# ============================================================================
# Importação de Reservas
# ============================================================================

def _find_student_for_reserve(
    pront_csv: str,
    nome_csv: str,
    all_students_map: Dict[str, int],
    all_students_records: Sequence[Student]
) -> Tuple[Optional[int], str]:
    """
    Tenta encontrar o ID do aluno para uma reserva, primeiro por match exato
    de prontuário, depois por similaridade (fuzzy).

    Args:
        pront_csv: Prontuário lido do CSV.
        nome_csv: Nome lido do CSV.
        all_students_map: Mapa {pront: student_id} para busca exata.
        all_students_records: Lista de todos os objetos Student do DB para busca fuzzy.

    Returns:
        Uma tupla (student_id, match_type), onde student_id é o ID encontrado
        ou None, e match_type é "Exato", "Fuzzy", ou "Nenhum".
    """
    # 1. Tentativa de Match Exato
    student_id = all_students_map.get(pront_csv)
    if student_id:
        return student_id, "Exato"

    # 2. Tentativa de Match Fuzzy (somente se biblioteca disponível e nome existe)
    if not FUZZYWUZZY_AVAILABLE:
        logger.warning(
            "Biblioteca 'fuzzywuzzy' não disponível. Busca por similaridade desativada.")
        return None, "Nenhum"
    if not nome_csv:
        logger.debug(
            "Prontuário exato '%s' não encontrado e nome ausente no CSV."
            " Impossível buscar por similaridade.", pront_csv)
        return None, "Nenhum"

    logger.debug(
        "Prontuário exato '%s' não encontrado. Tentando busca por similaridade (Nome: '%s')...",
        pront_csv, nome_csv)
    best_match_student: Optional[Student] = None
    highest_score = 0
    pront_csv_cleaned = PRONTUARIO_CLEANUP_REGEX.sub("", pront_csv).upper()
    nome_csv_lower = nome_csv.lower()

    for db_student in all_students_records:
        pront_db_cleaned = PRONTUARIO_CLEANUP_REGEX.sub(
            "", db_student.pront).upper()
        nome_db_lower = db_student.nome.lower()
        pront_score = fuzz.ratio(pront_csv_cleaned, pront_db_cleaned)
        name_score = fuzz.token_set_ratio(nome_csv_lower, nome_db_lower)
        combined_score = (name_score * NAME_WEIGHT) + \
            (pront_score * PRONT_WEIGHT)

        if combined_score > highest_score:
            highest_score = combined_score
            best_match_student = db_student

    if highest_score >= FUZZY_MATCH_THRESHOLD and best_match_student:
        student_id = best_match_student.id
        logger.info(
            "Match por similaridade encontrado (CSV: %s/%s): Aluno DB %s/%s"
            " (ID: %d) com score %.2f", pront_csv, nome_csv,
            best_match_student.pront, best_match_student.nome,
            student_id, highest_score)
        return student_id, "Fuzzy"
    else:
        logger.warning("Nenhum match por similaridade encontrado (acima de %d)"
                       " para CSV Pront/Nome: %s/%s. Melhor score: %.2f.",
                       FUZZY_MATCH_THRESHOLD, pront_csv, nome_csv, highest_score)
        return None, "Nenhum"


def _process_reserve_csv_row(
    row_raw: Dict[str, str],
    line_number: int,
    all_students_map: Dict[str, int],
    all_students_records: Sequence[Student]
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Processa uma única linha do CSV de reservas.

    Args:
        row_raw: Dicionário bruto da linha do CSV.
        line_number: O número da linha no arquivo (para logging).
        all_students_map: Mapa {pront: student_id}.
        all_students_records: Lista de todos os Student do DB.

    Returns:
        Uma tupla: (dados_reserva, status).
        dados_reserva: Dict pronto para inserção se sucesso, None caso contrário.
        status: "OK_Exato", "OK_Fuzzy", "Pular_DadosInvalidos", "Pular_AlunoNaoEncontrado", "Erro".
    """
    try:
        row = adjust_keys(row_raw)
        pront_csv = row.get('pront')
        nome_csv = row.get('nome', '')
        data_csv = datetime.strptime(str(row.get('data')), "%d/%m/%Y").strftime("%Y-%m-%d")
        dish_csv = row.get('dish')
        is_snack = str(row.get('snacks', 'false')).lower() in [
            'true', '1', 'sim', 'yes', 'lanche']
        is_canceled = str(row.get('canceled', 'false')).lower() in [
            'true', '1', 'sim', 'yes', 'cancelado']

        if not pront_csv or not data_csv:
            logger.warning(
                "Pulando linha %d do CSV de reservas: 'pront' ou 'data' ausente. Dados: %s",
                line_number, row_raw)
            return None, "Pular_DadosInvalidos"

        # Encontra o ID do aluno (exato ou fuzzy)
        student_id, match_type = _find_student_for_reserve(
            pront_csv, nome_csv, all_students_map, all_students_records
        )

        if student_id:
            reserve_data = {
                'student_id': student_id,
                'data': data_csv,
                'dish': dish_csv or UI_TEXTS.get("default_snack_name", "Não Especificado"),
                'snacks': is_snack,
                'canceled': is_canceled,
            }
            status = f"OK_{match_type}"
            return reserve_data, status
        else:
            # Se _find_student_for_reserve não achou (nem exato, nem fuzzy acima do threshold)
            return None, "Pular_AlunoNaoEncontrado"

    except Exception as row_err:
        logger.error("Erro ao processar linha %d do CSV de reservas: %s. Dados: %s",
                     line_number, row_err, row_raw, exc_info=True)
        return None, "Erro"


def import_reserves_csv(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                        csv_file_path: str) -> bool:
    """
    Orquestra a importação de dados de reservas de um arquivo CSV.

    Processa cada linha, tentando encontrar o aluno correspondente (exato ou
    fuzzy) e insere as reservas válidas em lote.

    Args:
        student_crud: Instância CRUD para Student.
        reserve_crud: Instância CRUD para Reserve.
        csv_file_path: Caminho para o arquivo CSV de reservas.

    Returns:
        True se a importação for bem-sucedida (ou arquivo vazio), False caso contrário.
    """
    logger.info("Iniciando importação de reservas do CSV: %s", csv_file_path)
    if not FUZZYWUZZY_AVAILABLE:
        logger.warning(
            "Biblioteca 'fuzzywuzzy' não encontrada."
            " A busca por similaridade para reservas órfãs estará desativada.")

    try:
        raw_reserve_data = load_csv_as_dict(csv_file_path)
        if raw_reserve_data is None:
            return False
        if not raw_reserve_data:
            logger.info("Arquivo CSV de reservas '%s' está vazio.",
                        csv_file_path)
            return True

        all_students_records: Sequence[Student] = student_crud.read_all()
        if not all_students_records:
            logger.error(
                "Não é possível importar reservas: Nenhum aluno no DB.")
            return False
        all_students_map: Dict[str, int] = {
            s.pront: s.id for s in all_students_records}
        logger.debug("Carregados %d registros de alunos para lookup.",
                     len(all_students_records))

        reserves_to_insert: List[Dict[str, Any]] = []
        skipped_count = 0
        error_count = 0
        fuzzy_match_count = 0

        for i, row_raw in enumerate(raw_reserve_data):
            reserve_data, status = _process_reserve_csv_row(
                row_raw, i + 2, all_students_map, all_students_records
            )
            if reserve_data:
                reserves_to_insert.append(reserve_data)
                if status == "OK_Fuzzy":
                    fuzzy_match_count += 1
            elif status == "Erro":
                error_count += 1
            elif status.startswith("Pular"):
                skipped_count += 1
            # Nenhuma ação para "OK_Exato" além de adicionar à lista

        logger.info(
            "Processamento CSV concluído. %d reservas para inserir (%d via similaridade),"
            " %d linhas puladas, %d erros.", len(
                reserves_to_insert), fuzzy_match_count, skipped_count,
            error_count)

        if reserves_to_insert:
            logger.info("Tentando inserir em lote %d reservas processadas de '%s'.",
                        len(reserves_to_insert), csv_file_path)
            success = reserve_crud.bulk_create(reserves_to_insert)
            if success:
                logger.info(
                    "Inserção em lote de reservas de '%s' concluída (duplicatas ignoradas).",
                    csv_file_path)
                return True
            else:
                logger.error("Falha na inserção em lote de reservas.")
                reserve_crud.rollback()
                return False
        else:
            logger.info(
                "Nenhuma reserva válida encontrada/processada para importar de '%s'.",
                csv_file_path)
            return True

    except Exception as e:
        logger.exception(
            "Erro inesperado durante importação de reservas do CSV '%s': %s", csv_file_path, e)
        try:
            reserve_crud.rollback()
        except Exception:
            pass
        return False


# ============================================================================
# Reserva de Lanches em Lote (Helper)
# ============================================================================

def reserve_snacks_for_all(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                           date: str, dish: str) -> bool:
    """
    Cria automaticamente reservas de lanche para TODOS os alunos cadastrados.
    (Função mantida da iteração anterior, com logs ajustados)

    Args:
        student_crud: Instância CRUD para Student.
        reserve_crud: Instância CRUD para Reserve.
        date: A data para a qual criar as reservas (formato YYYY-MM-DD).
        dish: O nome do lanche a ser registrado na reserva.

    Returns:
        True se a operação foi bem-sucedida, False caso contrário.
    """
    logger.info(
        "Iniciando reserva de lanche em lote para o prato '%s' na data '%s' para"
        " todos os alunos.", dish, date)
    try:
        all_students = student_crud.read_all()
        if not all_students:
            logger.warning(
                "Nenhum aluno encontrado no banco de dados para reservar lanches.")
            return True

        reserves_to_insert = [{
            'student_id': student.id, 'data': date, 'dish': dish,
            'snacks': True, 'canceled': False
        } for student in all_students]
        logger.info("Preparando %d reservas de lanche para inserção em lote...", len(
            reserves_to_insert))

        success = reserve_crud.bulk_create(reserves_to_insert)
        if success:
            logger.info(
                "Reservas de lanche em lote para '%s' processadas com sucesso"
                " (novas inseridas, duplicatas ignoradas).", date)
            return True
        else:
            logger.error(
                "Falha na inserção em lote durante reserva de lanches para '%s'.", date)
            reserve_crud.rollback()
            return False
    except SQLAlchemyError as e:
        logger.error(
            "Erro de banco de dados durante reserva de lanches em lote para '%s': %s. Revertendo.",
            date, e, exc_info=True)
        reserve_crud.rollback()
        return False
    except Exception as e:
        logger.exception(
            "Erro inesperado ao reservar lanches para '%s': %s", date, e)
        reserve_crud.rollback()
        return False
