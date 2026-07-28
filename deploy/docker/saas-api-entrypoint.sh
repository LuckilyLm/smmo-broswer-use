#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
export XVFB_SCREEN="${XVFB_SCREEN:-0}"
export XVFB_WHD="${XVFB_WHD:-1366x900x24}"
export NOVNC_LISTEN="${NOVNC_LISTEN:-0.0.0.0:6080}"
export VNC_LISTEN_PORT="${VNC_LISTEN_PORT:-5901}"

if [[ "${SAAS_ENABLE_NOVNC:-true}" == "true" ]]; then
  mkdir -p /tmp/.X11-unix
  chmod 1777 /tmp/.X11-unix
  display_number="${DISPLAY#:}"
  display_number="${display_number%%.*}"
  rm -f "/tmp/.X${display_number}-lock" "/tmp/.X11-unix/X${display_number}"

  Xvfb "${DISPLAY}" -screen "${XVFB_SCREEN}" "${XVFB_WHD}" -nolisten tcp -ac >/tmp/xvfb.log 2>&1 &
  for _attempt in $(seq 1 40); do
    if [[ -S "/tmp/.X11-unix/X${display_number}" ]]; then
      break
    fi
    sleep 0.25
  done
  fluxbox >/tmp/fluxbox.log 2>&1 &
  x11vnc -display "${DISPLAY}" -forever -shared -nopw -listen 0.0.0.0 -rfbport "${VNC_LISTEN_PORT}" >/tmp/x11vnc.log 2>&1 &

  if command -v novnc_proxy >/dev/null 2>&1; then
    novnc_proxy --vnc "127.0.0.1:${VNC_LISTEN_PORT}" --listen "${NOVNC_LISTEN}" >/tmp/novnc.log 2>&1 &
  else
    websockify --web=/usr/share/novnc "${NOVNC_LISTEN}" "127.0.0.1:${VNC_LISTEN_PORT}" >/tmp/novnc.log 2>&1 &
  fi
fi

exec "$@"
