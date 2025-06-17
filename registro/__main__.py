# ----------------------------------------------------------------------------
# File: registro/__main__.py (Ponto de Entrada da Aplicação via Pacote)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Ponto de entrada principal para execução da aplicação de registro de refeições
quando o pacote `registro` é executado diretamente (ex: `python -m registro`).

Este script configura o ambiente (logging, DPI, arquivos de config) e
inicia a interface gráfica principal (RegistrationApp).
"""
import ctypes
import json
import logging
import platform
import sys
import tkinter as tk  # Importa tkinter base para messagebox de erro crítico
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import messagebox
from typing import Optional  # Importa Optional para type hinting

# Importações locais relativas (necessárias para rodar como pacote)
try:
    # '.control' e '.view' indicam importação de dentro do mesmo pacote 'registro'
    from .control.constants import LOG_DIR, SNACKS_JSON_PATH, UI_TEXTS
    from .view.registration_app import RegistrationApp  # A classe principal da UI
except ImportError as e:
    # Se falhar, talvez o script esteja sendo executado de forma inesperada
    print(f"Erro Fatal: Falha ao importar módulos internos do pacote 'registro' ({e}).",
          file=sys.stderr)
    print("Certifique-se de que está executando como 'python -m registro' "
          "a partir do diretório pai.", file=sys.stderr)
    sys.exit(1)

# --- Constantes Globais do Módulo ---
LOG_FORMAT = "%(asctime)s - %(levelname)-8s - [%(name)s:%(lineno)d] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_SEPARATOR = "=" * 35

# --- Funções Auxiliares de Configuração ---


def _setup_file_logging(root_logger: logging.Logger, log_dir: Path):
    """Configura o handler de logging para arquivo rotativo."""
    try:
        log_file = log_dir / "registro_app.log"
        # Cria handler com rotação (10MB por arquivo, mantém 5 backups)
        file_h = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
        )
        file_h.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        file_h.setLevel(logging.INFO)  # Nível para arquivo
        root_logger.addHandler(file_h)
        return True  # Indica sucesso
    except PermissionError:
        # Usa o logger já parcialmente configurado (console) para avisar
        logging.warning(
            "Permissão negada para escrever no arquivo de log: %s. Logs de arquivo desativados.",
            log_file
        )
    except Exception as file_log_err:
        logging.warning(
            "Erro ao configurar log para arquivo (%s). Logs de arquivo desativados.",
            file_log_err, exc_info=False  # Não precisa do traceback completo para este aviso
        )
    return False  # Indica falha


def setup_logging():
    """Configura o sistema de logging global (arquivo rotativo e console)."""
    log_dir = Path(LOG_DIR)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)  # Garante que o diretório exista

        # Configura logger raiz, limpando handlers anteriores (force=True)
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT,
                            force=True, handlers=[])
        root_logger = logging.getLogger()  # Pega o logger raiz

        # Handler para console (stdout) - adicionado primeiro
        stream_h = logging.StreamHandler(sys.stdout)
        stream_h.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        stream_h.setLevel(logging.INFO)  # Nível INFO para console
        root_logger.addHandler(stream_h)

        # Tenta configurar o logging para arquivo
        _setup_file_logging(root_logger, log_dir)

        # Reduz verbosidade de libs externas (opcional)
        logging.getLogger("fuzzywuzzy").setLevel(logging.WARNING)

        logging.info("Sistema de logging configurado.")

    except Exception as log_setup_err:
        # Erro crítico irrecuperável na configuração básica do logging
        print(f"FATAL: Erro irrecuperável ao configurar logging: {log_setup_err}", file=sys.stderr)
        try:  # Tenta messagebox como último recurso
            temp_root = tk.Tk()
            temp_root.withdraw()
            messagebox.showerror("Erro Crítico de Logging",
                                 f"Falha grave ao iniciar sistema de logs:\n{log_setup_err}")
            temp_root.destroy()
        except Exception:
            pass  # Ignora erros na messagebox de fallback
        sys.exit(1)  # Sai imediatamente


# Chama a configuração de logging o mais cedo possível
setup_logging()
# Obtém o logger para este módulo (__main__) APÓS a configuração
logger = logging.getLogger(__name__)


def set_dpi_awareness():
    """Tenta configurar a percepção de DPI no Windows para melhor escala da UI."""
    # Só executa em Windows
    if platform.system() != "Windows":
        logger.debug("Configuração DPI não aplicável para %s.", platform.system())
        return

    try:
        # Tenta o método mais moderno primeiro (Win 10+), 1 = System Aware
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore
        logger.info(UI_TEXTS.get("log_dpi_set_shcore",
                                 "DPI awareness definido (System Aware via shcore)."))
    except (AttributeError, OSError) as e1:
        # OSError pode ocorrer se shcore.dll não for encontrada
        logger.debug(
            "Método shcore.SetProcessDpiAwareness não disponível (%s), tentando user32...",
            type(e1).__name__)
        # Fallback para método mais antigo (Win Vista+)
        try:
            ctypes.windll.user32.SetProcessDPIAware() # type: ignore
            logger.info(UI_TEXTS.get("log_dpi_set_user32", "DPI awareness definido (via user32)."))
        except (AttributeError, OSError) as e2:
            logger.warning(
                UI_TEXTS.get(
                    "log_dpi_set_warn",
                    "Não foi possível configurar DPI awareness (nenhum método suportado"
                    " encontrado: %s / %s). A escala da UI pode parecer incorreta."),
                type(e1).__name__, type(e2).__name__
            )
        except Exception as dpi_err_user32:
            # Captura outros erros inesperados com user32
            logger.exception("Erro inesperado ao configurar DPI awareness via user32: %s",
                             dpi_err_user32)
    except Exception as dpi_err_shcore:
        # Captura outros erros inesperados com shcore
        logger.exception("Erro inesperado ao configurar DPI awareness via shcore: %s",
                         dpi_err_shcore)


def ensure_initial_config():
    """Garante que arquivos/diretórios de configuração iniciais existam."""
    try:
        # Resolve o caminho absoluto para o diretório de configuração
        config_dir = Path("./config").resolve()
        # Cria o diretório (e pais, se necessário) sem erro se já existir
        config_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Diretório de configuração verificado/criado: %s", config_dir)

        # Verifica/Cria snacks.json padrão
        # Usa o nome do arquivo da constante, garantindo que esteja no config_dir
        snacks_filename = Path(SNACKS_JSON_PATH).name
        snacks_path = config_dir / snacks_filename
        if not snacks_path.exists():
            # Obtém o valor padrão dos textos da UI
            default_snack = UI_TEXTS.get("default_snack_name", "Lanche Padrão")
            # Salva como uma lista JSON (importante manter o formato de lista)
            with open(snacks_path, "w", encoding="utf-8") as f:
                json.dump([default_snack], f, indent=2, ensure_ascii=False)
            logger.info(
                UI_TEXTS.get("log_default_snacks_created", "Arquivo padrão '{filename}' criado."
                             ).format(
                    filename=snacks_filename
                )
            )
        else:
            logger.debug("Arquivo '%s' já existe em %s.", snacks_filename, config_dir)

        # Adicione aqui verificações para outros arquivos de configuração se necessário

    except PermissionError as perm_err:
        # Erro específico de permissão
        logger.critical("Erro de Permissão ao acessar/criar config em '%s': %s",
                        config_dir, perm_err, exc_info=True)
        messagebox.showerror(
            UI_TEXTS.get("config_permission_error_title", "Erro Crítico de Permissão"),
            UI_TEXTS.get("config_permission_error_message",
                         "Não foi possível acessar ou criar o diretório/arquivo de configuração:\n"
                         "{path}\n\nVerifique as permissões de escrita."
                         ).format(path=perm_err.filename or config_dir),
        )
        sys.exit(1)  # Sai imediatamente
    except Exception as config_err:
        # Outros erros durante a configuração
        logger.critical("Erro inesperado durante a configuração inicial.", exc_info=True)
        messagebox.showerror(
            UI_TEXTS.get("config_error_title", "Erro Crítico de Configuração"),
            UI_TEXTS.get("config_error_message", "Falha inesperada na configuração inicial:\n"
                         "{config_err}\nA aplicação não pode continuar.").format(
                config_err=config_err),
        )
        sys.exit(1)  # Sai imediatamente

# --- Função Principal de Execução ---


def run_application() -> int:
    """
    Configura o ambiente e executa a aplicação principal RegistrationApp.
    Retorna o código de saída (0 para sucesso, 1 para erro).
    """
    logger.info("Iniciando configuração do ambiente da aplicação...")
    # 1. Configurar DPI (antes de iniciar Tk para valer)
    set_dpi_awareness()

    # 2. Garantir Configurações Iniciais
    ensure_initial_config()

    # 3. Iniciar a Aplicação Principal
    app: Optional[RegistrationApp] = None
    exit_code: int = 1  # Assume erro por padrão
    try:
        logger.info("Criando instância da RegistrationApp...")
        app = RegistrationApp()  # Inicialização pode falhar e chamar sys.exit()

        # Se app foi criado e a janela existe (inicialização bem-sucedida)
        if app and app.winfo_exists():
            logger.info("Iniciando loop principal Tkinter (mainloop)...")
            app.mainloop()  # Bloqueia aqui até o fechamento da janela
            logger.info("Aplicação finalizada normalmente (mainloop concluído).")
            exit_code = 0  # Sucesso
        else:
            # Se chegou aqui, a inicialização falhou, mas não chamou sys.exit()
            # (pode acontecer se _handle_initialization_error falhar em exibir msg)
            logger.error("Falha crítica: A janela principal da aplicação não foi criada.")
            # exit_code já é 1

    except Exception as main_err:
        # Captura erros críticos não tratados durante a inicialização ou execução
        logger.critical("Erro crítico não tratado durante a execução principal.", exc_info=True)
        try:
            # Tenta mostrar messagebox como último recurso
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                UI_TEXTS.get("critical_error_title", "Erro Crítico Inesperado"),
                UI_TEXTS.get("critical_error_message", "Erro inesperado:\n\n{error}"
                             ).format(error=main_err)
            )
            root.destroy()
        except Exception as tk_err:
            logger.error("Falha ao exibir messagebox de erro crítico: %s", tk_err)
            print(f"ERRO CRÍTICO: {main_err}", file=sys.stderr)
        # exit_code já é 1
    finally:
        # Garante que a mensagem de fim seja logada e os recursos de log liberados
        logger.info(UI_TEXTS.get("log_app_end", "{sep} FIM DA APLICAÇÃO {sep}\n").format(
            sep=LOG_SEPARATOR))
        logging.shutdown()  # Fecha handlers de log

    return exit_code


# --- Bloco de Execução Principal (quando rodado como script/pacote) ---
if __name__ == "__main__":
    # Registra o início da execução via __main__
    logger.info(UI_TEXTS.get("log_app_start",
                "\n{sep} INÍCIO DA EXECUÇÃO VIA __main__ {sep}").format(sep=LOG_SEPARATOR))
    # Chama a função principal que faz tudo e retorna o código de saída
    final_exit_code = run_application()
    # Sai do script Python com o código retornado
    sys.exit(final_exit_code)
