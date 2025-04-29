# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# File: registro/control/reserves.py (Importador de Reservas e Alunos)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Funções para importar dados de alunos e reservas a partir de arquivos CSV
para o banco de dados, gerenciando a criação de novos registros e associações.
"""
import logging
from typing import Dict, List, Set, Tuple, Optional, Any

from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session as SQLASession

# Importações locais
from registro.control.generic_crud import CRUD
from registro.control.utils import adjust_keys, load_csv_as_dict  # Assumindo utils.py refatorado
from registro.model.tables import Group, Reserve, Student  # Assumindo models.py existe

logger = logging.getLogger(__name__)


def import_students_csv(student_crud: CRUD[Student], group_crud: CRUD[Group],
                        csv_file_path: str) -> bool:
    """
    Importa dados de alunos de um arquivo CSV para o banco de dados.

    Cria novos alunos e grupos (turmas) se não existirem. Associa os alunos
    aos seus respectivos grupos. Utiliza operações em lote para eficiência.

    Args:
        student_crud: Instância CRUD para o modelo Student.
        group_crud: Instância CRUD para o modelo Group.
        csv_file_path: Caminho para o arquivo CSV de alunos. O CSV deve conter
                       pelo menos as colunas 'pront' (ou equivalente) e 'nome'.
                       Uma coluna 'turma' é usada para associação.

    Returns:
        True se a importação for bem-sucedida (ou arquivo vazio), False caso contrário.
    """
    logger.info(f"Iniciando importação de alunos do CSV: {csv_file_path}")
    try:
        # Carrega os dados brutos do CSV
        raw_student_data = load_csv_as_dict(csv_file_path)
        if raw_student_data is None:
            logger.error(f"Falha ao carregar dados de alunos de {csv_file_path}.")
            return False
        if not raw_student_data:
            logger.info(f"Arquivo CSV de alunos '{csv_file_path}' está vazio. Nada a importar.")
            return True

        # --- Coleta de Dados Existentes ---
        # Obtém prontuários e nomes de grupos já existentes no DB para evitar duplicação
        existing_students_pronts: Set[str] = {s.pront for s in student_crud.read_all()}
        existing_groups_names: Set[str] = {g.nome for g in group_crud.read_all()}
        logger.debug(
            f"Encontrados {len(existing_students_pronts)} alunos e {len(existing_groups_names)} grupos existentes no DB.")

        # --- Processamento dos Dados do CSV ---
        students_to_create: List[Dict[str, Any]] = []
        groups_to_create: Set[str] = set()
        # Armazena associações (pront, nome_grupo) a serem feitas
        student_group_associations: Set[Tuple[str, str]] = set()
        # Conjunto para rastrear prontuários já adicionados na lista `students_to_create`
        # e evitar tentar criar o mesmo aluno múltiplas vezes dentro deste lote
        pronts_in_current_batch: Set[str] = set()

        for i, row_raw in enumerate(raw_student_data):
            try:
                # Normaliza chaves e processa valores da linha
                row = adjust_keys(row_raw)
                pront = row.get('pront')
                nome = row.get('nome')
                group_name = row.get('turma')

                # Validação básica da linha
                if not pront or not nome:
                    logger.warning(f"Pulando linha {i+2} do CSV de alunos: 'pront' ou 'nome' ausente. Dados: {row_raw}")
                    continue

                # --- Preparação para Criação de Aluno ---
                # Verifica se o aluno é novo (não existe no DB e não foi adicionado neste lote)
                if pront not in existing_students_pronts and pront not in pronts_in_current_batch:
                    # Seleciona apenas os campos relevantes para a tabela Student
                    student_data = {k: v for k, v in row.items() if k in ['pront', 'nome']}
                    students_to_create.append(student_data)
                    pronts_in_current_batch.add(pront)  # Marca como adicionado neste lote

                # --- Preparação para Criação/Associação de Grupo ---
                if group_name:
                    # Adiciona a associação desejada
                    student_group_associations.add((pront, group_name))
                    # Se o grupo é novo (não existe no DB e não foi marcado para criação)
                    if group_name not in existing_groups_names and group_name not in groups_to_create:
                        groups_to_create.add(group_name)

            except Exception as row_err:
                logger.error(
                    f"Erro ao processar linha {i+2} do CSV de alunos: {row_err}. Dados: {row_raw}", exc_info=True)

        # --- Operações no Banco de Dados ---
        db_session = student_crud.get_session()
        try:
            # 1. Cria Grupos Novos (se houver)
            if groups_to_create:
                logger.info(f"Criando {len(groups_to_create)} novos grupos...")
                group_data = [{'nome': name} for name in groups_to_create]
                if not group_crud.bulk_create(group_data):
                    # bulk_create já faz rollback em caso de erro
                    raise RuntimeError("Falha ao criar novos grupos em lote.")
                logger.info("Novos grupos criados com sucesso.")
                # Atualiza o conjunto de nomes existentes para a próxima etapa
                existing_groups_names.update(groups_to_create)

            # 2. Cria Alunos Novos (se houver)
            if students_to_create:
                logger.info(f"Criando {len(students_to_create)} novos alunos...")
                if not student_crud.bulk_create(students_to_create):
                    # bulk_create já faz rollback
                    raise RuntimeError("Falha ao criar novos alunos em lote.")
                logger.info("Novos alunos criados com sucesso.")
                # Atualiza o conjunto de prontuários existentes
                existing_students_pronts.update(s['pront'] for s in students_to_create)

            # 3. Associa Alunos a Grupos (se houver associações)
            if student_group_associations:
                logger.info(f"Associando {len(student_group_associations)} links aluno-grupo...")
                # Usa a função refatorada para fazer as associações
                if not _associate_students_with_groups_refactored(db_session, student_crud, group_crud,
                                                                  student_group_associations):
                    # A função de associação já faz rollback se necessário
                    raise RuntimeError("Falha ao associar alunos aos grupos.")
                logger.info("Associações aluno-grupo concluídas.")

            logger.info(f"Importação de alunos do CSV '{csv_file_path}' concluída com sucesso.")
            return True

        except (SQLAlchemyError, RuntimeError) as db_err:
            # Captura erros do DB ou exceções levantadas nas etapas anteriores
            logger.error(f"Erro de banco de dados ou falha durante importação de alunos: {db_err}. "
                         "Transação será revertida (rollback).", exc_info=True)
            # Garante o rollback caso não tenha sido feito internamente
            db_session.rollback()
            return False
    except Exception as e:
        logger.exception(f"Erro inesperado durante importação de alunos do CSV '{csv_file_path}': {e}")
        return False


def _associate_students_with_groups_refactored(db_session: SQLASession,
                                               student_crud: CRUD[Student], group_crud: CRUD[Group],
                                               associations: Set[Tuple[str, str]]) -> bool:
    """
    Associa alunos existentes aos seus grupos (turmas) correspondentes.
    Carrega alunos e grupos relevantes do banco de dados e adiciona as
    associações na sessão SQLAlchemy.

    Args:
        db_session: A sessão SQLAlchemy ativa.
        student_crud: Instância CRUD para Student.
        group_crud: Instância CRUD para Group.
        associations: Um conjunto de tuplas `(prontuario_aluno, nome_grupo)`.

    Returns:
        True se as associações foram processadas com sucesso (mesmo que nenhuma
        nova associação tenha sido necessária), False se ocorrer um erro de banco
        de dados.
    """
    if not associations:
        logger.debug("Nenhuma associação aluno-grupo para processar.")
        return True

    try:
        # --- Busca Eficiente de Dados ---
        # Obtém todos os prontuários e nomes de grupo únicos das associações pedidas
        pronts_to_fetch = {pront for pront, _ in associations}
        group_names_to_fetch = {gname for _, gname in associations}

        # Busca todos os alunos e grupos relevantes de uma vez do DB
        # Filtra usando 'in_' para eficiência
        student_map: Dict[str, Student] = {
            s.pront: s for s in student_crud.read_filtered(pront__in=pronts_to_fetch)
        }
        group_map: Dict[str, Group] = {
            g.nome: g for g in group_crud.read_filtered(nome__in=group_names_to_fetch)
        }
        logger.debug(
            f"Buscados {len(student_map)} alunos e {len(group_map)} grupos relevantes para associação.")

        # --- Realiza as Associações na Sessão ---
        association_count = 0
        # Itera sobre as associações solicitadas
        for pront, group_name in associations:
            student = student_map.get(pront)
            group = group_map.get(group_name)

            if student and group:
                # Verifica se a associação já existe antes de adicioná-la
                # Acessar student.groups pode carregar a relação se for lazy='select'
                # Para lazy='dynamic', a checagem seria diferente (ex: query .filter().count())
                # Assumindo lazy='select' ou similar onde a lista é carregada.
                if group not in student.groups:
                    student.groups.append(group)  # Adiciona a associação na sessão
                    association_count += 1
                    logger.debug(f"Associando aluno {pront} ao grupo {group_name}.")
                # else: # Associação já existe, não faz nada
                #    logger.debug(f"Associação entre {pront} e {group_name} já existe.")
            elif not student:
                logger.warning(
                    f"Não é possível associar: Aluno com prontuário '{pront}' não encontrado no mapa buscado.")
            elif not group:
                logger.warning(
                    f"Não é possível associar: Grupo com nome '{group_name}' não encontrado no mapa buscado.")

        # --- Commit das Associações ---
        if association_count > 0:
            # Commita apenas se novas associações foram adicionadas
            db_session.commit()
            logger.info(f"{association_count} novas associações aluno-grupo commitadas.")
        else:
            logger.info("Nenhuma nova associação aluno-grupo foi necessária.")
        return True

    except SQLAlchemyError as e:
        logger.error(f"Erro de banco de dados durante associação aluno-grupo: {e}. Revertendo.", exc_info=True)
        db_session.rollback()
        return False
    except Exception as e:
        # Captura outros erros inesperados
        logger.exception(f"Erro inesperado ao associar alunos a grupos: {e}")
        db_session.rollback()
        return False


def import_reserves_csv(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                        csv_file_path: str) -> bool:
    """
    Importa dados de reservas de um arquivo CSV para o banco de dados.

    Assume que os alunos referenciados nas reservas já existem no banco de dados
    (devem ser importados primeiro, por exemplo, via `import_students_csv`).
    Utiliza `bulk_create` para inserir as reservas.

    Args:
        student_crud: Instância CRUD para Student (usada para buscar IDs).
        reserve_crud: Instância CRUD para Reserve.
        csv_file_path: Caminho para o arquivo CSV de reservas. O CSV deve conter
                       pelo menos 'pront' e 'data'. Colunas opcionais incluem
                       'dish', 'snacks', 'canceled'.

    Returns:
        True se a importação for bem-sucedida (ou arquivo vazio), False caso contrário.
    """
    logger.info(f"Iniciando importação de reservas do CSV: {csv_file_path}")
    try:
        # Carrega os dados brutos do CSV
        raw_reserve_data = load_csv_as_dict(csv_file_path)
        if raw_reserve_data is None:
            logger.error(f"Falha ao carregar dados de reservas de {csv_file_path}.")
            return False
        if not raw_reserve_data:
            logger.info(f"Arquivo CSV de reservas '{csv_file_path}' está vazio. Nada a importar.")
            return True

        # --- Busca IDs dos Alunos ---
        # Cria um mapa de prontuário para ID de aluno para busca rápida
        all_students_map: Dict[str, int] = {s.pront: s.id for s in student_crud.read_all()}
        if not all_students_map:
            logger.error("Não é possível importar reservas: Nenhum aluno encontrado no banco de dados.")
            return False
        logger.debug(f"Criado mapa de lookup para {len(all_students_map)} alunos.")

        # --- Processamento dos Dados de Reserva ---
        reserves_to_insert: List[Dict[str, Any]] = []
        for i, row_raw in enumerate(raw_reserve_data):
            try:
                # Normaliza chaves e valores
                row = adjust_keys(row_raw)
                pront = row.get('pront')
                data = row.get('data')  # Esperado YYYY-MM-DD ou formato compatível com DB
                dish = row.get('dish')
                # Converte valores textuais ('true', '1', 'sim', 'lanche') para booleano
                is_snack = str(row.get('snacks', 'false')).lower() in ['true', '1', 'sim', 'yes', 'lanche']
                is_canceled = str(row.get('canceled', 'false')).lower() in ['true', '1', 'sim', 'yes', 'cancelado']

                # Validação básica
                if not pront or not data:
                    logger.warning(
                        f"Pulando linha {i+2} do CSV de reservas: 'pront' ou 'data' ausente. Dados: {row_raw}")
                    continue

                # Busca o ID do aluno no mapa
                student_id = all_students_map.get(pront)
                if student_id:
                    # Monta o dicionário de dados para a tabela Reserve
                    reserve_data = {
                        'student_id': student_id,
                        'data': data,
                        # Usa nome padrão se vazio
                        'dish': dish or UI_TEXTS.get("default_snack_name", "Não Especificado"),
                        'snacks': is_snack,
                        'canceled': is_canceled
                    }
                    reserves_to_insert.append(reserve_data)
                else:
                    # Aluno referenciado na reserva não existe no DB
                    logger.warning(
                        f"Pulando linha {i+2} do CSV de reservas: Aluno pront '{pront}' não encontrado no banco de dados.")

            except Exception as row_err:
                logger.error(
                    f"Erro ao processar linha {i+2} do CSV de reservas: {row_err}. Dados: {row_raw}", exc_info=True)

        # --- Inserção em Lote no Banco de Dados ---
        if reserves_to_insert:
            logger.info(
                f"Tentando inserir em lote {len(reserves_to_insert)} reservas processadas de '{csv_file_path}'.")
            # Tenta inserir usando bulk_create (que lida com erros e rollback)
            # A constraint UNIQUE no model Reserve(student_id, data, snacks) com
            # sqlite_on_conflict="IGNORE" fará o DB ignorar inserções duplicadas.
            success = reserve_crud.bulk_create(reserves_to_insert)
            if success:
                logger.info(f"Inserção em lote de reservas de '{csv_file_path}' concluída (duplicatas ignoradas).")
                return True
            else:
                # Erro já logado por bulk_create
                logger.error(f"Falha na inserção em lote de reservas (verificar logs do CRUD).")
                # Rollback já deve ter sido feito por bulk_create, mas garantir não custa.
                reserve_crud.rollback()
                return False
        else:
            logger.info(f"Nenhuma reserva válida encontrada para importar de '{csv_file_path}'.")
            return True

    except Exception as e:
        logger.exception(f"Erro inesperado durante importação de reservas do CSV '{csv_file_path}': {e}")
        # Tenta garantir o rollback em caso de erro não tratado
        try:
            reserve_crud.rollback()
        except Exception:
            pass
        return False


def reserve_snacks_for_all(student_crud: CRUD[Student], reserve_crud: CRUD[Reserve],
                           date: str, dish: str) -> bool:
    """
    Cria automaticamente reservas de lanche para TODOS os alunos cadastrados
    para uma data e nome de lanche específicos.

    Útil para garantir que todos tenham reserva para sessões de lanche onde
    a reserva é opcional ou presumida. Ignora duplicatas devido à constraint
    UNIQUE no banco de dados.

    Args:
        student_crud: Instância CRUD para Student.
        reserve_crud: Instância CRUD para Reserve.
        date: A data para a qual criar as reservas (formato YYYY-MM-DD).
        dish: O nome do lanche a ser registrado na reserva.

    Returns:
        True se a operação foi bem-sucedida, False caso contrário.
    """
    logger.info(f"Iniciando reserva de lanche em lote para o prato '{dish}' na data '{date}' para todos os alunos.")
    try:
        # Busca todos os alunos cadastrados
        all_students = student_crud.read_all()
        if not all_students:
            logger.warning("Nenhum aluno encontrado no banco de dados para reservar lanches.")
            return True  # Sucesso, pois não há o que fazer

        # Prepara a lista de dicionários para inserção em lote
        reserves_to_insert = [{
            'student_id': student.id,
            'data': date,
            'dish': dish,
            'snacks': True,  # Marca explicitamente como reserva de lanche
            'canceled': False  # Reserva ativa
        } for student in all_students]

        logger.info(f"Preparando {len(reserves_to_insert)} reservas de lanche para inserção em lote...")
        # Tenta a inserção em lote (duplicatas serão ignoradas pelo DB)
        success = reserve_crud.bulk_create(reserves_to_insert)

        if success:
            logger.info(
                f"Reservas de lanche em lote para '{date}' processadas com sucesso (novas inseridas, duplicatas ignoradas).")
            return True
        else:
            # Erro já logado por bulk_create
            logger.error(
                f"Falha na inserção em lote durante reserva de lanches para '{date}' (verificar logs do CRUD).")
            reserve_crud.rollback()
            return False

    except SQLAlchemyError as e:
        logger.error(
            f"Erro de banco de dados durante reserva de lanches em lote para '{date}': {e}. Revertendo.", exc_info=True)
        reserve_crud.rollback()
        return False
    except Exception as e:
        logger.exception(f"Erro inesperado ao reservar lanches para '{date}': {e}")
        reserve_crud.rollback()
        return False
