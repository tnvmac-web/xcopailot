/**
 * X-Copilot Web Dashboard — SPA with embedded TUI
 *
 * Mirrors Hermes web/ dashboard pattern.
 * Embeds real X-Copilot TUI via xterm.js PTY bridge,
 * not a React rewrite of the chat experience.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { JsonRpcClient, wsUrl, apiUrl } from "@xcopilot/shared";

// ── Types ──────────────────────────────────────────

interface Session {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
}

interface Message {
  role: "user" | "assistant" | "system" | "error";
  content: string;
  timestamp: string;
}

interface Task {
  task_id: string;
  goal: string;
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled";
  created_at: string;
  summary?: string;
}

// ── TUI Terminal Component ─────────────────────────

function TuiTerminal({ sessionId }: { sessionId: string | null }) {
  const terminalRef = useRef<HTMLDivElement>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!terminalRef.current || !sessionId) return;

    // Dynamically import xterm.js
    import("xterm").then(({ Terminal }) => {
      import("@xterm/addon-fit").then(({ FitAddon }) => {
        import("@xterm/addon-webgl").then(({ WebglAddon }) => {
          const term = new Terminal({
            theme: {
              background: "#0d1117",
              foreground: "#e0e0e0",
              cursor: "#e94560",
              selection: "#264f78",
            },
            fontFamily: "monospace",
            fontSize: 14,
            allowTransparency: true,
          });

          const fitAddon = new FitAddon();
          term.loadAddon(fitAddon);

          const webglAddon = new WebglAddon();
          term.loadAddon(webglAddon);

          term.open(terminalRef.current!);
          fitAddon.fit();

          // Connect to PTY bridge via WebSocket
          const ws = new WebSocket(wsUrl("/api/pty"));
          ws.onopen = () => {
            setConnected(true);
            // Send session ID to attach to the right PTY
            ws.send(JSON.stringify({ type: "attach", session_id: sessionId }));
          };

          // Send terminal input to backend
          term.onData((data) => {
            ws.send(JSON.stringify({ type: "input", data }));
          });

          // Receive PTY output from backend
          ws.onmessage = (event) => {
            try {
              const msg = JSON.parse(event.data);
              if (msg.type === "output") {
                term.write(msg.data);
              } else if (msg.type === "resize") {
                term.resize(msg.cols, msg.rows);
              }
            } catch {
              // Ignore parse errors
            }
          };

          ws.onclose = () => {
            setConnected(false);
          };

          // Handle resize
          const handleResize = () => fitAddon.fit();
          window.addEventListener("resize", handleResize);

          return () => {
            window.removeEventListener("resize", handleResize);
            ws.close();
            term.dispose();
          };
        }).catch(() => {
          // WebGL not available, fall back to canvas
          const term = new Terminal({
            theme: { background: "#0d1117", foreground: "#e0e0e0" },
            fontFamily: "monospace",
            fontSize: 14,
          });
          term.open(terminalRef.current!);
          setConnected(true);
        });
      }).catch(() => {
        // Fit addon not available
        const term = new Terminal({
          theme: { background: "#0d1117", foreground: "#e0e0e0" },
          fontFamily: "monospace",
          fontSize: 14,
        });
        term.open(terminalRef.current!);
        setConnected(true);
      });
    }).catch(() => {
      // xterm not available, show placeholder
      if (terminalRef.current) {
        terminalRef.current.innerHTML = "<div style='color:#e0e0e0;padding:16px'>Terminal not available</div>";
      }
    });
  }, [sessionId]);

  return (
    <div className="tui-terminal">
      <div className="terminal-header">
        <span>Terminal</span>
        <span className={`status-dot ${connected ? "running" : "stopped"}`} />
      </div>
      <div ref={terminalRef} className="terminal-container" />
    </div>
  );
}

// ── Chat Panel (composer + transcript) ─────────────

function ChatPanel({ sessionId }: { sessionId: string | null }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const clientRef = useRef<JsonRpcClient | null>(null);

  useEffect(() => {
    clientRef.current = new JsonRpcClient(wsUrl("/ws"));
    clientRef.current.connect().catch(() => {});

    return () => {
      clientRef.current?.disconnect();
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || !clientRef.current?.isConnected) return;

    const userMessage: Message = { role: "user", content: text, timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, userMessage]);

    const assistantMessage: Message = { role: "assistant", content: "", timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, assistantMessage]);
    setStreaming(true);

    try {
      const result = await clientRef.current!.request<{ content: string }>("chat.send", [text, sessionId]);
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant") {
          updated[updated.length - 1] = { ...last, content: result.content };
        }
        return updated;
      });
    } catch (err: any) {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant") {
          updated[updated.length - 1] = { ...last, role: "error", content: `Error: ${err.message}` };
        }
        return updated;
      });
    } finally {
      setStreaming(false);
    }
  }, [sessionId]);

  return (
    <div className="chat-panel">
      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="role">{msg.role === "user" ? "You" : "X-Copilot"}</div>
            <div className="content">{msg.content}</div>
          </div>
        ))}
        {streaming && <div className="cursor">▊</div>}
        <div ref={messagesEndRef} />
      </div>
      <Composer onSend={sendMessage} disabled={streaming} />
    </div>
  );
}

function Composer({ onSend, disabled }: { onSend: (text: string) => void; disabled: boolean }) {
  const [text, setText] = useState("");

  const handleSubmit = () => {
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    setText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="composer">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type a message... (Shift+Enter for newline)"
        rows={1}
        disabled={disabled}
      />
      <button onClick={handleSubmit} disabled={disabled || !text.trim()}>
        Send
      </button>
    </div>
  );
}

// ── Main Dashboard ─────────────────────────────────

export default function Dashboard() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [serverStatus, setServerStatus] = useState<"running" | "stopped" | "error">("checking");
  const [activeView, setActiveView] = useState<"chat" | "terminal" | "tasks" | "settings">("chat");

  // Check server status
  useEffect(() => {
    const check = async () => {
      try {
        const resp = await fetch(apiUrl("/api/status"));
        const data = await resp.json();
        setServerStatus(data.status === "ready" ? "running" : "stopped");
      } catch {
        setServerStatus("stopped");
      }
    };
    check();
    const interval = setInterval(check, 10000);
    return () => clearInterval(interval);
  }, []);

  // Load sessions
  useEffect(() => {
    const load = async () => {
      try {
        const resp = await fetch(apiUrl("/api/sessions"));
        const data = await resp.json();
        setSessions(data.sessions || []);
      } catch {
        // Ignore
      }
    };
    load();
  }, []);

  // Load tasks
  useEffect(() => {
    const load = async () => {
      try {
        const resp = await fetch(apiUrl("/api/delegation/tasks"));
        const data = await resp.json();
        setTasks(data.tasks || []);
      } catch {
        // Ignore
      }
    };
    load();
  }, []);

  return (
    <div className="dashboard">
      <header className="header">
        <h1>X-Copilot</h1>
        <nav>
          <button className={activeView === "chat" ? "active" : ""} onClick={() => setActiveView("chat")}>
            Chat
          </button>
          <button className={activeView === "terminal" ? "active" : ""} onClick={() => setActiveView("terminal")}>
            Terminal
          </button>
          <button className={activeView === "tasks" ? "active" : ""} onClick={() => setActiveView("tasks")}>
            Tasks
          </button>
          <button className={activeView === "settings" ? "active" : ""} onClick={() => setActiveView("settings")}>
            Settings
          </button>
        </nav>
        <span className={`status-dot ${serverStatus}`}>{serverStatus}</span>
      </header>

      <div className="main">
        <aside className="sidebar">
          <div className="sidebar-header">Sessions</div>
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`session-item ${s.id === activeSession ? "active" : ""}`}
              onClick={() => setActiveSession(s.id)}
            >
              <div className="session-title">{s.title}</div>
              <div className="session-time">{new Date(s.updated_at).toLocaleDateString()}</div>
            </div>
          ))}
          {sessions.length === 0 && <div className="empty">No sessions</div>}
        </aside>

        <div className="content">
          {activeView === "chat" && <ChatPanel sessionId={activeSession} />}
          {activeView === "terminal" && <TuiTerminal sessionId={activeSession} />}
          {activeView === "tasks" && (
            <div className="tasks-view">
              <h3>Delegation Tasks</h3>
              {tasks.map((t) => (
                <div key={t.task_id} className="task-item">
                  <div className="goal">{t.goal}</div>
                  <span className={`status status-${t.status}`}>{t.status}</span>
                </div>
              ))}
              {tasks.length === 0 && <div className="empty">No tasks</div>}
            </div>
          )}
          {activeView === "settings" && (
            <div className="settings-view">
              <h3>Settings</h3>
              <p>Model, permission mode, provider settings.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}