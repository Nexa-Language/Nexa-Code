# Nexa Code

A terminal coding assistant built with Nexa definitions, the Nexa execution runtime, and Ink/React.

Nexa Code 3.0 新增原生 Open Programs 的目标、证据、修订与补丁授权工作流；2.4 兼容入口继续把连续对话、审批恢复、预算、取消和工具执行交给 Nexa runtime。.nx 定义 Agent 与 **50 个公开工具**；Python host 管理工作区、会话和协议；Ink 提供独立的 Nexa 终端界面。

[Open Programs 3.0](docs/OPEN_PROGRAMS.md) · [安装 / Installation](docs/INSTALL.md) · [升级迁移 / Migration](docs/MIGRATION.md) · [50 tools / 50 commands](docs/FEATURES.md) · [Architecture & protocol](docs/ARCHITECTURE.md) · [文档索引](docs/INDEX.md)

## 当前版本

本工作树为 Nexa Code 3.0.0.dev0，依赖已发布的 [Nexa v3.0.0](https://github.com/Nexa-Language/Nexa/releases/tag/v3.0.0)，固定源码 SHA 为 [2743796](https://github.com/Nexa-Language/Nexa/commit/274379606e53c90d2d25774f6bb8984c777d0759)。安装使用该版本的显式源码来源。PyPI 的同名 nexa-lang 属于其他项目，请按安装页指定来源。

## 开始使用

需要 Python 3.10+、uv、Node.js 20+、pnpm 10.18.3。源码布局如下：

~~~text
work/
└── Nexa-Facility/
    ├── .runtime/nexa-3.0.0/  # 固定发行源码
    └── Nexa-Code/           # 本仓库
~~~

在本仓库运行：

~~~bash
uv sync --locked --all-extras
pnpm --dir ui-ink install --frozen-lockfile
pnpm --dir ui-ink build
uv run nexa-code-engine --cwd /absolute/project --doctor
./nexa-cc.sh --cwd /absolute/project
~~~

启动时直接编译 .nx，无需生成 src/main.py。配置由 runtime 从目标工作区及其父目录的 .nxs 与环境读取，最近目录优先。使用 --model 选择模型，--provider chat|responses|anthropic 选择协议；配置示例见[安装页](docs/INSTALL.md)。

新工作流使用显式 `--program <file.nx> --environment <environment.json>`，详见 [Open Programs](docs/OPEN_PROGRAMS.md)。以下交互保留 2.4 连续对话行为。

## 日常使用

- 输入任务后按 Enter；Ctrl+J 换行，Tab 补全命令，方向键选择历史或菜单。
- 审批显示实际参数、工作区、run/call ID、策略来源及文件差异。y 允许本次，n 拒绝，s / p 经第二次确认保存精确参数的会话 / 持久规则。
- /resume 选择会话；/model 选择模型并新建会话；/cost 查看当前会话及研究子运行累计 usage。
- Esc 或 Ctrl+C 取消；空闲时连续两次 Ctrl+C 退出。后台任务带期限、持续收集有界输出，并随 host 退出清理。
- /permissions plan 进入只读模式；/permissions bypass confirm 为当前会话启用 bypass；deny 始终优先。
- /theme light 或 /theme graphite 切换主题，Ctrl+O 展开工具输出。/help 列出全部 50 个命令名及别名。

原生会话保存在目标项目的 .nexa-code/sessions.sqlite3，包含关联 run、checkpoint 和审批 journal。大输出与文件快照保存在同一目录。旧 JSONL 通过 /resume /absolute/history.jsonl 导入为新会话，原文件保留。

## 开发与验收

~~~bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run isort --check-only nexa_code tests/runtime tests/conftest.py scripts setup.py run_harness_bench.py
uv run ty check
pnpm --dir ui-ink typecheck
pnpm --dir ui-ink test
pnpm --dir ui-ink format:check
pnpm --dir ui-ink build
uv build --wheel
uv run python scripts/check_wheel.py dist/nexa_code-3.0.0.dev0-py3-none-any.whl --runtime-wheel /absolute/nexa_lang-3.0.0-py3-none-any.whl
uv run python scripts/pty_smoke.py
~~~

默认测试禁用网络，通过 fixture provider 驱动真实 runtime、文件工具、子进程和 MCP stdio。PTY 脚本运行实际 Ink 与 Python host，[终端记录](docs/evidence/ink-pty.txt)覆盖命令、审批、文件检查、取消和退出。真实 provider、外部 Web/MCP HTTP 与操作系统通知需独立集成验收；Windows 子进程树清理仍需平台验证。

历史实验报告保留在 docs/reports/，其版本、模型和测试条件属于旧实现。本轮接入未进行性能对比跑分；当前行为及限制以[功能清单](docs/FEATURES.md)为准。

## 致谢

[Qifan Wu](https://github.com/cookiesheep) 完成了早期实验；[Yipeng Ouyang](https://github.com/ouyangyipeng) 提出了项目并推进 Nexa 的 Agent 运行时。本项目使用 [Nexa](https://github.com/Nexa-Language/Nexa)、Ink 与 React；早期交互和工具工作流参考了 Claude Code。
