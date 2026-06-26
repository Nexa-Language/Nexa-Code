# 文档索引

> 本文件是 claude-code-port 所有文档的目录。根目录只放活跃文档（每阶段更新），其余在 docs/。

## 根目录（活跃，每阶段更新）
| 文件 | 用途 |
|---|---|
| `README.md` | 项目入口：怎么跑、定位、铁律 |
| `ROADMAP_V2.md` | 权威规划（Phase 0-12 + 未来），进度日志 |
| `PORT_TRACE.md` | 组件→CC源 映射（审计抓手，每组件登记） |

## docs/audits/（审查报告，Codex 产出，不改代码）
| 文件 | 内容 | 日期 |
|---|---|---|
| `UX_TEST_IMPROVEMENT_AUDIT.md` | UX 差距清单(15条) + 源码级对比 + 测试设计 + P0/P1/P2 改进规划 | 2026-06-26 |
| `CODE_REVIEW_NEXA_ENGINE.md` | Nexa 引擎代码审查（5 HIGH / 8 MED / 4 LOW） | 2026-06-26 |
| `VISUAL_COMPARISON.md` | 视觉对比（CC vs port 截图，4 组） | 2026-06-26 |

## docs/reports/（报告）
| 文件 | 内容 | 日期 |
|---|---|---|
| `TEST_EXECUTION_REPORT.md` | 测试执行（60 项：57 pass / 3 fail + 根因） | 2026-06-26 |
| `FINAL_REPORT.md` | Phase 0-5 核心子集范围声明（已移植/未移植/out-of-scope） | 2026-06-25 |
| `VALUE_REPORT.md` | 价值实证（行数对比 + ~9.9× 压缩 + 结论） | 2026-06-25 |

## docs/planning/（早期规划，已被 ROADMAP_V2 取代）
| 文件 | 说明 |
|---|---|
| `PORT_PLAN.md` | Phase 0-5 初始规划（已被 ROADMAP_V2 覆盖，保留供参考） |

## 文档规范
- **报告/审计** → `docs/audits/` 或 `docs/reports/`
- **规划** → 根目录 `ROADMAP_V2.md`（权威）或 `docs/planning/`（历史）
- **活跃更新**（PORT_TRACE/README/ROADMAP）→ 根目录
- 新报告命名：`{TYPE}_{SUBJECT}.md`（如 `AUDIT_SECURITY.md`、`REPORT_PHASE13.md`）
