#!/data/data/com.termux/files/usr/bin/bash
# 频率采样器：后台运行，每秒记录三簇的当前频率与频率上限
# 用法: freqmon.sh <秒数> <输出文件>
secs="${1:-60}"
out="${2:-$HOME/bench/results/freq.tsv}"
end=$(( $(date +%s) + secs ))
: > "$out"
while [ "$(date +%s)" -lt "$end" ]; do
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(date +%s%N)" \
    "$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq 2>/dev/null)" \
    "$(cat /sys/devices/system/cpu/cpufreq/policy4/scaling_cur_freq 2>/dev/null)" \
    "$(cat /sys/devices/system/cpu/cpufreq/policy7/scaling_cur_freq 2>/dev/null)" \
    "$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq 2>/dev/null)" \
    "$(cat /sys/devices/system/cpu/cpufreq/policy4/scaling_max_freq 2>/dev/null)" \
    "$(cat /sys/devices/system/cpu/cpufreq/policy7/scaling_max_freq 2>/dev/null)" \
    >> "$out"
  sleep 1
done
