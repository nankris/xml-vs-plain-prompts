#!/bin/bash
# driver_cc.sh JOBS_FILE PARALLEL LOG : each line of JOBS_FILE = arguments to run_cc.py
source /workspace/tools/setup.sh >/dev/null 2>&1
export H=/workspace/work/tig/_harness
JOBS=$1; P=${2:-2}; LOG=${3:-$JOBS.log}
echo "start $(date -u +%s) jobs=$(grep -v '^#' $JOBS | grep -vc '^$') P=$P" >> $LOG
grep -v '^#' "$JOBS" | grep -v '^$' | xargs -d '\n' -P "$P" -n 1 bash -c '[ -e "$H/CC_QUOTA_HIT" ] && exit 0; [ -e "$H/CC_STOP" ] && exit 0; eval "python3 $H/run_cc.py $1"' _ >> $LOG 2>&1
echo "done $(date -u +%s)" >> $LOG
