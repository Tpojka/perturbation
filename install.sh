#!/usr/bin/env bash
# macOS / Ubuntu: install Perturbation (see perturbation/install).
cd "$(dirname "$0")" && exec python3 -m perturbation.install "$@"
