# ----------------------------------------------------------------------------
# File: registro/view/action_search_panel.py (Painel de Ação/Busca)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Define o painel esquerdo da interface, contendo busca, lista de elegíveis,
preview e botão de registro.
"""
import logging
import re
import tkinter as tk
from datetime import datetime
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

import ttkbootstrap as ttk
from fuzzywuzzy import fuzz
from ttkbootstrap.constants import (
    DANGER,
    DEFAULT,
    DISABLED,
    INFO,
    LEFT,
    NORMAL,
    SUCCESS,
    WARNING,
    W,
    X,
)

from registro.control.constants import PRONTUARIO_CLEANUP_REGEX, UI_TEXTS
from registro.control.session_manage import SessionManager
from registro.view.simple_treeview import SimpleTreeView

# Evita importação circular para type hinting
if TYPE_CHECKING:
    # Importa apenas para checagem de tipo, não em tempo de execução
    from registro.view.registration_app import RegistrationApp

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Painel de Ação e Busca (Esquerda)
# ----------------------------------------------------------------------------


class ActionSearchPanel(ttk.Frame):
    """
    Painel contendo a barra de busca, lista de alunos elegíveis, preview
    e botão de registro.
    """

    SEARCH_DEBOUNCE_DELAY = 350  # ms para aguardar antes de buscar

    def __init__(
        self,
        master: tk.Widget,
        app: "RegistrationApp",  # Usa o type hint
        session_manager: "SessionManager",  # Usa o type hint (ou importar diretamente)
    ):
        """
        Inicializa o painel de Ação/Busca.

        Args:
            master: O widget pai (geralmente o PanedWindow).
            app: Referência à instância principal da RegistrationApp.
            session_manager: Instância do SessionManager para acesso aos dados.
        """
        super().__init__(master, padding=10)
        self._app = app  # Referência à app principal para callbacks/acesso
        self._session_manager = session_manager

        # --- Atributos de Estado e Widgets Internos ---
        self._search_after_id: Optional[str] = None  # ID do timer do debounce
        # Cache dos resultados da busca atual
        self._current_eligible_matches_data: List[Dict[str, Any]] = []
        # Dados do aluno selecionado na lista
        self._selected_eligible_data: Optional[Dict[str, Any]] = None

        # Widgets (inicializados nos métodos _create_*)
        self._search_entry_var: tk.StringVar = tk.StringVar()
        self._search_entry: Optional[ttk.Entry] = None
        self._clear_button: Optional[ttk.Button] = None
        self._eligible_students_tree: Optional[SimpleTreeView] = None
        self._selected_student_label: Optional[ttk.Label] = None
        self._register_button: Optional[ttk.Button] = None
        self._action_feedback_label: Optional[ttk.Label] = None

        # Configuração do Grid interno do painel
        # Área da lista expande verticalmente
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)  # Expansão horizontal

        # Criação dos widgets internos
        self._create_search_bar()
        self._create_eligible_list()
        self._create_preview_area()
        self._create_action_area()

        # Bindings de eventos
        if self._search_entry:
            self._search_entry.bind(
                "<Return>", lambda _: self._register_selected_eligible()
            )
            self._search_entry.bind("<Down>", lambda _: self._select_next_eligible(1))
            self._search_entry.bind("<Up>", lambda _: self._select_next_eligible(-1))
            self._search_entry.bind(
                "<Escape>", lambda _: self._search_entry_var.set("")
            )  # Limpa busca
        if self._eligible_students_tree:
            self._eligible_students_tree.view.bind(
                "<<TreeviewSelect>>", self._on_eligible_student_select
            )
            self._eligible_students_tree.view.bind(
                "<Double-1>", lambda _: self._register_selected_eligible()
            )

    @property
    def search_after_id(self) -> Optional[str]:
        """Retorna o ID do timer de debounce atual."""
        return self._search_after_id

    @search_after_id.setter
    def search_after_id(self, value: Optional[str]):
        """Define o ID do timer de debounce."""
        self._search_after_id = value

    def _create_search_bar(self):
        """Cria a barra de busca com entrada e botão de limpar."""
        search_bar = ttk.Frame(self)
        search_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        search_bar.grid_columnconfigure(0, weight=1)  # Entry expande

        # Campo de entrada da busca
        self._search_entry = ttk.Entry(
            search_bar,
            textvariable=self._search_entry_var,
            font=(None, 12),
            bootstyle=INFO,  # type: ignore
        )
        self._search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        # Associa a função de debounce à mudança no texto
        self._search_entry_var.trace_add("write", self._on_search_entry_change)

        # Botão para limpar a busca
        self._clear_button = ttk.Button(
            search_bar,
            text=UI_TEXTS.get("clear_search_button", "❌"),
            width=3,
            command=self.clear_search,  # Chama método local
            bootstyle="danger-outline",  # type: ignore
        )
        self._clear_button.grid(row=0, column=1)

    def _create_eligible_list(self):
        """Cria a tabela (SimpleTreeView) para exibir os alunos elegíveis."""
        eligible_frame = ttk.Labelframe(
            self, text=UI_TEXTS.get("eligible_students_label", "Alunos Elegíveis"), padding=(5, 5)
        )
        # Posiciona abaixo da busca
        eligible_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 10))
        eligible_frame.grid_rowconfigure(0, weight=1)  # Treeview expande
        eligible_frame.grid_columnconfigure(0, weight=1)

        # Definição das colunas usando UI_TEXTS
        elig_cols = [
            {
                "text": UI_TEXTS.get("col_nome_eligible", "Nome"),
                "stretch": True,
                "iid": "name",
            },
            {
                "text": UI_TEXTS.get("col_info_eligible", "Turma | Pront"),
                "width": 160,
                "anchor": W,
                "iid": "info",
                "minwidth": 100,
            },
            {
                "text": UI_TEXTS.get("col_dish_eligible", "Prato/Status"),
                "width": 130,
                "anchor": W,
                "iid": "dish",
                "minwidth": 80,
            },
        ]
        # Cria a instância da SimpleTreeView
        self._eligible_students_tree = SimpleTreeView(
            master=eligible_frame, coldata=elig_cols, height=10  # Ajustar altura
        )
        self._eligible_students_tree.grid(row=0, column=0, sticky="nsew")

    def _create_preview_area(self):
        """Cria a área para exibir informações do aluno selecionado."""
        preview_frame = ttk.Frame(self, padding=(0, 0))
        # Posiciona abaixo da lista de elegíveis
        preview_frame.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        # Label para o preview
        self._selected_student_label = ttk.Label(
            preview_frame,
            text=UI_TEXTS.get("select_student_preview", "Selecione um aluno da lista."),
            justify=LEFT,
            bootstyle="inverse-info",  # type: ignore
            wraplength=350,  # Quebra linha para nomes/turmas longas
            style="Preview.TLabel"  # Aplica estilo customizado se definido
        )
        self._selected_student_label.pack(fill=X, expand=True)

    def _create_action_area(self):
        """Cria a área com o botão de registrar e o label de feedback."""
        action_frame = ttk.Frame(self)
        # Posiciona *acima* da lista de elegíveis (row=1)
        action_frame.grid(row=1, column=0, sticky="ew", pady=(5, 5))  # Adiciona padding inferior
        action_frame.columnconfigure(1, weight=1)  # Botão registrar expande

        # Botão de Registrar
        self._register_button = ttk.Button(
            action_frame,
            text=UI_TEXTS.get("register_selected_button", "Registrar Selecionado"),
            command=self._register_selected_eligible,  # Chama método local
            bootstyle="success",  # type: ignore
            state=DISABLED,  # Começa desabilitado
        )
        # Coloca o botão à direita
        self._register_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        # Label para feedback da última ação (registro, erro, etc.)
        self._action_feedback_label = ttk.Label(
            action_frame,
            text="",
            # width=35, # Largura pode ser controlada pelo grid/pack
            anchor=W,
            style="Feedback.TLabel",  # Usa estilo customizado
        )
        # Coloca o feedback à esquerda
        self._action_feedback_label.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        action_frame.columnconfigure(0, weight=2)  # Dá mais espaço para o feedback

    # --- Métodos Públicos (Controle Externo) ---

    def clear_search(self, *_):
        """Limpa o campo de busca, a lista de resultados e o estado relacionado."""
        logger.debug("Limpando busca no painel de ação.")
        # Limpa a variável Tk (dispara _on_search_entry_change)
        if self._search_entry:
            self._search_entry_var.set("")
            # _on_search_entry_change cuidará de limpar a tabela e resetar estados
            self.focus_entry()  # Foca de volta no campo após limpar
        else:
            logger.warning("Tentativa de limpar busca com campo não inicializado.")

    def focus_entry(self):
        """Coloca o foco no campo de busca."""
        if self._search_entry:
            # Usa after para garantir que o widget esteja pronto
            self.after(50, self._search_entry.focus_set)
            logger.debug("Foco agendado para o campo de busca.")
        else:
            logger.warning("Tentativa de focar campo de busca não inicializado.")

    def refresh_results(self):
        """Força a re-execução da busca atual."""
        logger.debug("Atualizando resultados da busca.")
        # Cancela qualquer busca pendente antes de forçar uma nova
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None
        self._perform_actual_search()  # Executa a busca imediatamente

    def disable_controls(self):
        """Desabilita os controles do painel (quando não há sessão ativa)."""
        if self._search_entry:
            self._search_entry.config(state=DISABLED)
            self._search_entry_var.set("")  # Limpa o texto também
        if self._clear_button:
            self._clear_button.config(state=DISABLED)
        if self._register_button:
            self._register_button.config(state=DISABLED)
        if self._eligible_students_tree:
            self._eligible_students_tree.delete_rows()
        self._selected_eligible_data = None
        self._current_eligible_matches_data = []  # Limpa cache
        self._update_preview_label()
        if self._action_feedback_label:
            self._action_feedback_label.config(text="")
        logger.debug("Controles do painel de ação desabilitados.")

    def enable_controls(self):
        """Habilita os controles do painel (quando uma sessão está ativa)."""
        if self._search_entry:
            self._search_entry.config(state=NORMAL)
        if self._clear_button:
            self._clear_button.config(state=NORMAL)
        # Botão de registrar continua DISABLED até selecionar alguém
        if self._register_button:
            self._register_button.config(state=DISABLED)
        logger.debug("Controles do painel de ação habilitados.")
        self.focus_entry()  # Coloca foco na busca ao habilitar

    # --- Métodos Internos (Lógica do Painel) ---

    def _on_search_entry_change(self, *_):
        """Callback chamado quando o texto da busca muda (com debounce)."""
        # Cancela timer anterior se existir
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None  # Reseta ID do timer

        search_term = self._search_entry_var.get()
        # Se termo curto, limpa tudo e retorna
        if len(search_term) < 2:
            if self._eligible_students_tree:
                self._eligible_students_tree.delete_rows()
            self._selected_eligible_data = None
            self._current_eligible_matches_data = []
            if self._register_button:
                self._register_button.config(state=DISABLED)
            self._update_preview_label()
            if self._action_feedback_label:
                # Mensagem mais clara se o campo estiver vazio
                placeholder = (UI_TEXTS.get("search_placeholder_empty",
                                            "Digite para buscar...") if not search_term else
                               UI_TEXTS.get("search_placeholder_min_chars",
                                            "Mínimo 2 caracteres..."))
                self._action_feedback_label.config(
                    text=placeholder,
                    bootstyle=DEFAULT,
                )  # type: ignore
            return

        # Agenda a busca real após o delay
        self._search_after_id = self.after(
            self.SEARCH_DEBOUNCE_DELAY, self._perform_actual_search
        )

    def _select_next_eligible(self, delta: int = 1):
        """Seleciona o próximo item (ou anterior) na lista de elegíveis."""
        try:
            if (not self._eligible_students_tree or
                    not self._eligible_students_tree.get_children_iids()):
                return  # Sai se a árvore não existe ou está vazia

            selected_iid = self._eligible_students_tree.get_selected_iid()
            iid_list = self._eligible_students_tree.get_children_iids()
            list_len = len(iid_list)

            if not selected_iid:  # Se nada selecionado, seleciona o primeiro/último
                next_index = 0 if delta > 0 else list_len - 1
            else:
                try:
                    current_index = iid_list.index(selected_iid)
                    next_index = current_index + delta
                    # Lógica de 'wrap around' (módulo)
                    next_index %= list_len
                except ValueError:  # Se o IID selecionado não estiver na lista (improvável)
                    next_index = 0 if delta > 0 else list_len - 1

            if 0 <= next_index < list_len:
                next_iid = iid_list[next_index]
                self._eligible_students_tree.view.focus(next_iid)
                self._eligible_students_tree.view.selection_set(next_iid)
                # Garante que o item selecionado esteja visível
                self._eligible_students_tree.view.see(next_iid)
            else:
                logger.warning("Índice calculado para seleção (%d) inválido.", next_index)

        except Exception as e:
            logger.exception("Erro ao selecionar próximo item da busca: %s", e)

    def _perform_actual_search(self):
        """Executa a busca filtrada e atualiza a lista de elegíveis."""
        self._search_after_id = None  # Marca que a busca agendada rodou
        search_term = self._search_entry_var.get()
        # Checagem dupla (caso o usuário apague rápido)
        if len(search_term) < 2:
            if self._action_feedback_label:
                self._action_feedback_label.config(text="")  # Limpa feedback
            # Garante que a lista seja limpa se o termo ficou < 2
            if self._eligible_students_tree:
                self._eligible_students_tree.delete_rows()
            self._selected_eligible_data = None
            self._current_eligible_matches_data = []
            self._update_preview_label()
            if self._register_button:
                self._register_button.config(state=DISABLED)
            return

        logger.debug("Executando busca debounced por: %s", search_term)
        # Busca alunos elegíveis do SessionManager (já filtrados por turma/reserva)
        eligible = self._session_manager.get_eligible_students()
        if eligible is None:
            logger.error("Lista de elegíveis N/A durante a busca.")
            if self._action_feedback_label:
                self._action_feedback_label.config(
                    text=UI_TEXTS.get("error_loading_list", "Erro ao carregar lista"),
                    bootstyle=DANGER,
                )  # type: ignore
            if self._eligible_students_tree:
                self._eligible_students_tree.delete_rows()
            return

        # Obtém prontuários já servidos para garantir exclusão (redundância segura)
        served = self._session_manager.get_served_pronts()

        # Realiza a busca fuzzy
        if search_term in ['todos', '---', '***']:
            matches = self._get_eligible_not_served(
                eligible, served, not_served=search_term != '***')
        else:
            matches = self._perform_fuzzy_search(search_term, eligible, served)

        # Atualiza a tabela
        if self._eligible_students_tree:
            self._update_eligible_treeview(matches)

        # Atualiza feedback e seleciona primeiro item
        if matches:
            if self._action_feedback_label:
                self._action_feedback_label.config(
                    text=UI_TEXTS.get("matches_found", "{count} resultado(s)").format(
                        count=len(matches)
                    ),
                    bootstyle=INFO,
                )  # type: ignore
            # Tenta focar e selecionar o primeiro item da lista
            try:
                if (
                    self._eligible_students_tree
                    and self._eligible_students_tree.get_children_iids()
                ):
                    first_iid = self._eligible_students_tree.get_children_iids()[0]
                    # Selecionar dispara o evento <<TreeviewSelect>> que
                    # chama _on_eligible_student_select
                    self._eligible_students_tree.view.focus(first_iid)
                    self._eligible_students_tree.view.selection_set(first_iid)
                    self._eligible_students_tree.view.see(first_iid)  # Garante visibilidade
            except Exception as e:
                logger.error("Erro ao auto-selecionar primeiro item da busca: %s", e)
        else:
            # Nenhum resultado encontrado
            if self._action_feedback_label:
                self._action_feedback_label.config(
                    text=UI_TEXTS.get(
                        "no_matches_found", "Nenhum resultado encontrado"
                    ),
                    bootstyle=WARNING,
                )  # type: ignore
            self._selected_eligible_data = None
            self._update_preview_label()
            if self._register_button:
                self._register_button.config(state=DISABLED)

    def _get_eligible_not_served(
        self, eligible_students: List[Dict[str, Any]],
        served_pronts: Set[str],
        not_served: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Filtra a lista de alunos elegíveis, retornando apenas aqueles cujo
        'Pront' não é encontrado no conjunto served_pronts. Também formata
        o campo 'info' para exibição.

        Args:
            eligible_students: Lista de dicionários representando todos os alunos potencialmente elegíveis.
                               Chaves esperadas: 'Pront', 'Nome', 'Turma'.
            served_pronts: Um set contendo as strings 'Pront' dos alunos já servidos.

        Returns:
            Uma lista de dicionários para alunos elegíveis que não foram servidos,
            com uma chave 'info' adicionada/atualizada. Ordenada alfabeticamente por 'Nome'.
        """
        logger.debug("Filtrando %d alunos elegíveis contra %d prontuários servidos.",
                     len(eligible_students), len(served_pronts))

        eligible_not_served = []
        skipped_count = 0

        for student in eligible_students:
            pront = student.get("Pront")

            # Validação básica: Pula se pront está faltando ou é None (opcional mas boa prática)
            if not pront:
                logger.warning("Aluno elegível sem prontuário encontrado, pulando: %s",
                               student.get('Nome', 'Nome Desconhecido'))
                skipped_count += 1
                continue

            # --- Lógica Principal: Verifica se foi servido ---
            if pront in served_pronts and not_served:
                skipped_count += 1
                print(f"Aluno já servido: {pront}")
                continue  # Pula este aluno, ele já foi servido

            # --- Prepara dados para o aluno que NÃO foi servido ---
            student_copy = student.copy()  # Trabalha em uma cópia

            # Formata o campo 'info' para exibição (Turma | Pront)
            display_turma = student_copy.get("Turma", "S/ Turma")  # Fornece um fallback
            # Usa o pront original para exibição, talvez com fallback se fosse None (já tratado acima)
            display_pront = pront

            student_copy["info"] = f"{display_turma} | {display_pront}"
            student_copy["score"] = 100  # Adiciona score padrão (não usado aqui, mas pode ser útil)
            # Adiciona o aluno preparado aos resultados
            eligible_not_served.append(student_copy)

        logger.debug("Filtragem concluída. %d alunos não servidos encontrados, %d pulados (servidos ou inválidos).",
                     len(eligible_not_served), skipped_count)

        # Ordena a lista final alfabeticamente por nome para exibição consistente
        eligible_not_served.sort(key=lambda x: x.get("Nome", "").lower())
        for i, student in enumerate(eligible_not_served):
            # Remove o campo 'score' se não for necessário
            student["score"] = (i*100)//len(eligible_not_served)

        self._current_eligible_matches_data = eligible_not_served
        return eligible_not_served

    def _perform_fuzzy_search(
        self,
        search_term: str,
        eligible_students: List[Dict[str, Any]],
        served_pronts: Set[str],
    ) -> List[Dict[str, Any]]:
        """
        Realiza busca fuzzy na lista de alunos elegíveis.

        Args:
            search_term: O termo a ser buscado.
            eligible_students: Lista de dicionários dos alunos elegíveis.
            served_pronts: Conjunto de prontuários já servidos.

        Returns:
            Lista de dicionários dos alunos que correspondem ao termo,
            ordenada por pontuação (score) descendente.
        """
        term_lower = search_term.lower().strip()
        matches_found = []
        # Detecta se a busca é por prontuário (apenas dígitos, 'x', espaço)
        is_pront_search = bool(re.fullmatch(
            r"(?:[a-z]{2})?[\dx\s]+", term_lower, re.IGNORECASE))

        search_key = "Pront" if is_pront_search else "Nome"
        # Limpa prefixo do prontuário para busca fuzzy apenas no número
        cleaned_search_term = (
            PRONTUARIO_CLEANUP_REGEX.sub("", term_lower)
            if is_pront_search
            else term_lower
        )
        # Define função e limiar de score (pode ser ajustado)
        match_func = fuzz.partial_ratio  # Bom para substrings
        threshold = 85 if is_pront_search else 70

        # Itera sobre alunos elegíveis
        for student in eligible_students:
            pront = student.get("Pront")
            # Pula se já servido (dupla checagem)
            if pront in served_pronts:
                continue

            # Obtém o valor a ser comparado (Nome ou Pront)
            value_to_match_raw = student.get(search_key, "")
            if not value_to_match_raw:
                continue  # Pula se valor vazio

            value_to_match_lower = value_to_match_raw.lower()
            # Limpa prontuário se for busca por prontuário para comparação fuzzy
            if is_pront_search:
                value_to_compare = PRONTUARIO_CLEANUP_REGEX.sub("", value_to_match_lower)
            else:
                value_to_compare = value_to_match_lower

            # Calcula o score de similaridade
            score = match_func(cleaned_search_term, value_to_compare)

            # Condição especial: se for busca exata por prontuário (sem fuzzy), aumenta score
            if is_pront_search and cleaned_search_term == value_to_compare:
                score = 100  # Match exato

            # Se o score for suficiente
            if score >= threshold:
                student_copy = student.copy()  # Cria cópia para não modificar original
                # Formata a coluna 'info' (Turma | Pront)
                display_turma = student.get("Turma", "S/ Turma")  # Fallback
                # Usa o prontuário original (sem limpeza) para exibição
                display_pront = pront or "S/ Pront."
                student_copy["info"] = f"{display_turma} | {display_pront}"
                student_copy["score"] = score  # Adiciona score para ordenação
                matches_found.append(student_copy)

        # Ordena por score descendente, depois alfabeticamente por nome como desempate
        matches_found.sort(key=lambda x: (-x["score"], x.get("Nome", "").lower()))
        # Atualiza o cache interno dos resultados exibidos
        self._current_eligible_matches_data = matches_found
        return matches_found

    def _update_eligible_treeview(self, matches_data: List[Dict[str, Any]]):
        """Popula a SimpleTreeView de elegíveis com os resultados da busca."""
        if not self._eligible_students_tree:
            return  # Sai se a tabela não existe

        self._eligible_students_tree.delete_rows()  # Limpa tabela
        if not matches_data:
            # Mensagem opcional quando não há resultados pode ir no feedback label
            return  # Sai se não há resultados

        # Mapeia os dados do dicionário para as colunas da SimpleTreeView ('name', 'info', 'dish')
        rowdata = []
        for m in matches_data:
            # Garante que os valores sejam strings para o Treeview
            row = (
                str(m.get("Nome", "N/A")),
                str(m.get("info", "N/A")),  # 'info' já formatado
                str(m.get("Prato", "N/A")),  # Prato/Status da reserva
            )
            rowdata.append(row)

        try:
            # Constrói a tabela com os novos dados
            self._eligible_students_tree.build_table_data(rowdata=rowdata)
        except Exception as e:
            logger.exception(
                "Erro ao construir tabela de elegíveis (%s): %s", type(e).__name__, e
            )
            messagebox.showerror(
                UI_TEXTS.get("ui_error_title", "Erro de UI"),
                UI_TEXTS.get(
                    "error_display_results", "Não foi possível exibir os resultados."
                ),
                parent=self._app,
            )

    def _on_eligible_student_select(self, _=None):
        """Callback quando uma linha é selecionada na tabela de elegíveis."""
        if not self._eligible_students_tree:
            return

        selected_iid = self._eligible_students_tree.get_selected_iid()
        if selected_iid:
            try:
                # Encontra o índice do IID selecionado na lista de IIDs atual da Treeview
                # Esta abordagem é FRÁGIL se a ordem da Treeview e do cache divergir
                # (ex: por ordenação) É MELHOR obter os valores da linha selecionada e
                # encontrar o dict correspondente no cache
                selected_values = self._eligible_students_tree.get_row_values(selected_iid)
                if not selected_values:
                    raise ValueError("Não foi possível obter valores da linha selecionada.")

                # Assume que a primeira coluna (Nome) e segunda (Info com Pront) são
                # suficientes para identificar
                # Pode ser necessário ajustar se houver duplicatas exatas nesses campos
                selected_name = selected_values[0]
                selected_info = selected_values[1]  # Contém Turma | Pront

                # Encontra o dicionário correspondente no cache
                found_student_data = None
                for student_data in self._current_eligible_matches_data:
                    # Compara nome e info (que já contém prontuário formatado)
                    if (student_data.get("Nome") == selected_name and
                            student_data.get("info") == selected_info):
                        found_student_data = student_data
                        break  # Encontrou

                if found_student_data:
                    self._selected_eligible_data = found_student_data
                    # Atualiza a UI com os dados selecionados
                    self._update_preview_label()
                    if self._register_button:
                        self._register_button.config(state=NORMAL)
                    # Atualiza feedback (opcional)
                    pront = self._selected_eligible_data.get("Pront", "?")
                    if self._action_feedback_label:
                        self._action_feedback_label.config(
                            text=f"Selecionado: {pront}", bootstyle=INFO
                        )  # type: ignore
                else:
                    # Inconsistência entre Treeview e cache de dados
                    logger.error(
                        "Não foi possível encontrar dados no cache para a linha selecionada: %s",
                        selected_values
                    )
                    self._selected_eligible_data = None
                    self._update_preview_label(error=True)
                    if self._register_button:
                        self._register_button.config(state=DISABLED)
                    if self._action_feedback_label:
                        self._action_feedback_label.config(
                            text=UI_TEXTS.get("select_error", "Erro Seleção"),
                            bootstyle=DANGER,
                        )  # type: ignore

            except (ValueError, IndexError, AttributeError, tk.TclError) as e:
                # Erros ao buscar índice, acessar cache ou atualizar UI
                logger.exception(
                    "Erro ao processar seleção de elegível (IID: %s): %s",
                    selected_iid, e
                )
                self._selected_eligible_data = None
                # Mostra erro no preview
                self._update_preview_label(error=True)
                if self._register_button:
                    self._register_button.config(state=DISABLED)
                if self._action_feedback_label:
                    self._action_feedback_label.config(
                        text=UI_TEXTS.get("select_error", "Erro Seleção"),
                        bootstyle=DANGER,
                    )  # type: ignore
        else:
            # Nenhuma linha selecionada (evento de desseleção)
            self._selected_eligible_data = None
            self._update_preview_label()  # Limpa o preview
            if self._register_button:
                self._register_button.config(state=DISABLED)
            # Limpa feedback ou volta para placeholder se a busca estiver vazia
            search_term = self._search_entry_var.get()
            if self._action_feedback_label:
                if len(search_term) < 2:
                    placeholder = (UI_TEXTS.get("search_placeholder_empty",
                                                "Digite para buscar...") if not search_term else
                                   UI_TEXTS.get("search_placeholder_min_chars",
                                                "Mínimo 2 caracteres..."))
                    self._action_feedback_label.config(
                        text=placeholder, bootstyle=DEFAULT)  # type: ignore
                else:
                    # Se havia resultados, apenas limpa o feedback de seleção
                    if self._current_eligible_matches_data:
                        self._action_feedback_label.config(
                            text=UI_TEXTS.get("matches_found", "{count} resultado(s)").format(
                                count=len(self._current_eligible_matches_data)
                            ), bootstyle=INFO)  # type: ignore
                    else:
                        # Se não havia resultados, mantém a mensagem de "não encontrado"
                        self._action_feedback_label.config(
                            text=UI_TEXTS.get("no_matches_found", "Nenhum resultado encontrado"),
                            bootstyle=WARNING)  # type: ignore

    def _update_preview_label(self, error: bool = False):
        """Atualiza o label de preview com informações do aluno selecionado ou mensagens padrão."""
        if not self._selected_student_label:
            return  # Sai se o label não existe

        style = "inverse-secondary"  # Padrão neutro
        if error:
            text = UI_TEXTS.get("error_selecting_data", "Erro ao obter dados do aluno.")
            style = "inverse-danger"
        elif self._selected_eligible_data:
            # Monta o texto com os dados do aluno
            pront = self._selected_eligible_data.get("Pront", "?")
            nome = self._selected_eligible_data.get("Nome", "?")
            turma = self._selected_eligible_data.get("Turma", "S/ Turma")  # Fallback
            prato = self._selected_eligible_data.get("Prato", "N/Definido")  # Fallback

            # Usa a string de formatação do UI_TEXTS
            text = UI_TEXTS.get(
                "selected_student_info",
                "Pront: {pront}\nNome: {nome}\nTurma: {turma}\nPrato: {prato}",
            ).format(
                pront=pront,
                nome=nome,
                turma=turma,
                prato=prato,
            )
            style = "inverse-info"
        else:
            # Texto padrão quando nada está selecionado
            text = UI_TEXTS.get(
                "select_student_preview", "Selecione um aluno da lista acima."
            )
            # Mantém o estilo padrão 'inverse-secondary'

        # Atualiza o texto e o estilo do label
        self._selected_student_label.config(text=text, bootstyle=style)  # type: ignore

    def _register_selected_eligible(self):
        """Tenta registrar o aluno atualmente armazenado em _selected_eligible_data."""
        if not self._selected_eligible_data:
            # Log em vez de messagebox, pois o botão deve estar desabilitado
            logger.warning(
                "Tentativa de registro sem aluno selecionado (botão deveria estar DISABLED).")
            # Garantir que o botão esteja desabilitado
            if self._register_button:
                self._register_button.config(state=DISABLED)
            return

        # Extrai dados necessários para o registro
        pront = self._selected_eligible_data.get("Pront")
        nome = self._selected_eligible_data.get("Nome", "?")
        turma = self._selected_eligible_data.get("Turma", "")
        prato = self._selected_eligible_data.get("Prato", "?")
        hora_consumo = datetime.now().strftime("%H:%M:%S")  # Hora atual

        # Validação básica
        if not pront:  # Checa apenas prontuário, nome pode ser "?" em alguns casos
            logger.error(
                "Não é possível registrar: Prontuário ausente ou inválido. Dados: %s",
                self._selected_eligible_data,
            )
            messagebox.showerror(
                UI_TEXTS.get("registration_error_title", "Erro no Registro"),
                UI_TEXTS.get(
                    "error_invalid_prontuario",  # Mensagem específica
                    "Prontuário do aluno selecionado está ausente ou inválido.",
                ),
                parent=self._app,
            )
            # Não limpa a seleção aqui, permite ao usuário corrigir ou selecionar outro
            return

        # Monta a tupla esperada pelo SessionManager
        student_tuple: Tuple[str, str, str, str, str] = (
            str(pront),
            str(nome),
            str(turma),
            str(hora_consumo),
            str(prato),
        )

        logger.info("Registrando aluno elegível via painel: %s - %s", pront, nome)
        # Chama o método de registro no SessionManager
        success = self._session_manager.record_consumption(student_tuple)

        # --- Feedback e Atualização Pós-Registro ---
        if success:
            logger.info("Aluno %s registrado com sucesso pelo SessionManager.", pront)
            # Notifica a App principal para atualizar o painel de status
            self._app.notify_registration_success(student_tuple)
            # Atualiza o feedback local
            if self._action_feedback_label:
                self._action_feedback_label.config(
                    text=UI_TEXTS.get(
                        "registered_feedback", "Registrado: {pront}"
                    ).format(pront=pront),
                    bootstyle=SUCCESS,
                )  # type: ignore
            # Limpa a busca, foca para o próximo registro e reseta seleção/botão
            # É importante resetar antes de limpar/focar
            self._selected_eligible_data = None
            self._update_preview_label()
            if self._register_button:
                self._register_button.config(state=DISABLED)
            self.clear_search()  # Isso já foca a entrada

        else:
            # Falha no registro (já servido ou erro DB)
            logger.warning("Falha ao registrar %s via SessionManager.", pront)
            # Verifica se o motivo foi já estar servido
            is_served = pront and pront in self._session_manager.get_served_pronts()
            if is_served:
                # Exibe aviso de já registrado
                messagebox.showwarning(
                    UI_TEXTS.get("already_registered_title", "Já Registrado"),
                    UI_TEXTS.get(
                        "already_registered_message", "{nome} ({pront})\n"
                        "Já consta como registrado nesta sessão."
                    ).format(nome=nome, pront=pront),
                    parent=self._app,
                )
                # Atualiza feedback local
                fb_text = UI_TEXTS.get(
                    "already_registered_feedback", "JÁ REGISTRADO: {pront}"
                ).format(pront=pront)
                fb_style = WARNING
                # Limpa a seleção e busca se já estava registrado
                self._selected_eligible_data = None
                self._update_preview_label()
                if self._register_button:
                    self._register_button.config(state=DISABLED)
                self.clear_search()  # Isso já foca

            else:
                # Outro erro (DB, etc. - erro já logado pelo SessionManager)
                messagebox.showerror(
                    UI_TEXTS.get("registration_error_title", "Erro no Registro"),
                    UI_TEXTS.get(
                        "registration_error_message",
                        "Não foi possível registrar o consumo para:\n{nome} ({pront})\n"
                        "Verifique os logs para detalhes."
                    ).format(nome=nome, pront=pront),
                    parent=self._app,
                )
                # Atualiza feedback local
                fb_text = UI_TEXTS.get(
                    "error_registering_feedback", "ERRO registro {pront}"
                ).format(pront=pront)
                fb_style = DANGER
                # Não limpa a seleção aqui, pode ser um erro temporário

            if self._action_feedback_label:
                self._action_feedback_label.config(text=fb_text, bootstyle=fb_style)  # type: ignore

            # Garante que o botão de registrar seja desabilitado se a seleção foi removida
            if not self._selected_eligible_data and self._register_button:
                self._register_button.config(state=DISABLED)
