# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# File: registro/__main__.py (Ponto de Entrada da Aplicação)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Ponto de entrada principal para execução da aplicação de registro de refeições
quando o pacote `registro` é executado diretamente (ex: `python -m registro`).

Configura o logging básico e inicia a interface gráfica do usuário (GUI).
"""
import sys
import logging

# Configuração inicial e básica do logging (antes de importar a GUI)
# Isso garante que logs de importação ou inicialização precoce sejam capturados.
# A configuração mais completa (com arquivo) será feita dentro de gui.main().
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)  # Logger para este módulo (__main__)

# Tenta importar a função principal da GUI
try:
    # A função que inicia a aplicação agora está em gui.main
    from registro.view.gui import main as start_gui
    # Importa textos da UI para mensagens de erro
    from registro.control.constants import UI_TEXTS
except ImportError as e:
    logger.exception("Falha ao importar o componente principal da GUI."
                     " Verifique a instalação e dependências.")
    # Exibe mensagem de erro mais amigável no console
    print(f"ERRO: Falha ao importar componentes da aplicação: {e}", file=sys.stderr)
    print("Verifique se todas as dependências estão instaladas corretamente.", file=sys.stderr)
    sys.exit(1)  # Encerra se a importação falhar

# Bloco principal executado quando o script é chamado
if __name__ == "__main__":
    logger.info("Aplicação iniciando via __main__.")
    try:
        # Chama a função que configura tudo e inicia a aplicação
        start_gui()
        logger.info("Aplicação finalizada normalmente.")
        sys.exit(0)  # Sai com código 0 (sucesso)
    except Exception as e:
        # Captura qualquer erro não tratado durante a execução da aplicação
        logger.exception("Um erro não tratado ocorreu durante a execução da aplicação.")
        try:
            # Tenta exibir uma messagebox de erro crítico se o Tkinter puder ser carregado
            import tkinter as tk
            from tkinter import messagebox
            # Cria uma janela raiz oculta apenas para poder mostrar a messagebox
            root = tk.Tk()
            root.withdraw()
            # Usa textos da UI para a mensagem de erro
            messagebox.showerror(
                UI_TEXTS.get("critical_error_title", "Erro Crítico"),
                UI_TEXTS.get("critical_error_message",
                             "A aplicação encontrou um erro inesperado e será encerrada:\n\n{error}").format(error=e)
            )
        except Exception as tk_err:
            # Se até a messagebox falhar, loga e imprime no console
            logger.error(f"Não foi possível exibir a messagebox de erro Tkinter: {tk_err}")
            print(f"ERRO CRÍTICO: Aplicação encontrou um erro inesperado:\n{e}", file=sys.stderr)
        sys.exit(1)  # Sai com código 1 (erro)
