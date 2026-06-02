#!/usr/bin/env bash
# run_phase.sh
# ─────────────────────────────────────────────────────────────────────────────
# Single entry point to run any phase script.
#
# Usage:
#   ./run_phase.sh 1        → runs phase1
#   ./run_phase.sh 4b       → runs phase4b (EDL)
#   ./run_phase.sh 4a       → runs phase4a (SOTIF)
#   ./run_phase.sh all      → runs all phases in order
#   ./run_phase.sh test     → runs utils self-test only
#
# Environment variables:
#   NUSCENES_DATAROOT   path to nuScenes mini dataset (default: /data/nuscenes)
#   OUTPUT_DIR          where to write results (default: reports/)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PHASE="${1:-help}"
NUSCENES_DATAROOT="${NUSCENES_DATAROOT:-/data/nuscenes}"
OUTPUT_DIR="${OUTPUT_DIR:-reports}"
SCRIPTS_DIR="$(dirname "$0")/scripts"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'   # no color

log_info()  { echo -e "${GREEN}[run_phase]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[run_phase]${NC} $*"; }
log_error() { echo -e "${RED}[run_phase]${NC} $*" >&2; }

run_script() {
    local script="$1"
    local label="$2"
    log_info "Running Phase $label → $script"
    if [[ ! -f "$script" ]]; then
        log_error "Script not found: $script"
        exit 1
    fi
    NUSCENES_DATAROOT="$NUSCENES_DATAROOT" \
    OUTPUT_DIR="$OUTPUT_DIR" \
    python "$script"
    log_info "Phase $label complete. Results in $OUTPUT_DIR/"
}

mkdir -p "$OUTPUT_DIR"

case "$PHASE" in
    1)
        run_script "$SCRIPTS_DIR/phase1_gradcam.py" "1 — GradCAM + MC Dropout + Planning"
        ;;
    2)
        run_script "$SCRIPTS_DIR/phase2_multicam.py" "2 — Multi-Camera GradCAM + Sensor Trust"
        ;;
    3)
        run_script "$SCRIPTS_DIR/phase3_sensitivity.py" "3 — 7×7 Sensitivity Matrix"
        ;;
    4a)
        run_script "$SCRIPTS_DIR/phase4a_sotif.py" "4a — SOTIF & ISO 26262 Safety Analysis"
        ;;
    4b)
        run_script "$SCRIPTS_DIR/phase4b_edl.py" "4b — Evidential Deep Learning"
        ;;
    5)
        run_script "$SCRIPTS_DIR/phase5_benchmark.py" "5 — Corruption Benchmark (8×5)"
        ;;
    all)
        log_info "Running all phases in sequence..."
        for p in 1 2 3 4a 4b 5; do
            "$0" "$p"
            echo ""
        done
        log_info "All phases complete."
        ;;
    test)
        log_info "Running utils/ self-test..."
        PYTHONPATH="$(dirname "$0")" python scripts/utils/__init__.py
        ;;
    help|*)
        echo ""
        echo "Usage: ./run_phase.sh [phase]"
        echo ""
        echo "  Phases:  1 | 2 | 3 | 4a | 4b | 5 | all | test"
        echo ""
        echo "  Examples:"
        echo "    ./run_phase.sh 4b          # Run Phase 4b (EDL)"
        echo "    ./run_phase.sh all         # Run all phases"
        echo "    ./run_phase.sh test        # Verify utils/ imports"
        echo ""
        echo "  Environment:"
        echo "    NUSCENES_DATAROOT=/path/to/nuscenes ./run_phase.sh 1"
        echo "    OUTPUT_DIR=my_results ./run_phase.sh 5"
        echo ""
        ;;
esac
