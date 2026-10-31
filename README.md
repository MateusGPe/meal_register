# Registro de Refeições

## Descrição

Esta aplicação fornece uma interface gráfica de usuário para registrar alunos para refeições. Ela permite que os usuários pesquisem alunos, registrem suas escolhas de refeição e gerenciem sessões de serviço. O sistema pode sincronizar dados com o Google Sheets e exportar dados de sessão para arquivos XLSX.

## Funcionalidades

* **Registro de Alunos:** Permite que os usuários pesquisem alunos por número de matrícula ou nome e registrem sua presença para uma refeição.
* **Gerenciamento de Sessões:** Permite a criação e configuração de sessões de serviço de refeições, incluindo a definição do tipo de refeição, data, hora e turmas aplicáveis.
* **Sincronização de Dados:** Pode sincronizar dados de refeições servidas com uma planilha do Google Sheets especificada.
* **Exportação de Dados:** Permite exportar os dados da sessão atual para um arquivo XLSX.
* **Filtragem por Turma:** Permite filtrar alunos com base nas turmas selecionadas para uma sessão.
* **Adição de Linhas Únicas:** Ao sincronizar com o Google Sheets, apenas linhas únicas são adicionadas, evitando duplicatas.
* **Armazenamento Local de Dados:** Gerencia os dados da sessão localmente em arquivos JSON.
* **Integração com Banco de Dados:** Utiliza SQLAlchemy para interagir com um banco de dados local para armazenar informações de alunos e reservas.

## Instalação

1. Certifique-se de ter o Python 3 instalado em seu sistema.
2. Instale o `uv` seguindo as instruções no site oficial: [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/)
3. Clone o repositório (se aplicável).
4. Navegue até o diretório do projeto no seu terminal.
5. Instale as dependências do projeto e configure o ambiente usando o `uv`:

   ```bash
   uv sync
   ```

6. Configure suas credenciais da API do Google Sheets. Siga as instruções em `registro/control/google_creds.py` (referenciado implicitamente) para criar uma conta de serviço e baixar o arquivo JSON de credenciais. Coloque este arquivo no local apropriado ou configure o caminho conforme necessário.

## Configuração

A aplicação utiliza diversos arquivos de configuração localizados no diretório `./config`:

* **`spreadsheet.json`:** Contém a chave da planilha do Google utilizada para a sincronização manual de dados.
* **`session.json`:** Armazena os dados da sessão de serviço de refeições atual (automático).
* **`lanches.json`:** Contém uma lista de lanches disponíveis (manual).
* **`students.csv`:** Utilizado para a importação automática de dados de alunos para o banco de dados local.
* **`reserves.csv`:** Utilizado para a importação automática de dados de reservas para o banco de dados local.

Certifique-se de que esses arquivos existam no diretório `./config` ou ajuste os caminhos no código, se necessário. Você pode precisar criar o diretório `./config` se ele não existir.

## Utilização

1. Execute a aplicação principal usando `uv run registrar`:

   ```bash
   uv run registrar
   ```

   *(Alternativamente, ative o ambiente virtual `.venv` e execute `registrar` diretamente.)*

2. Ao iniciar, se nenhuma sessão anterior for encontrada, uma caixa de diálogo "Nova sessão" aparecerá.
3. Na caixa de diálogo, configure o tipo de refeição, hora, data, período e selecione as turmas para a sessão.
4. Clique em "Ok" para iniciar a sessão.
5. Na janela principal, use a aba "Registrar" para pesquisar alunos digitando seu número de matrícula ou nome.
6. Selecione o aluno nos resultados da pesquisa e clique em "Registrar" ou dê um duplo clique no aluno para registrar sua refeição.
7. A aba "Sessão" permite visualizar e gerenciar a sessão atual, exportar dados e sincronizar com o Google Sheets.
8. Clique em "Salvar (xlsx)..." para salvar os dados da sessão em um arquivo XLSX na sua pasta de Documentos e enviar os dados da sessão para a planilha do Google especificada.
9. Clique em "Salvar e encerrar..." para salvar os dados da sessão em um arquivo XLSX na sua pasta de Documentos, enviar os dados da sessão para a planilha do Google especificada e fechar a aplicação, removendo o arquivo de sessão local.
10. Use o botão "Sync" na aba "Sessão" para sincronizar as reservas com a planilha do Google configurada.

## Licença

Este projeto está licenciado sob a Licença MIT.

## Direitos Autorais

Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
