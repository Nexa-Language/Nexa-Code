# Nexa Harness-Bench 基线报告

> 项目第一个客观质量坐标。**基准驱动开发** Phase B/C 交付物。
> 公平基线更新于 2026-08-07（含 fixture + AGENTS.md 两 H1 修复后的全量重跑）。
> 原始数据：`bench_merged_351.json`（351 任务逐条 pass/fail + 耗时 + 失败原因）。

---

## 1. 基线分数

| Harness | Model | 分数 | 备注 |
|---|---|---|---|
| Claude Code CLI | Claude Opus 4.8 | 351/351 (100.0%) | 满分基准 |
| Claude Code CLI | Claude Sonnet 4.6 | 341/351 (97.2%) | |
| deepagents | GLM-5.2 | 340/351 (96.9%) | 同模型家族 |
| **deepagents** | **GLM-5.1** | **335/351 (95.4%)** | ← **直接对比对象（同 harness 不同模型）** |
| **Nexa harness** | **GLM-5.1** | **321/351 (91.5%)** | ← **本项目公平基线（含两 H1 修复）** |

**结论**：Nexa harness + GLM-5.1 = **321/351 (91.5%)**，落后 deepagents + 同模型 14 任务 / 3.9 个百分点。

> **历史**：原始基线 **293/351 (83.5%)** 对 Nexa 不公——runner 漏调 `task.setup(ws)` 导致
> 28 个二进制 fixture（sqlite/xlsx/zip/gz/tar/cp1251…）从未生成，agent 找不到输入文件。
> 修复 a4af21b（fixture）+ a3fa23d（AGENTS.md）后全量重跑，回收 +28 → 321/351。
> 旧两段式跑法见 §6；本轮公平重跑分三段（1-262 / 263-338 / 339-351）合并去重无重叠。

---

## 2. 关键判断：差距是「结构性」的，不是「散乱」的

58 个失败**高度聚类**于 5 个可解释的子系统，不是随机分布。这是「分数可以真实改善」的前提：

| 簇 | 主题 | 任务数 | 占失败比 | 性质 | 置信 |
|---|---|---|---|---|---|
| **E** | 内存子系统（AGENTS.md 不加载） | 15 | 26% | **H1 已证明** | 高 |
| **A** | 二进制格式（xlsx/sqlite/zip/gzip/tar） | 25 | 43% | H1-提示 / H2 嫌疑 | 待单跑 |
| **C** | 超时循环（多步重构/分析） | 9 | 16% | H1 / H2 混合 | 待单跑 |
| **B** | 内容差异（产出但错） | 3 | 5% | H2 模型逻辑 | 中 |
| **F** | 编码/污染（cp1251/BOM/NUL） | 2 | 3% | H1 嫌疑 | 待单跑 |
| **D** | 重构不完整 | 1 | 2% | H2 | 中 |
| 杂项 | 环境/难判定 | 3 | 5% | H3/H2 | 低 |

**E + A = 40/58 = 69% 的失败**集中在这两个子系统。其中 E 已证明是单根因 H1（一次修复回收 15 任务）。

---

## 3. 失败三分类（H1/H2/H3）

### 簇 E — 内存子系统（15 任务）✅ **H1 已证明**

**根因（CC 源码对照铁证）**：

- CC `refs/claude-code-ts/src/utils/autonomyAuthority.ts`：
  - L16 `AUTONOMY_AGENTS_FILENAME = 'AGENTS.md'`
  - L433–455 发现并加载 AGENTS.md 文件
  - L497–499 `if (snapshot.agentsContent)` → 注入 `"Workspace authority from AGENTS.md:\n{内容}"` 进系统上下文
- Nexa `src/context.nx`：`get_claude_md()` **只发现 CLAUDE.md 层级**（L88，user `~/.claude/CLAUDE.md` + project cwd 向上 `CLAUDE.md` / `.claude/CLAUDE.md`），**完全不读 AGENTS.md**。

bench 的 memory 任务把指令放进 `AGENTS.md`（Codex/OpenAI 约定），其中第 2、5 条明确要求：「用户报告新事实（姓名/城市/偏好…）→ 以 `- Ключ: Значение` 存入 `MEMORY.md`」。agent 有 Write/Edit 工具能写，但**因为从不加载 AGENTS.md，从未见到这条指令** → 不写 MEMORY.md → 全族失败。

任务：
- 直接证明（verifier 查 MEMORY.md 内容）：223（- Город: Москва）、232（- Фокус-день: пятница）、251（height fact）、253（company FerrisCorp）
- 高度嫌疑（memory 任务，缺输出文件，同根因待修后单跑确认）：224、227、231、234、235、237、238、240、241、243、250

**修复**：`context.nx` 的 `get_claude_md` / 上下文组装阶段增加 AGENTS.md 发现（cwd 向上 + 根），注入为 workspace authority。**预期回收：15 任务（4 直接 + 11 待确认）**。

---

### 簇 A — 二进制格式（25 任务）⚠️ H1-提示 / H2 嫌疑（待单跑）

| 任务 | 类型 | 失败 |
|---|---|---|
| 111_xlsx_extract_b2 | xlsx 读 | 超时 |
| 112_xlsx_sum_column | xlsx 读 | total.txt 缺 |
| 113_xlsx_update_cell | xlsx 写 | inventory.xlsx 缺 |
| 123_sqlite_count | sqlite 读 | count.txt 缺 |
| 124_sqlite_sum | sqlite 读 | total.txt 缺 |
| 148_csv_to_xlsx | xlsx 写 | scores.xlsx 缺 |
| 149_sqlite_to_json | sqlite 读 | 超时 |
| 152_sqlite_join_to_json | sqlite 读 | 超时 |
| 153_xlsx_to_markdown_report | xlsx 读 | report.md 缺 |
| 158_xlsx_split_sheets | xlsx 写 | 超时 |
| 159_unzip_extract | zip 读 | extracted/ 缺 |
| 160_create_zip | zip 写 | bundle.zip 缺 |
| 161_gzip_compress | gzip 写 | input.txt.gz 缺 |
| 191_sqlite_revenue_report | sqlite 读 | 超时 |
| 196_xlsx_to_csv_and_json | xlsx 读 | data.csv 缺 |
| 198_tar_extract | tar 读 | extracted/ 缺 |
| 199_sqlite_filtered_export | sqlite 读 | big_clicks.csv 缺 |
| 201_reconcile_vip_users | sqlite 读 | 超时 |
| 202_zip_sales_consolidation | zip 读 | 超时 |
| 203_sqlite_team_markdown_report | sqlite 读 | team_report.md 缺 |
| 207_inventory_anomaly_report | xlsx 读 | 超时 |
| 210_tar_manifest_with_hashes | tar 读 | 超时 |
| 219_sql_paid_leaderboard | sqlite 读 | paid_leaderboard.csv 缺 |
| 328_skill_d2_meridian_reconcile_xlsx | xlsx 读 | reconciliation.csv 缺 |
| 343_adv_gzip_masquerade | gzip 读 | secret.txt 缺 |

**关键事实**：Nexa **有功能正常的 Bash 工具**（`src/tools/bash.nx`，`subprocess.run([bash,'-c',cmd])`，无命令过滤）→ agent 完全有能力跑 `python -c "import openpyxl; ..."` / `sqlite3` / `unzip` / `gzip -d`。所以**不是缺能力**。

**两种可能**：
- **H1-提示**：系统提示/工具描述里没有「二进制文件用 python 库（openpyxl/sqlite3/zipfile/gzip/tarfile）处理」的引导 → agent 不往 python 方向想。
- **H2**：GLM-5.1 本身没想到用 python 处理二进制（模型局限）。

**诊断动作（Phase C）**：单跑 task_123（sqlite_count）看 agent 是否尝试 python。若从不尝试 → 查 CC 系统提示有无二进制/python 引导（H1-提示）；若尝试但失败 → H2。

---

### 簇 C — 超时循环·非二进制（9 任务）⚠️ H1 / H2 混合（待单跑）

| 任务 | 主题 |
|---|---|
| 69_remove_comments | 注释剥离（文本） |
| 212_merge_config_precedence | 配置合并 |
| 217_extract_user_emails | JSON 邮件抽取 |
| 266_terminal_sha256_manifest | 哈希 manifest |
| 308_detect_unresolved_conflicts | 冲突检测 |
| 309_rename_refactor_scale | rename 传播 12 站点 |
| 311_apply_patch_stack_multifile | 9 patch 跨 4 文件 |
| 323_skill_g1_create_slugify_skill | skill 创建 |
| 341_adv_set_e_abort | set -e 脚本恢复 |

**观察**：266/308/309/311 连续超时，全是「多步重构 / 多文件 patch / 冲突传播」类 agentic 任务。Nexa **有** `multi_edit.nx`，所以多编辑原语存在。超时可能是：
- **H1**：agent 用单条 Edit 逐个改 → 工具调用数爆炸 → 300s 用尽；或缺「批量 patch 原语 / agentic 终止预算」。
- **H2**：GLM 反复重试/重做（redo loop）。

**诊断动作**：单跑 task_309 看工具调用轨迹。

---

### 簇 B — 内容差异（3 任务）🔵 H2 模型逻辑

| 任务 | 失败 |
|---|---|
| 132_md5_hash | hash 内容错 |
| 145_log_top_ip | top IP 错（预期 10.0.0.1） |
| 312_policy_driven_merge | m13.py 行错（VALUE = 16） |

agent 产出了文件但内容错——模型推理/计算错误。**H2，记录跳过**。

---

### 簇 F — 编码/污染（2 任务）⚠️ H1 嫌疑（待单跑）

| 任务 | 失败 |
|---|---|
| 333_adv_cp1251_decode | result.json 缺（读 cp1251→UTF-8） |
| 344_adv_dirty_log_sanitize | error_codes.txt 缺（BOM/NUL 净化） |

**嫌疑**：Nexa `read.nx` 默认按 UTF-8 读文件 → cp1251 / BOM / NUL 字节读出乱码或报错 → agent 看不到正确内容 → 放弃/循环。

**诊断动作**：查 `read.nx` 是否支持指定 encoding / BOM 剥离（对照 CC Read 的 encoding 参数）。

---

### 簇 D — 重构不完整（1 任务）🔵 H2

220_python_import_migration：`src/core/math_ops.py` 缺——agent 没把 import 迁移传播完整。H2。

---

### 杂项（3 任务）

| 任务 | 性质 |
|---|---|
| 334_adv_locked_file | H3/环境——bench 为 POSIX（chmod）设计，Windows 权限语义不同。单跑判定。 |
| 349_adv_malformed_skill_frontmatter | H2/D——frontmatter YAML 闭合修复失败（两目录）。 |
| 351_adv_huge_file_no_slurp | H2——~100MB 日志不能 slurp；Nexa 有 grep，理应能流式查。agent 没产出 answer.json。 |

---

## 4. 修复优先级（按影响面排序）

| # | 根因 | 簇 | 预期回收 | 性质 | 动作 |
|---|---|---|---|---|---|
| 1 | **AGENTS.md 不加载** | E | 15 | H1 已证明 | ✅ **已修（a3fa23d），实测回收 14 确定性 + task_223 flaky~50%** |
| 2 | 二进制处理引导 | A | ≤25（待诊断定 H1/H2 比例） | 待单跑 | 单跑 task_123 → 查 CC 系统提示 |
| 3 | 超时/循环行为 | C | ≤9 | 待单跑 | 单跑 task_309 看轨迹 |
| 4 | 编码处理 | F | 2 | 待单跑 | 查 `read.nx` encoding |

**乐观估计**：#1 已回收 14（实测）。若 #2 引导再回收 A 的 1/2（12），即 +26 → **319/351 (90.9%)**，逼近 deepagents 水平。剩余为 H2 模型上限（内容错、未传播完整、环境差异），属真实模型能力，不动 harness 凑分。

---

## 5. 守则（本轮自我约束，逐字执行）

- ✅ 拿到基线分数前**未改任何 src/*.nx**（先有数字再有改动）——已满足。
- 每个修复**必须**绑定失败 task_id，过验证门（`nexa build` 无新警告 + `test_tools.py` ≥60 PASS + 修复任务单跑 PASS 带事件证据）。
- **只修 H1**，对照 CC 源码可证明。H2/H3 记录跳过，**不凑分**。
- 不新增 CC 里没有的工具；不碰 ui-ink/、ui/。
- commit 带 `bench A→B`；不加 CC trailer；不 commit LICENSE / benchmark_results_*.json。

---

## 6. 跑法记录（复现用）

```
# runner 已修三层 bug（提交 c63204f 超时 / 138d59a 增量落盘 / 2ea7cc5 崩溃健壮）
python run_harness_bench.py --tasks 351 --timeout 300

# 本次因首段崩溃，两段式：
#   第一段: --tasks 351（157 任务后崩溃，挽救 JSON）
#   恢复段: --start 157 --tasks 194
# 合并: benchmark_results_MERGED_351.json（本报告 bench_raw_351.json 即此）
```

模型：GLM-5.1 coding 端点。总用时 ~11152s（恢复段）+ 首段。

---

## 7. Phase C #1 验证结果（memory 簇 · 已修 a3fa23d）

修复 `context.nx` 加载 AGENTS.md 后，全量重跑 memory 簇 32 任务（`--tag memory --tasks 100`）：

| 指标 | 基线 | 修复后 |
|---|---|---|
| memory 簇 PASS | 17/32 | **31/32** |

**确定性回收 14 个**（FAIL→PASS 稳定）：224、227、231、232、234、235、237、238、240、241、243、250、251、253。
包括此前怀疑可能是 H2 的全部「缺输出文件」型任务——它们其实都是 H1（agent 只缺 AGENTS.md 指令），加载后全部回收。证明「不盲猜分类、单跑验证」的必要性。

**task_223 flaky ~50%**（连跑 4 次 2 过 2 不过）：修复后从 0% 升到 ~50%，但 prompt「写 now.py」task-聚焦时 GLM 有时忘了存 MEMORY.md。轻度 H2 模型依从性，**不动 harness 凑**，记为边际。

**更新基线**：293 + 14（确定性）= **307/351 (87.5%)**，较首基线 83.5% +4.0pp。task_223 边际另计（全量重跑可确认）。一个根因（AGENTS.md 不加载）→ +14 任务，验证「按影响面排序」策略有效。

事件证据（task_223 过的那次）：工具调用 Read×3/Write×3/Bash×2，MEMORY.md 写入 "- Город: Москва"，now.py 用 timedelta(hours=3) Moscow tz。

---

## 8. 公平基线（全量重跑，2026-08-07）

runner 已调 `task.setup(ws)`（生成二进制 fixture，修复 a4af21b）+ `context.nx` 加载 AGENTS.md（修复 a3fa23d）后，全量重跑 351 任务，三段合并：

| 段 | 范围 | PASS | 说明 |
|---|---|---|---|
| seg1 | 1–262 | 246/262 (93.9%) | 含主 wait poll-loop 修复 85f864e |
| seg2 | 263–338 | 64/76 (84.2%) | adv/skill 密集段 |
| seg3 | 339–351 | 11/13 (84.6%) | adv 尾段，含 _kill_tree 修复 |
| **合并** | **1–351** | **321/351 (91.5%)** | 无缺口、无重叠、无重复 |

### 8.1 runner 健壮性修复（_kill_tree）

本轮修了第三个 runner bug——超时杀进程树偶发挂死 4 小时：

- **根因**：`_kill_tree` 的 `subprocess.run([taskkill], timeout=15)` 底层是 `Popen.wait(timeout=15)`，在本 Windows 环境偶发不触发 TimeoutExpired（与 task_262 主 wait 62min 同根因）。taskkill 卡在顽固进程树时 `run(timeout=15)` 永不返回 → `_kill_tree` 阻塞至 taskkill 自行退出。实测：task_339 拖到 14470s/4h、task_337 2071s、task_336 450s。
- **修复**：`_kill_tree` 全程 fire-and-forget（优先 psutil `children(recursive)+kill`，回退 `taskkill` 用 `Popen` 不 wait、再回退 `os.kill`）；超时后 `proc.wait(timeout=10)` → 手动 poll 循环 30s 上限。数学封顶单任务超时路径 ≤ 300+30=330s。
- **验证**：① 构造上不可超 330s（fire-and-forget + 硬 cap）；② seg3 全程无 overshoot（最慢 task_341 106.7s，exit 0）；③ seg2 的 13 个真超时任务全部在 ~300.6–301.1s 干净被杀，证明 poll-loop 超时路径生产可用。诚实注：本轮无「顽固树被 fire-and-forget 在 300s 杀掉」的运行时实例（尾段无任务触发顽固超时），靠构造证明 + seg2 干净杀佐证。

### 8.2 剩余 30 失败的三分类（单点，需 3× 重跑定 variance）

| 类 | 数 | 任务 | 性质 |
|---|---|---|---|
| **确定性 H2**（内容错/缺产物/硬超时） | ~17 | 86（numbers.txt 行序错）、202（csv 内容错）、212（config 合并超时，多步重构）、220（import 迁移不完整）、262（pytest 断言）、266（SHA256SUMS 缺）、306（merged.json 缺）、311（mod.c 返回 200 非 300）、312（policy merge 硬超时）、319（parsed.csv 缺）、328（xlsx reconcile 缺）、349（frontmatter 未闭合）、351（巨型日志 answer.json 缺）、112（xlsx openpyxl，已诊断 H2）、117（data.yaml 缺，213s 非超时）、210（tar manifest 超时）、149（sqlite 超时） | 模型逻辑/能力上限，不动 harness 凑分 |
| **抖动超时**（简单任务本轮卡死，疑似 GLM variance） | ~10 | 35（去空行·本该秒级）、102（csv filter）、137/144（grep）、161（gzip）、211（merge intervals）、317/323/325/326（skill 任务批量超时） | 单点样本，3× 重跑大概率部分回收 |
| **bug 残影**（elapsed 被 pre-fix bug 抬高，但仍 FAIL） | 3 | 262（3747s）、336（450s）、337（2071s） | 失败本身真实，耗时是旧 bug；现 runner 已不会再现 |

**variance 诚实标注**：321/351 是**单点估计**。已知抖动源：task_223 flaky~50%（本轮 FAIL）、若干简单任务本轮偶发超时（如 35/102/137/144）。剔除 ~10 个抖动超时后，确定性通过率约 **331/351 (94.3%)**——更接近 deepagents 水平，但需 3× 重跑确认，不提前主张。

### 8.3 修复前后对比（bench A→B）

| 指标 | 原始（不公平） | +AGENTS.md(a3fa23d) | +fixture(a4af21b) 公平重跑 |
|---|---|---|---|
| 分数 | 293/351 (83.5%) | 307/351 (87.5%, 投影) | **321/351 (91.5%)** |
| 与 deepagents 差距 | -42 任务 / -11.9pp | -28 | **-14 / -3.9pp** |

两个 H1 修复（对照 CC 源码可证）合计回收 **+28 任务**，差距从 11.9pp 收窄至 3.9pp。剩余差距主要是 H2 模型上限（GLM-5.1 在多步重构/二进制处理/skill 编排上的能力边界）+ 抖动，属真实模型能力，不动 harness 凑分。

