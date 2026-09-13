#!/usr/bin/env python3
"""生成结构等价的 C / Zig 多模块工程，用于构建速度基准。

用法:
  gen.py c   <target_lines> <outdir>
  gen.py zig <target_lines> <outdir>

设计要点:
  * 每条语句自包含（不跨语句依赖临时变量），两种语言按同一操作序列渲染
  * 同一条语句在 C / Zig 里占用相同行数 -> 总行数可精确对等
  * 每个模块都引用公共定义 (common.h / common.zig)，用于测"改公共定义后重编放大"
  * 累加进共享状态并在 main 汇总输出，防止被优化删除
  * 按目标行数二分反推每函数语句数，两边各自命中目标 ±2%
"""
import os
import sys

# 语句模式 id: 0..4
N_PATTERNS = 5


def pattern_of(mi, fi, k):
    return (mi * 7 + fi * 3 + k) % N_PATTERNS


def n_lines_of_pattern(p):
    # 模式 2 是 if/else（5 行），其余为 1 行 —— 两种语言一致
    return 5 if p == 2 else 1


def line_cost(mi, fi, steps):
    return sum(n_lines_of_pattern(pattern_of(mi, fi, k)) for k in range(steps))


# ---------------- C ----------------
def c_stmt(p, mi, fi, k):
    idx = f"(a + {k * 13} + b * {k + 1})"
    coef = (k % 9) + 2
    const = (k * 31) % 97
    mask = 1 << (1 + (const % 5))
    if p == 0:
        return [f"    acc += s->buf[({idx}) & 63] * {coef};"]
    if p == 1:
        return [f"    s->buf[(b + {k * 5}) & 63] = (int32_t)(acc + {const});"]
    if p == 2:
        return [
            f"    if (acc & {mask}) {{",
            f"        acc += {coef * 11};",
            "    } else {",
            f"        acc -= {const};",
            "    }",
        ]
    if p == 3:
        return [f"    acc = (acc << {1 + (k % 3)}) + {const};"]
    return [f"    for (int j = 0; j < 4; ++j) {{ acc += s->buf[(j + {k}) & 63]; }}"]


def c_fn(mi, fi, steps):
    out = [f"static int32_t f{fi:02d}(Mod{mi} *s, int32_t a, int32_t b) {{",
           "    int32_t acc = (a * 3) ^ (b + 7);",
           "    acc += s->counter * 5;"]
    for k in range(steps):
        out += c_stmt(pattern_of(mi, fi, k), mi, fi, k)
    out += ["    s->counter = acc & 0xffff;",
            "    s->total ^= acc;",
            "    g_sink = (g_sink + acc) & 0x7fffffff;",
            "    return acc;",
            "}"]
    return "\n".join(out) + "\n"


def gen_c(nmods, funcs, steps):
    out = {}
    out["common.h"] = (
        "#ifndef BENCH_COMMON_H\n#define BENCH_COMMON_H\n\n"
        "#include <stdint.h>\n\n"
        "#define BENCH_BUF 64\n"
        f"#define BENCH_MODS {nmods}\n\n"
        "extern int32_t g_sink;\n\n#endif\n"
    )
    for mi in range(nmods):
        out[f"mod_{mi:02d}.h"] = (
            f"#ifndef BENCH_MOD_{mi:02d}_H\n#define BENCH_MOD_{mi:02d}_H\n\n"
            '#include "common.h"\n\n'
            "typedef struct {\n    int32_t buf[BENCH_BUF];\n    int32_t counter;\n    int32_t total;\n"
            f"}} Mod{mi};\n\nint32_t mod{mi}_run(Mod{mi} *s);\n\n#endif\n"
        )
        body = [f'#include "mod_{mi:02d}.h"', ""]
        for fi in range(funcs):
            body.append(c_fn(mi, fi, steps))
        body.append(f"int32_t mod{mi}_run(Mod{mi} *s) {{")
        body.append("    int32_t acc = 0;")
        for fi in range(funcs):
            body.append(f"    acc += f{fi:02d}(s, acc, {fi + 1});")
        body.append("    return acc;")
        body.append("}")
        out[f"mod_{mi:02d}.c"] = "\n".join(body) + "\n"
    main = ['#include <stdio.h>', '#include "common.h"']
    for mi in range(nmods):
        main.append(f'#include "mod_{mi:02d}.h"')
    main += ["", "int32_t g_sink = 0;", "", "int main(void) {", "    int32_t total = 0;"]
    for mi in range(nmods):
        main.append(f"    Mod{mi} m{mi} = {{{{0}}, 0, 0}};")
    main.append("    for (int iter = 0; iter < 8; ++iter) {")
    for mi in range(nmods):
        main.append(f"        total += mod{mi}_run(&m{mi});")
    main += ["    }",
             f'    printf("checksum=%d sink=%d\\n", (int)total, (int)g_sink);',
             "    return 0;", "}"]
    out["main.c"] = "\n".join(main) + "\n"
    out["Makefile"] = (
        "CC ?= clang\nCFLAGS ?= -O2 -std=c11\n"
        "SRCS := $(wildcard *.c)\nOBJS := $(SRCS:.c=.o)\n\n"
        "app: $(OBJS)\n\t$(CC) $(CFLAGS) -o $@ $(OBJS)\n\n"
        "%.o: %.c common.h\n\t$(CC) $(CFLAGS) -c $< -o $@\n\n"
        "clean:\n\trm -f $(OBJS) app\n\n.PHONY: clean\n"
    )
    return out


# ---------------- Zig ----------------
def z_stmt(p, mi, fi, k):
    idx = f"(a + {k * 13} + b * {k + 1})"
    coef = (k % 9) + 2
    const = (k * 31) % 97
    mask = 1 << (1 + (const % 5))
    if p == 0:
        return [f"    acc +%= s.buf[@intCast(({idx}) & 63)] *% {coef};"]
    if p == 1:
        return [f"    s.buf[@intCast((b + {k * 5}) & 63)] = @intCast(acc +% {const});"]
    if p == 2:
        return [
            f"    if (acc & {mask} != 0) {{",
            f"        acc +%= {coef * 11};",
            "    } else {",
            f"        acc -%= {const};",
            "    }",
        ]
    if p == 3:
        return [f"    acc = (acc << {1 + (k % 3)}) +% {const};"]
    return [f"    for (0..4) |j| {{ acc +%= s.buf[@intCast((j + {k}) & 63)]; }}"]


def z_fn(mi, fi, steps):
    out = [f"fn f{fi:02d}(s: *Mod{mi}, a: i32, b: i32) i32 {{",
           "    var acc: i32 = (a *% 3) ^ (b +% 7);",
           "    acc +%= s.counter *% 5;"]
    for k in range(steps):
        out += z_stmt(pattern_of(mi, fi, k), mi, fi, k)
    out += ["    s.counter = acc & 0xffff;",
            "    s.total ^= acc;",
            "    common.g_sink = (common.g_sink +% acc) & 0x7fffffff;",
            "    return acc;",
            "}"]
    return "\n".join(out) + "\n"


def gen_zig(nmods, funcs, steps):
    out = {}
    out["common.zig"] = (
        "pub const BENCH_BUF: usize = 64;\n"
        f"pub const BENCH_MODS: usize = {nmods};\n\n"
        "pub var g_sink: i32 = 0;\n\n"
        "pub const BenchState = struct {\n"
        "    buf: [BENCH_BUF]i32 = @splat(0),\n"
        "    counter: i32 = 0,\n"
        "    total: i32 = 0,\n"
        "};\n"
    )
    for mi in range(nmods):
        body = ['const common = @import("common.zig");', "",
                f"const Mod{mi} = common.BenchState;", ""]
        for fi in range(funcs):
            body.append(z_fn(mi, fi, steps))
        body.append(f"pub fn run(s: *Mod{mi}) i32 {{")
        body.append("    var acc: i32 = 0;")
        for fi in range(funcs):
            body.append(f"    acc +%= f{fi:02d}(s, acc, {fi + 1});")
        body.append("    return acc;")
        body.append("}")
        body.append("")
        body.append(f"pub fn entry(s: *Mod{mi}) i32 {{ return run(s); }}")
        out[f"mod_{mi:02d}.zig"] = "\n".join(body) + "\n"
    main = ['const std = @import("std");', 'const common = @import("common.zig");']
    for mi in range(nmods):
        main.append(f'const m{mi:02d} = @import("mod_{mi:02d}.zig");')
    main += ["", "pub fn main() void {", "    var total: i32 = 0;",
             "    var states: [common.BENCH_MODS]common.BenchState = undefined;",
             "    for (&states) |*st| st.* = .{};",
             "    var iter: usize = 0;",
             "    while (iter < 8) : (iter += 1) {"]
    for mi in range(nmods):
        main.append(f"        total +%= m{mi:02d}.entry(&states[{mi}]);")
    main += ["    }",
             '    std.debug.print("checksum={d} sink={d}\\n", .{ total, common.g_sink });',
             "}"]
    out["main.zig"] = "\n".join(main) + "\n"
    return out



# ---------------- Rust ----------------
def rs_stmt(p, mi, fi, k):
    idx = f"(a + {k * 13} + b * {k + 1})"
    coef = (k % 9) + 2
    const = (k * 31) % 97
    mask = 1 << (1 + (const % 5))
    if p == 0:
        return [f"    acc = acc.wrapping_add(s.buf[(({idx}) & 63) as usize].wrapping_mul({coef}));"]
    if p == 1:
        return [f"    s.buf[((b + {k * 5}) & 63) as usize] = acc.wrapping_add({const});"]
    if p == 2:
        return [
            f"    if acc & {mask} != 0 {{",
            f"        acc = acc.wrapping_add({coef * 11});",
            "    } else {",
            f"        acc = acc.wrapping_sub({const});",
            "    }",
        ]
    if p == 3:
        return [f"    acc = (acc << {1 + (k % 3)}).wrapping_add({const});"]
    return [f"    for j in 0..4 {{ acc = acc.wrapping_add(s.buf[((j + {k}) & 63) as usize]); }}"]


def rs_fn(mi, fi, steps):
    out = [f"    #[inline(never)]",
           f"    pub fn f{fi:02d}(s: &mut BenchState, a: i32, b: i32) -> i32 {{",
           "        let mut acc: i32 = (a.wrapping_mul(3)) ^ (b.wrapping_add(7));",
           "        acc = acc.wrapping_add(s.counter.wrapping_mul(5));"]
    for k in range(steps):
        out += rs_stmt(pattern_of(mi, fi, k), mi, fi, k)
    out += ["        s.counter = acc & 0xffff;",
            "        s.total ^= acc;",
            "        unsafe { G_SINK = (G_SINK.wrapping_add(acc)) & 0x7fffffff; }",
            "        acc",
            "    }"]
    return "\n".join(out) + "\n"


def gen_rust(nmods, funcs, steps):
    out = {}
    out["common.rs"] = (
        "pub const BENCH_BUF: usize = 64;\n"
        f"pub const BENCH_MODS: usize = {nmods};\n\n"
        "pub static mut G_SINK: i32 = 0;\n\n"
        "#[derive(Clone, Copy)]\n"
        "pub struct BenchState {\n"
        "    pub buf: [i32; BENCH_BUF],\n"
        "    pub counter: i32,\n"
        "    pub total: i32,\n"
        "}\n\n"
        "impl BenchState {\n"
        "    pub fn new() -> Self { BenchState { buf: [0; BENCH_BUF], counter: 0, total: 0 } }\n"
        "}\n"
    )
    out["main.rs"] = "mod common;\n" + "".join(f"mod m{mi:02d};\n" for mi in range(nmods)) + "\nuse common::*;\n\npub fn main() {\n    let mut total: i32 = 0;\n" + "".join(f"    let mut s{mi} = BenchState::new();\n" for mi in range(nmods)) + "    for _ in 0..8 {\n" + "".join(f"        total = total.wrapping_add(m{mi:02d}::entry(&mut s{mi}));\n" for mi in range(nmods)) + "    }\n    println!(\"checksum={} sink={}\", total, unsafe { G_SINK });\n}\n"
    for mi in range(nmods):
        body = ["use crate::common::*;", "", f"pub struct Mod{mi};", "", f"impl Mod{mi} {{"]
        for fi in range(funcs):
            body.append(rs_fn(mi, fi, steps))
        body.append(f"    pub fn run(s: &mut BenchState) -> i32 {{")
        body.append("        let mut acc: i32 = 0;")
        for fi in range(funcs):
            body.append(f"        acc = acc.wrapping_add(Mod{mi}::f{fi:02d}(s, acc, {fi + 1}));")
        body.append("        acc")
        body.append("    }")
        body.append("}")
        body.append("")
        body.append(f"pub fn entry(s: &mut BenchState) -> i32 {{ Mod{mi}::run(s) }}")
        out[f"m{mi:02d}.rs"] = "\n".join(body) + "\n"
    return out


def count_lines(files):
    return sum(v.count("\n") for v in files.values())


def build(lang, nmods, funcs, steps, outdir):
    gen = {"c": gen_c, "zig": gen_zig, "rust": gen_rust}[lang]
    files = gen(nmods, funcs, steps)
    os.makedirs(outdir, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(outdir, name), "w") as f:
            f.write(content)
    return dict(lang=lang, lines=count_lines(files), modules=nmods,
                funcs=funcs, steps=steps, files=len(files))


def main():
    # gen.py <lang> <outdir> <nmods> <funcs> <steps>
    lang, outdir = sys.argv[1], sys.argv[2]
    nmods, funcs, steps = (int(x) for x in sys.argv[3:6])
    info = build(lang, nmods, funcs, steps, outdir)
    print(" ".join(f"{k}={v}" for k, v in info.items()))


if __name__ == "__main__":
    main()
