# conf.py
"""
Arquivo de configuração para o gerador de documentação Sphinx.

Este arquivo contém uma variedade de configurações e opções para personalizar o
processo de geração de documentação para o projeto "Registro de Refeições".

Principais Recursos:
- Adiciona o diretório raiz do projeto ao `sys.path` para descoberta de módulos.
- Configura extensões do Sphinx como autodoc, napoleon, intersphinx e outras.
- Configura a saída HTML com o tema moderno "Furo".
- Inclui opções para autodoc, napoleon, intersphinx e autosummary.
- Cria mocks de importação para dependências indisponíveis ou pesadas durante o build.

Para mais detalhes sobre a configuração do Sphinx, visite:
https://www.sphinx-doc.org/en/master/usage/configuration.html
"""
# -- Configuração de Caminho -------------------------------------------------

# Se extensões (ou módulos a serem documentados com autodoc) estiverem em outro
# diretório, adicione esses diretórios ao sys.path aqui. Se o diretório for relativo
# à raiz da documentação, use os.path.abspath para torná-lo absoluto.
#
import os
import sys
# Adiciona o diretório raiz do projeto ao path
sys.path.insert(0, os.path.abspath('../..'))  # Ajuste se a estrutura de docs diferir
print(sys.path)  # Linha de depuração para verificar o sys.path
# -- Informações do Projeto --------------------------------------------------

project = 'Registro de Refeições'  # pylint: disable=invalid-name
copyright = '2024-2025, Mateus G Pereira'  # pylint: disable=redefined-builtin,invalid-name
author = 'Mateus G Pereira'  # pylint: disable=invalid-name

# A versão completa, incluindo tags alfa/beta/rc - pode ser obtida dinamicamente
# do seu pacote, ex.: usando importlib.metadata se configurado no pyproject.toml
# Por enquanto, usando um valor de espaço reservado.
release = '0.1.0'  # pylint: disable=invalid-name
version = '0.1'  # pylint: disable=invalid-name

# -- Configuração Geral ------------------------------------------------------

# Adicione aqui os nomes dos módulos de extensão do Sphinx, como strings.
# Podem ser extensões que acompanham o Sphinx (chamadas 'sphinx.ext.*') ou personalizadas.
extensions = [
    'sphinx.ext.autodoc',        # Inclui documentação a partir de docstrings
    'sphinx.ext.napoleon',       # Suporte para docstrings no estilo Google e NumPy
    'sphinx.ext.intersphinx',    # Links para documentação de outros projetos
    'sphinx.ext.viewcode',       # Adiciona links para o código-fonte
    'sphinx.ext.todo',           # Suporte para itens a fazer (todo)
    'sphinx.ext.autosummary',    # Gera tabelas de resumo
    'sphinx_copybutton',         # Adiciona botão de "copiar" aos blocos de código
    'sphinx.ext.githubpages',    # Auxilia na publicação no GitHub Pages
]

# Adicione aqui caminhos que contenham modelos, relativos a este diretório.
templates_path = ['_templates']

# Sufixo(s) dos nomes de arquivos-fonte.
# É possível especificar múltiplos sufixos como uma lista de strings:
# source_suffix = ['.rst', '.md']
source_suffix = '.rst'  # pylint: disable=invalid-name

# Documento raiz. (Substitui master_doc no Sphinx 4.0+)
root_doc = 'index'  # pylint: disable=invalid-name

# Idioma para conteúdo gerado automaticamente pelo Sphinx. Consulte a documentação
# para obter uma lista de idiomas suportados.
# Também usado se você fizer tradução de conteúdo via catálogos gettext.
# Normalmente o idioma é definido via linha de comando para esses casos.
language = 'pt_BR'  # pylint: disable=invalid-name

# Lista de padrões, relativos ao diretório fonte, que correspondem a arquivos e
# diretórios a serem ignorados ao buscar arquivos-fonte.
# Este padrão também afeta html_static_path e html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Opções para Saída HTML --------------------------------------------------

# Tema a ser utilizado para páginas HTML e HTML Help. Consulte a documentação
# para uma lista de temas integrados.
# Opções populares: 'alabaster', 'sphinx_rtd_theme', 'furo'
html_theme = 'furo'  # pylint: disable=invalid-name # Usando o tema moderno Furo

# Adicione aqui caminhos que contenham arquivos estáticos personalizados (como folhas de estilo),
# relativos a este diretório. Eles são copiados após os arquivos estáticos internos,
# logo um arquivo chamado "default.css" sobrescreverá o "default.css" interno.
html_static_path = ['_static']

# Você pode adicionar um logotipo aqui se tiver um
# html_logo = "_static/logo.png"

# As opções de tema são específicas de cada tema e personalizam sua aparência.
# Para obter uma lista de opções disponíveis para cada tema, consulte a documentação.
# html_theme_options = {}

# -- Opções para autodoc -----------------------------------------------------

# Extrai automaticamente typehints quando especificados e os coloca nas
# descrições da respectiva função/método.
autodoc_typehints = "description"  # pylint: disable=invalid-name

# Não exibe a assinatura da classe junto com o nome da classe.
autodoc_class_signature = "separated"  # pylint: disable=invalid-name

# Opções padrão para diretivas autodoc. Aplicadas a todas as diretivas autodoc.
autodoc_default_options = {
    'members': True,             # Documenta membros (métodos, atributos)
    'member-order': 'bysource',  # Ordena membros conforme aparecem no código-fonte
    'undoc-members': True,       # Documenta membros sem docstrings (usar com cautela)
    'show-inheritance': True,    # Exibe classes base
    # 'private-members': True,   # Descomente para documentar membros privados (_*)
    # 'special-members': '__init__', # Descomente para documentar membros especiais como __init__
}

# Mocks de importação para módulos que podem não estar disponíveis durante o build.
# Especialmente bibliotecas de GUI, bibliotecas específicas de hardware ou dependências pesadas.
autodoc_mock_imports = [
    'tkinter',
    'ttkbootstrap',
    'gspread',
    'google',          # Mantém nível superior
    'google.auth',
    'google.oauth2',
    'google.auth.transport',  # Mantém submódulos necessários
    'google.auth.transport.requests',
    'google.auth.exceptions',
    'google.oauth2.credentials',
    'google_auth_oauthlib',
    'google_auth_oauthlib.flow',
    'xlsxwriter',
    'xlsxwriter.exceptions',
    'fuzzywuzzy',
    'ctypes',
    'sqlalchemy',     # Mantém nível superior
    'sqlalchemy.orm',  # Mantém submódulos necessários
    'sqlalchemy.exc',
    'sqlalchemy.dialects',
    'sqlalchemy.dialects.sqlite',
    # Adicione explicitamente a classe base se necessário, embora mockar sqlalchemy.exc deva cobrir
    # 'sqlalchemy.exc.SQLAlchemyError',
    # 'sqlalchemy.exc.IntegrityError',
]


# -- Opções para Napoleon ----------------------------------------------------

# Configurações do Napoleon para analisar docstrings no estilo Google
napoleon_google_docstring = True  # pylint: disable=invalid-name
napoleon_numpy_docstring = False  # pylint: disable=invalid-name # Desativa explicitamente estilo NumPy
napoleon_include_init_with_doc = True  # pylint: disable=invalid-name
napoleon_include_private_with_doc = False  # pylint: disable=invalid-name
napoleon_include_special_with_doc = True  # pylint: disable=invalid-name
napoleon_use_admonition_for_examples = False  # pylint: disable=invalid-name
napoleon_use_admonition_for_notes = False  # pylint: disable=invalid-name
napoleon_use_admonition_for_references = False  # pylint: disable=invalid-name
napoleon_use_ivar = False  # pylint: disable=invalid-name
napoleon_use_param = True  # pylint: disable=invalid-name
napoleon_use_rtype = True  # pylint: disable=invalid-name
napoleon_preprocess_types = True  # pylint: disable=invalid-name
napoleon_type_aliases = None  # pylint: disable=invalid-name
napoleon_attr_annotations = True  # pylint: disable=invalid-name

# -- Opções para intersphinx -------------------------------------------------

# Configuração de exemplo para o intersphinx: referência à biblioteca padrão do Python.
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'sqlalchemy': ('https://docs.sqlalchemy.org/en/20/', None),  # Verifica versão
    'ttkbootstrap': ('https://ttkbootstrap.readthedocs.io/en/latest/', None),
    # Adicione mapeamentos para outras bibliotecas como gspread se disponível e necessário
    # 'gspread': ('https://gspread.readthedocs.io/en/latest/', None),
}

# -- Opções para todo --------------------------------------------------------

# Se True, `todo` e `todoList` produzem saída, caso contrário não produzem nada.
todo_include_todos = True  # pylint: disable=invalid-name

# -- Opções para Autosummary -------------------------------------------------
# Ativa sphinx.ext.autosummary
autosummary_generate = True  # pylint: disable=invalid-name
# Não documenta membros importados dentro dos módulos
autosummary_imported_members = False  # pylint: disable=invalid-name

# --- Opcional: Configuração do Copybutton ---
# Exclui prompts (>>> , ... ) e saídas de console C#
copybutton_prompt_text = (  # pylint: disable=invalid-name
    r">>> |\.\.\. |\$ |In \[\d*\]: | {2,5}\.\.\.: | {5,8}: ")  # Ativa sphinx.ext.autosummary
# Trata o prompt do copybutton como expressão regular
copybutton_prompt_is_regexp = True  # pylint: disable=invalid-name
