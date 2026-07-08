#!/usr/bin/env python
"""Nexa Harness-Bench Runner — 跑 Harness-Bench 351 任务评测 Nexa harness。

用法（在 claude-code-port 目录下）：
  python run_harness_bench.py --tasks 5          # 先跑前 5 个验证可行性
  python run_harness_bench.py --tasks 351        # 跑全套（3-5 小时）
  python run_harness_bench.py --tag easy          # 只跑 easy 标签的任务

前置：
  1. nexa build src/main.nx --harness=warn（编译引擎）
  2. secrets.nxs 配好 GLM coding 端点
  3. Harness-Bench repo clone 到 ../harness-bench 或环境变量 HARNESS_BENCH_PATH
"""
import argparse, json, os, shutil, subprocess, sys, time, tempfile, traceback
from pathlib import Path

# ─── 路径 ───
THIS_DIR = Path(__file__).parent.resolve()
NEXA_SRC = str(THIS_DIR / "src" / "main.nx")
SECRETS = THIS_DIR / "secrets.nxs"
HARNESS_BENCH = Path(os.environ.get("HARNESS_BENCH_PATH", str(THIS_DIR.parent / "harness-bench")))

if not HARNESS_BENCH.exists():
    # 尝试 Temp 目录
    for p in [Path("D:/Temp/wqf18/harness-bench"), Path("/tmp/harness-bench")]:
        if p.exists():
            HARNESS_BENCH = p
            break

sys.path.insert(0, str(HARNESS_BENCH))

# ─── 导入任务 ───
from harness_bench.tasks import ALL_TASKS, get_task
from harness_bench.core import Task, VerifyResult


def run_nexa_on_task(task: Task, timeout: int = 300) -> VerifyResult:
    """在临时目录跑 Nexa harness 处理单个任务。"""
    with tempfile.TemporaryDirectory(prefix=f"nexa_bench_{task.id}_") as workdir:
        workdir = Path(workdir)

        # 1. 写入 setup_files
        for rel, content in task.setup_files.items():
            f = workdir / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content, encoding="utf-8")

        # 2. 复制 secrets.nxs 到工作目录（Nexa 从 CWD 加载）
        if SECRETS.exists():
            shutil.copy(SECRETS, workdir / "secrets.nxs")

        # 3. 构造 Nexa 命令：stdin pipe prompt + /exit
        # 用 JSON events 模式（非交互），permission=auto
        stdin_data = json.dumps({"type": "message", "content": task.prompt}) + "\n" + \
                      json.dumps({"type": "exit"}) + "\n"

        env = {
            **os.environ,
            "NEXA_PERMISSION_MODE": "auto",
            "NEXA_QUIET": "1",
            "NEXA_JSON_EVENTS": "1",
            "NEXA_STREAM_TOOLS": "1",
            "PYTHONUNBUFFERED": "1",
        }

        try:
            proc = subprocess.run(
                ["nexa", "run", NEXA_SRC],
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(workdir),
                env=env,
                encoding="utf-8",
                errors="replace",
            )

            # 解析 JSON 事件（判断 agent 是否完成）
            events = []
            for line in (proc.stdout or "").split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

            done = any(e.get("type") == "done" for e in events)
            errors = [e for e in events if e.get("type") == "error"]

            if not done and not events:
                return VerifyResult(False, f"无输出（exit={proc.returncode}, stderr={proc.stderr[:100] if proc.stderr else ''})")
            if errors and not done:
                return VerifyResult(False, f"引擎错误: {errors[0].get('message', '')[:100]}")

        except subprocess.TimeoutExpired:
            return VerifyResult(False, f"超时 ({timeout}s)")
        except Exception as e:
            return VerifyResult(False, f"运行异常: {str(e)[:100]}")

        # 4. 运行 verifier 检查工作目录
        try:
            result = task.verifier(workdir)
            return result
        except Exception as e:
            return VerifyResult(False, f"验证异常: {str(e)[:100]}")


def main():
    parser = argparse.ArgumentParser(description="Nexa Harness-Bench Runner")
    parser.add_argument("--tasks", type=int, default=5, help="跑前 N 个任务（默认 5）")
    parser.add_argument("--tag", type=str, default=None, help="只跑指定标签的任务")
    parser.add_argument("--timeout", type=int, default=300, help="每任务超时秒数")
    parser.add_argument("--start", type=int, default=0, help="从第 N 个任务开始")
    args = parser.parse_args()

    tasks = ALL_TASKS
    if args.tag:
        tasks = [t for t in tasks if args.tag in t.tags]
    tasks = tasks[args.start:args.start + args.tasks]

    print(f"\n{'='*60}")
    print(f"Nexa Harness-Bench Runner")
    print(f"任务数: {len(tasks)} | 超时: {args.timeout}s/任务")
    print(f"模型: GLM-5.1 (coding endpoint)")
    print(f"{'='*60}\n")

    passed = 0
    failed = 0
    results = []

    for i, task in enumerate(tasks):
        elapsed = 0
        t0 = time.time()
        print(f"[{i+1}/{len(tasks)}] {task.id}: {task.name}...", end=" ", flush=True)

        result = run_nexa_on_task(task, timeout=args.timeout)
        elapsed = time.time() - t0

        if result.passed:
            passed += 1
            print(f"✅ PASS ({elapsed:.1f}s)")
        else:
            failed += 1
            print(f"❌ FAIL ({elapsed:.1f}s) — {result.message}")

        results.append({
            "id": task.id,
            "name": task.name,
            "passed": result.passed,
            "message": result.message,
            "elapsed": round(elapsed, 1),
        })

    # ─── 汇总 ───
    total = passed + failed
    rate = (passed / total * 100) if total > 0 else 0
    print(f"\n{'='*60}")
    print(f"结果: {passed}/{total} PASS ({rate:.1f}%)")
    print(f"用时: {sum(r['elapsed'] for r in results):.0f}s")
    print(f"{'='*60}")

    # 对比数据
    print(f"\n对比（Harness-Bench 官方数据）:")
    print(f"  Claude Code + Opus 4.8  = 351/351 (100.0%)")
    print(f"  Claude Code + Sonnet 4.6 = 341/351 (97.2%)")
    print(f"  deepagents + GLM-5.1     = 335/351 (95.4%)")
    print(f"  Nexa harness + GLM-5.1   = {passed}/{total} ({rate:.1f}%)")
    print(f"{'='*60}\n")

    # 保存结果
    out_file = THIS_DIR / f"benchmark_results_{int(time.time())}.json"
    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"详细结果已保存: {out_file}")


if __name__ == "__main__":
    main()
