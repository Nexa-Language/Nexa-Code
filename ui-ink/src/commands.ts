// commands.ts — 斜杠命令清单（对齐 CC 的 PromptInputFooterSuggestions 数据）
// 来源：引擎 run_command 派发的 20 命令（commands.nx /help 输出）
export interface Command {
  name: string;
  desc: string;
  source?: string;
}

export const COMMANDS: Command[] = [
  { name: "/help", source: "builtin", desc: "Show help and available commands" },
  { name: "/clear", source: "builtin", desc: "Clear conversation history" },
  { name: "/compact", source: "builtin", desc: "Compact conversation but keep a summary" },
  { name: "/model", source: "builtin", desc: "Show / switch the current model" },
  { name: "/cost", source: "builtin", desc: "Show token usage and cost" },
  { name: "/status", source: "builtin", desc: "Show session status (cwd, model, git)" },
  { name: "/context", source: "builtin", desc: "Show assembled context" },
  { name: "/config", source: "builtin", desc: "Show config / settings" },
  { name: "/vim", source: "builtin", desc: "Toggle editor mode (normal <-> vim)" },
  { name: "/fast", source: "builtin", desc: "Toggle fast mode" },
  { name: "/rewind", source: "builtin", desc: "Rewind to a previous message" },
  { name: "/resume", source: "builtin", desc: "Resume a previous session" },
  { name: "/init", source: "builtin", desc: "Analyze repo and create CLAUDE.md" },
  { name: "/doctor", source: "builtin", desc: "Diagnose installation and settings" },
  { name: "/add-dir", source: "builtin", desc: "Add a working directory" },
  { name: "/memory", source: "builtin", desc: "Show CLAUDE.md memory file hierarchy" },
  { name: "/permissions", source: "builtin", desc: "Show allow/deny permission rules" },
  { name: "/agents", source: "builtin", desc: "Manage agent configurations" },
  { name: "/mcp", source: "builtin", desc: "Show configured MCP servers" },
  { name: "/copy", source: "builtin", desc: "Copy last assistant reply to clipboard" },
  { name: "/usage", source: "builtin", desc: "Detailed token and cost statistics" },
  { name: "/export", source: "builtin", desc: "Export conversation to markdown" },
  { name: "/undo", source: "builtin", desc: "Undo last file edit from snapshot" },
  { name: "/review", source: "builtin", desc: "Show git diff for review" },
  { name: "/share", source: "builtin", desc: "Share conversation as markdown file" },
  { name: "/git", source: "builtin", desc: "Git helpers: status, log, branch, diff, show" },
  { name: "/pr", source: "builtin", desc: "Create a pull request" },
  { name: "/login", source: "builtin", desc: "Show API/provider configuration" },
  { name: "/exit", source: "builtin", desc: "Exit the REPL" },
];
