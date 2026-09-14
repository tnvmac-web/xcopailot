/**
 * X-Copilot Shared Package (@xcopilot/shared)
 *
 * Framework-agnostic utilities used by both desktop and web surfaces.
 * Mirrors Hermes @hermes/shared pattern.
 */

// ── JSON-RPC Client ──────────────────────────────────────

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: unknown[];
}

export interface JsonRpcResponse<T = unknown> {
  jsonrpc: "2.0";
  id: number;
  result?: T;
  error?: { code: number; message: string };
}

export interface JsonRpcNotification {
  jsonrpc: "2.0";
  method: string;
  params?: unknown[];
}

export class JsonRpcClient {
  private url: string;
  private id = 0;
  private pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void }>();
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private onNotification?: (method: string, params?: unknown[]) => void;

  constructor(url: string, options?: { onNotification?: (method: string, params?: unknown[]) => void }) {
    this.url = url;
    this.onNotification = options?.onNotification;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log("[jsonrpc] Connected");
        resolve();
      };

      this.ws.onmessage = (event) => {
        try {
          const msg: JsonRpcResponse | JsonRpcNotification = JSON.parse(event.data);
          if ("result" in msg || "error" in msg) {
            const pending = this.pending.get(msg.id);
            if (pending) {
              this.pending.delete(msg.id);
              if ("result" in msg) {
                pending.resolve(msg.result);
              } else {
                pending.reject(new Error(msg.error?.message || "Unknown error"));
              }
            }
          } else {
            // Notification
            this.onNotification?.(msg.method, msg.params);
          }
        } catch (e) {
          console.error("[jsonrpc] Parse error:", e);
        }
      };

      this.ws.onerror = (err) => {
        reject(err);
      };

      this.ws.onclose = () => {
        // Auto-reconnect
        if (this.reconnectTimer) return;
        this.reconnectTimer = setTimeout(() => {
          this.reconnectTimer = null;
          this.connect().catch(() => {});
        }, 3000);
      };
    });
  }

  request<T = unknown>(method: string, params?: unknown[]): Promise<T> {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error("Not connected"));
        return;
      }

      const id = ++this.id;
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject });

      const req: JsonRpcRequest = { jsonrpc: "2.0", id, method, params };
      this.ws.send(JSON.stringify(req));
    });
  }

  sendNotification(method: string, params?: unknown[]): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    const notif: JsonRpcNotification = { jsonrpc: "2.0", method, params };
    this.ws.send(JSON.stringify(notif));
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.pending.clear();
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// ── Types ─────────────────────────────────────────────────

export interface Session {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
}

export interface Message {
  role: "user" | "assistant" | "system" | "error";
  content: string;
  timestamp: string;
}

export interface Task {
  task_id: string;
  goal: string;
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled";
  created_at: string;
  started_at?: string;
  completed_at?: string;
  summary?: string;
  error?: string;
}

export interface Settings {
  model: string;
  permission_mode: "standard" | "plan" | "bypass" | "auto-ask" | "dont-ask";
  provider: string;
}

export interface CronJob {
  id: string;
  command: string;
  schedule: string;
  enabled: boolean;
  created_at: string;
}

export interface ToolSchema {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

// ── WebSocket URL helpers ─────────────────────────────────

export function wsUrl(path: string): string {
  const u = new URL(path, `http://${window.location.host}`);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return u.toString();
}

export function apiUrl(path: string): string {
  return `${window.location.origin}${path}`;
}