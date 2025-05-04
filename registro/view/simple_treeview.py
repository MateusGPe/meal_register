# ----------------------------------------------------------------------------
# File: registro/view/simple_treeview.py (Helper TreeView)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Fornece a classe auxiliar SimpleTreeView, um wrapper para ttk.Treeview.
"""
import logging
import re
import tkinter as tk
from tkinter import ttk
from functools import partial
from typing import Any, Dict, List, Optional, Tuple

from ttkbootstrap.constants import END, HORIZONTAL, VERTICAL, W

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Classe SimpleTreeView (Helper para Tabelas)
# ----------------------------------------------------------------------------


class SimpleTreeView:
    """
    Um wrapper em torno de ttk.Treeview que fornece funcionalidades comuns
    de tabela como carregamento de dados, manipulação de linhas, tratamento
    de seleção, ordenação e identificação de cliques.
    """

    def __init__(
        self,
        master: tk.Widget,
        coldata: List[Dict[str, Any]],
        height: int = 10,
        bootstyle: str = "light",
    ):
        """
        Inicializa a SimpleTreeView.

        Args:
            master: O widget pai.
            coldata: Lista de dicionários definindo as colunas. Chaves esperadas
                     por dict: 'text' (cabeçalho), 'iid' (ID interno único),
                     'width', 'minwidth', 'stretch', 'anchor'.
            height: Número inicial de linhas visíveis.
            bootstyle: Estilo ttkbootstrap para o widget Treeview.
        """
        self.master = master
        self.coldata = coldata
        # IDs internos das colunas (gerados a partir de iid ou text)
        self.column_ids: List[str] = []
        # Mapeia ID da coluna para texto do cabeçalho
        self.column_text_map: Dict[str, str] = {}

        # Processa coldata para gerar IDs e mapeamento
        for i, cd in enumerate(self.coldata):
            iid = cd.get("iid")  # ID interno preferencial
            text = cd.get("text", f"col_{i}")  # Texto do cabeçalho
            # Usa iid se fornecido, senão gera um ID a partir do texto
            fallback_id = str(iid) if iid else re.sub(r"\W|^(?=\d)", "_", text).lower()
            col_id = fallback_id
            # Garante IDs únicos mesmo se houver iids/textos duplicados
            if col_id in self.column_ids:
                original_col_id = col_id
                # Adiciona índice para garantir unicidade
                col_id = f"{col_id}_{i}"
                logger.warning(
                    "ID de coluna duplicado '%s' detectado, usando único '%s'.",
                    original_col_id,
                    col_id,
                )
            self.column_ids.append(col_id)
            self.column_text_map[col_id] = text
        logger.debug("Colunas SimpleTreeView: IDs=%s", self.column_ids)

        # --- Criação dos Widgets ---
        self.frame = ttk.Frame(master)
        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

        # Cria o Treeview
        self.view = ttk.Treeview(
            self.frame,
            columns=self.column_ids,  # Define as colunas pelo ID interno
            show="headings",  # Mostra apenas cabeçalhos, não a coluna #0
            height=height,
            selectmode="browse",  # Permite selecionar apenas uma linha
            style="Custom.Treeview",  # Estilo ttkbootstrap
            bootstyle=bootstyle,  # type: ignore
        )
        self.view.grid(row=0, column=0, sticky="nsew")

        # Scrollbars
        sb_v = ttk.Scrollbar(self.frame, orient=VERTICAL, command=self.view.yview)
        sb_v.grid(row=0, column=1, sticky="ns")
        sb_h = ttk.Scrollbar(self.frame, orient=HORIZONTAL, command=self.view.xview)
        sb_h.grid(row=1, column=0, sticky="ew")
        self.view.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)

        # Configura as propriedades das colunas
        self._configure_columns()

    def _configure_columns(self):
        """Configura as propriedades (largura, alinhamento, etc.) das colunas."""
        for i, cd in enumerate(self.coldata):
            col_id = self.column_ids[i]  # ID interno da coluna
            # Obtém propriedades do coldata com valores padrão
            width = cd.get("width", 100)
            minwidth = cd.get("minwidth", 40)
            stretch = cd.get("stretch", False)
            anchor = cd.get("anchor", W)  # Alinhamento padrão à esquerda
            text = cd.get("text", col_id)  # Texto do cabeçalho

            try:
                # Configura a coluna
                self.view.column(
                    col_id,
                    width=width,
                    minwidth=minwidth,
                    stretch=stretch,
                    anchor=anchor,
                )
                # Configura o cabeçalho
                self.view.heading(col_id, text=text, anchor=anchor)
            except tk.TclError as e:
                # Erro comum se o ID da coluna for inválido para Tcl
                logger.error(
                    "Erro ao configurar coluna '%s' (Texto: '%s'): %s", col_id, text, e
                )

    def setup_sorting(self, sortable_columns: Optional[List[str]] = None):
        """
        Habilita a ordenação por clique no cabeçalho para colunas especificadas.

        Args:
            sortable_columns: Lista de IDs de colunas que devem ser ordenáveis.
                              Se None, todas as colunas são configuradas.
        """
        target_col_ids = (
            sortable_columns if sortable_columns is not None else self.column_ids
        )
        logger.debug("Configurando ordenação para colunas: %s", target_col_ids)
        for col_id in target_col_ids:
            if col_id in self.column_ids:
                try:
                    # Define o comando a ser chamado ao clicar no cabeçalho
                    # Usa partial para passar o ID da coluna e o estado inicial (não reverso)
                    self.view.heading(
                        col_id, command=partial(self.sort_column, col_id, False)
                    )
                except tk.TclError as e:
                    logger.error(
                        "Erro ao definir comando de ordenação para coluna '%s': %s",
                        col_id,
                        e,
                    )
            else:
                logger.warning(
                    "Não é possível configurar ordenação para ID de coluna inexistente: '%s'",
                    col_id,
                )

    def sort_column(self, col_id: str, reverse: bool):
        """Ordena os itens da treeview com base nos valores da coluna especificada."""
        if col_id not in self.column_ids:
            logger.error(
                "Não é possível ordenar por ID de coluna desconhecido: %s", col_id
            )
            return
        logger.debug("Ordenando por coluna '%s', reverso=%s", col_id, reverse)

        try:
            # Obtém os dados da coluna para cada item na Treeview: (valor, iid_item)
            data = [
                (self.view.set(iid, col_id), iid) for iid in self.view.get_children("")
            ]
        except tk.TclError as e:
            logger.error(
                "Erro de ordenação (obter dados) para coluna '%s': %s", col_id, e
            )
            return

        try:
            # Define a chave de ordenação: minúsculo para strings, valor original para outros
            def sort_key_func(item_tuple):
                value = item_tuple[0]
                # Tenta converter para número se possível (melhora ordenação numérica)
                try:
                    return float(value)
                except ValueError:
                    pass
                try:
                    return int(value)
                except ValueError:
                    pass
                # Se não for número, usa string minúscula
                return str(value).lower() if isinstance(value, str) else value

            # Ordena a lista de dados
            data.sort(key=sort_key_func, reverse=reverse)
        except Exception as sort_err:
            logger.exception(
                "Erro de ordenação (ordenar dados) para coluna '%s': %s",
                col_id,
                sort_err,
            )
            return

        # Move os itens na Treeview para a nova ordem
        for index, (_, iid) in enumerate(data):
            try:
                # Move item para a nova posição (index)
                self.view.move(iid, "", index)
            except tk.TclError as move_err:
                logger.error("Erro de ordenação (mover item) '%s': %s", iid, move_err)

        # Atualiza o comando do cabeçalho para inverter a ordenação no próximo clique
        try:
            self.view.heading(
                col_id, command=partial(self.sort_column, col_id, not reverse)
            )
        except tk.TclError as head_err:
            logger.error(
                "Erro de ordenação (atualizar comando cabeçalho) para '%s': %s",
                col_id,
                head_err,
            )

    def identify_clicked_cell(
        self, event: tk.Event
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Identifica o ID do item (linha) e o ID da coluna clicados em um evento.

        Args:
            event: O objeto de evento do Tkinter (geralmente de um clique).

        Returns:
            Uma tupla (iid_linha, id_coluna). Retorna (None, None) se o clique
            não foi em uma célula válida.
        """
        try:
            # Identifica a região clicada (célula, cabeçalho, etc.)
            region = self.view.identify_region(event.x, event.y)
            if region != "cell":  # Só processa cliques em células
                return None, None
            # Identifica o item (linha) na posição do evento
            # Mais robusto que identify("item",...)
            iid = self.view.identify_row(event.y)
            # Identifica a coluna simbólica (ex: '#1', '#2')
            col_symbol = self.view.identify_column(event.x)
            # Converte o símbolo para índice numérico (0-based)
            col_index = int(col_symbol.replace("#", "")) - 1
            # Obtém o ID interno da coluna a partir do índice
            column_id = self.column_id_from_index(col_index)
            return iid, column_id
        except (ValueError, IndexError, TypeError, tk.TclError) as e:
            logger.warning("Não foi possível identificar célula clicada: %s", e)
            return None, None

    def grid(self, **kwargs):
        """Passa opções de grid para o frame principal da SimpleTreeView."""
        self.frame.grid(**kwargs)

    def pack(self, **kwargs):
        """Passa opções de pack para o frame principal da SimpleTreeView."""
        self.frame.pack(**kwargs)

    def delete_rows(self, iids: Optional[List[str]] = None):
        """
        Deleta linhas especificadas (por IID) ou todas as linhas se iids for None.

        Args:
            iids: Lista de IDs das linhas a serem deletadas. Se None, deleta todas.
        """
        # Define os IIDs alvo (ou todos se None)
        target_iids = iids if iids is not None else self.view.get_children()
        if not target_iids:  # Nada a deletar
            return
        try:
            # Deleta os itens (o '*' desempacota a lista/tupla)
            self.view.delete(*target_iids)
        except tk.TclError as e:
            logger.error("Erro ao deletar linhas %s: %s", target_iids, e)

    def build_table_data(self, rowdata: List[Tuple]):
        """Limpa a tabela e a reconstrói com novos dados."""
        self.delete_rows()  # Limpa a tabela atual
        # Itera sobre os novos dados e insere cada linha
        for row_values in rowdata:
            try:
                # Verifica se o número de valores corresponde ao número de colunas
                if len(row_values) == len(self.column_ids):
                    self.view.insert("", END, values=row_values)
                else:
                    logger.warning(
                        "Incompatibilidade no número de colunas ao inserir linha:"
                        " %d valores vs %d colunas. Linha: %s",
                        len(row_values),
                        len(self.column_ids),
                        row_values,
                    )
            except Exception as e:
                logger.error("Erro ao inserir linha %s: %s", row_values, e)

    def insert_row(
        self, values: Tuple, index: Any = END, iid: Optional[str] = None
    ) -> Optional[str]:
        """
        Insere uma única linha na tabela.

        Args:
            values: Tupla de valores para a nova linha (na ordem das colunas).
            index: Posição onde inserir a linha (padrão: END).
            iid: ID interno opcional para a nova linha.

        Returns:
            O IID da linha inserida, ou None se ocorrer um erro.
        """
        try:
            # Insere a linha e retorna o IID usado (pode ser auto-gerado)
            return self.view.insert("", index, values=values, iid=iid)
        except tk.TclError as e:
            # Erro comum se tentar inserir IID duplicado
            logger.error(
                "Erro ao inserir linha com valores %s (IID: %s): %s", values, iid, e
            )
            return None

    def get_children_iids(self) -> Tuple[str, ...]:
        """Retorna uma tupla com os IIDs de todos os itens na Treeview."""
        try:
            return self.view.get_children()
        except tk.TclError as e:
            logger.error("Erro ao obter IIDs filhos: %s", e)
            return tuple()  # Retorna tupla vazia em caso de erro

    def get_selected_iid(self) -> Optional[str]:
        """Retorna o IID do primeiro item selecionado, ou None se nada selecionado."""
        selection = self.view.selection()
        return selection[0] if selection else None  # selection() retorna tupla

    def get_row_values(self, iid: str) -> Optional[Tuple]:
        """
        Obtém a tupla de valores para um determinado IID de item, na ordem das colunas.

        Args:
            iid: O ID do item (linha) a ser consultado.

        Returns:
            Uma tupla com os valores da linha, ou None se o IID não existir ou ocorrer erro.
        """
        # Verifica se o item existe antes de tentar obter valores
        if not self.view.exists(iid):
            logger.warning("Tentativa de obter valores para IID inexistente: %s", iid)
            return None
        try:
            # view.set(iid) retorna um dicionário {col_id: valor}
            item_dict = self.view.set(iid)
            # Monta a tupla na ordem definida por self.column_ids
            return tuple(item_dict.get(cid, "") for cid in self.column_ids)
        except (tk.TclError, KeyError) as e:
            logger.error("Erro ao obter valores para IID %s: %s", iid, e)
            return None

    def get_selected_row_values(self) -> Optional[Tuple]:
        """Obtém a tupla de valores para a linha atualmente selecionada."""
        iid = self.get_selected_iid()  # Obtém o IID selecionado
        # Retorna valores ou None
        return self.get_row_values(iid) if iid else None

    def column_id_from_index(self, index: int) -> Optional[str]:
        """Obtém o ID interno da coluna a partir do seu índice (0-based)."""
        if 0 <= index < len(self.column_ids):
            return self.column_ids[index]
        else:
            logger.warning("Índice de coluna inválido: %d", index)
            return None
