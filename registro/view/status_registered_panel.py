# ----------------------------------------------------------------------------
# File: registro/view/status_registered_panel.py (Painel de Status/Registrados)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Define o painel direito da interface, exibindo contadores e a lista
de alunos já registrados, com funcionalidade de remoção.
"""
import logging
import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import ttkbootstrap as ttk
from ttkbootstrap.constants import CENTER, PRIMARY, WARNING  # Importa constantes usadas

# Importações locais relativas
from registro.control.constants import UI_TEXTS
from registro.control.session_manage import SessionManager
from registro.view.simple_treeview import SimpleTreeView

# Evita importação circular para type hinting
if TYPE_CHECKING:
    from .registration_app import RegistrationApp

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Painel de Status e Registrados (Direita)
# ----------------------------------------------------------------------------


class StatusRegisteredPanel(ttk.Frame):
    """
    Painel exibindo contadores (Registrados/Restantes) e a tabela de
    alunos já registrados na sessão atual, com opção de remoção.
    """

    ACTION_COLUMN_ID = "action_col"  # ID interno para a coluna de ação
    ACTION_COLUMN_TEXT = UI_TEXTS.get(
        "col_action", "❌"
    )  # Texto/ícone do cabeçalho da coluna

    def __init__(
        self,
        master: tk.Widget,
        app: "RegistrationApp",  # Usa type hint
        session_manager: "SessionManager",  # Usa type hint
    ):
        """
        Inicializa o painel de Status/Registrados.

        Args:
            master: O widget pai (geralmente o PanedWindow).
            app: Referência à instância principal da RegistrationApp.
            session_manager: Instância do SessionManager para acesso aos dados.
        """
        super().__init__(master, padding=(10, 10, 10, 0))  # Padding ajustado
        self._app = app
        self._session_manager:SessionManager = session_manager

        # --- Atributos de Widgets Internos ---
        self._registered_count_label: Optional[ttk.Label] = None
        self._remaining_count_label: Optional[ttk.Label] = None
        self._registered_students_table: Optional[SimpleTreeView] = None

        # Configuração do Grid interno
        # Área da tabela (row 0) expande verticalmente
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)  # Expansão horizontal total

        # Definição das colunas da tabela de registrados
        # (gerada no método _get_registered_cols_definition)
        self._registered_cols_definition: List[Dict[str, Any]] = []

        # Criação dos widgets internos
        # A ordem de criação pode ser importante para o layout do grid
        self._create_registered_table()  # Cria a tabela primeiro (row 0)
        self._create_counters_area()  # Cria os contadores abaixo (row 1)

        # Bindings da tabela (se a tabela foi criada)
        if self._registered_students_table:
            # Clique simples para ação (mais intuitivo que duplo clique aqui)
            self._registered_students_table.view.bind(
                "<Button-1>", self._on_registered_table_click
            )
            # Tecla Delete quando a tabela tem foco
            self._registered_students_table.view.bind(
                "<Delete>", self._on_table_delete_key
            )
            # Tecla Backspace (alternativa comum)
            self._registered_students_table.view.bind(
                "<BackSpace>", self._on_table_delete_key
            )

    def _get_registered_cols_definition(self) -> List[Dict[str, Any]]:
        """Retorna a definição das colunas para a tabela de registrados."""
        # Usa UI_TEXTS para os cabeçalhos visíveis
        return [
            {
                "text": UI_TEXTS.get("col_prontuario", "🆔 Pront."),
                "stretch": False,
                "width": 100,
                "iid": "pront",
                "minwidth": 80,
            },
            {
                "text": UI_TEXTS.get("col_nome", "✍️ Nome"),
                "stretch": True,  # Permite que o nome expanda
                "iid": "nome",
                "minwidth": 150,
            },
            {
                "text": UI_TEXTS.get("col_turma", "👥 Turma"),
                "stretch": False,
                "width": 150,
                "iid": "turma",
                "minwidth": 100,
            },
            {
                "text": UI_TEXTS.get("col_hora", "⏱️ Hora"),
                "stretch": False,
                "width": 70,
                "anchor": CENTER,
                "iid": "hora",
                "minwidth": 60,
            },
            {
                "text": UI_TEXTS.get("col_prato_status", "🍽️ Prato/Status"),
                "stretch": True,  # Permite expandir
                "width": 150,
                "iid": "prato",
                "minwidth": 100,
            },
            # Coluna de Ação (Remoção)
            {
                "text": self.ACTION_COLUMN_TEXT,  # Ícone/Texto de ação
                "stretch": False,
                "width": 40,  # Largura fixa pequena
                "anchor": CENTER,
                "iid": self.ACTION_COLUMN_ID,  # ID específico
                "minwidth": 30,
            },
        ]

    def _create_counters_area(self):
        """Cria a área inferior (row 1) com os labels de contagem."""
        counters_frame = ttk.Frame(self, padding=(0, 5))  # Padding vertical
        # Posiciona abaixo da tabela (row 1)
        counters_frame.grid(row=1, column=0, sticky="ew")
        counters_frame.columnconfigure(0, weight=1)  # Expande primeira label
        counters_frame.columnconfigure(1, weight=1)  # Expande segunda label

        # Label Contagem Registrados
        self._registered_count_label = ttk.Label(
            counters_frame,
            text=UI_TEXTS.get(
                "registered_count_label", "Registrados: -"
            ),  # Texto inicial
            bootstyle="secondary",  # Estilo inicial neutro # type: ignore
            font=("Helvetica", 10, "bold"),
            padding=(5, 2),  # Padding interno
            anchor=CENTER,
        )
        self._registered_count_label.grid(
            row=0, column=0, sticky="ew", padx=(0, 5)
        )  # Ocupa coluna 0

        # Label Contagem Elegíveis/Restantes
        self._remaining_count_label = ttk.Label(
            counters_frame,
            text=UI_TEXTS.get(
                "remaining_count_label", "Elegíveis: - / Restantes: -"
            ),  # Texto inicial
            bootstyle="secondary",  # Estilo inicial neutro # type: ignore
            font=("Helvetica", 10, "bold"),
            padding=(5, 2),  # Padding interno
            anchor=CENTER,
        )
        self._remaining_count_label.grid(
            row=0, column=1, sticky="ew", padx=(5, 0)
        )  # Ocupa coluna 1

    def _create_registered_table(self):
        """Cria a tabela (SimpleTreeView) para exibir os alunos registrados (row 0)."""
        reg_frame = ttk.Labelframe(
            self,
            text=UI_TEXTS.get(
                "registered_students_label",
                "✅ Alunos Registrados (Clique ❌ para Remover)",
            ),
            padding=(5, 5),
        )
        # Posiciona na linha superior (row 0), ocupando toda a largura
        reg_frame.grid(row=0, column=0, sticky="nsew")
        reg_frame.rowconfigure(
            0, weight=1
        )  # Tabela expande verticalmente dentro do frame
        reg_frame.columnconfigure(
            0, weight=1
        )  # Tabela expande horizontalmente dentro do frame

        # Obtém a definição das colunas
        self._registered_cols_definition = self._get_registered_cols_definition()

        # Cria a instância da SimpleTreeView
        self._registered_students_table = SimpleTreeView(
            master=reg_frame,
            coldata=self._registered_cols_definition,
            height=15,  # Altura inicial (ajustável)
            #bootstyle="default",  # Estilo padrão para a tabela de registrados
        )
        self._registered_students_table.grid(row=0, column=0, sticky="nsew")

        # Configura ordenação para todas as colunas exceto a de ação
        sortable_cols_comp = [
            str(cd.get("iid"))  # Usa get com None como fallback
            for cd in self._registered_cols_definition
            if cd.get("iid") and cd.get("iid") != self.ACTION_COLUMN_ID
        ]
        sortable_cols: List[str] | None = (
            sortable_cols_comp if sortable_cols_comp else None
        )
        self._registered_students_table.setup_sorting(sortable_columns=sortable_cols)

    # --- Métodos Públicos (Controle Externo e Atualização) ---

    def load_registered_students(self):
        """Carrega ou recarrega os dados na tabela de alunos registrados."""
        if not self._registered_students_table:
            logger.warning(
                "Tabela de registrados não inicializada. Impossível carregar."
            )
            return

        logger.debug("Carregando/recarregando tabela de registrados...")
        try:
            # Não precisa limpar antes, build_table_data já faz isso
            # self._registered_students_table.delete_rows()
            served_data = self._session_manager.get_served_students_details()
            if served_data:
                # Adiciona o texto/ícone da coluna de ação a cada linha
                # Garante que todos os dados sejam strings
                rows_with_action = [
                    tuple(map(str, row)) + (self.ACTION_COLUMN_TEXT,)
                    for row in served_data
                    if len(row) == 5  # Checa se tem 5 colunas de dados
                ]
                self._registered_students_table.build_table_data(
                    rowdata=rows_with_action
                )
                logger.info(
                    "Carregados %d alunos registrados na tabela.", len(rows_with_action)
                )
                # Se houve linhas inválidas puladas
                if len(rows_with_action) < len(served_data):
                    logger.warning(
                        "%d linhas de 'servidos' foram puladas devido a"
                        " formato inválido.",
                        len(served_data) - len(rows_with_action),
                    )
            else:
                # Limpa a tabela explicitamente se não há dados
                self._registered_students_table.delete_rows()
                logger.info("Nenhum aluno registrado para exibir na tabela.")

            # Atualiza contadores após carregar a tabela
            self.update_counters()

        except Exception as e:
            logger.exception(
                "Erro ao carregar tabela de registrados (%s): %s", type(e).__name__, e
            )
            messagebox.showerror(
                UI_TEXTS.get("error_title", "Erro"),
                UI_TEXTS.get(
                    "error_loading_registered",
                    "Não foi possível carregar a lista de alunos registrados.",
                ),
                parent=self._app,  # Usa a janela principal como pai
            )
            # Limpa a tabela em caso de erro grave
            if self._registered_students_table:
                self._registered_students_table.delete_rows()
            self.update_counters()  # Reseta contadores

    def update_counters(self):
        """Atualiza os labels dos contadores (Registrados/Restantes)."""
        if not self._registered_count_label or not self._remaining_count_label:
            logger.warning("Labels de contador não inicializados para atualização.")
            return

        reg_text = UI_TEXTS.get("registered_count_label", "Registrados: -")
        rem_text = UI_TEXTS.get("remaining_count_label", "Elegíveis: - / Restantes: -")
        reg_style = "secondary"  # Estilo padrão
        rem_style = "secondary"  # Estilo padrão

        # Calcula contagens apenas se houver sessão ativa
        if self._session_manager and self._session_manager.get_session_info():
            try:
                registered_count = len(self._session_manager.get_served_pronts())
                # get_eligible_students retorna apenas os NÃO servidos
                eligible_not_served = self._session_manager.get_eligible_students()
                eligible_not_served_count = (
                    len(eligible_not_served) if eligible_not_served is not None else 0
                )
                # Total elegível = não servidos + registrados
                total_eligible_count = eligible_not_served_count + registered_count
                # Restantes = elegíveis não servidos
                remaining_count = eligible_not_served_count

                # Formata os textos usando UI_TEXTS
                reg_text = UI_TEXTS.get(
                    "registered_count_label", "Registrados: {count}"
                ).format(count=registered_count)
                rem_text = UI_TEXTS.get(
                    "remaining_count_label",
                    "Elegíveis: {eligible_count} / Restantes: {remaining_count}",
                ).format(
                    eligible_count=total_eligible_count, remaining_count=remaining_count
                )
                # Define estilo com base nas contagens (opcional)
                reg_style = PRIMARY if registered_count >= 0 else "danger"
                rem_style = PRIMARY if remaining_count >= 0 else "danger"

            except Exception as e:
                logger.exception(
                    "Erro ao calcular/atualizar contadores (%s): %s",
                    type(e).__name__,
                    e,
                )
                # Define textos e estilos de erro
                reg_text = UI_TEXTS.get("registered_count_label", "Registrados: Erro")
                rem_text = UI_TEXTS.get(
                    "remaining_count_label", "Elegíveis: Erro / Restantes: Erro"
                )
                reg_style = "danger"
                rem_style = "danger"

        # Atualiza os labels e seus estilos
        self._registered_count_label.config(text=reg_text, bootstyle=reg_style)  # type: ignore
        self._remaining_count_label.config(text=rem_text, bootstyle=rem_style)  # type: ignore

    def clear_table(self):
        """Limpa a tabela de registrados e reseta contadores
        (usado quando a sessão termina/falha)."""
        logger.debug("Limpando tabela de registrados e contadores.")
        if self._registered_students_table:
            self._registered_students_table.delete_rows()
        self.update_counters()  # Reseta contadores para o estado sem sessão

    def remove_row_from_table(self, iid_to_delete: str):
        """Remove uma linha específica da tabela pela sua IID e atualiza contadores."""
        if not self._registered_students_table:
            return
        try:
            # Verifica se a linha existe antes de tentar deletar
            if self._registered_students_table.view.exists(iid_to_delete):
                self._registered_students_table.delete_rows([iid_to_delete])
                logger.debug(
                    "Linha %s removida da tabela de registrados UI.", iid_to_delete
                )
                # Atualiza contadores após remover da UI
                self.update_counters()
            else:
                logger.warning(
                    "Tentativa de remover IID %s que não existe na tabela UI.",
                    iid_to_delete,
                )
                # Recarrega a tabela inteira se houver inconsistência
                self.load_registered_students()

        except Exception as e:
            logger.exception("Erro ao remover linha %s da UI: %s", iid_to_delete, e)
            # Se falhar, força recarregamento completo como fallback
            self.load_registered_students()

    # --- Métodos Internos (Handlers de Eventos) ---

    def _on_registered_table_click(self, event: tk.Event):
        """Handler para cliques na tabela (detecta clique na coluna de ação)."""
        if not self._registered_students_table:
            return
        # Identifica a célula clicada
        iid, col_id = self._registered_students_table.identify_clicked_cell(event)

        # Se clicou na coluna de ação de uma linha válida
        if iid and col_id == self.ACTION_COLUMN_ID:
            logger.debug("Coluna de ação clicada para a linha iid: %s", iid)
            # Pede confirmação e inicia processo de deleção
            self._confirm_and_delete_consumption(iid)
        # Opcional: Selecionar a linha com clique simples em qualquer célula (exceto ação)
        elif iid and self._registered_students_table.view.exists(iid):
            # Evita que o clique na coluna de ação também selecione a linha
            if col_id != self.ACTION_COLUMN_ID:
                try:
                    # Foca e seleciona a linha clicada
                    self._registered_students_table.view.focus(iid)
                    if self._registered_students_table.get_selected_iid() != iid:
                        self._registered_students_table.view.selection_set(iid)
                except tk.TclError as e:
                    logger.warning("Erro Tcl ao focar/selecionar linha %s: %s", iid, e)

    def _on_table_delete_key(self, _=None):
        """Handler para tecla Delete/Backspace na tabela de registrados."""
        if not self._registered_students_table:
            return
        selected_iid = self._registered_students_table.get_selected_iid()
        if selected_iid:
            logger.debug(
                "Tecla Delete/Backspace pressionada para iid selecionado: %s",
                selected_iid,
            )
            # Pede confirmação e inicia processo de deleção para a linha selecionada
            self._confirm_and_delete_consumption(selected_iid)
        else:
            logger.debug(
                "Tecla Delete/Backspace pressionada, mas nenhuma linha selecionada."
            )

    def _confirm_and_delete_consumption(self, iid_to_delete: str):
        """Pede confirmação ao usuário e, se confirmado, chama a App principal para deletar."""
        if not self._registered_students_table:
            return

        # Obtém os dados da linha completa (incluindo a coluna de ação)
        row_values_full = self._registered_students_table.get_row_values(iid_to_delete)
        if not row_values_full or len(row_values_full) != len(
            self._registered_cols_definition
        ):
            # Compara com o número esperado de colunas na definição
            logger.error(
                "Não foi possível obter valores válidos (esperado %d, obtido %d) para iid %s"
                " ao tentar deletar.",
                len(self._registered_cols_definition),
                len(row_values_full) if row_values_full else 0,
                iid_to_delete,
            )
            messagebox.showerror(
                UI_TEXTS.get("error_title", "Erro Interno"),
                UI_TEXTS.get(
                    "error_getting_row_data",
                    "Erro ao obter dados da linha selecionada para remoção.",
                ),
                parent=self._app,
            )
            return

        # Extrai os dados relevantes para a lógica (as 5 primeiras colunas definidas)
        try:
            # Pega os 5 primeiros valores, que correspondem aos dados do aluno
            data_for_logic = tuple(row_values_full[:5])
            pront, nome = (
                data_for_logic[0],
                data_for_logic[1],
            )  # Pega pront e nome para a mensagem

            # Validação extra (prontuário não pode ser vazio)
            if not pront:
                raise ValueError("Prontuário vazio na linha selecionada para deleção.")
        except (IndexError, ValueError) as e:
            logger.error(
                "Erro ao extrair ou validar dados da linha %s para deleção: %s. Dados: %s",
                iid_to_delete,
                e,
                row_values_full,
            )
            messagebox.showerror(
                UI_TEXTS.get("error_title", "Erro de Dados"),
                UI_TEXTS.get(
                    "error_processing_row_data",
                    "Erro ao processar os dados da linha selecionada. Verifique os logs.",
                ),
                parent=self._app,
            )
            return

        # Pede confirmação
        confirm_title = UI_TEXTS.get("confirm_deletion_title", "Confirmar Remoção")
        confirm_msg_template = UI_TEXTS.get(
            "confirm_deletion_message",
            "Tem certeza que deseja remover o registro para:\n\nProntuário: {pront}\nNome: {nome}?",
        )
        confirm_msg = confirm_msg_template.format(pront=pront, nome=nome)

        if messagebox.askyesno(
            confirm_title,
            confirm_msg,
            icon=WARNING,  # Constante ttkbootstrap para ícone de aviso
            parent=self._app,  # Mostra sobre a janela principal
        ):
            # Delegação para a App principal tratar a deleção no backend e UI
            logger.info(
                "Confirmada deleção de consumo para %s (iid UI: %s). Delegando para App.",
                pront,
                iid_to_delete,
            )
            # Passa os dados lógicos e o IID da UI para a App principal
            self._app.handle_consumption_deletion(data_for_logic, iid_to_delete)
        else:
            logger.debug("Deleção de %s cancelada pelo usuário.", pront)
