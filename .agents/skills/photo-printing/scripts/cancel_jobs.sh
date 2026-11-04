#!/usr/bin/env bash
# Cancel all active print jobs on Canon G640 queue

echo "Cancelling active Canon G640 print jobs..."
python3 g640rip_cli.py cancel
cancel -a Canon_G600_series 2>/dev/null || true
echo "Print queue cleared."
