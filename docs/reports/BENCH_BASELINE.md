# Nexa Harness-Bench 基线报告

> 项目第一个客观质量坐标。**基准驱动开发** Phase B 交付物。
> 生成于 2026-08-07。原始数据：`bench_raw_351.json`（351 任务逐条 pass/fail + 耗时 + 失败原因）。

---

## 1. 基线分数

| Harness | Model | 分数 | 备注 |
|---|---|---|---|
| Claude Code CLI | Claude Opus 4.8 | 351/351 (100.0%) | 满分基准 |
| Claude Code CLI | Claude Sonnet 4.6 | 341/351 (97.2%) | |
| deepagents | GLM-5.2 | 340/351 (96.9%) | 同模型家族 |
| **deepagents** | **GLM-5.1** | **335/351 (95.4%)** | ← **直接对比对象（同 harness 不同模型）** |
| **Nexa harness** | **GLM-5.1** | **293/351 (83.5%)** | ← **本项目基线** |

**结论**：Nexa harness + GLM-5.1 = **293/351 (83.5%)**，落后 deepagents + 同模型 42 任务 / 11.9 个百分点。

跑法：两段式（第一段崩溃挽救 157 任务 145 PASS + 恢复段 158–351 共 194 任务 148 PASS），合并去重后无重叠，合计 351。

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

