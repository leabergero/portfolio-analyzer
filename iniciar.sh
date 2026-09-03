#!/bin/bash
# Arranca el server si no está corriendo y abre la interfaz en el navegador.
cd "$(dirname "$0")" || exit 1
URL=http://127.0.0.1:5002/

if ! curl -sf -o /dev/null "$URL"; then
    setsid .venv/bin/python -m api.app > /tmp/portfolio-analyzer.log 2>&1 &
fi

for _ in $(seq 60); do
    curl -sf -o /dev/null "$URL" && exec xdg-open "$URL"
    sleep 0.5
done

notify-send "Portfolio Analyzer" "No arrancó en 30s — mirá /tmp/portfolio-analyzer.log"
exit 1
