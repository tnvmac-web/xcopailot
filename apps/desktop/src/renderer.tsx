/**
 * X-Copilot Desktop App — Renderer
 *
 * Own composer/transcript — not embedding web dashboard.
 * Communicates with backend via JSON-RPC (@xcopilot/shared).
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { JsonRpcClient } from "@xcopilot/shared";

// ── Types ──────────────────────────────────────────

interface Message {
  role: "user" | "assistant" | "system" | "error";
  content: string;
  timestamp: string;
}

interface Session {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
}

interface Task {
  task_id: string;
  goal: string;
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled";
  created_at: string;
  summary?: string;
}

// ── API Client ─────────────────────────────────────

const client = new JsonRpcClient(`ws://${window.location.host}/ws`);

async function apiCall<T>(method: string, params?: unknown[]): Promise<T> {
  return client.request<T>(method, params);
}

// ── Components ─────────────────────────────────────

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`message ${isUser ? "user" : "assistant"}`}>
      <div className="role">{isUser ? "You" : "X-Copilot"}</div>
      <div className="content">{message.content}</div>
    </div>
  );
}

function Composer({ onSend, disabled }: { onSend: (text: string) => void; disabled: boolean }) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    setText("");
    inputRef.current?.focus();
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
        ref={inputRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type a message..."
        rows={1}
        disabled={disabled}
      />
      <button onClick={handleSubmit} disabled={disabled || !text.trim()}>
        Send
      </button>
    </div>
  );
}

function SessionList({ sessions, activeId, onSelect }: { sessions: Session[]; activeId: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="session-list">
      <div className="session-list-header">Sessions</div>
      {sessions.map((s) => (
        <div
          key={s.id}
          className={`session-item ${s.id === activeId ? "active" : ""}`}
          onClick={() => onSelect(s.id)}
        >
          <div className="session-title">{s.title}</div>
          <div className="session-time">{new Date(s.updated_at).toLocaleDateString()}</div>
        </div>
      ))}
      {sessions.length === 0 && <div className="empty">No sessions</div>}
    </div>
  );
}

function TaskPanel({ tasks }: { tasks: Task[] }) {
  return (
    <div className="task-panel">
      <div className="task-panel-header">Tasks</div>
      {tasks.map((t) => (
        <div key={t.task_id} className="task-item">
          <div className="goal">{t.goal.substring(0, 50)}</div>
          <span className={`status status-${t.status}`}>{t.status}</span>
        </div>
      ))}
      {tasks.length === 0 && <div className="empty">No tasks</div>}
    </div>
  );
}

// ── Main App ───────────────────────────────────────

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [serverStatus, setServerStatus] = useState<"running" | "stopped" | "error">("checking");
  const [streaming, setStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Connect to backend
  useEffect(() => {
    client.connect().catch(() => {});

    // Check server status
    const check = async () => {
      try {
        const status = await apiCall<{ status: string }>("server.status");
        setServerStatus(status.status === "running" ? "running" : "stopped");
      } catch {
        setServerStatus("stopped");
      }
    };
    check();

    // Load sessions
    const loadSessions = async () => {
      try {
        const data = await apiCall<{ sessions: Session[] }>("sessions.list");
        setSessions(data.sessions);
      } catch {
        // Ignore
      }
    };
    loadSessions();

    // Load tasks
    const loadTasks = async () => {
      try {
        const data = await apiCall<{ tasks: Task[] }>("tasks.list");
        setTasks(data.tasks);
      } catch {
        // Ignore
      }
    };
    loadTasks();

    // Periodic server status check
    const interval = setInterval(check, 10000);
    return () => {
      clearInterval(interval);
      client.disconnect();
    };
  }, []);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Send message
  const handleSend = useCallback(async (text: string) => {
    if (!text.trim()) return;

    const userMessage: Message = { role: "user", content: text, timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, userMessage]);

    // Add streaming placeholder
    const assistantMessage: Message = { role: "assistant", content: "", timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, assistantMessage]);
    setStreaming(true);

    try {
      const result = await apiCall<{ content: string }>("chat.send", [text, activeSession]);
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

    // Refresh sessions and tasks
    try {
      const data = await apiCall<{ sessions: Session[] }>("sessions.list");
      setSessions(data.sessions);
    } catch {
      // Ignore
    }
    try {
      const data = await apiCall<{ tasks: Task[] }>("tasks.list");
      setTasks(data.tasks);
    } catch {
      // Ignore
    }
  }, [activeSession]);

  // Create new session
  const handleNewSession = async () => {
    try {
      const data = await apiCall<{ session: Session }>("sessions.create");
      setActiveSession(data.session.id);
      setMessages([]);
      const sessions = await apiCall<{ sessions: Session[] }>("sessions.list");
      setSessions(sessions.sessions);
    } catch {
      // Ignore
    }
  };

  // Load session
  const handleLoadSession = async (sessionId: string) => {
    try {
      const data = await apiCall<{ messages: Message[] }>("sessions.messages", [sessionId]);
      setActiveSession(sessionId);
      setMessages(data.messages);
    } catch {
      // Ignore
    }
  };

  return (
    <div className="app">
      <div className="header">
        <h1>X-Copilot</h1>
        <div className="header-actions">
          <button onClick={handleNewSession}>New Session</button>
          <span className={`status-dot ${serverStatus}`}>{serverStatus}</span>
        </div>
      </div>

      <div className="main">
        <SessionList sessions={sessions} activeId={activeSession} onSelect={handleLoadSession} />

        <div className="chat-area">
          <div className="messages">
            {messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))}
            {streaming && <div className="cursor">▊</div>}
            <div ref={messagesEndRef} />
          </div>
          <Composer onSend={handleSend} disabled={serverStatus !== "running" || streaming} />
        </div>

        <TaskPanel tasks={tasks} />
      </div>
    </div>
  );
}