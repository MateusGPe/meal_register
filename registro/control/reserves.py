# ----------------------------------------------------------------------------
# File: registro/control/reserves.py (Refined Reserves Importer)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Fornece funções para importar dados de alunos e reservas de arquivos CSV
e para reservar lanches para todos os alunos.
"""

import csv
import logging
from typing import Dict, List, Set, Tuple, Optional, Any

# Importações SQLAlchemy e locais
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from registro.control.generic_crud import CRUD
from registro.control.utils import adjust_keys, load_csv_as_dict
from registro.model.tables import Group, Reserve, Student

logger = logging.getLogger(__name__)

# --- Funções de Importação CSV ---


def import_students_csv(student_crud: CRUD[Student], turma_crud: CRUD[Group],
                        csv_file_path: str) -> bool:
    """
    Importa dados de alunos de um CSV para o DB, incluindo turmas e associações.

    Lê pront, nome, turma. Cria Student e Group se não existirem.
    Associa Students a Groups. Usa bulk operations para eficiência.

    Args:
        student_crud (CRUD[Student]): CRUD para Alunos.
        turma_crud (CRUD[Group]): CRUD para Turmas (Grupos).
        csv_file_path (str): Caminho do arquivo CSV dos alunos.

    Returns:
        bool: True se sucesso, False se erro.
    """
    logger.info(f"Iniciando importação de alunos do CSV: {csv_file_path}")
    try:
        # Carrega dados brutos do CSV
        raw_student_data = load_csv_as_dict(csv_file_path)
        if raw_student_data is None:
            return False  # Erro na leitura já logado
        if not raw_student_data:
            logger.info("CSV de alunos vazio.")
            return True

        # --- Prepara dados para processamento ---
        existing_students_pronts = {s.pront for s in student_crud.read_all()}
        existing_groups_names = {g.nome for g in turma_crud.read_all()}

        students_to_create: List[Dict[str, Any]] = []
        groups_to_create: Set[str] = set()
        # (pront, group_name)
        student_group_associations: Set[Tuple[str, str]] = set()

        # --- Processa cada linha do CSV ---
        for i, row_raw in enumerate(raw_student_data):
            try:
                # Normaliza chaves e valores básicos
                row = adjust_keys(row_raw)  # Usa utils.adjust_keys
                pront = row.get('pront')
                nome = row.get('nome')
                group_name = row.get('turma')  # Chave 'turma' após adjust_keys

                # Valida dados essenciais da linha
                if not pront or not nome:
                    logger.warning(
                        f"Linha {i+2} CSV alunos ignorada: pront ou nome ausente. Linha: {row_raw}")
                    continue

                # Verifica se o aluno precisa ser criado
                if pront not in existing_students_pronts and pront not in {s['pront'] for s in students_to_create}:
                    # Prepara dados do aluno (remove 'turma' se existir, será associada depois)
                    # Apenas campos do Student
                    student_data = {k: v for k, v in row.items() if k in [
                        'pront', 'nome']}
                    students_to_create.append(student_data)

                # Verifica se a turma precisa ser criada e prepara associação
                if group_name:
                    student_group_associations.add((pront, group_name))
                    if group_name not in existing_groups_names:
                        # Adiciona ao set para criar depois
                        groups_to_create.add(group_name)

            except Exception as row_err:
                logger.error(
                    f"Erro processando linha {i+2} CSV alunos: {row_err}. Linha: {row_raw}", exc_info=True)
                # Decide se continua ou aborta (aqui continua)

        # --- Executa operações no DB ---
        try:
            # Cria novas turmas (se houver)
            if groups_to_create:
                logger.info(f"Criando {len(groups_to_create)} novas turmas...")
                if not turma_crud.bulk_create([{'nome': name} for name in groups_to_create]):
                    # Força rollback
                    raise RuntimeError("Falha ao criar novas turmas em massa.")
                logger.info("Novas turmas criadas.")
                # Atualiza lista de turmas existentes para associação
                existing_groups_names.update(groups_to_create)

            # Cria novos alunos (se houver)
            if students_to_create:
                logger.info(
                    f"Criando {len(students_to_create)} novos alunos...")
                if not student_crud.bulk_create(students_to_create):
                    # Força rollback
                    raise RuntimeError("Falha ao criar novos alunos em massa.")
                logger.info("Novos alunos criados.")
                # Atualiza lista de alunos existentes para associação
                existing_students_pronts.update(
                    s['pront'] for s in students_to_create)

            # Associa alunos a turmas (se houver associações)
            if student_group_associations:
                logger.info(
                    f"Associando {len(student_group_associations)} alunos a turmas...")
                if not _associate_students_with_groups(student_crud, turma_crud, student_group_associations,
                                                       existing_students_pronts, existing_groups_names):
                    # Força rollback
                    raise RuntimeError("Falha ao associar alunos a turmas.")
                logger.info("Associações aluno-turma concluídas.")

            logger.info(
                f"Importação de alunos do CSV '{csv_file_path}' concluída com sucesso.")
            return True

        except (SQLAlchemyError, RuntimeError) as db_err:
            logger.error(
                f"Erro de banco de dados durante importação de alunos: {db_err}", exc_info=True)
            student_crud.rollback()  # Garante rollback em caso de erro na fase de DB
            return False

    except Exception as e:  # Captura erros gerais (leitura CSV, etc.)
        logger.exception(
            f"Erro inesperado durante importação de alunos do CSV '{csv_file_path}': {e}")
        return False


def _associate_students_with_groups(student_crud: CRUD[Student], turma_crud: CRUD[Group],
                                    associations: Set[Tuple[str, str]],
                                    all_pronts: Set[str], all_group_names: Set[str]) -> bool:
    """
    Associa Students a Groups existentes baseado em um conjunto de tuplas (pront, group_name).
    Busca os objetos Student e Group no DB e atualiza a relação `student.groups`.

    Args:
        student_crud: CRUD para Alunos.
        turma_crud: CRUD para Turmas.
        associations: Conjunto de tuplas (pront, group_name) a associar.
        all_pronts: Conjunto de todos os pronts existentes (otimização).
        all_group_names: Conjunto de todos os nomes de grupos existentes (otimização).

    Returns:
        bool: True se sucesso, False se erro.
    """
    try:
        # Busca todos os alunos e grupos relevantes de uma vez para evitar N+1 queries
        pronts_in_associations = {pront for pront, _ in associations}
        groups_in_associations = {gname for _, gname in associations}

        students_map: Dict[str, Student] = {
            # Adapte se read_filtered não suportar __in
            s.pront: s for s in student_crud.read_filtered(pront__in=list(pronts_in_associations))
            # Alternativa: ler todos e filtrar: s for s in student_crud.read_all() if s.pront in pronts_in_associations
        }
        groups_map: Dict[str, Group] = {
            # Adapte se read_filtered não suportar __in
            g.nome: g for g in turma_crud.read_filtered(nome__in=list(groups_in_associations))
            # Alternativa: g for g in turma_crud.read_all() if g.nome in groups_in_associations
        }

        association_count = 0
        # Itera sobre as associações desejadas
        for pront, group_name in associations:
            student = students_map.get(pront)
            group = groups_map.get(group_name)

            if student and group:
                # Verifica se a associação já existe para evitar duplicatas na lista (SQLAlchemy pode lidar com isso, mas é mais explícito)
                if group not in student.groups:
                    student.groups.append(group)
                    logger.debug(f"Associando {pront} ao grupo '{group_name}'")
                    association_count += 1
                # else: logger.debug(f"Associação {pront} - '{group_name}' já existe.")
            elif not student:
                logger.warning(
                    f"Não foi possível associar: Aluno com pront {pront} não encontrado no DB.")
            elif not group:
                logger.warning(
                    f"Não foi possível associar: Grupo com nome '{group_name}' não encontrado no DB.")

        if association_count > 0:
            student_crud.commit()  # Comita todas as associações adicionadas
            logger.info(
                f"{association_count} novas associações aluno-grupo salvas.")
        else:
            logger.info("Nenhuma nova associação aluno-grupo a ser salva.")
        return True

    except SQLAlchemyError as e:
        logger.error(
            f"Erro de DB ao associar alunos a grupos: {e}", exc_info=True)
        student_crud.rollback()
        return False
    except Exception as e:  # Captura outros erros
        logger.exception(f"Erro inesperado ao associar alunos a grupos: {e}")
        student_crud.rollback()
        return False


def import_reserves_csv(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                        csv_file_path: str) -> bool:
    """
    Importa dados de reservas de um CSV para o banco de dados.

    Lê pront, nome, turma, dish, data do CSV. Associa a reserva ao Student
    correspondente (ignora reservas de alunos não encontrados).
    Usa bulk create para eficiência.

    Args:
        student_crud (CRUD[Student]): CRUD para Alunos.
        reserve_crud (CRUD[Reserve]): CRUD para Reservas.
        csv_file_path (str): Caminho do arquivo CSV das reservas.

    Returns:
        bool: True se sucesso, False se erro.
    """
    logger.info(f"Iniciando importação de reservas do CSV: {csv_file_path}")
    try:
        # Carrega dados brutos do CSV
        raw_reserve_data = load_csv_as_dict(csv_file_path)
        if raw_reserve_data is None:
            return False  # Erro na leitura já logado
        if not raw_reserve_data:
            logger.info("CSV de reservas vazio.")
            return True

        # --- Prepara dados para processamento ---
        # Busca todos os alunos de uma vez para mapeamento rápido pront -> id
        all_students_map: Dict[str, int] = {
            s.pront: s.id for s in student_crud.read_all()}
        if not all_students_map:
            logger.error(
                "Nenhum aluno encontrado no banco de dados. Impossível importar reservas.")
            return False

        reserves_to_insert: List[Dict[str, Any]] = []

        # --- Processa cada linha do CSV ---
        for i, row_raw in enumerate(raw_reserve_data):
            try:
                row = adjust_keys(row_raw)  # Normaliza chaves
                pront = row.get('pront')
                data = row.get('data')
                dish = row.get('dish')  # Pode ser None/vazio
                # Ignora 'turma' e 'nome' aqui, foca na reserva
                # Define 'snacks' como False (importação padrão é almoço/jantar?)
                # Define 'canceled' como False (assume que CSV são reservas válidas)
                # Ajuste essas lógicas se o CSV tiver essas informações

                # Valida dados essenciais
                if not pront or not data:
                    logger.warning(
                        f"Linha {i+2} CSV reservas ignorada: pront ou data ausente. Linha: {row_raw}")
                    continue

                # Verifica se o aluno da reserva existe no DB
                student_id = all_students_map.get(pront)
                if student_id:
                    reserve_data = {
                        'student_id': student_id,
                        'data': data,
                        'dish': dish or 'Não especificado',  # Valor padrão se vazio
                        'snacks': False,  # Assumido como não-lanche
                        # Pega do CSV se existir, senão False
                        'canceled': row.get('canceled', False)
                    }
                    reserves_to_insert.append(reserve_data)
                else:
                    logger.warning(
                        f"Linha {i+2} CSV reservas ignorada: Aluno pront '{pront}' não encontrado no DB.")

            except Exception as row_err:
                logger.error(
                    f"Erro processando linha {i+2} CSV reservas: {row_err}. Linha: {row_raw}", exc_info=True)

        # --- Insere reservas no DB ---
        if reserves_to_insert:
            logger.info(
                f"Tentando inserir {len(reserves_to_insert)} reservas processadas do CSV '{csv_file_path}'.")
            # Usa bulk_create para inserir. A constraint Unique (_pront_uc) no modelo Reserve
            # com `sqlite_on_conflict="IGNORE"` deve lidar com duplicatas no SQLite.
            # Para outros DBs, pode ser necessário tratamento adicional ou `ON CONFLICT DO NOTHING`.
            if reserve_crud.bulk_create(reserves_to_insert):
                logger.info(
                    f"Importação de reservas do CSV '{csv_file_path}' concluída com sucesso.")
                return True
            else:
                logger.error(
                    f"Falha no bulk_create durante importação de reservas do CSV '{csv_file_path}'.")
                return False  # Erro já logado pelo bulk_create
        else:
            logger.info(
                f"Nenhuma reserva válida para importar do CSV '{csv_file_path}'.")
            return True  # Sucesso, mas nada a importar

    except Exception as e:  # Captura erros gerais
        logger.exception(
            f"Erro inesperado durante importação de reservas do CSV '{csv_file_path}': {e}")
        return False

# --- Função para Reservar Lanches ---


def reserve_snacks(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                   data: str, dish: str) -> bool:
    """
    Cria reservas de lanche para *todos* os alunos existentes na data especificada.

    Args:
        student_crud (CRUD[Student]): CRUD para Alunos.
        reserve_crud (CRUD[Reserve]): CRUD para Reservas.
        data (str): Data da reserva ('YYYY-MM-DD').
        dish (str): Nome/descrição do lanche.

    Returns:
        bool: True se sucesso, False se erro.
    """
    logger.info(
        f"Iniciando reserva de lanche '{dish}' para data '{data}' para todos os alunos.")
    try:
        all_students = student_crud.read_all()
        if not all_students:
            logger.warning(
                "Nenhum aluno encontrado no DB para reservar lanches.")
            return True  # Sucesso, mas nada a fazer

        reserves_to_insert = [{
            'student_id': student.id,
            'data': data,
            'dish': dish,
            'snacks': True,  # Marca como lanche
            'canceled': False
        } for student in all_students]

        logger.info(
            f"Preparando {len(reserves_to_insert)} reservas de lanche para inserção...")
        # Usa bulk_create. Duplicatas serão ignoradas pela constraint `_pront_uc` no SQLite.
        if reserve_crud.bulk_create(reserves_to_insert):
            logger.info(
                f"Reservas de lanche para '{data}' criadas/ignoradas com sucesso.")
            return True
        else:
            logger.error(
                f"Falha no bulk_create ao reservar lanches para '{data}'.")
            return False  # Erro já logado

    except Exception as e:  # Captura erros gerais
        logger.exception(
            f"Erro inesperado ao reservar lanches para '{data}': {e}")
        return False
