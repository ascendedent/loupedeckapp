#!/usr/bin/env bash
# Build a single-file AppImage.
#
# Why AppImage and not Flatpak: this app needs /dev/uinput, through ydotool, to
# type anything. A Flatpak cannot reach it without permissions that defeat the
# point of the sandbox (see packaging/flatpak/README.md). An AppImage is not
# sandboxed. It is a bundle, so the app has exactly the access the user does.
#
#   ./packaging/appimage/build.sh            # build into dist/
#   APPIMAGE_SKIP_PACK=1 ./...../build.sh    # AppDir only, no squashfs step
#
# Needs: python3, pip, and appimagetool (downloaded on first run if absent).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="${REPO}/build/appimage"
APPDIR="${BUILD}/loupedeckapp.AppDir"
DIST="${REPO}/dist"
TOOLS="${BUILD}/tools"

APP_ID="loupedeckapp"
ARCH="$(uname -m)"

echo "== cleaning"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin" "${APPDIR}/usr/lib" \
         "${APPDIR}/usr/share/applications" \
         "${APPDIR}/usr/share/icons/hicolor/scalable/apps" \
         "${DIST}" "${TOOLS}"

# The interpreter, laid out exactly as it is on this system. Distributions do
# not agree on where the standard library lives (Fedora splits lib and lib64),
# and PYTHONHOME only works if the layout under it matches what the interpreter
# was built to expect, so every path is copied to the same place relative to
# the prefix rather than to a guess.
echo "== bundling the interpreter"
PYBIN="$(command -v python3)"
BASE_PREFIX="$(python3 -c 'import sys; print(sys.base_prefix)')"
cp "${PYBIN}" "${APPDIR}/usr/bin/python3"

for path in stdlib platstdlib; do
    SRC="$(python3 -c "import sysconfig; print(sysconfig.get_paths()['${path}'])")"
    [ -d "${SRC}" ] || continue
    REL="${SRC#${BASE_PREFIX}/}"
    [ "${REL}" = "${SRC}" ] && continue     # outside the prefix; skip it
    if [ -e "${APPDIR}/usr/${REL}" ]; then
        continue                            # stdlib and platstdlib are the same here
    fi
    mkdir -p "${APPDIR}/usr/${REL}"
    cp -r "${SRC}/." "${APPDIR}/usr/${REL}/"
    # site-packages is not the standard library: it is whatever the machine
    # doing the build happens to have installed. Copying it swept 30MB of this
    # machine's unrelated packages into the bundle, which is both waste and a
    # good way to redistribute software nobody meant to ship. pip fills this
    # directory properly a few steps below.
    rm -rf "${APPDIR}/usr/${REL}/site-packages" \
           "${APPDIR}/usr/${REL}/dist-packages"
    # Costly and unused: the test suite, the Tk bindings and the IDLE editor.
    rm -rf "${APPDIR}/usr/${REL}/test" "${APPDIR}/usr/${REL}/idlelib" \
           "${APPDIR}/usr/${REL}/tkinter" "${APPDIR}/usr/${REL}/turtledemo" \
           "${APPDIR}/usr/${REL}/lib2to3"
done

# Shared libraries the interpreter itself needs (libpython, libssl, ...).
echo "== copying the interpreter's shared libraries"
ldd "${PYBIN}" | awk '/=> \//{print $3}' | sort -u | while read -r lib; do
    cp -Ln "${lib}" "${APPDIR}/usr/lib/" 2>/dev/null || true
done

# The app and its dependencies. --prefix, not --target: the assets (qml/,
# Images/, Profiles/) install as data files under share/, and --target drops
# them on the floor, which would produce a bundle that dies on a missing
# Main.qml.
# --ignore-installed matters: pip decides what is already satisfied by looking
# at the environment it is running in, so building from a virtualenv that has
# PySide6 in it produced a bundle with no PySide6 at all.
echo "== installing the app and its dependencies"
python3 -m pip install --quiet --upgrade --ignore-installed \
    --prefix "${APPDIR}/usr" "${REPO}[device]"

# Qt ships far more than this app loads, and PySide6 pulls all of it: the
# untrimmed bundle is 800MB, of which a quarter is a web browser engine.
#
# Both spellings have to be matched. PySide6 names its modules QtWebEngine
# while the libraries underneath are libQt6WebEngineCore, so a list of "Qt*"
# patterns quietly missed the 195MB one.
echo "== trimming Qt"
for name in WebEngine WebView WebChannel WebSockets 3D Charts \
            DataVisualization Quick3D Multimedia Designer Help Bluetooth Nfc \
            Positioning Location Sensors SerialBus SerialPort RemoteObjects \
            Scxml SpatialAudio TextToSpeech VirtualKeyboard Pdf; do
    for spelling in "Qt${name}" "Qt6${name}"; do
        find "${APPDIR}/usr" -depth -name "*${spelling}*" -print0 2>/dev/null \
            | xargs -0 rm -rf 2>/dev/null || true
    done
done
# What the browser engine leaves behind: its .pak resources, its locales, and
# the media codecs nothing else here uses.
QTDIR="$(find "${APPDIR}/usr" -maxdepth 6 -type d -name Qt -path "*PySide6*" | head -1)"
if [ -n "${QTDIR}" ]; then
    rm -rf "${QTDIR}/resources" "${QTDIR}/translations/qtwebengine_locales"
    find "${QTDIR}/lib" -name "libav*" -o -name "libsw*" 2>/dev/null \
        | xargs -r rm -rf
fi
# Developer tools that ride along in the wheel and have no place in a bundle.
for tool in qmlls qmlformat qmllint assistant designer linguist lrelease \
            lupdate qmlprofiler qmltestrunner; do
    rm -rf "${APPDIR}"/usr/lib*/python*/site-packages/PySide6/"${tool}"
done

echo "== desktop entry and icon"
cp "${REPO}/packaging/loupedeckapp.desktop" \
   "${APPDIR}/usr/share/applications/${APP_ID}.desktop"
cp "${REPO}/packaging/loupedeckapp.desktop" "${APPDIR}/${APP_ID}.desktop"
cp "${REPO}/packaging/icons/loupedeckapp.svg" \
   "${APPDIR}/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
cp "${REPO}/packaging/icons/loupedeckapp.svg" "${APPDIR}/${APP_ID}.svg"

cat > "${APPDIR}/AppRun" <<'RUN'
#!/usr/bin/env bash
# Entry point. Everything is relative to $HERE: an AppImage mounts somewhere
# different on every run, so no path in here may be absolute.
HERE="$(dirname "$(readlink -f "${0}")")"
export PYTHONHOME="${HERE}/usr"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${HERE}/usr/lib64:${LD_LIBRARY_PATH:-}"
# Do not put the working directory on sys.path. Started from a checkout of this
# project, the bundle would otherwise import that checkout instead of itself,
# which is a confusing way to test something you believe is self-contained.
export PYTHONSAFEPATH=1
# Where the app looks for qml/, Images/ and Profiles/. An AppImage mounts
# somewhere different on every run, so it cannot be worked out from sys.prefix.
export LOUPEDECKAPP_PREFIX="${HERE}/usr"
exec "${HERE}/usr/bin/python3" -c \
    "import sys; sys.argv[0]='loupedeckapp'; from qml_app import main; main()" "$@"
RUN
chmod +x "${APPDIR}/AppRun"

if [ -n "${APPIMAGE_SKIP_PACK:-}" ]; then
    echo "== AppDir ready at ${APPDIR} (packing skipped)"
    exit 0
fi

TOOL="${TOOLS}/appimagetool"
if [ ! -x "${TOOL}" ]; then
    echo "== fetching appimagetool"
    curl -fsSL -o "${TOOL}" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "${TOOL}"
fi

echo "== packing"
ARCH="${ARCH}" "${TOOL}" "${APPDIR}" "${DIST}/LoupedeckConfig-${ARCH}.AppImage"
echo "built ${DIST}/LoupedeckConfig-${ARCH}.AppImage"
