#! /bin/sh

sphinx-apidoc -f -o ./docs/ limacharlie

cd docs ; make html ; cd ..