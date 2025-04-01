# Meal Registration / Registro de Refeições

## Description / Descrição

This application provides a graphical user interface for registering students for meals. It allows users to search for students, record their meal choices, and manage serving sessions. The system can synchronize data with Google Sheets and export session data to XLSX files.

Esta aplicação fornece uma interface gráfica de usuário para registrar alunos para refeições. Ela permite que os usuários pesquisem alunos, registrem suas escolhas de refeição e gerenciem sessões de serviço. O sistema pode sincronizar dados com o Google Sheets e exportar dados de sessão para arquivos XLSX.

## Features / Funcionalidades

* **Student Registration / Registro de Alunos:** Allows users to search for students by registration number or name and record their attendance for a meal. / Permite que os usuários pesquisem alunos por número de matrícula ou nome e registrem sua presença para uma refeição.
* **Session Management / Gerenciamento de Sessões:** Enables the creation and configuration of meal serving sessions, including setting the meal type, date, time, and applicable classes. / Permite a criação e configuração de sessões de serviço de refeições, incluindo a definição do tipo de refeição, data, hora e turmas aplicáveis.
* **Data Synchronization / Sincronização de Dados:** Can synchronize served meal data with a specified Google Sheet. / Pode sincronizar dados de refeições servidas com uma planilha do Google especificada.
* **Data Export / Exportação de Dados:** Allows exporting the current session's data to an XLSX file. / Permite exportar os dados da sessão atual para um arquivo XLSX.
* **Class Filtering / Filtragem por Turma:** Enables filtering students based on selected classes for a session. / Permite filtrar alunos com base nas turmas selecionadas para uma sessão.
* **Unique Row Appending / Adição de Linhas Únicas:** When synchronizing with Google Sheets, only unique rows are appended, preventing duplicates. / Ao sincronizar com o Google Sheets, apenas linhas únicas são adicionadas, evitando duplicatas.
* **Local Data Storage / Armazenamento Local de Dados:** Manages session data locally in JSON files. / Gerencia os dados da sessão localmente em arquivos JSON.
* **Database Integration / Integração com Banco de Dados:** Uses SQLAlchemy for interacting with a local database to store student and reserve information. / Utiliza SQLAlchemy para interagir com um banco de dados local para armazenar informações de alunos e reservas.


## Installation / Instalação

1.  Ensure you have Python 3 installed on your system. / Certifique-se de ter o Python 3 instalado em seu sistema.
2.  Install Poetry following the instructions on the official Poetry website: [https://python-poetry.org/docs/#installation](https://python-poetry.org/docs/#installation) / Instale o Poetry seguindo as instruções no site oficial do Poetry: [https://python-poetry.org/docs/#installation](https://python-poetry.org/docs/#installation)
3.  Clone the repository (if applicable). / Clone o repositório (se aplicável).
4.  Navigate to the project directory in your terminal. / Navegue até o diretório do projeto no seu terminal.
5.  Install the project dependencies using Poetry: / Instale as dependências do projeto usando o Poetry:

    ```bash
    poetry install
    ```

6.  Set up your Google Sheets API credentials. Follow the instructions in the `registro/control/google_creds.py` (implicitly referenced) to create a service account and download the credentials JSON file. Place this file in the appropriate location or configure the path as needed. / Configure suas credenciais da API do Google Sheets. Siga as instruções em `registro/control/google_creds.py` (referenciado implicitamente) para criar uma conta de serviço e baixar o arquivo JSON de credenciais. Coloque este arquivo no local apropriado ou configure o caminho conforme necessário.

## Configuration / Configuração

The application uses several configuration files located in the `./config` directory:

A aplicação utiliza diversos arquivos de configuração localizados no diretório `./config`:

* **`spreadsheet.json`:** Contains the key of the Google Spreadsheet used for manual data synchronization. / Contém a chave da planilha do Google utilizada para a sincronização manual de dados.
* **`session.json`:** Stores the data for the current meal serving session. / Armazena os dados da sessão de serviço de refeições atual (automático).
* **`lanches.json`:** Contains a list of available snacks. / Contém uma lista de lanches disponíveis (manual).
* **`students.csv`:** Used for automatic importing of student data into the local database. / Utilizado para a importação automática de dados de alunos para o banco de dados local.
* **`reserves.csv`:** Used for automatic importing of reserve data into the local database. / Utilizado para a importação automática de dados de reservas para o banco de dados local.

Ensure these files exist in the `./config` directory or adjust the paths in the code if necessary. You might need to create the `./config` directory if it doesn't exist.

Certifique-se de que esses arquivos existam no diretório `./config` ou ajuste os caminhos no código, se necessário. Você pode precisar criar o diretório `./config` se ele não existir.

## Usage / Utilização

1.  Activate the Poetry shell within the project directory: / Ative o shell do Poetry dentro do diretório do projeto:

    ```bash
    poetry shell
    ```

2.  Run the main application script using the `registrar` command defined in `pyproject.toml`: / Execute o script principal da aplicação usando o comando `registrar` definido em `pyproject.toml`:

    ```bash
    registrar
    ```

3.  Upon starting, if no previous session is found, a "Nova seção" (New Session) dialog will appear. / Ao iniciar, se nenhuma sessão anterior for encontrada, uma caixa de diálogo "Nova seção" aparecerá.
4.  In the dialog, configure the meal type, time, date, period, and select the classes for the session. / Na caixa de diálogo, configure o tipo de refeição, hora, data, período e selecione as turmas para a sessão.
5.  Click "Ok" to start the session. / Clique em "Ok" para iniciar a sessão.
6.  In the main window, use the "Registrar" tab to search for students by typing their registration number or name. / Na janela principal, use a aba "Registrar" para pesquisar alunos digitando seu número de matrícula ou nome.
7.  Select the student from the search results and click "Registrar" or double-click the student to record their meal. / Selecione o aluno nos resultados da pesquisa e clique em "Registrar" ou clique duas vezes no aluno para registrar sua refeição.
8.  The "Sessão" tab allows you to view and manage the current session, export data, and synchronize with Google Sheets. / A aba "Sessão" permite visualizar e gerenciar a sessão atual, exportar dados e sincronizar com o Google Sheets.
9.  Click "Salvar (xlsx)..." to save the session data to an XLSX file in your Documents folder and upload the session data to the specified Google Sheet. / Clique em "Salvar (xlsx)..." para salvar os dados da sessão em um arquivo XLSX na sua pasta de Documentos e enviar os dados da sessão para a planilha do Google especificada.
10. Click "Salvar e encerrar..." to save the session data to an XLSX file in your Documents folder, upload the session data to the specified Google Sheet, and close the application, removing the local session file. / Clique em "Salvar e encerrar..." para salvar os dados da sessão em um arquivo XLSX na sua pasta de Documentos, enviar os dados da sessão para a planilha do Google especificada e fechar a aplicação, removendo o arquivo de sessão local.
11. Use the "Sync" button in the "Sessão" tab to synchronize the reserves with the configured Google Sheet. / Use o botão "Sync" na aba "Sessão" para sincronizar as reservas com a planilha do Google configurada.

## License / Licença

This project is licensed under the MIT License. / Este projeto está licenciado sob a Licença MIT.

## Copyright / Direitos Autorais

Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>