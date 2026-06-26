# 此文件由 Nexa Code Generator 自动生成
import os
import sys
import time
import json
import pydantic
from src.runtime.stdlib import STD_NAMESPACE_MAP
from src.runtime.agent import NexaAgent
from src.runtime.evaluator import nexa_semantic_eval, nexa_intent_routing
from src.runtime.orchestrator import join_agents, nexa_pipeline, nexa_context_pipeline
from src.runtime.dag_orchestrator import dag_fanout, dag_merge, dag_branch, dag_parallel_map, SmartRouter
from src.runtime.memory import global_memory
from src.runtime.stdlib import STD_TOOLS_SCHEMA, STD_NAMESPACE_MAP
# v2.2.1: Terminal UI functions (rich-based rendering)
from src.runtime.stdlib import (_std_ui_banner, _std_ui_markdown, _std_ui_code, _std_ui_panel, _std_ui_thinking, _std_ui_success, _std_ui_error, _std_ui_warning, _std_ui_info, _std_ui_input, _std_ui_agent_reply, _std_ui_tool_call)
from src.runtime.secrets import nexa_secrets
from src.runtime.core import nexa_fallback, nexa_img_loader
from src.runtime.mcp_client import fetch_mcp_tools
from src.runtime.meta import runtime, get_loop_count, get_last_result, set_loop_count, set_last_result
from src.runtime.reason import reason, reason_float, reason_int, reason_bool, reason_str, reason_dict, reason_list, reason_model
from src.runtime.hitl import wait_for_human, ApprovalStatus, HITLManager
from src.runtime.contracts import ContractSpec, ContractClause, OldValues, ContractViolation, check_requires, check_ensures, capture_old_values
from src.runtime.type_system import TypeChecker, TypeInferrer, TypeViolation, TypeWarning, TypeCheckResult, TypeMode, LintMode, get_type_mode, get_lint_mode, PrimitiveTypeExpr, GenericTypeExpr, UnionTypeExpr, OptionTypeExpr, ResultTypeExpr, AliasTypeExpr, FuncTypeExpr, SemanticTypeExpr, build_type_expr_from_ast, build_protocol_fields_from_ast
# v1.2: Error Propagation (错误传播)
from src.runtime.result_types import NexaResult, NexaOption, ErrorPropagation, propagate_or_else, try_propagate, wrap_agent_result
# P3-3: Pattern Matching (模式匹配)
from src.runtime.pattern_matching import nexa_match_pattern, nexa_destructure, nexa_make_variant, _nexa_is_tuple_like, _nexa_is_list_like, _nexa_is_dict_with_keys, _nexa_is_variant, _nexa_list_rest, _nexa_dict_rest
# P3-4: ADT — Struct/Enum/Trait/Impl (代数数据类型)
from src.runtime.adt import register_struct, make_struct_instance, struct_get_field, struct_set_field, is_struct_instance, register_enum, make_variant, make_unit_variant, is_variant_instance, register_trait, register_impl, call_trait_method, lookup_struct, lookup_enum, lookup_trait, lookup_impl, ContractViolation
# P3-4: ADT — Struct/Enum/Trait/Impl (代数数据类型)
from src.runtime.adt import register_struct, make_struct_instance, struct_get_field, struct_set_field, is_struct_instance, register_enum, make_variant, make_unit_variant, is_variant_instance, register_trait, register_impl, call_trait_method, lookup_struct, lookup_enum, lookup_trait, lookup_impl, ContractViolation
# P1-3: Background Job System (后台任务系统)
from src.runtime.jobs import JobSpec, JobPriority, JobStatus, BackoffStrategy, JobRegistry, JobQueue, JobWorker, JobScheduler
# P1-4: Built-In HTTP Server (内置 HTTP 服务器)
from src.runtime.http_server import NexaHttpServer, ServerState, CorsConfig, CspConfig, NexaRequest, RouteSegment, RouteSegmentType, Route, ContractViolation, text, html, json_response, redirect, status_response, create_response, parse_form, parse_json_body, create_error_response, get_mime_type, cache_control_for, apply_security_headers, HotReloadWatcher
# P1-5: Database Integration (内置数据库集成)
from src.runtime.database import NexaDatabase, NexaSQLite, NexaPostgres, DatabaseError, query, query_one, execute, close, begin, commit, rollback, python_to_sql, sql_to_python, adapt_sql_params, agent_memory_query, agent_memory_store, agent_memory_delete, agent_memory_list, contract_violation_to_http_status, verify_wal_mode, verify_foreign_keys
# P2-1: Built-In Auth & OAuth (内置认证与 OAuth)
from src.runtime.auth import NexaAuth, ProviderConfig, AuthConfig, Session, oauth, enable_auth, get_user, get_session, jwt_sign, jwt_verify, jwt_decode, csrf_token, csrf_field, verify_csrf, require_auth, require_auth_middleware, logout_user, agent_api_key_generate, agent_api_key_verify, agent_auth_context, handle_auth_start, handle_auth_callback, handle_auth_logout
# P2-3: KV Store (内置键值存储)
from src.runtime.kv_store import NexaKVStore, KVHandle, kv_open, kv_get, kv_get_int, kv_get_str, kv_get_json, kv_set, kv_set_nx, kv_del, kv_has, kv_list, kv_incr, kv_expire, kv_ttl, kv_flush, agent_kv_query, agent_kv_store, agent_kv_context
# P2-2: Structured Concurrency (结构化并发)
from src.runtime.concurrent import NexaChannel, NexaTask, NexaSchedule, NexaConcurrencyRuntime, RUNTIME, channel, send, recv, recv_timeout, try_recv, close, select, spawn, await_task, try_await, cancel_task, parallel, race, after, schedule, cancel_schedule, sleep_ms, thread_count, parse_interval
# P2-4: Template System (模板系统)
from src.runtime.template import NexaTemplateRenderer, TemplateContentParser, _nexa_tpl_escape, _nexa_tpl_join, _nexa_tpl_safe_str, FILTER_REGISTRY, render_string, template, compile_template, render, agent_template_prompt, agent_template_slot_fill, agent_template_register, agent_template_list, agent_template_unregister
# v2.0: Harness Native Runtime
from src.runtime.harness_kernel import HarnessKernel, HarnessRuntimeMode, AutoLoopConfig, StepResult, AutoLoopResult, ContextScope, get_kernel, reset_kernel
from src.runtime.execution_engine import ExecutionEngine
from src.runtime.context_manager import ContextManager, estimate_tokens
from src.runtime.tool_output_store import ToolOutputStore, get_tool_output_store
from src.runtime.tool_registry import ToolRegistry, ToolSchema, get_tool_registry
from src.runtime.lifecycle_hooks import LifecycleHookManager
from src.runtime.state_store import StateStore
from src.runtime.trace_system import TraceSystem
from src.runtime.evaluation_interface import EvaluationInterface, VerifyResult, BehavioralTrace
from src.runtime.llm_router import LLMRouter, ModelRequirement, ModelInfo
from src.runtime.actor_system import ActorSystem, ActorHandle, ActorMessage, ActorConfig

# P2-4: Template filter function aliases (for generated template code)
_nexa_tpl_filter_upper = FILTER_REGISTRY.get('upper')
_nexa_tpl_filter_uppercase = FILTER_REGISTRY.get('uppercase')
_nexa_tpl_filter_lower = FILTER_REGISTRY.get('lower')
_nexa_tpl_filter_lowercase = FILTER_REGISTRY.get('lowercase')
_nexa_tpl_filter_capitalize = FILTER_REGISTRY.get('capitalize')
_nexa_tpl_filter_trim = FILTER_REGISTRY.get('trim')
_nexa_tpl_filter_truncate = FILTER_REGISTRY.get('truncate')
_nexa_tpl_filter_replace = FILTER_REGISTRY.get('replace')
_nexa_tpl_filter_escape = FILTER_REGISTRY.get('escape')
_nexa_tpl_filter_raw = FILTER_REGISTRY.get('raw')
_nexa_tpl_filter_safe = FILTER_REGISTRY.get('safe')
_nexa_tpl_filter_default = FILTER_REGISTRY.get('default')
_nexa_tpl_filter_length = FILTER_REGISTRY.get('length')
_nexa_tpl_filter_first = FILTER_REGISTRY.get('first')
_nexa_tpl_filter_last = FILTER_REGISTRY.get('last')
_nexa_tpl_filter_reverse = FILTER_REGISTRY.get('reverse')
_nexa_tpl_filter_join = FILTER_REGISTRY.get('join')
_nexa_tpl_filter_slice = FILTER_REGISTRY.get('slice')
_nexa_tpl_filter_json = FILTER_REGISTRY.get('json')
_nexa_tpl_filter_number = FILTER_REGISTRY.get('number')
_nexa_tpl_filter_url_encode = FILTER_REGISTRY.get('url_encode')
_nexa_tpl_filter_strip_tags = FILTER_REGISTRY.get('strip_tags')
_nexa_tpl_filter_word_count = FILTER_REGISTRY.get('word_count')
_nexa_tpl_filter_line_count = FILTER_REGISTRY.get('line_count')
_nexa_tpl_filter_indent = FILTER_REGISTRY.get('indent')
_nexa_tpl_filter_date = FILTER_REGISTRY.get('date')
_nexa_tpl_filter_sort = FILTER_REGISTRY.get('sort')
_nexa_tpl_filter_unique = FILTER_REGISTRY.get('unique')
_nexa_tpl_filter_abs = FILTER_REGISTRY.get('abs')
_nexa_tpl_filter_ceil = FILTER_REGISTRY.get('ceil')
_nexa_tpl_filter_floor = FILTER_REGISTRY.get('floor')

# v1.1: 渐进式类型系统 — 初始化类型检查器
__type_checker = TypeChecker()
__type_mode = get_type_mode()

# P3-6: Null Coalescing helper (空值合并辅助函数)
def _nexa_null_coalesce(left, right):
    if left is None:
        return right
    if isinstance(left, dict) and left.get('_nexa_option_variant') == 'None':
        return right
    if isinstance(left, dict) and not left:
        return right
    return left

# P3-3: Pattern Matching (模式匹配)
from src.runtime.pattern_matching import nexa_match_pattern, nexa_destructure, nexa_make_variant, _nexa_is_tuple_like, _nexa_is_list_like, _nexa_is_dict_with_keys, _nexa_is_variant, _nexa_list_rest, _nexa_dict_rest
# P3-4: ADT — Struct/Enum/Trait/Impl (代数数据类型)
from src.runtime.adt import register_struct, make_struct_instance, struct_get_field, struct_set_field, is_struct_instance, register_enum, make_variant, make_unit_variant, is_variant_instance, register_trait, register_impl, call_trait_method, lookup_struct, lookup_enum, lookup_trait, lookup_impl, ContractViolation

# P3-5: Defer helper (延迟执行辅助函数)
def _nexa_defer_execute(stack):
    while stack:
        try:
            stack.pop()()
        except Exception:
            pass  # defer should not raise on cleanup

# P3-1: String Interpolation helper (字符串插值辅助函数)
def _nexa_interp_str(value):
    'Convert any value to string for interpolation. None -> chr(34)empty stringchr(34), dict -> JSON, etc.'
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, dict):
        if value.get('_nexa_option_variant') == 'Some':
            return _nexa_interp_str(value.get('value'))
        if value.get('_nexa_option_variant') == 'None':
            return ''
        try:
            return json.dumps(value, default=str)
        except Exception:
            return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        try:
            return json.dumps(value, default=str)
        except Exception:
            return str(value)
    return str(value)

# ==========================================
# [Target Code] 自动生成的编排逻辑
# ==========================================

__tool_Read_schema = {
    "name": "Read",
    "description": "Read a file from the local filesystem. Standalone apps can access any file directly. Can read text files (with line numbers, cat -n format), images (PNG, JPG, JPEG, GIF, WEBP), PDF files, and Jupyter notebooks. When reading text files supports optional offset and limit parameters. For images/PDFs max 15 pages per request. You MUST use the offset and limit parameters to read files LARGER than 2000 lines or you will not be able to recall content correctly.",
    "parameters": {
        "type": "object",
        "properties": {
        "file_path": {
                "type": "string",
                "description": "Parameter file_path"
        },
        "offset": {
                "type": "string",
                "description": "Parameter offset"
        },
        "limit": {
                "type": "string",
                "description": "Parameter limit"
        },
        "pages": {
                "type": "string",
                "description": "Parameter pages"
        }
},
        "required": ["file_path", "offset", "limit", "pages"]
    }
}

def Read(file_path, offset, limit, pages):
    """Read a file from the local filesystem. Standalone apps can access any file directly. Can read text files (with line numbers, cat -n format), images (PNG, JPG, JPEG, GIF, WEBP), PDF files, and Jupyter notebooks. When reading text files supports optional offset and limit parameters. For images/PDFs max 15 pages per request. You MUST use the offset and limit parameters to read files LARGER than 2000 lines or you will not be able to recall content correctly."""
    import os
    import base64
    
    MAX_SIZE_BYTES = 256 * 1024   # MAX_OUTPUT_SIZE = 256KB (limits.ts:65)
    MAX_TOKENS = 25000            # DEFAULT_MAX_OUTPUT_TOKENS (limits.ts:18)
    PDF_MAX_PAGES = 20            # PDF_MAX_PAGES_PER_READ
    
    BINARY_EXT = {'.png','.jpg','.jpeg','.gif','.bmp','.ico','.webp','.tiff','.tif',
    '.mp4','.mov','.avi','.mkv','.webm','.wmv','.flv','.m4v','.mpeg','.mpg',
    '.mp3','.wav','.ogg','.flac','.aac','.m4a','.wma','.aiff','.opus',
    '.zip','.tar','.gz','.bz2','.7z','.rar','.xz','.z','.tgz','.iso',
    '.exe','.dll','.so','.dylib','.bin','.o','.a','.obj','.lib','.app','.msi','.deb','.rpm',
    '.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.odt','.ods','.odp',
    '.ttf','.otf','.woff','.woff2','.eot',
    '.pyc','.pyo','.class','.jar','.war','.ear','.node','.wasm','.rlib',
    '.sqlite','.sqlite3','.db','.mdb','.idx',
    '.psd','.ai','.eps','.sketch','.fig','.xd','.blend','.3ds','.max',
    '.swf','.fla','.lockb','.dat','.data'}
    IMAGE_EXT = {'png','jpg','jpeg','gif','webp'}   # FileReadTool.ts:187
    BLOCKED_DEVICES = {'/dev/zero','/dev/random','/dev/urandom','/dev/full','/dev/stdin',
    '/dev/tty','/dev/console','/dev/stdout','/dev/stderr','/dev/fd/0','/dev/fd/1','/dev/fd/2'}
    
    # expandPath: trim + 规范化 (FileReadTool.ts:519)
    fp = (file_path or '').strip()
    full = os.path.abspath(fp)
    _ext_lower = os.path.splitext(full)[1].lower()
    ext = _ext_lower[1:]   # 去点
    
    # device 路径阻断 (FileReadTool.ts:484-490)
    if full in BLOCKED_DEVICES:
        return "Cannot read '%s': this device file would block or produce infinite output." % file_path
    
    # offset 默认 1 (FileReadTool.ts:495)；limit 可空
    _off = int(offset) if offset else 1
    _lim = int(limit) if limit else None
    
    # --- notebook (.ipynb) (FileReadTool.ts:813-855) ---
    if ext == 'ipynb':
        if not os.path.isfile(full):
            return "File does not exist. %s" % file_path
        import json
        try:
            with open(full, 'r', encoding='utf-8', errors='replace') as _f:
                nb = json.load(_f)
        except Exception as _e:
            return "Failed to read notebook: %s" % _e
        out = []
        for _idx, _cell in enumerate(nb.get('cells', [])):
            _ctype = _cell.get('cell_type', 'unknown')
            _src = ''.join(_cell.get('source', [])) if isinstance(_cell.get('source'), list) else str(_cell.get('source', ''))
            out.append('Cell %d (%s):' % (_idx, _ctype))
            out.append(_src)
            _outs = _cell.get('outputs', []) or []
            for _o in _outs:
                _ot = _o.get('output_type', 'output')
                _txt = _o.get('text') or (_o.get('data', {}) or {}).get('text/plain') or ''
                if isinstance(_txt, list):
                    _txt = ''.join(_txt)
                if _txt:
                    out.append('[%s] %s' % (_ot, _txt))
            out.append('')
        _cells_text = '\n'.join(out)
        if len(_cells_text.encode('utf-8')) > MAX_SIZE_BYTES:
            return "Notebook content exceeds maximum allowed size (%d bytes). Use Bash with jq to read specific portions." % MAX_SIZE_BYTES
        return _cells_text or '<system-reminder>Warning: the notebook exists but has no cells.</system-reminder>'
    
    # --- image (FileReadTool.ts:857-883) ---
    if ext in IMAGE_EXT:
        if not os.path.isfile(full):
            return "File does not exist. %s" % file_path
        if os.path.getsize(full) == 0:
            return "Image file is empty: %s" % file_path
        with open(full, 'rb') as _f:
            _buf = _f.read()
        _b64 = base64.b64encode(_buf).decode('ascii')
        # partial: Nexa 字符串工具无法注入多模态 image block；返回数据+说明（忠实检测+读取）
        return "[image:%s media_type=image/%s size=%d bytes base64_len=%d]\n(Multimodal visual injection is a Nexa runtime limitation; base64 payload above. Resize/downsample deferred.)" % (file_path, ext, len(_buf), len(_b64))
    
    # --- pdf (FileReadTool.ts:885-1009) ---
    if ext == 'pdf':
        if not os.path.isfile(full):
            return "File does not exist. %s" % file_path
        # partial: 完整 PDF 文本/page 提取需 poppler (pdfmdtext/pdftoppm)；此处返回说明
        if pages:
            return "[pdf:%s pages=%s] PDF page extraction requires poppler-utils (pdftoppm). Max %d pages/request. Install: brew install poppler / apt-get install poppler-utils." % (file_path, pages, PDF_MAX_PAGES)
        return "[pdf:%s] Full PDF read requires poppler-utils. Use the pages parameter to read specific page ranges (e.g. pages: \"1-5\", max %d pages)." % (file_path, PDF_MAX_PAGES)
    
    # --- binary 拒绝 (FileReadTool.ts:467-480) ---
    if _ext_lower in BINARY_EXT:
        return "This tool cannot read binary files. The file appears to be a binary %s file. Please use appropriate tools for binary file analysis." % _ext_lower
    
    # --- text (FileReadTool.ts:1011-1078) ---
    if not os.path.isfile(full):
        return "File does not exist. %s" % file_path
    
    _total_bytes = os.path.getsize(full)
    # maxSizeBytes 门：门的是【整个文件大小】(非切片)；仅当未指定 limit 时强制 (limits.ts:9-13, FileReadTool.ts:1018)
    if _lim is None and _total_bytes > MAX_SIZE_BYTES:
        return "File content (%d bytes) exceeds maximum allowed size (%d bytes). Use offset and limit parameters to read specific portions of the file, or use Grep/Glob to search for specific content." % (_total_bytes, MAX_SIZE_BYTES)
    
    # 0 字节文件 → "contents are empty" (FileReadTool.ts:698-699)
    if _total_bytes == 0:
        return '<system-reminder>Warning: the file exists but the contents are empty.</system-reminder>'
    
    with open(full, 'r', encoding='utf-8', errors='replace') as _f:
        _all_lines = _f.read().split('\n')
    # 若 read 末尾带 \n，split 会多一个空串，与 CC 一致处理
    _total_lines = len(_all_lines)
    
    # offset 1-based → 0-based start (FileReadTool.ts:1012 lineOffset = offset-1)
    _start = max(0, _off - 1)
    if _lim is not None:
        _slice = _all_lines[_start:_start + _lim]
    else:
        _slice = _all_lines[_start:]
    _content = '\n'.join(_slice)
    
    # maxTokens 门：粗估 (4 bytes/token) (FileReadTool.ts:745-763)
    if len(_content.encode('utf-8')) > MAX_TOKENS * 4:
        return "File content (estimated %d tokens) exceeds maximum allowed tokens (%d). Use offset and limit parameters to read specific portions of the file, or use Grep to search for specific content." % (len(_content.encode('utf-8')) // 4, MAX_TOKENS)
    
    # 空内容 / offset 超出 (FileReadTool.ts:690-701)
    if not _content:
        if _total_lines == 0:
            return '<system-reminder>Warning: the file exists but the contents are empty.</system-reminder>'
        return '<system-reminder>Warning: the file exists but is shorter than the provided offset (%d). The file has %d lines.</system-reminder>' % (_off, _total_lines)
    
    # addLineNumbers: cat -n 格式 — padStart(6)+'→'；>=6 位无 pad (file.ts:310-318)
    # 记录 readFileState 供 Edit/Write staleness 检查 (FileEditTool.ts:437-451 / FileWriteTool)
    globals().setdefault('_CCPORT_READ_STATE', {})[full] = {
        'mtime': os.path.getmtime(full), 'offset': _off, 'limit': _lim, 'content': _content}
    _lines = _content.split('\n')
    _numbered = []
    for _i, _line in enumerate(_lines):
        _n = _start + _i + 1
        _ns = str(_n)
        if len(_ns) >= 6:
            _numbered.append('%s→%s' % (_ns, _line))
        else:
            _numbered.append('%s→%s' % (_ns.rjust(6), _line))
    return '\n'.join(_numbered)
from src.runtime.tools_registry import LOCAL_TOOLS
LOCAL_TOOLS['Read'] = Read

if __name__ == "__main__":
