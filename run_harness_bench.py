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
import argparse, json, os, shutil, subprocess, sys, threading, time, tempfile, traceback
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


def _kill_tree(pid: int) -> None:
    """杀整棵进程树（父 + 所有子进程），防止 worker / openai HTTP 长连接 / 子
    Python 泄漏。Windows 用 taskkill /T；POSIX 优先 psutil，回退 killpg。"""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=15,
            )
            return
        # POSIX：优先 psutil 杀整树
        try:
            import psutil
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
            parent.kill()
            return
        except ImportError:
            pass
        import signal as _sig
        try:
            os.killpg(os.getpgid(pid), _sig.SIGKILL)
        except Exception:
            os.kill(pid, _sig.SIGKILL)
    except Exception:
        pass


def run_nexa_on_task(task: Task, timeout: int = 300) -> VerifyResult:
    """在临时目录跑 Nexa harness 处理单个任务。

    进程管理用 Popen + daemon drain 线程，避免 subprocess.run 的
    communicate() 在 stderr 管道写满时死锁、导致 timeout 失效。
    超时时杀整棵进程树，防止子进程泄漏。"""
    # ignore_cleanup_errors=True：Windows 下子进程被 kill 后文件句柄释放有延迟，
    # rmtree 撞上锁会抛 PermissionError；临时目录是一次性的，清不掉就留着（OS 自清），
    # 绝不能让单个任务的目录清理拖垮整个长跑。
    with tempfile.TemporaryDirectory(prefix=f"nexa_bench_{task.id}_", ignore_cleanup_errors=True) as workdir:
        workdir = Path(workdir)

        # 1. 任务 setup：写 setup_files（newline="" LF 保真）+ 调 setup_callback
        #    （程序化建二进制 fixture：users.db / .xlsx / .zip / .tar / .gz / cp1251 /
        #     锁定文件 / 大日志 等）。对齐 bench 官方 runner（runner.py:643、
        #    runner_cli.py:1304、runner_openrouter.py:404、harbor_export.py:291 均调
        #    task.setup(ws)）。此前只手写 setup_files、漏调 setup_callback → 二进制
        #    fixture 从未生成，agent 找不到输入文件（bench 基线对 Nexa 不公的根因，
        #    影响 28/58 失败）。core.py Task.setup 用 newline="" 防 Windows \r\n 翻译
        #    破坏字节级任务（md5/哈希）。
        task.setup(workdir)

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
            "PYTHONIOENCODING": "utf-8",
        }

        proc = None
        timed_out = False
        try:
            # Popen + drain 线程：drain 持续排空 stdout/stderr，管道永不写满，
            # 主线程 wait(timeout) 的 poll 才能真正被超时中断（不死锁）。
            proc = subprocess.Popen(
                ["nexa", "run", NEXA_SRC],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(workdir),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            stdout_chunks = []
            stderr_chunks = []

            def _drain(stream, sink):
                try:
                    for line in iter(stream.readline, ""):
                        sink.append(line)
                except Exception:
                    pass
                finally:
                    try:
                        stream.close()
                    except Exception:
                        pass

            t_out = threading.Thread(target=_drain, args=(proc.stdout, stdout_chunks), daemon=True)
            t_err = threading.Thread(target=_drain, args=(proc.stderr, stderr_chunks), daemon=True)
            t_out.start()
            t_err.start()

            # 写入 stdin（prompt + exit）并关闭，agent 从 stdin 读
            try:
                proc.stdin.write(stdin_data)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

            # 手动 poll 超时：不依赖 proc.wait(timeout)——task_262 实测它偶尔不触发
            # TimeoutExpired（进程跑了 3747s/62min 才自己退出，300s 上限形同虚设，
            # 拖垮整趟长跑）。改用 time.time() 墙钟 + proc.poll() 非阻塞轮询，到点必杀。
            # drain 线程持续排空管道，poll 不依赖管道状态，超时真正可强制触发。
            deadline = time.time() + timeout
            while True:
                if proc.poll() is not None:
                    break  # 进程已退出
                if time.time() >= deadline:
                    timed_out = True
                    _kill_tree(proc.pid)
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
                    break
                time.sleep(0.5)

            # 等 drain 线程读完尾部数据
            t_out.join(timeout=5)
            t_err.join(timeout=5)

            stdout_text = "".join(stdout_chunks)
            stderr_text = "".join(stderr_chunks)

            if timed_out:
                return VerifyResult(False, f"超时 ({timeout}s)")

            # 解析 JSON 事件（判断 agent 是否完成）
            events = []
            for line in stdout_text.split("\n"):
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
                return VerifyResult(False, f"无输出（exit={proc.returncode}, stderr={stderr_text[:100] if stderr_text else ''})")
            if errors and not done:
                return VerifyResult(False, f"引擎错误: {errors[0].get('message', '')[:100]}")

        except Exception as e:
            if proc is not None:
                try:
                    _kill_tree(proc.pid)
                except Exception:
                    pass
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
    out_file = THIS_DIR / f"benchmark_results_{int(time.time())}.json"

    for i, task in enumerate(tasks):
        elapsed = 0
        t0 = time.time()
        print(f"[{i+1}/{len(tasks)}] {task.id}: {task.name}...", end=" ", flush=True)

        # 单任务任何未捕获异常（如临时目录清理、verifier 崩溃）降级为 FAIL，
        # 绝不让一个任务的意外中断结束整个 351 长跑。
        try:
            result = run_nexa_on_task(task, timeout=args.timeout)
        except Exception as e:
            result = VerifyResult(False, f"运行异常(未捕获): {str(e)[:100]}")
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

        # 增量落盘：长跑（数百任务）中途被中断也不丢已跑结果
        try:
            out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

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

    # 结果已随每任务增量写入；此处仅最终确认落盘
    try:
        out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    print(f"详细结果已保存: {out_file}")


if __name__ == "__main__":
    main()
