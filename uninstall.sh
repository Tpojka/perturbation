#!/usr/bin/env bash
# macOS / Ubuntu: remove Perturbation.
cd "$(dirname "$0")" && exec python3 -m perturbation.install uninstall
