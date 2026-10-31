# Makefile mínimo para a documentação do Sphinx
#

# Você pode definir essas variáveis a partir da linha de comando e também
# do ambiente para as duas primeiras.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = build

# Coloque em primeiro para que "make" sem argumentos seja equivalente a "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Alvo genérico: direciona todos os alvos desconhecidos para o Sphinx usando a nova
# opção "make mode". $(O) serve como atalho para $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
