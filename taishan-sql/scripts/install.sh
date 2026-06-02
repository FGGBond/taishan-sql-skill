#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_DIR="${SCRIPT_DIR}/cli"
VENV_DIR="${SCRIPT_DIR}/.venv"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

warn() {
  echo "WARN: $*" >&2
}

find_python() {
  local cmd
  for cmd in python3 python py; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      continue
    fi
    if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      echo "$cmd"
      return 0
    fi
    warn "$cmd found but requires Python 3.10+ ($( "$cmd" -V 2>&1 || true ))"
  done
  return 1
}

ensure_pip() {
  local py="$1"
  if "$py" -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  warn "pip missing for $py; bootstrapping with ensurepip"
  "$py" -m ensurepip --upgrade >/dev/null 2>&1 || \
    die "pip is unavailable. Install pip for $py, then rerun: bash scripts/install.sh"
}

upgrade_build_tools() {
  local py="$1"
  shift
  # Old pip may fail editable installs without newer setuptools/wheel.
  "$py" -m pip install "$@" --upgrade pip setuptools wheel
}

install_editable() {
  local py="$1"
  shift
  if "$py" -m pip install "$@" -e "${CLI_DIR}"; then
    return 0
  fi
  warn "Global install failed; retrying with --user"
  "$py" -m pip install "$@" --user -e "${CLI_DIR}"
}

PYTHON="$(find_python)" || die "Python 3.10+ is required (python3 recommended). Install it and rerun."

CLI_BIN=""
INSTALL_MODE=""

if "$PYTHON" -m venv --help >/dev/null 2>&1; then
  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "Creating virtualenv at ${VENV_DIR}" >&2
    if ! "$PYTHON" -m venv "${VENV_DIR}" 2>/dev/null; then
      warn "Could not create venv (on Debian/Ubuntu try: sudo apt install python3-venv)"
    fi
  fi
fi

if [[ -x "${VENV_DIR}/bin/python" ]]; then
  VENV_PY="${VENV_DIR}/bin/python"
  ensure_pip "${VENV_PY}"
  upgrade_build_tools "${VENV_PY}"
  install_editable "${VENV_PY}"
  CLI_BIN="${VENV_DIR}/bin/taishan-sql"
  INSTALL_MODE="venv (${VENV_DIR})"
else
  ensure_pip "${PYTHON}"
  upgrade_build_tools "${PYTHON}"
  install_editable "${PYTHON}"
  if command -v taishan-sql >/dev/null 2>&1; then
    CLI_BIN="$(command -v taishan-sql)"
    INSTALL_MODE="pip (PATH)"
  else
    USER_BASE="$("${PYTHON}" -m site --user-base)"
    if [[ -x "${USER_BASE}/bin/taishan-sql" ]]; then
      CLI_BIN="${USER_BASE}/bin/taishan-sql"
      INSTALL_MODE="pip (--user, ${USER_BASE}/bin)"
    else
      CLI_BIN="${PYTHON} -m taishan_sql"
      INSTALL_MODE="pip (module fallback)"
    fi
  fi
fi

chmod +x "${SCRIPT_DIR}/taishan-sql" 2>/dev/null || true

echo ""
echo "taishan-sql installed via ${INSTALL_MODE}."
echo "Preferred entrypoint: bash scripts/taishan-sql doctor"
echo "Direct CLI: ${CLI_BIN} doctor"
