#!/data/data/com.termux/files/usr/bin/bash
# 生成所有档位的对等 C / Zig 工程
# 档位格式: <name> <modules> <funcs_per_module> <steps_per_func>
set -eu
BENCH="${BENCH:-$HOME/bench}"
CASES="light 2 8 6
mid 12 10 20
heavy 40 12 40
xheavy 120 12 60"

mkdir -p "$BENCH/cases"
while read -r name m f s; do
  [ -z "$name" ] && continue
  printf '%-8s ' "$name"
  python3 "$BENCH/gen/gen.py" c   "$BENCH/cases/$name/c"   "$m" "$f" "$s"
  printf '%-8s ' ""
  python3 "$BENCH/gen/gen.py" zig "$BENCH/cases/$name/zig" "$m" "$f" "$s"
done <<< "$CASES"
