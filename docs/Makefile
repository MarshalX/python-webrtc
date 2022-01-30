# makefile for Sphinx documentation

SPHINXOPTS ?=
SPHINXBUILD ?= sphinx-build
SPHINXGENERATE ?= sphinx-apidoc
MODULEPATH = ../python-webrtc/python/webrtc
EXCLUDEPATTERN = ../python-webrtc/python/webrtc/utils/**
SOURCEDIR = source
BUILDDIR = build

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

gen:
	@$(SPHINXGENERATE) -f -e -M -o "$(SOURCEDIR)" "$(MODULEPATH)" "$(EXCLUDEPATTERN)" $(O)

.PHONY: gen Makefile

%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
