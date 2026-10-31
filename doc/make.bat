@ECHO OFF

pushd %~dp0

REM Arquivo de comando para a documentação do Sphinx

if "%SPHINXBUILD%" == "" (
	set SPHINXBUILD=sphinx-build
)
set SOURCEDIR=source
set BUILDDIR=build

%SPHINXBUILD% >NUL 2>NUL
if errorlevel 9009 (
	echo.
	echo.O comando 'sphinx-build' não foi encontrado. Certifique-se de ter o Sphinx
	echo.instalado, e então configure a variável de ambiente SPHINXBUILD para apontar
	echo.para o caminho completo do executável 'sphinx-build'. Alternativamente, você
	echo.pode adicionar o diretório do Sphinx ao PATH.
	echo.
	echo.Se você não tem o Sphinx instalado, obtenha-o em:
	echo.https://www.sphinx-doc.org/
	exit /b 1
)

if "%1" == "" goto help

%SPHINXBUILD% -M %1 %SOURCEDIR% %BUILDDIR% %SPHINXOPTS% %O%
goto end

:help
%SPHINXBUILD% -M help %SOURCEDIR% %BUILDDIR% %SPHINXOPTS% %O%

:end
popd
