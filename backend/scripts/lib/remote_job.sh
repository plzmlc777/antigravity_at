#!/bin/bash
# 원격(민트) 장시간 작업을 띄우고 **완료를 정확히** 기다린다.
#
# ⚠ 왜 필요한가 — 2026-08-15 에 감시자가 조용히 고장났다
#     감시 루프가 `pgrep -f lifecycle_1h_backtest` 로 완료를 판정했는데,
#     그 pgrep 을 실어 나르는 **ssh 명령 자체의 cmdline 에 같은 문자열이
#     들어 있어** 언제나 자기 자신을 매칭했다. 작업은 18:41 에 끝났는데
#     감시자는 계속 "진행 중"이라 자동 보고가 오지 않았다.
#     대표님이 물어보셔서 발견했다 — 안 물어보셨으면 몰랐다.
#
#     패턴 매칭으로 프로세스 생사를 판정하지 마라. **작업이 스스로 완료를
#     남기게** 하고 그 표식만 본다.
#
# 만들면서 자체 시험에 세 번 더 걸렸다 — 전부 조용히 실패하는 종류다:
#   ① `{ ... }` 로 감싸면 명령 안의 `exit` 가 래퍼까지 죽여 완료 표식을
#      못 남긴다 → **서브셸** `( ... )` 로 감싼다
#   ② `sh` 는 민트에서 dash 라 `source` 가 없어 **rc=127** 로 죽는다
#      → `bash` 로 실행한다
#   ③ 명령에 작은따옴표가 들어가면 `bash -c '...'` 인용이 깨진다
#      → **base64 로 감싸** 인용 문제를 원천 차단한다
#
# 사용:
#   source scripts/lib/remote_job.sh
#   remote_launch mint /home/mint/auto_trading/backend myjob \
#       "source venv/bin/activate && PYTHONPATH=. python3 -m scripts.foo"
#   remote_wait mint myjob 240        # 30초 간격 240회(=2시간)까지
#   remote_log  mint myjob            # 로그 출력

REMOTE_STATE_DIR=${REMOTE_STATE_DIR:-/tmp/remote_jobs}

# remote_launch <host> <workdir> <name> <command>
remote_launch() {
    local host=$1 wd=$2 name=$3 cmd=$4 b64
    # ⚠ base64 — 명령 안의 따옴표·개행이 인용을 깨뜨리지 못하게 한다
    b64=$(printf '%s' "$cmd" | base64 -w0)
    ssh -o ConnectTimeout=30 "$host" \
        "D=$REMOTE_STATE_DIR; N=$name; mkdir -p \$D; \
         rm -f \$D/\$N.done \$D/\$N.rc; cd $wd || exit 1; \
         echo $b64 | base64 -d > \$D/\$N.cmd; \
         nohup bash -c '( bash '\$D'/'\$N'.cmd ) > '\$D'/'\$N'.log 2>&1; \
           echo \$? > '\$D'/'\$N'.rc; touch '\$D'/'\$N'.done' >/dev/null 2>&1 & \
         sleep 1; echo launched:$name"
}

# remote_wait <host> <name> [max_polls] — 완료 표식만 본다(패턴 매칭 없음)
remote_wait() {
    local host=$1 name=$2 max=${3:-240} i rc
    for ((i = 0; i < max; i++)); do
        if ssh -o ConnectTimeout=20 "$host" \
               "test -f $REMOTE_STATE_DIR/$name.done" 2>/dev/null; then
            rc=$(ssh -o ConnectTimeout=20 "$host" \
                 "cat $REMOTE_STATE_DIR/$name.rc 2>/dev/null" || echo "?")
            echo "done:$name rc=$rc"
            return 0
        fi
        sleep 30
    done
    echo "timeout:$name (${max}회 폴링 초과 — 작업은 계속 돌고 있을 수 있다)"
    return 1
}

# remote_log <host> <name> [tail_lines]
remote_log() {
    local host=$1 name=$2 n=${3:-40}
    ssh -o ConnectTimeout=20 "$host" "tail -$n $REMOTE_STATE_DIR/$name.log"
}
