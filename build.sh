#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "== building with pyinstaller"
pyinstaller -n vaelstrom --noconfirm --log-level WARN --paths env/Lib/site-packages/ vaelstrom/__main__.py

echo "== copying vaelstrom_url_handler.exe"
cp "vaelstrom_url_handler/win32/vaelstrom_url_handler.exe" "dist/vaelstrom/"

echo "== acquiring git info"
git update-index -q --refresh
GIT_HASH="$(git rev-parse --short HEAD)"
GIT_DIRTY=""
if ! git diff-index --quiet HEAD -- ; then
    GIT_DIRTY="-dirty"
fi
ZIPFILE="vaelstrom_${GIT_HASH}${GIT_DIRTY}.zip"

echo "== creating $ZIPFILE ..."
pushd dist > /dev/null
rm -f "$ZIPFILE"
../7z.exe a "$ZIPFILE" vaelstrom/
popd > /dev/null

echo "== finished"
