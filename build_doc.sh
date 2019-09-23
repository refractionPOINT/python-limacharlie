#! /bin/sh

export SPHINX_APIDOC_OPTIONS="members,no-undoc-members,show-inheritence"

sphinx-apidoc -f -o ./docs/ limacharlie limacharlie/DRCli.py

cd docs ; make html ; cd ..