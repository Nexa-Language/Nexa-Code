# 基准驱动开发 · Phase A / B / C

> 本文件是交给「Claude Code 开发会话」的完整提示词。目标：把项目从「堆功能不堆证据」切换到「拿客观分数驱动修复」。
> 给开发会话时直接引用本文件：`@docs/dev-prompts/PHASE_BENCH_BASELINE.md`。

---

## 0. 北极星与心法

- **目标**：跑通 Harness-Bench 351，拿到 `Nexa harness + GLM-5.1 = X/351 (Y%)`——本项目的**第一个客观质量坐标**。
- **对比锚点**：`deepagents + GLM-5.1 = 335/351 (95.4%)`（官方数据）。我们不奢求追平，但要知道自己在哪。
- **心法（揪头发，升一层看）**：过去 76 个 commit 堆了大量功能，却**从没有一个客观分数证明质量**。这一阶段的产出不是「又加了 N 个命令」，而是「分数从 A 提升到 B」。即使最终只做到 250/351，只要 A→B 真实可复现，这一阶段就成功。
- **铁律**：从今天起，**没有一个失败 task_id 作依据的 .nx 改动 = 不许动**。这是用户明确要求的「理性而非盲目」。

---

## 前置：环境自检（动手前先过，5 分钟）

1. `nexa build src/main.nx` → 成功（编译引擎）。
2. `secrets.nxs` 存在，GLM coding 端点 `https://open.bigmodel.cn/api/coding/paas/v4` 可通。
3. `HARNESS_BENCH_PATH` 指向 `D:/Temp/wqf18/harness-bench`（或 runner 自动探测成功）。
4. `python tests/tools/test_tools.py` → 记录当前基线 = **60 PASS / 0 FAIL / 2 SKIP**（回归红线）。

任一项不通 → 先解决环境，**不要**碰 src/*.nx。

---

## Phase A — 修 runner 超时 bug（解锁阻塞，本会话内必须完成）

文件：`run_harness_bench.py`，函数 `run_nexa_on_task`（37–108 行）。

当前 bug 有**两层**，都要修：

### 层 1：管道死锁（timeout 失效的根因）

67–77 行用 `subprocess.run(..., capture_output=True)`，内部即 `communicate()`。当 Nexa 引擎 + GLM 重试退避**狂刷 stderr/stdout**（task_03 实测 814s）时，子进程 stderr 管道缓冲区（Windows ~4KB）写满，而 `subprocess.run` 在 communicate 中一次性排空前不继续——**死锁**。Python 卡在 C 层读管道，`timeout` 的 poll 无法中断，于是 300s 被拖成 814s。

**解法**：改用 `subprocess.Popen` + 后台 daemon 线程 drain stdout/stderr 到 list（线程安全 append），主线程 `proc.wait(timeout=timeout)`。这样 timeout 真正可触发。

### 层 2：进程树未清理（子进程杀不掉）

即使 timeout 触发，`TimeoutExpired` 默认只 `.kill()` 直接子进程（nexa python 进程），它 spawn 的 worker / openai HTTP 长连接 / 子 Python 进程**不会被杀**，GLM 端继续被占用，任务叠加。

**解法**：超时时杀整树。Windows：`subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)])`；或更可移植用 `psutil`：`p = psutil.Process(proc.pid); [c.kill() for c in p.children(recursive=True)]; p.kill()`（无 psutil 则 `pip install psutil`）。

### 验收标准

- `python run_harness_bench.py --tasks 5 --timeout 120`：task_03 要么 120s 内完成、要么 ~120s 内被硬 kill 返回 FAIL（message 含「超时」），**绝不许拖到 814s**。
- 其余 4 个任务结果不变（仍 PASS）。
- 再 smoke：`--tasks 10`，全部在各自 timeout 内返回（即使 FAIL）。

### 实现注意

- 现有 `env["PYTHONUNBUFFERED"]="1"` 保留；补 `env["PYTHONIOENCODING"]="utf-8"`。
- drain 线程用 `daemon=True`；保留「解析 JSON events 判断 done」逻辑，**只重构进程管理层**。
- Windows 下 `Popen` 可加 `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP`，便于按组杀。

---

## Phase B — 跑 351 拿基线（后台，3–5h）

Phase A 验收通过后：

1. 确认 `nexa build src/main.nx` 成功、secrets 通、harness-bench 路径命中。
2. 后台启动：`python run_harness_bench.py --tasks 351 --timeout 300`，**用 `run_in_background`**，跑完通知。
3. 跑的过程中**不要**改 src/（会污染正在跑的引擎）。可做：读 `PORT_TRACE.md`、准备失败分类 checklist。
4. 产出：`benchmark_results_*.json`（本地，gitignored）+ 控制台 `Nexa harness + GLM-5.1 = X/351 (Y%)`。

---

## Phase C — 失败分类 + 根因修复循环（核心，反盲目的关键）

拿到失败列表后，对**每个**失败 task 先做三分类——**不许跳过分类直接改代码**：

| 类别 | 判据 | 动作 |
|---|---|---|
| **H1 harness bug** | 任务本该能过，但引擎有缺陷：工具返回错、循环早退、JSON 事件漏 `done`、工具参数序列化错、该调用的工具没调用、context 拼接错、permission 拦截了本该放行的操作。证据：对照 CC 原版 `refs/claude-code-ts/` 能指出 Nexa 哪里偏离。 | **修**。对照 CC 源码修正 `src/*.nx` → rebuild → 单跑该 task 验证 PASS → 过 §验证门。 |
| **H2 模型能力限制** | harness 表现正确（工具调用对、循环对），但 GLM-5.1 推理/规划不如 Opus。证据：单跑看 events，agent 思路跑偏、选错工具、没规划好——**不是** harness 的锅。 | **不修**。记入 BENCH_BASELINE.md「模型天花板」表，标注「需更强模型」，跳过。**不许**为过任务 hard-code hack。 |
| **H3 verifier 问题** | task 的 setup_files / prompt / verifier 本身有歧义或过严（要求精确字符串，agent 生成等价但写法不同）。 | **谨慎**。先确认是 verifier 而非 harness；若 CC+Opus 也会被判过严，记录并跳过。**不许**改 harness 迁就 verifier。 |

### 修复策略

- **H1 优先**，按「影响面」排序：一个根因（如工具参数序列化）能解释多个失败 task 的，先修它，收益最大。
- 修完一个 H1 → **重跑它影响的所有 task** 确认（不必立刻全量重跑）。
- 阶段性（如修满 5 个根因）做一次 `--tasks 351` 全量重跑，确认分数真实提升（防单 task 过了却引入回归）。
- **铁律**：H2/H3 一律不许改 harness 凑过。**分数可以低，但必须真实。**

---

## 验证门（每个 commit 前必过）

1. `nexa build src/main.nx` → 成功，无新增 warning。
2. `python tests/tools/test_tools.py` → **≥ 60 PASS**（基线 60/0/2）。回归即返工。
3. 该 commit 修复的 task → 单跑 PASS（贴 events 证据）。
4. commit message 格式（让 git log 成为分数上升轨迹）：
   `fix(bench): task_XX <根因一句话> — bench A→B`
   例：`fix(bench): task_073 Edit 返回未刷 context — bench 280→283`

---

## 提交与推送

- 「修复一个 H1 根因并验证通过」= 一个原子 commit。
- **不加** `Co-Authored-By: Claude` trailer；**不碰** `LICENSE`（用户与队友讨论中，仓库当前无 LICENSE）。
- 推送前 `git fetch`；若远端有队友新提交，用 `git merge origin/master --no-edit`（教训：本环境用 merge 不用 rebase，rebase 会卡在引入 gitignored 文件的旧 commit）。
- 推送：`git push origin master`（个人账号 cookiesheep）。

---

## 本阶段交付物

1. `run_harness_bench.py` 健壮的超时 + 进程树清理（Phase A）。
2. 第一个客观分数：`Nexa + GLM-5.1 = X/351 (Y%)`。
3. `docs/reports/BENCH_BASELINE.md`（**入库**）：分数 + 失败三分类表 + 已修根因清单 + 模型天花板清单。这是本阶段唯一需要写进 git 的核心文档。
4. git log 可见分数上升轨迹。

---

## 不要做的事（防盲目清单）

- ❌ 不要为了「好看」去深化 partial 命令——除非某个失败 task 明确指向它。
- ❌ 不要新增 CC 里没有的工具。
- ❌ 不要碰 `ui-ink/`、`ui/`（Codex 领域）。
- ❌ 不要 commit `LICENSE` / trailer / `benchmark_results_*.json`。
- ❌ **不要在拿到基线分数前就改引擎**——先有数字，再有改动。

---

## 一句话总结（给开发会话的启动指令）

> 先做环境自检 → 修 `run_nexa_on_task` 的两层超时 bug（管道死锁 + 进程树清理）→ smoke 10 个 → 后台起 `--tasks 351` 拿基线 → 对失败做 H1/H2/H3 三分类，只修 H1 且对照 CC 源码、每修必过验证门、commit 带 `bench A→B`。拿到第一个真实分数即本阶段成功。
