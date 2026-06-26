// commands.ts — 斜杠命令清单（对齐 CC 的 PromptInputFooterSuggestions 数据）
// 来源：引擎 run_command 派发的 20 命令（commands.nx /help 输出）
export interface Command {
  name: string;
  desc: string;
}

export const COMMANDS: Command[] = [
  { name: "/help", desc: "Show help and available commands" },
  { name: "/clear", desc: "Clear conversation history" },
  { name: "/compact", desc: "Compact conversation but keep a summary" },
  { name: "/model", desc: "Show / switch the current model" },
  { name: "/cost", desc: "Show token usage and cost" },
  { name: "/status", desc: "Show session status (cwd, model, git)" },
  { name: "/context", desc: "Show assembled context" },
  { name: "/config", desc: "Show config / settings" },
  { name: "/vim", desc: "Toggle editor mode (normal <-> vim)" },
  { name: "/fast", desc: "Toggle fast mode" },
  { name: "/rewind", desc: "Rewind to a previous message" },
  { name: "/resume", desc: "Resume a previous session" },
  { name: "/init", desc: "Analyze repo and create CLAUDE.md" },
  { name: "/doctor", desc: "Diagnose installation and settings" },
  { name: "/add-dir", desc: "Add a working directory" },
  { name: "/memory", desc: "Show CLAUDE.md memory file hierarchy" },
  { name: "/permissions", desc: "Show allow/deny permission rules" },
  { name: "/agents", desc: "List configured agents" },
  { name: "/mcp", desc: "Show configured MCP servers" },
  { name: "/copy", desc: "Copy last assistant reply to clipboard" },
  { name: "/usage", desc: "Detailed token and cost statistics" },
  { name: "/export", desc: "Export conversation to markdown" },
  { name: "/undo", desc: "Undo last file edit from snapshot" },
  { name: "/review", desc: "Show git diff for review" },
  { name: "/share", desc: "Share conversation as markdown file" },
  { name: "/git", desc: "Git helpers: status, log, branch, diff, show" },
  { name: "/pr", desc: "Create a pull request" },
  { name: "/login", desc: "Show API/provider configuration" },
  { name: "/exit", desc: "Exit the REPL" },
];
