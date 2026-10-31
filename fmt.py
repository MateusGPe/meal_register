#!/usr/bin/env python3
"""
Utilitário para conversão de formatação em chamadas de logger.
Converte f-strings para formatação no estilo % (lazy logging).
"""
import ast
import sys
import os
import argparse
import textwrap
from typing import List, Tuple, Union

# Níveis de logging considerados
LOGGING_LEVELS = {'debug', 'info', 'warning', 'error', 'critical', 'exception', 'log'}

class FStringToPercentTransformer(ast.NodeTransformer):
    """
    Um transformador AST que localiza chamadas logger.level(f"...")
    e as converte para logger.level("... %s ...", var1, var2).

    NOTA: Atualmente transforma apenas chamadas diretas em nomes de logger definidos
          em `logger_names` (ex: `logger.info(...)`, `log.debug(...)`).
          Não lida com loggers acessados como atributos
          (ex: `self.logger.info(...)`).
    """
    def __init__(self):
        super().__init__()
        self.transformed_count = 0  # Rastreia se alguma transformação ocorreu no arquivo

    def visit_Call(self, node: ast.Call) -> ast.Call:
        # Garante que os nós filhos sejam visitados primeiro
        self.generic_visit(node)

        # Verifica se é uma chamada de método como obj.metodo()
        if not isinstance(node.func, ast.Attribute):
            return node

        # Verifica se o objeto chamado é 'logger' (ou um alias comum)
        logger_names = {'logger', 'log', 'logging'}
        # --- Limitação: Apenas verifica acesso por Name simples ---
        if not isinstance(node.func.value, ast.Name) or node.func.value.id not in logger_names:
            return node
        # --- Fim da Limitação ---

        # Verifica se o nome do método é um nível de logging
        level_name = node.func.attr
        if level_name not in LOGGING_LEVELS:
            return node

        # Verifica se há argumentos posicionais e se o primeiro é uma f-string
        if not node.args or not isinstance(node.args[0], ast.JoinedStr):
            return node

        fstring_node = node.args[0]
        original_other_args = node.args[1:]  # Mantém outros argumentos posicionais se houver
        original_keywords = node.keywords    # Mantém argumentos nomeados como exc_info=True

        format_string_parts: List[str] = []
        format_args: List[ast.expr] = []

        try:
            for value_node in fstring_node.values:
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    # Parte literal: escapa caracteres %
                    format_string_parts.append(value_node.value.replace('%', '%%'))
                elif isinstance(value_node, ast.FormattedValue):
                    # Parte de expressão {expr!s:format}
                    if value_node.conversion == 114:  # '!r'
                        format_string_parts.append("%r")
                    else:  # inclui '!s', '!a' e sem especificador
                        format_string_parts.append("%s")

                    if value_node.value is None:  # Não deve acontecer em código válido
                        print(f"Aviso: Nó FormattedValue não possui valor: {ast.dump(value_node)}", file=sys.stderr)
                        # Define como lidar - pular ou usar espaço reservado
                        format_string_parts.append("{INVALID_FSTRING_VALUE}")
                        continue  # Não adiciona a format_args

                    format_args.append(value_node.value)
                    # Especificador de formato (value_node.format_spec) é ignorado conforme solicitado

                else:
                    # Não deve acontecer com f-strings válidas
                    print(f"Aviso: Ignorando tipo de nó inesperado {type(value_node)} na f-string: {ast.dump(value_node)}", file=sys.stderr)
                    format_string_parts.append("{UNEXPECTED_NODE}")

            # --- Constrói o novo nó ---
            new_format_string = "".join(format_string_parts)
            new_args = [ast.Constant(value=new_format_string)] + format_args + list(original_other_args)

            new_call_node = ast.Call(
                func=node.func,
                args=new_args,
                keywords=original_keywords
            )

            ast.copy_location(new_call_node, node)
            ast.fix_missing_locations(new_call_node)  # Importante

            # Incrementa o contador apenas se o nó realmente mudou
            if ast.unparse(node) != ast.unparse(new_call_node):
                self.transformed_count += 1

            return new_call_node

        except Exception as e:
            # Relatório aprimorado de erro
            try:
                original_code_snippet = ast.unparse(node)
            except Exception:
                original_code_snippet = ast.dump(node)
            print(f"Erro ao transformar nó próximo a '{original_code_snippet}': {e}", file=sys.stderr)
            raise


def transform_source_code(source_code: str) -> Tuple[str, int]:
    """
    Analisa o código-fonte Python, aplica a transformação de f-string para formatação %
    em chamadas de logger, e retorna o código modificado e a contagem de transformações.

    Requer Python 3.9+ para ast.unparse.

    Returns:
        Tuple[str, int]: (código_fonte_modificado, número_de_transformações)

    Raises:
        SyntaxError: Se o código-fonte não puder ser analisado.
        Exception: Se ocorrer um erro durante a visitação da transformação.
    """
    if sys.version_info < (3, 9):
        raise RuntimeError("Este script requer Python 3.9 ou superior para funcionalidade ast.unparse.")

    tree = ast.parse(source_code)  # Pode gerar SyntaxError
    transformer = FStringToPercentTransformer()
    new_tree = transformer.visit(tree)  # Pode gerar exceções de visit_Call
    ast.fix_missing_locations(new_tree)  # Garante que a árvore seja válida após transformações
    modified_code = ast.unparse(new_tree)
    return modified_code, transformer.transformed_count


def process_file(filename: str) -> bool:
    """
    Lê um arquivo, transforma seu conteúdo e grava de volta se houver alteração.

    Args:
        filename: Caminho para o arquivo Python.

    Returns:
        True se o arquivo foi processado com sucesso (mesmo sem alterações),
        False se ocorreu um erro.
    """
    print(f"Processando {filename}...", file=sys.stderr)
    try:
        # Lê o conteúdo original
        with open(filename, 'r', encoding='utf-8') as f_in:
            original_content = f_in.read()

        # Transforma
        modified_content, transform_count = transform_source_code(original_content)

        # Grava de volta se modificado
        if transform_count > 0:
            print(f"  Aplicando {transform_count} transformação(ões).", file=sys.stderr)
            with open(filename.replace('.py', '_md.py'), 'w', encoding='utf-8') as f_out:
                f_out.write(modified_content)
        else:
            print("  Nenhuma transformação necessária.", file=sys.stderr)

        return True

    except FileNotFoundError:
        print(f"Erro: Arquivo não encontrado: {filename}", file=sys.stderr)
        return False
    except SyntaxError as e:
        print(f"Erro: Falha ao analisar código Python em {filename}: {e}", file=sys.stderr)
        return False
    except OSError as e:
        print(f"Erro: Falha ao ler ou gravar arquivo {filename}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Erro: Erro inesperado ao processar arquivo {filename}: {e}", file=sys.stderr)
        return False


def main():
    """
    Função principal para lidar com argumentos de linha de comando e processar arquivos.
    """
    parser = argparse.ArgumentParser(
        description="Converte f-strings de logger para formatação no estilo % em arquivos Python.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent('''\
        Exemplo:
          %(prog)s meu_modulo.py utils/helpers.py

        Nota:
          - Requer Python 3.9+.
          - Modifica arquivos no local. Certifique-se de ter backups ou usar controle de versão.
          - Atualmente só transforma chamadas diretas nas variáveis 'logger', 'log' ou 'logging'.
            Chamadas como 'self.logger.info(f"...")' NÃO são transformadas.
        ''')
    )
    parser.add_argument(
        'filenames',
        metavar='ARQUIVO',
        nargs='+',  # Exige um ou mais nomes de arquivo
        help='Caminho(s) para o(s) arquivo(s) Python a processar.'
    )

    args = parser.parse_args()

    files_processed = 0
    files_failed = 0

    for filename in args.filenames:
        if not os.path.isfile(filename):
            print(f"Aviso: Ignorando caminho que não é arquivo: {filename}", file=sys.stderr)
            continue

        if process_file(filename):
            files_processed += 1
        else:
            files_failed += 1

    print("\n--- Resumo ---", file=sys.stderr)
    print(f"Arquivos processados: {files_processed}", file=sys.stderr)
    print(f"Arquivos com falha:  {files_failed}", file=sys.stderr)

    return 1 if files_failed > 0 else 0  # Retorna código de saída diferente de zero se houver erros


# --- Execução Principal ---
if __name__ == "__main__":
    sys.exit(main())
