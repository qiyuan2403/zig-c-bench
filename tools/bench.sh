#!/data/data/com.termux/files/usr/bin/bash
# 用法: bench.sh <case> <lang> <mode> <reps>
#   case : light | mid | heavy | xheavy
#   lang : c | zig
#   mode : clean | incr-fn | incr-hdr
# 结果追加到 $BENCH/results/measure.tsv
#        case  lang  mode  rep  ms  rc
set -u
BENCH="${BENCH:-$HOME/bench}"
ZIGBIN="${ZIGBIN:-zig}"
ZIGOPT="${ZIGOPT:--OReleaseFast}"
COOL="${COOL:-15}"          # 两次测量之间的散热秒数
cs="$1"; lang="$2"; mode="$3"; reps="${4:-3}"
dir="$BENCH/cases/$cs/$lang"
out="$BENCH/results/measure.tsv"
mkdir -p "$BENCH/results"

build() {
  if [ "$lang" = c ]; then
    ( cd "$dir" && make -j8 )
  else
    ( cd "$dir" && "$ZIGBIN" build-exe main.zig "$ZIGOPT" -femit-bin=app )
  fi
}

wipe() {
  if [ "$lang" = c ]; then
    rm -f "$dir"/*.o "$dir"/app
  else
    rm -rf "$dir/.zig-cache" "$dir"/app "$dir"/zig-out
  fi
}

tweak_fn() {
  local v=$(( ($1 % 4) + 2 ))
  if [ "$lang" = c ]; then
    sed -i "s/counter \* [0-9]*/counter * $v/" "$dir/mod_00.c"
  else
    sed -i "s/s\.counter \*% [0-9]*/s.counter *% $v/" "$dir/mod_00.zig"
  fi
}

tweak_hdr() {
  local v=$(( ($1 % 2) * 2 + 64 ))
  if [ "$lang" = c ]; then
    sed -i "s/#define BENCH_BUF [0-9]*/#define BENCH_BUF $v/" "$dir/common.h"
  else
    sed -i "s/pub const BENCH_BUF: usize = [0-9]*/pub const BENCH_BUF: usize = $v/" "$dir/common.zig"
  fi
}

record() {  # $1=rep
  local start end rc ms
  start=$(date +%s%N)
  build >/dev/null 2>&1
  rc=$?
  end=$(date +%s%N)
  ms=$(( (end - start) / 1000000 ))
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$cs" "$lang" "$mode" "$1" "$ms" "$rc" >> "$out"
  printf '  rep%-2s %8s ms  rc=%s\n' "$1" "$ms" "$rc"
}

echo "### $cs / $lang / $mode / reps=$reps  (zigbin=$ZIGBIN opt=$ZIGOPT)"
case "$mode" in
  clean)
    for i in $(seq 0 "$reps"); do
      wipe
      sync
      sleep "$COOL"
      record "$i"          # rep0 = 预热，丢弃
    done
    ;;
  incr-fn|incr-hdr)
    wipe
    build >/dev/null 2>&1 || { echo "基线构建失败"; exit 1; }
    for i in $(seq 1 "$reps"); do
      if [ "$mode" = incr-fn ]; then tweak_fn "$i"; else tweak_hdr "$i"; fi
      sleep "$COOL"
      record "$i"
    done
    ;;
  *)
    echo "未知 mode: $mode"; exit 2;;
esac
