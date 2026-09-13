#!/data/data/com.termux/files/usr/bin/bash
# 采样 CPU 频率与（若可读）温度，输出一行紧凑摘要
# 用法: freq.sh <label>
label="${1:-sample}"
freqs=""
for c in 0 4 7; do
  f=$(cat "/sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq" 2>/dev/null)
  freqs="$freqs cpu$c=${f:--}"
done
t=""
for z in /sys/class/thermal/thermal_zone*/temp; do
  [ -r "$z" ] && t="$t $(cat "$z" 2>/dev/null)"
done
printf '%s\t%s\ttemp:%s\n' "$label" "$freqs" "${t:--}"
