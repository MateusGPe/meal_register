import logging
from typing import Dict, List, Optional, Set

from sqlalchemy import distinct
from sqlalchemy.orm import Session

from registro.control.utils import to_code
from registro.model.tables import Group, Reserve, Student

# logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class StudentFilter:
    def __init__(self, session: Session):
        self._session = session
        self._filtered_discentes = []

    def _get_student_groups_map(self, student_ids: Set[int]) -> Dict[int, List[str]]:
        student_groups_map: Dict[int, List[str]] = {}
        if not student_ids:
            log.info("No student IDs provided to fetch groups.")
            return student_groups_map

        try:
            log.info("Querying groups for %d student IDs.", len(student_ids))
            group_data = self._session.query(Student.id, Group.name)\
                .join(Student.groups)\
                .filter(Student.id.in_(student_ids))\
                .all()

            log.info("Processing %d group entries.", len(group_data))
            for s_id, g_name in group_data:
                student_groups_map.setdefault(s_id, []).append(g_name)

            for groups in student_groups_map.values():
                groups.sort()

            log.info("Successfully built student groups map.")
        except Exception as e:
            log.error(
                "Error querying or processing student groups: %s", e, exc_info=True)
            return {}

        return student_groups_map

    def _query_reserved_students(self, date: str, selected_groups: Set[str], is_snack: bool):
        if not selected_groups:
            log.info("No groups selected for querying reserved students.")
            return []

        try:
            log.info("Querying reserved students for groups: %s, snack: %s, date: %s",
                     selected_groups, is_snack, date)
            query = self._session.query(
                distinct(Reserve.id).label("reserve_id"),
                Student.pront,
                Student.name,
                Reserve.dish,
                Reserve.date,
                Student.id.label("student_id")
            ).select_from(Reserve).join(
                Reserve.student
            ).join(
                Student.groups
            ).filter(
                Reserve.date == date,
                Reserve.snacks == is_snack,
                Group.name.in_(selected_groups)
            )
            results = query.all()
            log.info("Found %d reserved student entries.", len(results))
            return results
        except Exception as e:
            log.error("Error querying reserved students: %s", e, exc_info=True)
            return []

    def _query_unreserved_students(self, date: str, selected_groups: Set[str], is_snack: bool):
        if not selected_groups:
            log.info("No groups selected for querying unreserved students.")
            return []

        try:
            log.info("Querying unreserved students for groups: %s, excluding snack: %s, date: %s",
                     selected_groups, is_snack, date)
            reserve_exists_subquery = self._session.query(Reserve.id).filter(
                Reserve.student_id == Student.id,
                Reserve.date == date,
                Reserve.snacks == is_snack
            ).exists()

            query = self._session.query(
                Student.pront,
                Student.name,
                Student.id.label("student_id")
            ).select_from(Student).join(
                Student.groups
            ).filter(
                Group.name.in_(selected_groups),
                ~reserve_exists_subquery
            ).distinct()

            results = query.all()
            log.info("Found %d unreserved student entries.", len(results))
            return results
        except Exception as e:
            log.error("Error querying unreserved students: %s",
                      e, exc_info=True)
            return []

    def _process_reserved_results(self, results, student_groups_map: Dict[int, List[str]]
                                  ) -> tuple[List[Dict], Set[str]]:
        processed_students = []
        processed_pronts = set()
        _pront_to_reserve_id_map = {}

        log.info("Processing %d reserved student results.", len(results))
        for row in results:
            if row.pront not in processed_pronts:
                student_info = {
                    "Pront": row.pront,
                    "Nome": row.name,
                    "Turma": ','.join(student_groups_map.get(row.student_id, [])),
                    "Prato": row.dish,
                    "Data": row.date,
                    "id": to_code(row.pront),
                    "Hora": None,
                    "reserve_id": row.reserve_id,
                    "student_id": row.student_id,
                }
                processed_students.append(student_info)
                processed_pronts.add(row.pront)
                _pront_to_reserve_id_map[row.pront] = row.reserve_id
        log.info("Formatted %d unique reserved student entries.",
                 len(processed_students))
        return processed_students, processed_pronts

    def _process_unreserved_results(self, date: str, results, student_groups_map: Dict[int, List[str]]) -> List[Dict]:
        processed_students = []
        log.info("Processing %d unreserved student results.", len(results))
        for row in results:
            student_info = {
                "Pront": row.pront,
                "Nome": row.name,
                "Turma": ','.join(student_groups_map.get(row.student_id, [])),
                "Prato": "SEM RESERVA",
                "Data": date,
                "id": to_code(row.pront),
                "Hora": None,
                "reserve_id": None,
                "student_id": row.student_id,
            }
            processed_students.append(student_info)
        log.info("Formatted %d unreserved student entries.",
                 len(processed_students))
        return processed_students

    def filter_students(self, date: str, all_selected_groups: Set[str], is_snack: bool) -> Optional[List[Dict]]:
        include_unreserved = 'SEM RESERVA' in all_selected_groups
        all_selected_groups.discard('SEM RESERVA')
        groups_to_query = all_selected_groups

        reserved_results = []
        unreserved_results = []

        if groups_to_query:
            reserved_results = self._query_reserved_students(
                date,
                groups_to_query,
                is_snack)

        if include_unreserved and groups_to_query:
            unreserved_results = self._query_unreserved_students(
                date,
                groups_to_query,
                is_snack)

        all_student_ids = {row.student_id for row in reserved_results} | \
                          {row.student_id for row in unreserved_results}

        student_groups_map = self._get_student_groups_map(all_student_ids)

        final_reserved_list, reserved_pronts = self._process_reserved_results(
            reserved_results, student_groups_map
        )
        final_unreserved_list = self._process_unreserved_results(
            date,
            unreserved_results,
            student_groups_map
        )

        combined_list = final_reserved_list
        for student_info in final_unreserved_list:
            if student_info["Pront"] not in reserved_pronts:
                combined_list.append(student_info)

        combined_list.sort(key=lambda x: x["Nome"])

        self._filtered_discentes = combined_list
        log.info("Final filtered list contains %d students.",
                 len(self._filtered_discentes))
        return self._filtered_discentes

    def get_filtered_students(self) -> List[Dict]:
        return self._filtered_discentes
