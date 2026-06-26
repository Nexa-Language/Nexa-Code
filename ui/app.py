# =============================================================================
# ui/app.py — Phase 8 原生 UI 外壳（Python Textual，混合架构）
# -----------------------------------------------------------------------------
# 架构边界（ROADMAP_V2 铁律）：本文件【不含 agent 逻辑】——
#   无 turn 循环、无工具执行、无权限决策、无 LLM 调用。
#   只做：输入处理 + 调引擎 API（src/main.py 编译产物）+ 渲染输出。
# 引擎 = Nexa 编译产物（src/main.py 的 run_one_turn/run_command/init_permissions/
#   seed_context/build_user_context 等 @tool fn → Python 函数）。本 UI import、驱动、渲染。
# 对齐 refs/claude-code-ts/src/screens/REPL.tsx 核心交互（Textual 实现，非 Ink）。
#
# 交互：banner + 消息流(rich markdown + 工具调用 panel) + 输入框 + 状态栏；
#   / 命令经 run_command 派发（含 __AS_PROMPT__ 哨兵路由 run_one_turn）；权限 ask 经
#   _CCPORT_ASK_HANDLER 回调弹 y/N modal；工具调用经 stdout 捕获实时渲染；
#   深/浅主题切换；Ctrl+C 退出 / ↑↓ 历史 / Esc 取消。引擎调用在 worker 线程（run_worker thread=True）。
# =============================================================================
import os
import sys
import re
import threading
from contextlib import redirect_stdout, redirect_stderr

# 引擎 = Nexa 编译产物（src/main.py）
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'src'))
import main as engine  # noqa: E402  引擎 API（无 agent 逻辑在本 UI）

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog, Static
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.binding import Binding
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule

_TOOL_CALL_RE = re.compile(r'\[Coder requested TOOL CALL\]:\s*(.+?)\s*->\s*(.+)')
_EXIT = '__CC_EXIT__'
_ASPROMPT = '__AS_PROMPT__:'


class AskModal(ModalScreen):
    """权限确认 y/N modal（对齐 CC 的 tool permission approval UI）。"""

    CSS = """
    AskModal { align: center middle; }
    #askbox { border: round $warning; padding: 1 2; width: 72; height: auto; background: $surface; }
    #askbody { margin-bottom: 1; }
    #askhint { color: $text-muted; }
    """

    def __init__(self, tool, args_str):
        super().__init__()
        self.tool = tool
        self.args_str = args_str

    def compose(self):
        yield Vertical(
            Static(f'Claude wants to use [bold]{self.tool}[/bold]\n\n{self._format_args()}',
                   id='askbody'),
            Static('[y] allow    [a] always allow once    [n / esc] deny', id='askhint'),
            id='askbox',
        )

    def on_key(self, event):
        # Textual backup only: "a" approves once and the persistent-rule gap is
        # documented in ENGINE_REQUESTS.md by the Ink polishing loop.
        self.dismiss(event.key in ('y', 'a'))

    def _format_args(self):
        try:
            import json
            obj = json.loads(self.args_str)
            if isinstance(obj, dict):
                return '\n'.join('%s: %s' % (k, str(v)[:160]) for k, v in obj.items())
        except Exception:
            pass
        return 'args: %s' % self.args_str[:240]


class _LineStream:
    """捕获引擎 stdout/stderr，按完整行回调（worker 线程写 → 主线程渲染）。"""

    def __init__(self, on_line):
        self._on_line = on_line
        self._buf = ''

    def write(self, s):
        try:
            self._buf += s or ''
            while '\n' in self._buf:
                line, self._buf = self._buf.split('\n', 1)
                if line.strip():
                    self._on_line(line)
        except Exception:
            pass
        return len(s) if isinstance(s, str) else 0

    def flush(self):
        if self._buf.strip():
            self._on_line(self._buf)
            self._buf = ''


class CCEngineApp(App):
    """Claude Code Nexa port — Textual UI 外壳（无 agent 逻辑）。"""

    CSS = """
    Screen { layout: vertical; }
    #msglog { border: round $primary; height: 1fr; }
    Input { dock: bottom; }
    """

    BINDINGS = [
        Binding('ctrl+c', 'quit', 'Quit', show=True, priority=True),
        Binding('up', 'history_prev', 'Prev', show=False),
        Binding('down', 'history_next', 'Next', show=False),
        Binding('escape', 'cancel', 'Cancel', show=False),
        Binding('t', 'toggle_theme', 'Theme', show=True),
    ]

    def __init__(self):
        super().__init__()
        self.history = []
        self.hist_idx = 0

    # ---- 布局 ----
    def compose(self) -> ComposeResult:
        yield Header(name='Claude Code — Nexa port (Textual UI)')
        yield RichLog(id='msglog', wrap=True, markup=True, auto_scroll=True)
        yield Input(placeholder='> prompt or /command   (Ctrl+C quit · ↑↓ history · t theme)', id='prompt')
        yield Footer()

    def on_mount(self):
        self.dark = True  # 深色主题默认
        # 引擎初始化（调引擎 API，非本 UI 实现 agent 逻辑）
        engine.init_permissions()
        engine.seed_context(engine.build_user_context('glm-4-flash'))
        # 权限 ask 经回调弹 modal（UI 可插拔；引擎侧 _CCPORT_ASK_HANDLER）
        engine.__dict__['_CCPORT_ASK_HANDLER'] = self._ask_handler
        log = self.query_one('#msglog', RichLog)
        log.write(Panel(
            Text('Claude Code — Nexa port\nPhase 8 Textual UI · engine: Nexa-compiled main.py · UI: Textual (no agent logic here)',
                 style='bold cyan'),
            title='Claude Code', border_style='cyan'))
        log.write(Text('engine ready: permissions + context seeded. Type a prompt or /help.', style='dim'))

    # ---- 输入处理 ----
    def on_input_submitted(self, event):
        text = (event.value or '').strip()
        inp = self.query_one('#prompt', Input)
        inp.value = ''
        if not text:
            return
        self.history.append(text)
        self.hist_idx = len(self.history)
        self.query_one('#msglog', RichLog).write(Text(f'> {text}', style='bold blue'))
        # 引擎调用丢 worker 线程（不冻 UI）；用闭包捕获 text（run_worker 跑无参闭包）
        def _job():
            self._engine_impl(text)
        self.run_worker(_job, thread=True, exclusive=False, group='engine', description='engine turn')

    # ---- 引擎 worker（线程里执行；捕获 stdout + 调引擎 API + 回主线程渲染）----
    def _engine_impl(self, text):
        stream = _LineStream(lambda ln: self.call_from_thread(self._render_stream_line, ln))
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                if text.startswith('/'):
                    out = engine.run_command(text) or ''
                    if out == _EXIT:
                        self.call_from_thread(self._exit_app)
                    elif out.startswith(_ASPROMPT):
                        reply = engine.run_one_turn(out[len(_ASPROMPT):])
                        self.call_from_thread(self._render_reply, reply)
                    else:
                        self.call_from_thread(self._emit_text, out)
                else:
                    reply = engine.run_one_turn(text)
                    self.call_from_thread(self._render_reply, reply)
        except Exception as e:
            self.call_from_thread(self._emit_error, '[engine error] %s' % e)

    # ---- 权限 ask 回调（worker 线程调）→ 主线程 modal → 等 y/N ----
    def _ask_handler(self, tool, args_str):
        box = {'ans': 'n'}
        done = threading.Event()

        def on_main():
            def resume(val):
                box['ans'] = 'y' if val else 'n'
                done.set()
            self.push_screen(AskModal(tool, args_str), resume)
        self.call_from_thread(on_main)
        done.wait(timeout=120)
        return box['ans']

    # ---- 渲染（主线程）----
    def _render_stream_line(self, line):
        m = _TOOL_CALL_RE.search(line)
        if m:
            tool, args = m.group(1).strip(), m.group(2).strip()
            self.query_one('#msglog', RichLog).write(
                Panel(Text(f'{tool}({args[:160]})', style='yellow'),
                      title='tool call', border_style='yellow', title_align='left'))

    def _render_reply(self, reply):
        log = self.query_one('#msglog', RichLog)
        if reply and reply.strip():
            try:
                log.write(Markdown(reply.strip()))
            except Exception:
                log.write(Text(reply.strip()))
        log.write(Rule(style='dim'))

    def _emit_text(self, s):
        self.query_one('#msglog', RichLog).write(Text(s, style='green'))

    def _emit_error(self, s):
        self.query_one('#msglog', RichLog).write(
            Panel(Text(s, style='bold red'), title='error', border_style='red', title_align='left'))

    def _exit_app(self):
        self.query_one('#msglog', RichLog).write(Text('Goodbye.', style='dim'))
        self.exit()

    # ---- actions（keybindings）----
    def action_toggle_theme(self):
        self.dark = not self.dark
        self.query_one('#msglog', RichLog).write(Text('theme: %s' % ('dark' if self.dark else 'light'), style='dim'))

    def action_history_prev(self):
        if not self.history or self.hist_idx <= 0:
            return
        self.hist_idx -= 1
        self.query_one('#prompt', Input).value = self.history[self.hist_idx]

    def action_history_next(self):
        if not self.history or self.hist_idx >= len(self.history) - 1:
            self.hist_idx = len(self.history)
            self.query_one('#prompt', Input).value = ''
            return
        self.hist_idx += 1
        self.query_one('#prompt', Input).value = self.history[self.hist_idx]

    def action_cancel(self):
        # Esc：取消进行中的 engine worker（若有）
        for w in self.workers:
            w.cancel()


def main():
    app = CCEngineApp()
    app.run()


if __name__ == '__main__':
    main()
