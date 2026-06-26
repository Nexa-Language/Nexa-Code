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

__tool_Grep_schema = {
    "name": "Grep",
    "description": "Search file contents with a regular expression (ripgrep). Output modes: content (matching lines, supports -A/-B/-C context, -n line numbers, head_limit), files_with_matches (file paths), count (match counts). Defaults to files_with_matches. head_limit defaults to 250, 0 for unlimited.",
    "parameters": {
        "type": "object",
        "properties": {
        "pattern": {
                "type": "string",
                "description": "Parameter pattern"
        },
        "path": {
                "type": "string",
                "description": "Parameter path"
        },
        "glob": {
                "type": "string",
                "description": "Parameter glob"
        },
        "output_mode": {
                "type": "string",
                "description": "Parameter output_mode"
        },
        "glob_type": {
                "type": "string",
                "description": "Parameter glob_type"
        },
        "context_before": {
                "type": "string",
                "description": "Parameter context_before"
        },
        "context_after": {
                "type": "string",
                "description": "Parameter context_after"
        },
        "context_c": {
                "type": "string",
                "description": "Parameter context_c"
        },
        "show_line_numbers": {
                "type": "string",
                "description": "Parameter show_line_numbers"
        },
        "case_insensitive": {
                "type": "string",
                "description": "Parameter case_insensitive"
        },
        "head_limit": {
                "type": "string",
                "description": "Parameter head_limit"
        },
        "offset": {
                "type": "string",
                "description": "Parameter offset"
        },
        "multiline": {
                "type": "string",
                "description": "Parameter multiline"
        }
},
        "required": ["pattern", "path", "glob", "output_mode", "glob_type", "context_before", "context_after", "context_c", "show_line_numbers", "case_insensitive", "head_limit", "offset", "multiline"]
    }
}

def Grep(pattern, path, glob, output_mode, glob_type, context_before, context_after, context_c, show_line_numbers, case_insensitive, head_limit, offset, multiline):
    """Search file contents with a regular expression (ripgrep). Output modes: content (matching lines, supports -A/-B/-C context, -n line numbers, head_limit), files_with_matches (file paths), count (match counts). Defaults to files_with_matches. head_limit defaults to 250, 0 for unlimited."""
    import os
    import shutil
    import subprocess
    
    DEFAULT_HEAD_LIMIT = 250   # GrepTool.ts:101-104
    
    _pat = pattern or ''
    _search_path = (path or '').strip() or os.getcwd()
    _search_path = os.path.abspath(_search_path)
    _glob = glob or ''
    _type = glob_type or ''
    _mode = (output_mode or 'files_with_matches')
    if _mode not in ('content', 'files_with_matches', 'count'):
        _mode = 'files_with_matches'
    _B = int(context_before) if context_before else None
    _A = int(context_after) if context_after else None
    _C = int(context_c) if context_c else None
    _n = show_line_numbers if show_line_numbers is not None else True
    _i = bool(case_insensitive) if case_insensitive else False
    _ml = bool(multiline) if multiline else False
    _hl = DEFAULT_HEAD_LIMIT if head_limit is None else int(head_limit)
    _off = int(offset) if offset else 0
    
    VCS_DIRS = ['.git', '.hg', '.svn', '.idea', '.vscode', 'node_modules']
    
    def _build_rg():
        a = ['--hidden']
        for _d in VCS_DIRS:
            a += ['--glob', '!' + _d]
        a += ['--max-columns', '500']
        if _ml:
            a += ['-U', '--multiline-dotall']
        if _i:
            a += ['-i']
        if _mode == 'files_with_matches':
            a += ['-l']
        elif _mode == 'count':
            a += ['-c']
        if _n and _mode == 'content':
            a += ['-n']
        if _mode == 'content':
            if _C is not None:
                a += ['-C', str(_C)]
            else:
                if _B is not None:
                    a += ['-B', str(_B)]
                if _A is not None:
                    a += ['-A', str(_A)]
        if _pat.startswith('-'):
            a += ['-e', _pat]
        else:
            a += [_pat]
        if _type:
            a += ['--type', _type]
        if _glob:
            for _raw in _glob.replace(',', ' ').split():
                a += ['--glob', _raw]
        a += [_search_path]
        return a
    
    # head_limit/offset 分页 (GrepTool.ts:108-126)
    def _paginate(_lines):
        if _off:
            _lines = _lines[_off:]
        if _hl and _hl > 0:
            _lines = _lines[:_hl]
        return _lines
    
    _rg = shutil.which('rg')
    if _rg:
        try:
            _proc = subprocess.run([_rg] + _build_rg(), capture_output=True, text=True, timeout=60)
            _out = (_proc.stdout or '').rstrip('\n')
            if not _out:
                return ''
            _lines = _out.split('\n')
            _lines = _paginate(_lines)
            return '\n'.join(_lines)
        except Exception:
            pass  # 降级到 Python
    
    # fallback: Python re 搜索（rg 不可用）
    import re
    _flags = re.MULTILINE
    if _i:
        _flags |= re.IGNORECASE
    try:
        _regex = re.compile(_pat, _flags)
    except re.error as _e:
        return 'Invalid regex: %s' % _e
    
    _files = []
    if os.path.isfile(_search_path):
        _files = [_search_path]
    else:
        for _root, _dirs, _fnames in os.walk(_search_path):
            _dirs[:] = [d for d in _dirs if d not in VCS_DIRS]
            for _fn in _fnames:
                _files.append(os.path.join(_root, _fn))
    
    _results = []
    for _f in _files:
        if _glob:
            import fnmatch as _fnm
            if not _fnm.fnmatch(os.path.basename(_f), _glob):
                continue
        try:
            with open(_f, 'r', encoding='utf-8', errors='ignore') as _fh:
                _txt = _fh.read()
        except Exception:
            continue
        _lines = _txt.split('\n')
        _matches = [(_i2 + 1, _l) for _i2, _l in enumerate(_lines) if _regex.search(_l)]
        if not _matches:
            continue
        if _mode == 'files_with_matches':
            _results.append(_f)
        elif _mode == 'count':
            _results.append('%s:%d' % (_f, len(_matches)))
        else:
            for _ln, _l in _matches:
                if _n:
                    _results.append('%s:%d:%s' % (_f, _ln, _l))
                else:
                    _results.append('%s:%s' % (_f, _l))
    
    _results = _paginate(_results)
    return '\n'.join(_results)
from src.runtime.tools_registry import LOCAL_TOOLS
LOCAL_TOOLS['Grep'] = Grep

if __name__ == "__main__":
