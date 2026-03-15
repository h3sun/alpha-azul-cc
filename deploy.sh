#!/bin/bash
set -e

echo "Building web version with pygbag..."
.venv/bin/python -m pygbag --build .

echo "Pushing build to gh-pages branch..."
rm -rf /tmp/gh-pages-deploy
git worktree prune
git worktree add /tmp/gh-pages-deploy gh-pages
cp build/web/index.html /tmp/gh-pages-deploy/
cp build/web/alpha-azul-cc.apk /tmp/gh-pages-deploy/
cp build/web/alpha-azul-cc.tar.gz /tmp/gh-pages-deploy/
cp build/web/favicon.png /tmp/gh-pages-deploy/
touch /tmp/gh-pages-deploy/.nojekyll

cd /tmp/gh-pages-deploy
git add -A
git commit -m "Deploy: update web build"
git push origin gh-pages

cd -
git worktree remove /tmp/gh-pages-deploy

echo "Done! GitHub Pages will update in a minute."
