# ----------------------------------------------------------------------------
# File: registro/control/metrics_calculator.py (Calculador de Métricas)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Calcula diversas métricas de uso da aplicação a partir dos dados do banco,
com capacidade de filtrar por tipo de refeição.
"""
import logging
from collections import Counter
from typing import Any, Dict, Optional

from sqlalchemy import func, distinct, case
from sqlalchemy.orm import Session as SQLASession

from registro.model.tables import Consumption, Reserve, Student, Session, Group, student_group_association

logger = logging.getLogger(__name__)

DAY_OF_WEEK_MAP_SQLITE = {
    0: "Domingo", 1: "Segunda-feira", 2: "Terça-feira", 3: "Quarta-feira",
    4: "Quinta-feira", 5: "Sexta-feira", 6: "Sábado"
}

class MetricsCalculator:
    """
    Calcula métricas agregadas do sistema, com opção de filtro por tipo de refeição.
    """

    def __init__(self, db_session: SQLASession):
        if db_session is None:
            raise ValueError("A sessão do banco de dados (db_session) não pode ser None.")
        self.db_session = db_session

    def _get_base_consumption_query(self, meal_type_filter: Optional[str] = None):
        """ Retorna uma query base para Consumption, filtrada por tipo de refeição se fornecido. """
        query = self.db_session.query(Consumption)
        if meal_type_filter:
            # Filter consumptions by joining with Session and checking session.refeicao
            query = query.join(Session, Consumption.session_id == Session.id)\
                         .filter(Session.refeicao == meal_type_filter) # meal_type_filter already lowercased by caller
        return query

    def _get_base_reserve_query(self, meal_type_filter: Optional[str] = None):
        """ Retorna uma query base para Reserve, filtrada por tipo de refeição se fornecido. """
        query = self.db_session.query(Reserve)
        if meal_type_filter:
            # Filter reserves by snacks boolean (True for lanche, False for almoço)
            is_snack_filter = (meal_type_filter == "lanche") # meal_type_filter already lowercased
            query = query.filter(Reserve.snacks == is_snack_filter)
        return query

    def _calculate_specific_metrics_set(self, meal_type_filter_orig: Optional[str] = None) -> Dict[str, Any]:
        """
        Calcula um conjunto de métricas para um tipo de refeição específico (ou globalmente).
        Args:
            meal_type_filter_orig: Original meal type filter string (e.g., "Almoço", "Lanche", or None).
                                   Will be lowercased for internal use.
        """
        metrics: Dict[str, Any] = {}
        
        # Normalize meal_type_filter to lowercase for consistent internal use
        meal_type_filter = meal_type_filter_orig.lower() if meal_type_filter_orig else None
        
        log_prefix = f"[{meal_type_filter_orig.capitalize() if meal_type_filter_orig else 'Global'}] "
        logger.debug(f"{log_prefix}Iniciando cálculo do conjunto de métricas...")

        # --- Métricas de Consumo ---
        total_consumptions = self._get_base_consumption_query(meal_type_filter).count()
        metrics["Total de Consumos"] = total_consumptions

        consumptions_with_reserve = self._get_base_consumption_query(meal_type_filter)\
            .filter(Consumption.reserve_id.isnot(None)).count()
        
        consumptions_walk_in = self._get_base_consumption_query(meal_type_filter)\
            .filter(Consumption.consumed_without_reservation == True).count()

        metrics["Consumo com Reserva (%)"] = (consumptions_with_reserve / total_consumptions * 100.0) \
            if total_consumptions > 0 else 0.0
        metrics["Consumo Walk-in (%)"] = (consumptions_walk_in / total_consumptions * 100.0) \
            if total_consumptions > 0 else 0.0

        # --- Métricas de Reserva ---
        total_reserves_made = self._get_base_reserve_query(meal_type_filter).count()
        metrics["Total de Reservas Feitas"] = total_reserves_made

        active_reserves = self._get_base_reserve_query(meal_type_filter)\
            .filter(Reserve.canceled == False).count()
        metrics["Total de Reservas Ativas (não canceladas)"] = active_reserves
        
        canceled_reserves = self._get_base_reserve_query(meal_type_filter)\
            .filter(Reserve.canceled == True).count()
        metrics["Taxa de Cancelamento de Reservas (%)"] = \
            (canceled_reserves / total_reserves_made * 100.0) if total_reserves_made > 0 else 0.0

        # --- Taxas de Comparecimento e No-Show (sobre reservas ativas do tipo especificado) ---
        if active_reserves > 0:
            # Query for consumptions linked to an active (non-canceled) reserve.
            # This count represents actual attendance against active reservations.
            attended_q = self.db_session.query(func.count(distinct(Consumption.id)))\
                .join(Reserve, Consumption.reserve_id == Reserve.id)\
                .filter(Reserve.canceled == False) # Ensure the linked reserve was active

            if meal_type_filter:
                # For typed metrics, ensure the reserve itself was of the correct type
                is_snack_val = (meal_type_filter == "lanche")
                attended_q = attended_q.filter(Reserve.snacks == is_snack_val)
                
                # And ensure the consumption happened in a session of the correct type
                attended_q = attended_q.join(Session, Consumption.session_id == Session.id)\
                                       .filter(Session.refeicao == meal_type_filter)
            
            attended_from_active_reserves = attended_q.scalar() or 0
                
            metrics["Taxa de Comparecimento (sobre ativas) (%)"] = \
                (attended_from_active_reserves / active_reserves * 100.0)
            
            no_show_count = active_reserves - attended_from_active_reserves
            metrics["Taxa de No-Show (sobre ativas) (%)"] = \
                (no_show_count / active_reserves * 100.0)
        else:
            metrics["Taxa de Comparecimento (sobre ativas) (%)"] = 0.0
            metrics["Taxa de No-Show (sobre ativas) (%)"] = 0.0
        
        # --- Métricas de Usuário ---
        # Query for unique users who consumed, filtered by meal type of the session.
        unique_users_q_base = self.db_session.query(func.count(distinct(Consumption.student_id)))
        if meal_type_filter:
            unique_users_q = unique_users_q_base.join(Session, Consumption.session_id == Session.id)\
                                                .filter(Session.refeicao == meal_type_filter)
        else:
            unique_users_q = unique_users_q_base
        unique_users_consumed = unique_users_q.scalar() or 0
        metrics["Contagem de Usuários Únicos (que consumiram)"] = unique_users_consumed

        metrics["Consumo Médio por Usuário (que consumiu)"] = \
            (total_consumptions / unique_users_consumed * 1.0) if unique_users_consumed > 0 else 0.0

        # --- Métricas Agrupadas ---
        metrics["Consumos por Turma"] = self._get_consumptions_by_group(meal_type_filter)
        metrics["Consumos por Dia da Semana"] = self._get_consumptions_by_day_of_week(meal_type_filter)
        metrics["Consumos por Hora do Dia"] = self._get_consumptions_by_hour_of_day(meal_type_filter)
        
        logger.debug(f"{log_prefix}Cálculo do conjunto de métricas concluído.")
        return metrics

    def calculate_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Calcula métricas globais, e separadamente para "Almoço" e "Lanche".
        Retorna um dicionário com chaves "Global", "Almoço", "Lanche".
        """
        logger.info("Iniciando cálculo de todos os conjuntos de métricas (Global, Almoço, Lanche)...")
        
        all_metrics_data: Dict[str, Dict[str, Any]] = {}
        
        # Define a structure for default error metrics to ensure all keys are present
        default_scalar_error = "Erro no cálculo"
        default_dict_error = {"Erro": -1}
        metric_keys_structure = {
            "Total de Consumos": default_scalar_error,
            "Total de Reservas Feitas": default_scalar_error, 
            "Total de Reservas Ativas (não canceladas)": default_scalar_error,
            "Consumo com Reserva (%)": default_scalar_error,
            "Consumo Walk-in (%)": default_scalar_error, 
            "Taxa de Cancelamento de Reservas (%)": default_scalar_error,
            "Taxa de Comparecimento (sobre ativas) (%)": default_scalar_error, 
            "Taxa de No-Show (sobre ativas) (%)": default_scalar_error,
            "Consumo Médio por Usuário (que consumiu)": default_scalar_error, 
            "Contagem de Usuários Únicos (que consumiram)": default_scalar_error,
            "Consumos por Turma": default_dict_error, 
            "Consumos por Dia da Semana": default_dict_error, 
            "Consumos por Hora do Dia": default_dict_error
        }

        try:
            # Pass original case for logging, _calculate_specific_metrics_set will lowercase
            all_metrics_data["Global"] = self._calculate_specific_metrics_set(meal_type_filter_orig=None)
            all_metrics_data["Almoço"] = self._calculate_specific_metrics_set(meal_type_filter_orig="Almoço")
            all_metrics_data["Lanche"] = self._calculate_specific_metrics_set(meal_type_filter_orig="Lanche")
            logger.info("Cálculo de todos os conjuntos de métricas concluído.")
        except Exception as e:
            logger.exception(f"Erro crítico ao calcular conjuntos de métricas: {e}")
            # Populate all scopes with default error structures if a major error occurs
            all_metrics_data["Global"] = metric_keys_structure.copy()
            all_metrics_data["Almoço"] = metric_keys_structure.copy()
            all_metrics_data["Lanche"] = metric_keys_structure.copy()
            
        return all_metrics_data

    def _get_consumptions_by_group(self, meal_type_filter: Optional[str] = None) -> Dict[str, int]:
        """ Retorna a contagem de consumos por nome da turma, filtrado por tipo de refeição. """
        try:
            # Base query joins Group, Student, Consumption via association table
            query = self.db_session.query(
                Group.nome,
                func.count(Consumption.id) # Count consumptions
            ).join(student_group_association, Group.id == student_group_association.c.group_id)\
            .join(Student, Student.id == student_group_association.c.student_id)\
            .join(Consumption, Student.id == Consumption.student_id)
            
            if meal_type_filter:
                # Further filter by session's meal type if specified
                query = query.join(Session, Consumption.session_id == Session.id)\
                            .filter(Session.refeicao == meal_type_filter)
                
            results = query.group_by(Group.nome)\
                        .order_by(func.count(Consumption.id).desc())\
                        .all()
            return {group_name: count for group_name, count in results} if results else {}
        except Exception as e:
            logger.error(f"Erro ao calcular consumos por turma ({meal_type_filter or 'Global'}): {e}", exc_info=True)
            return {"Erro": -1}


    def _get_consumptions_by_day_of_week(self, meal_type_filter: Optional[str] = None) -> Dict[str, int]:
        """ Retorna a contagem de consumos por dia da semana, filtrado por tipo de refeição. """
        try:
            # Query consumptions, group by day of week extracted from session date
            query = self.db_session.query(
                func.strftime('%w', Session.data).label('day_of_week_num'), # SQLite specific: %w is day of week (0=Sunday)
                func.count(Consumption.id)
            ).join(Session, Consumption.session_id == Session.id)

            if meal_type_filter:
                query = query.filter(Session.refeicao == meal_type_filter)
                
            results = query.group_by('day_of_week_num')\
                        .order_by('day_of_week_num')\
                        .all()
            
            day_counts = Counter()
            for day_num_str, count in results:
                try:
                    day_num = int(day_num_str or 0)
                    day_name = DAY_OF_WEEK_MAP_SQLITE.get(day_num, f"Desconhecido ({day_num_str})")
                    day_counts[day_name] += count
                except ValueError: # Should not happen with %w
                    logger.warning(f"Valor não numérico para dia da semana: {day_num_str}")
                    day_counts[f"Inválido ({day_num_str})"] += count

            return dict(day_counts) if day_counts else {}
        except Exception as e:
            logger.error(f"Erro ao calcular consumos por dia da semana ({meal_type_filter or 'Global'}): {e}", exc_info=True)
            return {"Erro": -1}

    def _get_consumptions_by_hour_of_day(self, meal_type_filter: Optional[str] = None) -> Dict[str, int]:
        """ Retorna a contagem de consumos por hora do dia, filtrado por tipo de refeição. """
        try:
            # Query consumptions, group by hour extracted from consumption_time
            query = self.db_session.query(
                func.strftime('%H', Consumption.consumption_time).label('hour_of_day'), # SQLite specific: %H is hour (00-23)
                func.count(Consumption.id)
            )
            if meal_type_filter:
                # Filter by session's meal type if specified
                query = query.join(Session, Consumption.session_id == Session.id)\
                            .filter(Session.refeicao == meal_type_filter)

            results = query.group_by('hour_of_day')\
                        .order_by('hour_of_day')\
                        .all()
            # Format hour as a range for display e.g., "09:00-09:59"
            return {f"{hour_str.zfill(2)}:00-{hour_str.zfill(2)}:59": count for hour_str, count in results} if results else {}
        except Exception as e:
            logger.error(f"Erro ao calcular consumos por hora ({meal_type_filter or 'Global'}): {e}", exc_info=True)
            return {"Erro": -1}

# END OF FILE registro/control/metrics_calculator.py
