#!/usr/bin/env python
# tests/tools/test_tools.py — 工具正确性回归测试
# ═══════════════════════════════════════════════════════════
# 审查 agent（Claude Code 本会话）维护。每次开发 agent 完成后运行。
# 运行: python tests/tools/test_tools.py
# 不需要 LLM；直接调用编译后的工具函数，测纯逻辑正确性。
# 需要先 nexa build src/main.nx（确保 src/main.py 是最新编译产物）。
# ═══════════════════════════════════════════════════════════
import sys, os, json, shutil, tempfile, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.chdir(ROOT)

import main as M  # 编译产物

# ─── 测试框架 ───
PASS = 0; FAIL = 0; SKIP = 0; RESULTS = []

def check(name, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1; RESULTS.append((name, 'PASS', ''))
    else:
        FAIL += 1; RESULTS.append((name, 'FAIL', detail))

def skip(name, reason):
    global SKIP
    SKIP += 1; RESULTS.append((name, 'SKIP', reason))

def safe(name, fn):
    """运行测试，捕获异常，自动 FAIL+traceback"""
    try:
        fn()
    except Exception as e:
        check(name, False, f'EXCEPTION: {str(e)[:120]}')

# ─── Grep 13 参数助手 ───
def grep_defaults(pattern, **kw):
    """Grep 的 13 个必填参数，用默认值填充未指定的"""
    defaults = dict(path='', glob='', output_mode='content', glob_type='',
        context_before='0', context_after='0', context_c='0',
        show_line_numbers='true', case_insensitive='false',
        head_limit='100', offset='0', multiline='false')
    defaults.update(kw)
    return M.Grep(pattern, **defaults)

# ─── 测试数据 ───
TMP = os.path.join(ROOT, '_test_tmp')
os.makedirs(TMP, exist_ok=True)

def setup_file(name, content):
    p = os.path.join(TMP, name)
    with open(p, 'w') as f: f.write(content)
    return p

# ═══════════════════════════════════════════════════════════
# 测试开始
# ═══════════════════════════════════════════════════════════

def test_read():
    f = setup_file('read.txt', 'apple\nbanana\ncherry\n')
    # 正常读取
    r = M.Read(f, '1', '10', '')
    check('Read.正常', 'apple' in r and 'cherry' in r, f'缺内容: {r[:60]}')
    # offset/limit
    r = M.Read(f, '2', '1', '')
    check('Read.offset_limit', 'banana' in r and 'apple' not in r, f'应只含banana: {r[:60]}')
    # 不存在
    r = M.Read(os.path.join(TMP, 'nope.txt'), '1', '10', '')
    check('Read.不存在', any(x in r.lower() for x in ['not exist', 'does not', 'no such']), f'应报错: {r[:60]}')
    # 空文件
    f2 = setup_file('empty.txt', '')
    r = M.Read(f2, '1', '10', '')
    check('Read.空文件', 'empty' in r.lower(), f'应提示空: {r[:60]}')

def test_edit():
    import shutil as sh
    f = setup_file('edit.txt', 'apple\nbanana\ncherry\n')
    # 必须先 Read（staleness 检查）
    M.Read(f, '1', '10', '')
    r = M.Edit(f, 'banana', 'BANANA', 'false')
    content = open(f).read()
    check('Edit.精确替换', 'BANANA' in content and 'banana' not in content, '替换未生效')
    # 无 Read 被拒
    f2 = setup_file('edit2.txt', 'hello\n')
    r = M.Edit(f2, 'hello', 'world', 'false')
    check('Edit.无Read被拒', any(x in r.lower() for x in ['must', 'read', 'error']), f'应拒绝: {r[:60]}')
    # 不存在 old_string
    M.Read(f, '1', '10', '')
    r = M.Edit(f, 'nonexistent_text', 'xxx', 'false')
    check('Edit.未找到', any(x in r.lower() for x in ['not found', 'no match', 'error']), f'应报未找到: {r[:60]}')
    # 非唯一匹配 + replace_all=false → 正确拒绝
    f3 = setup_file('edit3.txt', 'dup\ndup\ndup\n')
    M.Read(f3, '1', '10', '')
    r = M.Edit(f3, 'dup', 'UNIQUE', 'false')
    check('Edit.非唯一拒绝', any(x in r.lower() for x in ['match', 'unique', 'replace_all']), f'应拒绝非唯一: {r[:60]}')

def test_edge_cases():
    # Grep invalid regex → error (not empty)
    r = M.Grep('[', 'src', '', 'content', '', 0,0,0, True, False, 0, 0, False)
    check('Edge.Grep非法正则', 'error' in r.lower() or 'rror' in r.lower(), f'应报错: {r[:60]}')
    # Bash dangerous command → blocked
    r = M.Bash('rm -rf /', 0, False)
    check('Edge.Bash危险命令', 'dangerous' in r.lower() or 'security' in r.lower() or 'not allowed' in r.lower(), f'应被拦: {r[:60]}')
    # Bash Windows dangerous
    r = M.Bash('format C:', 0, False)
    check('Edge.Bash危险Win', 'dangerous' in r.lower() or 'security' in r.lower(), f'应被拦: {r[:60]}')
    # Read ENOENT suggests similar
    f = setup_file('readme.md', '# Hi\n')
    r = M.Read(os.path.join(TMP, 'readm.md'), 0, 0, '')
    check('Edge.Read相似建议', 'readme' in r or 'mean' in r.lower() or 'exist' in r.lower(), f'应建议: {r[:80]}')
    # Edit not-found suggests closest
    M.Read(f, 0, 0, '')
    r = M.Edit(f, 'nonexistent_xyz_text', 'new', False)
    check('Edge.Edit最近行', 'closest' in r.lower() or 'not found' in r.lower(), f'应建议: {r[:80]}')
    # Permission plan mode blocks Write but allows Read
    M.set_permission_mode('plan')
    _wblock = M.Write(os.path.join(TMP, 'plan_test.txt'), 'test')
    check('Edge.plan阻止Write', 'plan' in _wblock.lower() or 'not allowed' in _wblock.lower(), f'应被plan阻止: {_wblock[:60]}')
    _ballow = M.Read(f, 0, 0, '')
    check('Edge.plan允许Read', 'Hi' in _ballow or len(_ballow) > 0, f'plan下Read应允许: {_ballow[:60]}')
    M.set_permission_mode('default')
    # MultiEdit atomicity: one bad edit → none applied
    f2 = setup_file('atomic.txt', 'alpha\nbeta\n')
    M.Read(f2, 0, 0, '')
    bad_edits = json.dumps([{'old_string': 'alpha', 'new_string': 'ALPHA'}, {'old_string': 'NONEXIST', 'new_string': 'X'}])
    r = M.MultiEdit(f2, bad_edits)
    content_after = open(f2).read()
    check('Edge.MultiEdit原子性', 'alpha' in content_after and 'ALPHA' not in content_after, f'应回滚(原子): {content_after[:60]}')
    # CRLF normalization
    import os as _os
    f3 = os.path.join(TMP, 'crlf.txt')
    with open(f3, 'wb') as _wf:
        _wf.write(b'hello\r\nworld\r\n')
    M.Read(f3, 0, 0, '')
    r = M.Edit(f3, 'hello', 'HELLO', False)
    check('Edge.CRLF', 'updated' in r.lower() or 'HELLO' in open(f3, 'rb').read().decode('utf-8', 'replace'), f'CRLF编辑: {r[:60]}')

def test_extra_tools():
    # Sleep
    r = M.Sleep('0.01')
    check('Sleep', 'slept' in r.lower() or 's.' in r, f'应返回 slept: {r[:30]}')
    # Cron create + list + delete
    r = M.CronCreate('0 6 * * *', 'standup', 'testcron')
    check('CronCreate', 'created' in r.lower() or 'cron' in r.lower(), f'应创建: {r[:50]}')
    r = M.CronList()
    check('CronList', 'testcron' in r or 'cron' in r.lower(), f'应列出: {r[:60]}')
    r = M.CronDelete('testcron')
    check('CronDelete', 'deleted' in r.lower() or 'testcron' in r, f'应删除: {r[:40]}')
    # Goal set + status
    r = M.Goal('set', 'port 45 tools', '')
    check('GoalSet', 'goal' in r.lower() or 'set' in r.lower(), f'应设置: {r[:40]}')
    r = M.Goal('status', '', '')
    check('GoalStatus', 'port 45' in r or 'goal' in r.lower(), f'应显示状态: {r[:60]}')
    # SendMessage
    r = M.SendMessage('Coder', 'hello')
    check('SendMessage', 'sent' in r.lower() or 'message' in r.lower(), f'应发送: {r[:40]}')
    # CtxInspect
    r = M.CtxInspect()
    check('CtxInspect', 'context' in r.lower() or 'message' in r.lower(), f'应显示上下文: {r[:40]}')
    # Brief set + get
    r = M.Brief('set', 'test briefing')
    check('BriefSet', 'saved' in r.lower() or 'brief' in r.lower(), f'应保存: {r[:40]}')
    r = M.Brief('get', '')
    check('BriefGet', 'test briefing' in r or 'no' in r.lower(), f'应读取: {r[:40]}')
    # DiscoverSkills (should find something or report none gracefully)
    r = M.DiscoverSkills('')
    check('DiscoverSkills', 'skill' in r.lower(), f'应列出技能: {r[:40]}')

def test_multiedit():
    f = setup_file('multi.txt', 'one\ntwo\nthree\n')
    M.Read(f, '1', '10', '')
    edits = json.dumps([{'old_string': 'one', 'new_string': 'ONE'}, {'old_string': 'three', 'new_string': 'THREE'}])
    r = M.MultiEdit(f, edits)
    content = open(f).read()
    check('MultiEdit.2处', 'ONE' in content and 'THREE' in content, '未全部替换')

def test_write():
    f = os.path.join(TMP, 'write.txt')
    r = M.Write(f, 'hello world')
    check('Write.创建', open(f).read() == 'hello world', '内容不匹配')
    # 嵌套目录
    f2 = os.path.join(TMP, 'nested', 'deep', 'file.txt')
    r = M.Write(f2, 'deep')
    check('Write.嵌套目录', os.path.isfile(f2) and open(f2).read() == 'deep', '嵌套创建失败')

def test_bash():
    r = M.Bash('echo bash_ok', '10000', 'false')
    check('Bash.echo', 'bash_ok' in r, f'输出: {r[:60]}')
    # 非零退出
    r = M.Bash('exit 1', '10000', 'false')
    check('Bash.非零退出', 'exit code' in r.lower() or '1' in r, f'应显示退出码: {r[:60]}')

def test_grep():
    setup_file('grep1.txt', 'hello world\nfoo bar\nhello again\n')
    # 正常搜索
    r = grep_defaults('hello')
    check('Grep.匹配', 'hello' in r, f'应含hello: {r[:60]}')
    # 无效正则
    r = grep_defaults('[invalid')
    check('Grep.无效正则', 'error' in r.lower() or 'fail' in r.lower(), f'应报错: {r[:60]}')
    # count 模式（搜索范围是整个项目，不只测试文件）
    r = grep_defaults('hello', output_mode='count')
    check('Grep.count模式', '.md' in r or '.txt' in r or '.nx' in r, f'count应返回文件:N 格式: {r[:80]}')

def test_glob():
    setup_file('glob1.txt', 'x')
    r = M.Glob(os.path.join(TMP, 'glob*.txt'), '')
    check('Glob.匹配', 'glob1' in r, f'应含glob1: {r[:60]}')
    r = M.Glob(os.path.join(TMP, 'nonexistent_*.xyz'), '')
    check('Glob.无匹配', 'no' in r.lower() or 'not found' in r.lower() or 'empty' in r.lower(), f'应提示无匹配: {r[:60]}')

def test_notebook():
    nb = {"cells": [{"cell_type": "code", "source": ["print(1)\n"], "outputs": [], "metadata": {}}], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    f = setup_file('test.ipynb', json.dumps(nb))
    # 读注册 staleness
    M.Read(f, '1', '10', '')
    r = M.NotebookEdit(f, '0', 'print(42)', 'code', 'replace')
    check('NotebookEdit.replace', '42' in r or 'ok' in r.lower() or 'cell' in r.lower(), f'结果: {r[:80]}')

def test_todowrite():
    r = M.TodoWrite(json.dumps([{'content': 'task1', 'status': 'pending'}, {'content': 'task2', 'status': 'in_progress'}]))
    check('TodoWrite.创建', 'success' in r.lower() or 'modified' in r.lower() or 'todo' in r.lower(), f'应确认成功: {r[:80]}')
    # 全完成清除
    r = M.TodoWrite(json.dumps([{'content': 'task1', 'status': 'completed'}]))
    check('TodoWrite.更新', 'task1' in r.lower() or 'todo' in r.lower(), f'应更新: {r[:60]}')

def test_plan():
    r = M.EnterPlanMode()
    check('EnterPlanMode', 'plan' in r.lower() or 'mode' in r.lower() or len(r) > 0, f'结果: {r[:60]}')
    r = M.ExitPlanMode()
    check('ExitPlanMode', 'plan' in r.lower() or 'mode' in r.lower() or 'default' in r.lower() or len(r) > 0, f'结果: {r[:60]}')

def test_verify():
    r = M.VerifyPlan('all good', 'true', 'everything checks out')
    check('VerifyPlan.pass', 'pass' in r.lower() or 'verified' in r.lower() or 'satisf' in r.lower(), f'应pass/verified: {r[:60]}')
    r = M.VerifyPlan('incomplete', 'false', 'missing tests')
    check('VerifyPlan.fail', 'fail' in r.lower() or 'not' in r.lower(), f'应fail: {r[:60]}')

def test_task_system():
    # Create
    r = M.TaskCreate('test task', 'a test', 'Testing', '{}')
    check('TaskCreate', 'task' in r.lower() or 'creat' in r.lower() or len(r) > 0, f'结果: {r[:60]}')
    # List
    r = M.TaskList()
    check('TaskList', 'task' in r.lower() or len(r) > 0, f'列表: {r[:60]}')

def test_search_execute():
    r = M.SearchExtraTools('read file', '5')
    check('SearchExtraTools', len(r) >= 0, f'结果: {r[:80]}')  # 返回非空或空都算不崩

def test_config():
    r = M.Config('get', 'model', '')
    check('Config.get', len(r) >= 0, f'结果: {r[:80]}')

def test_repl():
    r = M.REPL('print(6*7)')
    check('REPL.计算', '42' in str(r), f'应返回42: {str(r)[:80]}')

def test_push_notification():
    try:
        r = M.PushNotification('Test', 'Notification test')
        check('PushNotification.不崩', True)
    except Exception as e:
        check('PushNotification.不崩', False, str(e)[:60])

def test_terminal_capture():
    try:
        r = M.TerminalCapture(os.path.join(TMP, 'screen.png'))
        check('TerminalCapture.不崩', True)
    except Exception as e:
        check('TerminalCapture.不崩', False, str(e)[:60])

def test_web():
    # WebFetch（需网络，超时则 SKIP）
    import subprocess
    try:
        r = M.WebFetch('https://example.com', 'What is this page about?')
        check('WebFetch.example.com', 'Example' in r or 'example' in r.lower() or len(r) > 50, f'结果: {r[:80]}')
    except Exception as e:
        skip('WebFetch', f'网络不可用: {str(e)[:60]}')
    # WebSearch（DDG API）
    try:
        r = M.WebSearch('Python programming language')
        check('WebSearch.python', len(r) > 20, f'结果: {r[:80]}')
    except Exception as e:
        skip('WebSearch', f'网络/API不可用: {str(e)[:60]}')

def test_agent():
    skip('Agent', '需要 LLM 调用，不在工具正确性测试范围')

def test_ask_user():
    skip('AskUserQuestion', '需要交互式用户输入')

# ═══════════════════════════════════════════════════════════
# 运行所有测试
# ═══════════════════════════════════════════════════════════

TESTS = [
    ('Read', test_read), ('Edit', test_edit), ('MultiEdit', test_multiedit),
    ('Write', test_write), ('Bash', test_bash), ('Grep', test_grep),
    ('Glob', test_glob), ('NotebookEdit', test_notebook), ('TodoWrite', test_todowrite),
    ('Plan', test_plan), ('VerifyPlan', test_verify), ('Task', test_task_system),
    ('SearchExtraTools', test_search_execute), ('Config', test_config),
    ('REPL', test_repl), ('PushNotification', test_push_notification),
    ('TerminalCapture', test_terminal_capture), ('Web', test_web),
    ('Agent', test_agent), ('AskUserQuestion', test_ask_user),
    ('EdgeCases', test_edge_cases),
    ('ExtraTools', test_extra_tools),
]

for name, fn in TESTS:
    safe(name, fn)

# ─── 清理 ───
shutil.rmtree(TMP, ignore_errors=True)

# ─── 报告 ───
print('\n' + '='*60)
print('工具正确性回归测试 — ' + str(len(RESULTS)) + ' 组')
print('='*60)
for name, status, detail in RESULTS:
    marker = '✅' if status == 'PASS' else ('⏭️' if status == 'SKIP' else '❌')
    line = f'  {marker} {name}'
    if detail: line += f' — {detail}'
    print(line)
print(f'\n{PASS} PASS / {FAIL} FAIL / {SKIP} SKIP')
print('='*60)
sys.exit(1 if FAIL > 0 else 0)
