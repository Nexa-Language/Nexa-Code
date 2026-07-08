# Harness-Bench 评测任务交接文档

> 把此文档直接发给新会话（Claude Code 或其他 AI），让它执行完整的 harness 质量评估。

---

## 你的任务

运行 Harness-Bench 351 任务集，评估 Nexa harness（用 GLM-5.1）的编码能力得分，并与官方排行榜对比。

## 背景

[Harness-Bench](https://github.com/ai-forever/harness-bench-fast) 是首个**专门隔离 harness 效应**的 benchmark——固定模型，换 harness，测差异。351 个任务覆盖文件创建/编辑/重构、CSV/JSON/XLSX 转换、pytest、搜索、多步管道。**全部机械验证**（无 LLM-as-judge）。

我们的项目（`D:\code\nexa\claude-code-port`）用 Nexa 语言实现了 Claude Code 的 harness。我们想知道：**Nexa 写的 harness 在同等模型（GLM-5.1）下能达到多少分？**

## 官方排行榜（对比基准）

| Harness | Model | 分数 | 参考值 |
|---|---|---|---|
| Claude Code CLI | Claude Opus 4.8 | 351/351 (100%) | 满分基准 |
| Claude Code CLI | Claude Sonnet 4.6 | 341/351 (97.2%) | |
| deepagents | GLM-5.2 | 340/351 (96.9%) | **同模型家族** |
| deepagents | **GLM-5.1** | **335/351 (95.4%)** | ← **直接对比对象** |
| deepagents | DeepSeek V3.2 | 326/351 (92.9%) | |

**核心目标**：Nexa harness + GLM-5.1 的分数 vs deepagents + GLM-5.1 的 335/351 (95.4%)。

## 初步结果（已跑 5/351）

```
[1/5] task_01_create_hello     ✅ PASS (29.6s)
[2/5] task_02_write_data_json  ✅ PASS (38.1s)
[3/5] task_03_slugify          ❌ FAIL (814s — 超时)
[4/5] task_04_write_numbers    ✅ PASS (51.9s)
[5/5] task_05_greet            ✅ PASS (27.2s)
结果: 4/5 PASS (80.0%)
```

**已知问题**：task_03 超时——GLM 重试退避把 120s 超时拉到了 814s。runner 需要加**硬 kill 子进程树**。

## 执行步骤

### 1. 确保环境就绪

```bash
cd D:/code/nexa/claude-code-port
nexa build src/main.nx --harness=warn    # 编译引擎
# 确认 secrets.nxs 存在且 GLM key 有效（coding 端点）
```

### 2. 修复 runner 超时问题

在 `run_harness_bench.py` 的 `run_nexa_on_task()` 里：
- 用 `subprocess.Popen` + `proc.kill()` 替代 `subprocess.run(timeout=)`（确保子进程树被杀死）
- 或用 `psutil` 杀整个进程树
- 超时后返回 FAIL，不要等引擎自己退出

### 3. 跑全套 351 任务

```bash
python run_harness_bench.py --tasks 351 --timeout 180
```

预计运行时间：3-5 小时（351 任务 × 平均 40s）。建议 `run_in_background`。

### 4. 如果需要分批跑

```bash
python run_harness_bench.py --tasks 50 --start 0     # 第 1-50
python run_harness_bench.py --tasks 50 --start 50    # 第 51-100
# ... 依此类推
```

### 5. 按难度分析

```bash
python run_harness_bench.py --tag easy       # 只跑 easy
python run_harness_bench.py --tag medium    # 只跑 medium
python run_harness_bench.py --tag hard      # 只跑 hard
```

## 结果分析要点

1. **总分**：X/351 (Y%) — 与 deepagents+GLM-5.1 的 335/351 (95.4%) 对比
2. **按难度分解**：easy/medium/hard/extreme 各多少分
3. **失败原因分类**：
   - 超时（harness 效率问题）
   - 验证失败（agent 逻辑问题）
   - 引擎错误（Nexa bug）
   - 无输出（spawn/通信问题）
4. **平均工具调用数**：越少 = harness 效率越高
5. **平均用时**：越短 = harness 效率越高

## 产出

1. `benchmark_results_<timestamp>.json` — 每个任务的 pass/fail + 耗时 + 失败原因
2. 一份评估报告：总分 + 按难度分解 + 失败原因分析 + 与 deepagents/Claude Code 的对比

## 文件位置

- Runner 脚本：`D:/code/nexa/claude-code-port/run_harness_bench.py`
- Harness-Bench repo：`D:/Temp/wqf18/harness-bench/`（或 clone `https://github.com/ai-forever/harness-bench-fast`）
- Nexa 引擎：`D:/code/nexa/claude-code-port/src/main.nx`
- Secrets：`D:/code/nexa/claude-code-port/secrets.nxs`（GLM coding 端点）

## 注意

- 每个任务会创建临时目录 + 复制 secrets.nxs + 运行 nexa run。确保磁盘空间足够。
- GLM API 有速率限制——如果 429 频繁，在 runner 里加 `time.sleep(2)` 间隔。
- 任务 prompt 是俄语（Harness-Bench 来自俄罗斯 ai-forever 团队）。GLM-5.1 理解俄语没问题，但如果某些任务因为语言问题失败，可以在 runner 里加翻译（Google Translate API 或 LLM 翻译）。
