#! /bin/sh

sphinx-apidoc -f -o ./docs/ limacharlie limacharlie/DRCli.py

cd docs ; make html ; cd ..