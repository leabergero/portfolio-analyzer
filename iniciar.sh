#!/bin/bash
# Arranca el server si no está corriendo y abre la interfaz en el navegador.
cd "$(dirname "$0")" || exit 1
PUERTO=${PA_PUERTO:-5002}
URL=http://127.0.0.1:$PUERTO/

if ! curl -sf -o /dev/null "$URL"; then
    PA_PUERTO=$PUERTO setsid .venv/bin/python -m api.app > /tmp/portfolio-analyzer-$PUERTO.log 2>&1 &
fi

for _ in $(seq 60); do
    curl -sf -o /dev/null "$URL" && exec xdg-open "$URL"
    sleep 0.5
done

notify-send "Portfolio Analyzer" "No arrancó en 30s — mirá /tmp/portfolio-analyzer-$PUERTO.log"
exit 1
