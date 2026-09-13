#!/data/data/com.termux/files/usr/bin/bash
# 用法: timeit.sh <label> <命令...>
# 输出: label<TAB>毫秒<TAB>退出码<TAB>时间戳
# 计时用 wall clock（date +%s%N），命令的 stdout/stderr 追加到 $BENCH_LOG
set -u
label="${1:?需要 label}"; shift
log="${BENCH_LOG:-$HOME/bench/results/raw.log}"
start=$(date +%s%N)
"$@" >>"$log" 2>&1
rc=$?
end=$(date +%s%N)
printf '%s\t%d\t%d\t%s\n' "$label" "$(( (end - start) / 1000000 ))" "$rc" "$(date -Iseconds)"
