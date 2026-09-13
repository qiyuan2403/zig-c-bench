#!/usr/bin/env bash
# x86_64 CI 基准：C vs Zig（0.16 稳定 / 0.17-dev），clean 与增量（含 -fincremental）
# 输出：results/cb.tsv  列 = 项 耗时ms 退出码
set -uo pipefail

R="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$R/results/cb.tsv"
mkdir -p "$R/results"
: > "$OUT"

Z16="${ZIG016:-$R/zig016/zig}"
Z17="${ZIG017:-$R/zig017/zig}"
JOBS="$(nproc)"

rec() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$OUT"; printf '%-34s %9s ms  rc=%s\n' "$1" "$2" "$3"; }

run() {  # run <label> <workdir> <cmd...>
  local label="$1" wd="$2"; shift 2
  local s e rc
  s=$(date +%s%N)
  ( cd "$wd" && "$@" ) >/dev/null 2>&1
  rc=$?
  e=$(date +%s%N)
  rec "$label" "$(( (e - s) / 1000000 ))" "$rc"
}

echo "## 环境"
echo "cores: $JOBS"
grep -m1 'model name' /proc/cpuinfo || true
"$Z16" version || true
"$Z17" version || true

echo
echo "## 生成对等工程"
rm -rf "$R/cases"
for spec in "light 2 8 6" "mid 12 10 20" "heavy 40 12 40"; do
  set -- $spec
  python3 "$R/gen/gen.py" c   "$R/cases/$1/c"   "$2" "$3" "$4"
  python3 "$R/gen/gen.py" zig "$R/cases/$1/zig" "$2" "$3" "$4"
done

tweak_c()   { sed -i "s/counter \* [0-9]*/counter * $(( ($1 % 4) + 2 ))/" "$1/mod_00.c"; }
tweak_zig() { sed -i "s/s\.counter \*% [0-9]*/s.counter *% $(( ($1 % 4) + 2 ))/" "$1/mod_00.zig"; }

echo
echo "## C：clean 与增量"
for cs in light mid heavy; do
  d="$R/cases/$cs/c"
  rm -f "$d"/*.o "$d"/app
  run "$cs/c/clean" "$d" make -j"$JOBS"
  tweak_c "$d" 1
  run "$cs/c/incr-fn" "$d" make -j"$JOBS"
  tweak_c "$d" 2
  run "$cs/c/incr-fn2" "$d" make -j"$JOBS"
done

echo
echo "## Zig 0.17：clean / 增量 / -fincremental"
for cs in light mid heavy; do
  d="$R/cases/$cs/zig"

  rm -rf "$d/.zig-cache" "$d"/app "$d"/zig-out
  run "$cs/zig17/clean" "$d" "$Z17" build-exe main.zig -OReleaseFast -femit-bin=app

  tweak_zig "$d" 1
  run "$cs/zig17/incr-nocache-flag" "$d" "$Z17" build-exe main.zig -OReleaseFast -femit-bin=app

  tweak_zig "$d" 2
  run "$cs/zig17/incr-again" "$d" "$Z17" build-exe main.zig -OReleaseFast -femit-bin=app

  rm -rf "$d/.zig-cache" "$d"/app "$d"/zig-out
  run "$cs/zig17/incr-FIRST" "$d" "$Z17" build-exe main.zig -OReleaseFast -fincremental -femit-bin=app

  tweak_zig "$d" 3
  run "$cs/zig17/incr-fincremental" "$d" "$Z17" build-exe main.zig -OReleaseFast -fincremental -femit-bin=app

  tweak_zig "$d" 4
  run "$cs/zig17/incr-fincremental2" "$d" "$Z17" build-exe main.zig -OReleaseFast -fincremental -femit-bin=app
done

echo
echo "## Zig 0.16（本机 aarch64 上用的就是这个版本线）"
for cs in light mid; do
  d="$R/cases/$cs/zig"
  rm -rf "$d/.zig-cache" "$d"/app "$d"/zig-out
  run "$cs/zig16/clean" "$d" "$Z16" build-exe main.zig -OReleaseFast -femit-bin=app
  tweak_zig "$d" 1
  run "$cs/zig16/incr" "$d" "$Z16" build-exe main.zig -OReleaseFast -femit-bin=app
done

echo
echo "## Zig Debug 档（迭代常用）"
for cs in light mid; do
  d="$R/cases/$cs/zig"
  rm -rf "$d/.zig-cache" "$d"/app
  run "$cs/zig17/clean-Debug" "$d" "$Z17" build-exe main.zig -ODebug -femit-bin=app
done

echo
echo "## 单次编译的固定开销（空程序）"
T="$R/tmp"; mkdir -p "$T"
printf 'pub fn main() void {}\n' > "$T/tiny.zig"
printf 'int main(void){return 0;}\n' > "$T/tiny.c"
rm -rf "$T/.zig-cache"
run "tiny/zig17/build-exe" "$T" "$Z17" build-exe tiny.zig -femit-bin=t1
run "tiny/zig17/build-exe-again" "$T" "$Z17" build-exe tiny.zig -femit-bin=t1
run "tiny/zig17/build-obj" "$T" "$Z17" build-obj tiny.zig -femit-bin=t1.o
run "tiny/zig17/fno-emit-bin" "$T" "$Z17" build-obj tiny.zig -fno-emit-bin
run "tiny/clang/-O2-c" "$T" clang -O2 -c tiny.c -o t1c.o
run "tiny/gcc/-O2-c" "$T" gcc -O2 -c tiny.c -o t1g.o

echo
echo "## 真实 C 工程：SQLite amalgamation（27 万行单文件）"
S="$R/sqlite"
if [ -f "$S/sqlite3.c" ]; then
  run "sqlite/clang-O2-c" "$S" clang -O2 -c sqlite3.c -o /tmp/sq-clang.o
  run "sqlite/gcc-O2-c"   "$S" gcc   -O2 -c sqlite3.c -o /tmp/sq-gcc.o
  run "sqlite/zigcc-O2-c" "$S" "$Z17" cc -O2 -c sqlite3.c -o /tmp/sq-zig.o
else
  echo "(跳过：未提供 sqlite3.c)"
fi

echo
echo "## 完成"
cat "$OUT"
