# tests/protocol/test_protocol.py — P0 Fix 5: JSON 事件协议 smoke tests
# 4 个最小测试：startup→ready / exit→session_end / permission request+response / long tool result 不截断
# 运行：python tests/protocol/test_protocol.py（tests 3-4 需 GLM key + 网络）
import subprocess, json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
ENV = {**os.environ, "NEXA_JSON_EVENTS": "1", "NEXA_QUIET": "1", "NEXA_STREAM_TOOLS": "1"}

def spawn_engine(permission_mode="auto"):
    env = {**ENV, "NEXA_PERMISSION_MODE": permission_mode}
    return subprocess.Popen([PY, "src/main.py"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True, encoding="utf-8", errors="replace")

def read_events(proc, timeout=60):
    """读取事件直到 timeout 或 session_end"""
    events = []
    import threading
    def reader():
        for line in proc.stdout:
            line = line.strip()
            if not line: continue
            try:
                ev = json.loads(line)
                events.append(ev)
                if ev.get("type") in ("session_end",): break
            except: pass
    t = threading.Thread(target=reader, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return events

def send(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()

PASS = "PASS"; FAIL = "FAIL"; SKIP = "SKIP"
results = []

# --- Test 1: startup → ready ---
try:
    p = spawn_engine()
    line = p.stdout.readline()
    ev = json.loads(line.strip())
    assert ev["type"] == "ready", f"expected ready, got {ev.get('type')}"
    results.append(("startup→ready", PASS, f"model={ev.get('model')}"))
    send(p, {"type": "exit"})
    p.wait(timeout=5)
except Exception as e:
    results.append(("startup→ready", FAIL, str(e)[:80]))

# --- Test 2: exit → session_end ---
try:
    p = spawn_engine()
    p.stdout.readline()  # consume ready
    send(p, {"type": "exit"})
    found_end = False
    for line in p.stdout:
        ev = json.loads(line.strip())
        if ev.get("type") == "session_end":
            found_end = True; break
    results.append(("exit→session_end", PASS if found_end else FAIL, ""))
    p.wait(timeout=5)
except Exception as e:
    results.append(("exit→session_end", FAIL, str(e)[:80]))

# --- Test 3: permission request + response (需 GLM) ---
try:
    p = spawn_engine("default")  # default 模式触发 ask
    p.stdout.readline()  # ready
    send(p, {"type": "message", "content": "Use Write to create a file called _perm_test.txt with content: hello"})
    # 等待 permission_request（或 done，若 agent 没调 Write）
    import threading
    perm_ev = [None]
    done_ev = [None]
    def reader3():
        for line in p.stdout:
            try:
                ev = json.loads(line.strip())
                if ev.get("type") == "permission_request" and perm_ev[0] is None:
                    perm_ev[0] = ev
                    # 发匹配的 permission_response
                    send(p, {"type": "permission_response", "request_id": ev["request_id"], "approved": True})
                elif ev.get("type") == "done":
                    done_ev[0] = ev; break
                elif ev.get("type") == "session_end":
                    break
            except: pass
    t3 = threading.Thread(target=reader3, daemon=True); t3.start(); t3.join(timeout=90)
    if perm_ev[0]:
        rid = perm_ev[0].get("request_id")
        assert rid is not None, "no request_id in permission_request"
        results.append(("permission request+response", PASS, f"request_id={rid}, tool={perm_ev[0].get('tool')}"))
    elif done_ev[0]:
        results.append(("permission request+response", SKIP, "agent didn't call Write (no permission triggered)"))
    else:
        results.append(("permission request+response", FAIL, "timeout"))
    send(p, {"type": "exit"})
    p.wait(timeout=5)
except Exception as e:
    results.append(("permission request+response", FAIL, str(e)[:80]))

# --- Test 4: long tool result 不截断 (>300 char, 需 GLM) ---
try:
    # 造一个 >300 字符的文件
    long_file = os.path.join(ROOT, "_long_test.txt")
    with open(long_file, "w") as f:
        f.write("x" * 500 + "\n")
    p = spawn_engine("auto")
    p.stdout.readline()  # ready
    send(p, {"type": "message", "content": "Use Read to read _long_test.txt, then say 'done'"})
    tool_result = [None]
    def reader4():
        for line in p.stdout:
            try:
                ev = json.loads(line.strip())
                if ev.get("type") == "tool_result":
                    tool_result[0] = ev.get("result", "")
                elif ev.get("type") == "done": break
                elif ev.get("type") == "session_end": break
            except: pass
    t4 = threading.Thread(target=reader4, daemon=True); t4.start(); t4.join(timeout=90)
    if tool_result[0] is not None:
        rlen = len(tool_result[0])
        results.append(("long tool result (>300, not truncated)", PASS if rlen > 300 else FAIL, f"result len={rlen}"))
    else:
        results.append(("long tool result (>300, not truncated)", SKIP, "no tool_result event (agent didn't read?)"))
    send(p, {"type": "exit"}); p.wait(timeout=5)
    os.unlink(long_file)
except Exception as e:
    results.append(("long tool result (>300, not truncated)", FAIL, str(e)[:80]))

# --- 汇总 ---
print("\n=== Protocol Smoke Tests ===")
for name, status, detail in results:
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
npass = sum(1 for _, s, _ in results if s == PASS)
nfail = sum(1 for _, s, _ in results if s == FAIL)
nskip = sum(1 for _, s, _ in results if s == SKIP)
print(f"\n{npass} PASS / {nfail} FAIL / {nskip} SKIP")
sys.exit(1 if nfail > 0 else 0)
