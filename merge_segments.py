#!/usr/bin/env python
"""合并多段 benchmark_results_*.json → 全 351 结果 + 汇总。gitignored，用完即删。
用法: python merge_segments.py <seg1.json> <seg2.json> [<seg3.json> ...]
最后一段通常用通配让 shell 展开最新的 tail 文件。"""
import json, sys, glob, re
from pathlib import Path
from collections import Counter

files = sys.argv[1:]
if not files:
    print("用法: python merge_segments.py <seg.json> [...]")
    sys.exit(1)

merged = {}
for f in files:
    data = json.loads(Path(f).read_text(encoding="utf-8"))
    print(f"  {f}: {len(data)} 条, PASS {sum(1 for r in data if r['passed'])}/{len(data)}")
    for r in data:
        merged[r["id"]] = r  # 后段覆盖前段（去重，非重叠时等价合并）

rows = list(merged.values())
def tnum(tid):
    m = re.search(r"task_(\d+)", tid)
    return int(m.group(1)) if m else 0
rows.sort(key=lambda r: tnum(r["id"]))

passed = sum(1 for r in rows if r["passed"])
total = len(rows)
print(f"\n合并后: {passed}/{total} PASS ({100*passed/total:.1f}%)")
print(f"  id 范围: {rows[0]['id']} … {rows[-1]['id']}")

# 缺口检查（应连续覆盖 1..351）
nums = sorted(tnum(r["id"]) for r in rows)
missing = [n for n in range(1, 352) if n not in set(nums)]
if missing:
    print(f"  ⚠️ 缺失 task 编号: {missing}")
dup = [k for k, v in Counter(r["id"] for r in rows).items() if v > 1]
if dup:
    print(f"  ⚠️ 合并后仍有重复（不应发生）: {dup}")

# 失败清单 + 耗时分布
fails = [r for r in rows if not r["passed"]]
print(f"\n失败 {len(fails)} 条:")
for r in fails:
    print(f"  {r['id']:40s} {r['elapsed']:6.1f}s  {r['message'][:60]}")

print(f"\n耗时 top10 慢任务:")
for r in sorted(rows, key=lambda x: -x["elapsed"])[:10]:
    flag = "" if r["passed"] else " ❌"
    print(f"  {r['id']:40s} {r['elapsed']:7.1f}s{flag}")

# 超时类（elapsed > 320 或 message 含超时）——验证 _kill_tree 修复用
overshoot = [r for r in rows if r["elapsed"] > 320 or "超时" in r["message"]]
print(f"\n超时类任务 {len(overshoot)} 条（应全部 elapsed < ~330，验证 _kill_tree 修复）：")
for r in overshoot:
    print(f"  {r['id']:40s} {r['elapsed']:7.1f}s  {'超时' if '超时' in r['message'] else '正常完成但慢'}")

out = Path("bench_merged_351.json")
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n已写出: {out}")
