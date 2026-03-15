#!/bin/bash
set -e

echo "Building web version with pygbag..."
.venv/bin/python -m pygbag --build .

echo "Copying build to docs/..."
cp build/web/index.html docs/index.html
cp build/web/alpha-azul-cc.apk docs/alpha-azul-cc.apk
cp build/web/alpha-azul-cc.tar.gz docs/alpha-azul-cc.tar.gz
cp build/web/favicon.png docs/favicon.png
touch docs/.nojekyll

echo "Committing and pushing..."
git add docs/
git commit -m "Deploy: update web build to docs/"
git push

echo "Done! GitHub Pages will update in a minute."
