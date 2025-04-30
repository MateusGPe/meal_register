# ----------------------------------------------------------------------------
# File: registro/control/constants.py (Constantes da Aplicação)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Define constantes globais, caminhos de arquivo, configurações e textos da UI
para a aplicação de registro de refeições.
"""
import re
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set, TypedDict

# --- Caminhos de Diretório e Arquivo ---
APP_DIR: Path = Path(".")
CONFIG_DIR: Path = APP_DIR / "config"
LOG_DIR: Path = APP_DIR / "logs"
CREDENTIALS_PATH: Path = CONFIG_DIR / "credentials.json"
DATABASE_URL: str = f"sqlite:///{CONFIG_DIR.resolve()}/registro.db"
RESERVES_CSV_PATH: Path = CONFIG_DIR / "reserves.csv"
SPREADSHEET_ID_JSON: Path = CONFIG_DIR / "spreadsheet.json"
STUDENTS_CSV_PATH: Path = CONFIG_DIR / "students.csv"
TOKEN_PATH: Path = CONFIG_DIR / "token.json"
SESSION_PATH: Path = CONFIG_DIR / "session.json"
SNACKS_JSON_PATH: Path = CONFIG_DIR / "lanches.json"  # Usado explicitamente em session_dialog

# --- Configurações da API Google ---
SCOPES: List[str] = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
RESERVES_SHEET_NAME: str = "DB"
STUDENTS_SHEET_NAME: str = "Discentes"

# --- Processamento de Texto e Dados ---
CAPITALIZATION_EXCEPTIONS: Set[str] = {
    "a", "o", "as", "os", "de", "do", "da", "dos", "das",
    "e", "é", "em", "com", "sem", "ou", "para", "por", "pelo", "pela",
    "no", "na", "nos", "nas"
}
# Mapeamento para ofuscar prontuários (usado em utils.to_code)
PRONTUARIO_OBFUSCATION_MAP: Dict[int, int] = str.maketrans("0123456789Xx", "abcdefghijkk")
# Tradução de chaves externas (CSV/Sheets) para chaves internas
EXTERNAL_KEY_TRANSLATION: Dict[str, str] = {
    'matrícula iq': 'pront',
    'matrícula': 'pront',
    'prontuário': 'pront',
    'refeição': 'dish',
    'curso': 'turma',
    'situação': 'status',
    'nome completo': 'nome'
}
# Regex para limpar prefixo "IQ0..." de prontuários
PRONTUARIO_CLEANUP_REGEX: re.Pattern[str] = re.compile(r"^[Ii][Qq]0+")

# --- Dados Específicos da Aplicação ---
INTEGRATED_CLASSES: List[str] = [
    "1º A - MAC", "1º A - MEC", "1º B - MEC", "2º A - MAC",
    "2º A - MEC", "2º B - MEC", "3º A - MEC", "3º B - MEC",
]

# Tipagem para dados de nova sessão
NewSessionData = TypedDict(
    'NewSessionData',
    {
        'refeição': Literal["Lanche", "Almoço"],
        'lanche': Optional[str],
        'período': str,  # Pode ser vazio, mantido por compatibilidade ou futuro uso
        'data': str,  # Esperado como YYYY-MM-DD internamente, convertido para UI
        'hora': str,  # HH:MM
        'groups': List[str]  # Nomes das turmas selecionadas
    }
)
# Alias para clareza onde usado (apesar de ser igual a NewSessionData)
SESSION = NewSessionData

# --- Constantes para API Windows (utils.get_documents_path) ---
CSIDL_PERSONAL: int = 5
SHGFP_TYPE_CURRENT: int = 0

# --- Cabeçalho para Exportação Excel ---
EXPORT_HEADER: List[str] = [
    "Matrícula", "Data", "Nome", "Turma", "Refeição", "Hora"
]

# --- Textos da Interface do Usuário (Centralizados) ---
UI_TEXTS: Dict[str, str] = {
    # Títulos de Janelas e Diálogos
    "app_title": "RU IFSP - Registro de Refeições",
    "session_dialog_title": "Selecionar ou Criar Sessão",
    "class_filter_dialog_title": "📊 Filtrar Turmas",
    "critical_error_title": "Erro Crítico",
    "initialization_error_title": "Erro de Inicialização",
    "callback_error_title": "Erro no Callback",
    "confirm_deletion_title": "Confirmar Remoção",
    "confirm_end_session_title": "Confirmar Fim da Sessão",
    "export_failed_title": "Falha na Exportação",
    "state_error_title": "Erro de Estado",
    "no_session_title": "Nenhuma Sessão",
    "operation_failed_title": "Operação Falhou",
    "sync_error_title": "Erro de Sincronização",
    "sync_complete_title": "Sincronização Concluída",
    "sync_status_unknown_title": "Status da Sincronização Desconhecido",
    "no_student_selected_title": "Nenhum Aluno Selecionado",
    "registration_error_title": "Erro no Registro",
    "already_registered_title": "Já Registrado",
    "delete_error_title": "Erro ao Remover",
    "export_success_title": "Sucesso na Exportação",
    "export_error_title": "Erro na Exportação",
    "config_error_title": "Erro de Configuração",
    "fatal_app_error_title": "Erro Fatal da Aplicação",
    "invalid_input_title": "Entrada Inválida",
    "invalid_selection_title": "Seleção Inválida",
    "save_error_title": "Erro ao Salvar",
    "empty_export_title": "Nada para Exportar",

    # Labels e Textos Estáticos
    "loading_session": "Carregando Sessão...",
    "status_ready": "Pronto.",
    "status_processing": "Processando...",
    "no_classes_available": "Nenhuma turma disponível.",
    "show_with_reservation": "Mostrar COM Reserva",
    "show_without_reservation": "Mostrar SEM Reserva (#)",
    "eligible_students_label": "🔍 Alunos Elegíveis (Resultados da Busca)",
    "select_student_preview": "Selecione um aluno da lista.",
    "select_student_placeholder": "Selecione um aluno...",  # Usado após registro/limpeza
    "registered_students_label": "✅ Alunos Registrados (Clique ❌ para Remover)",
    "registered_count_label": "Registrados: {count}",
    "remaining_count_label": "Elegíveis: {eligible_count} / Restantes: {remaining_count}",
    "error_loading_list": "Erro ao carregar lista",
    "no_matches_found": "Nenhum resultado encontrado",
    "matches_found": "{count} resultado(s)",
    "selected_student_info": "Pront: {pront}\nNome: {nome}\nTurma: {turma}\nPrato: {prato}",
    "error_selecting_data": "Erro ao selecionar dados.",
    "select_error": "Erro na Seleção",
    "registered_feedback": "Registrado: {pront}",
    "already_registered_feedback": "JÁ REGISTRADO: {pront}",
    "error_registering_feedback": "ERRO registro {pront}",
    "search_placeholder": "Digite nome ou prontuário (mín. 2 caracteres)...",
    "new_session_group_label": "➕ Detalhes da Nova Sessão",
    "time_label": "⏰ Horário:",
    "date_label": "📅 Data:",
    "meal_type_label": "🍽️ Refeição:",
    "specific_snack_label": "🥪 Lanche Específico:",
    "participating_classes_label": "🎟️ Selecione Turmas Participantes",
    "no_classes_found_db": "Nenhuma turma encontrada no banco de dados.",
    "edit_session_group_label": "📝 Selecionar Sessão Existente para Editar",
    "edit_session_placeholder": "Selecione uma sessão existente para carregar...",
    "no_existing_sessions": "Nenhuma sessão existente encontrada.",
    "error_loading_sessions": "Erro ao carregar sessões",  # Para combobox de sessões

    # Textos de Botões
    "export_end_button": "💾 Exportar e Encerrar",
    "sync_served_button": "📤 Sincronizar Servidos",
    "sync_master_button": "🔄 Sincronizar Cadastros",
    "filter_classes_button": "📊 Filtrar Turmas",
    "change_session_button": "⚙️ Alterar Sessão",
    "clear_search_button": "❌",  # Botão pequeno ao lado da busca
    "register_selected_button": "➕ Registrar Selecionado",
    "clear_all_button": "⚪ Limpar Todos",  # Filtro de turmas / Seleção de turmas (Sessão)
    "select_all_button": "✅ Selecionar Todos",  # Filtro de turmas
    "cancel_button": "❌ Cancelar",
    "apply_filters_button": "✔️ Aplicar Filtros",
    "select_integrated_button": "🔗 Selecionar Integrais",  # Seleção de turmas (Sessão)
    "select_others_button": "📚 Selecionar Outros",  # Seleção de turmas (Sessão)
    "invert_selection_button": "🔄 Inverter Seleção",  # Seleção de turmas (Sessão)
    "sync_reservations_button": "📥 Sincronizar Reservas",  # Diálogo de Sessão
    "ok_button": "✔️ OK",  # Diálogo de Sessão

    # Nomes de Colunas (UI)
    "col_action": "❌",  # Coluna de ação (remover)
    "col_prontuario": "🆔 Pront.",
    "col_nome": "✍️ Nome",
    "col_turma": "👥 Turma",
    "col_hora": "⏱️ Hora",
    "col_prato_status": "🍽️ Prato/Status",
    "col_nome_eligible": "Nome",  # Tabela de elegíveis
    "col_info_eligible": "Turma | Pront",  # Tabela de elegíveis
    "col_dish_eligible": "Prato/Status",  # Tabela de elegíveis

    # Mensagens (Messagebox, Logs para Usuário)
    "initialization_error_message": "Falha: {component}\n{error}\n\nAplicação será encerrada.",
    "critical_error_message": "A aplicação encontrou um erro inesperado e será encerrada:\n\n{error}",
    "callback_error_message": "Falha ao aplicar filtros:\n{error}",
    "confirm_deletion_message": "Remover registro para:\n{pront} - {nome}?",
    "confirm_end_session_message": "Isso exportará os dados localmente (se houver) e encerrará a sessão atual.\n\nProsseguir?",
    "export_failed_message": "Falha ao exportar dados da sessão localmente.\nEncerrar sessão mesmo assim?",
    "state_error_message": "Não foi possível limpar o arquivo de estado.\nA sessão pode recarregar.",
    "no_session_message": "Nenhuma sessão ativa.",
    "operation_failed_message": "Não foi possível {action_desc}.",
    "sync_error_message": "{task_name} Falhou:\n{error}",
    "sync_complete_message": "{task_name} concluído com sucesso.",
    "sync_status_unknown_message": "{task_name} finalizado com status incerto.",
    "no_student_selected_message": "Selecione um aluno elegível da lista primeiro.",
    "already_registered_message": "{nome} ({pront})\nJá registrado.",
    "registration_error_message": "Não foi possível registrar:\n{nome} ({pront})",
    "delete_error_message": "Não foi possível remover {nome}.",
    "export_success_message": "Exportado para:\n{file_path}",
    "export_error_message": "Falha na exportação para Excel.",
    "export_generic_error_message": "Erro na exportação:\n{error}",
    "config_error_message": "Falha na configuração: {config_err}",
    "fatal_app_error_message": "Um erro inesperado ocorreu:\n{app_err}",
    "invalid_time_format": "Formato de hora inválido. Use HH:MM.",
    "invalid_date_format": "Formato de data inválido. Use {date_format}.",  # Será formatado com DD/MM/YYYY
    "select_meal_type": "Selecione um Tipo de Refeição válido.",
    "specify_snack_name": "Especifique o nome do lanche para 'Lanche'.",
    "select_one_class": "Selecione pelo menos uma turma participante.",
    "new_snack_save_error": "Não foi possível salvar a nova opção de lanche.",
    "unexpected_snack_save_error": "Erro inesperado ao salvar lista de lanches.",
    "sync_reserves_error_message": "Falha ao sincronizar reservas:\n{error}",
    "sync_reserves_complete_message": "Reservas sincronizadas com sucesso com o banco de dados.",
    "sync_reserves_unknown_message": "Sincronização finalizada, mas status incerto.",
    "empty_export_message": "Nenhum aluno registrado para exportar.",
    "confirm_sync_master_message": "Sincronizar dados de alunos e reservas a partir das Planilhas Google?",

    # Termos Padrão / Internos (Menos provável de mudar, mas centralizado por segurança)
    "meal_lunch": "Almoço",
    "meal_snack": "Lanche",
    "default_snack_name": "Lanche Padrão",
    "no_reservation_status": "Sem Reserva",
    "unknown_meal_type": "Desconhecido",  # Para nome de aba/arquivo se tipo faltar

    # Logs voltados ao usuário (Exemplo - poderia ser mais específico)
    "log_app_start": "{sep} INÍCIO DA APLICAÇÃO {sep}\n",
    "log_app_end": "{sep} FIM DA APLICAÇÃO {sep}\n",
    "log_dpi_set_shcore": "Reconhecimento de DPI definido (shcore).",
    "log_dpi_set_user32": "Reconhecimento de DPI definido (user32).",
    "log_dpi_set_warn": "Não foi possível definir reconhecimento de DPI (APIs não encontradas).",
    "log_default_snacks_created": "Arquivo de lanches padrão criado: '{path}'."
}
