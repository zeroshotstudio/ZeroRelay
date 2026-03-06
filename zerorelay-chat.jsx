import { useState, useEffect, useRef, useCallback } from "react";

const COLORS = {
  bg: "#0a0a0b",
  surface: "#131316",
  border: "#232328",
  textPrimary: "#e8e8ed",
  textSecondary: "#8e8e99",
  textDim: "#5a5a66",
  accentBlue: "#4a9eff",
  accentGreen: "#34d399",
  accentOrange: "#f59e0b",
  accentRed: "#ef4444",
  accentPurple: "#a78bfa",
};

const ROLE_META = {
  jimmy: { label: "Jimmy", color: COLORS.accentOrange, icon: "🏍" },
  claude_ai: { label: "Claude.ai", color: COLORS.accentBlue, icon: "◈" },
  vps_claude: { label: "Z (Claude Code)", color: COLORS.accentGreen, icon: "⚡" },
};

const STATUS_META = {
  disconnected: { color: COLORS.accentRed, label: "Disconnected" },
  connecting: { color: COLORS.accentOrange, label: "Connecting..." },
  connected: { color: COLORS.accentGreen, label: "Connected" },
};

export default function ZeroRelayChat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [wsUrl, setWsUrl] = useState("");
  const [myRole, setMyRole] = useState("jimmy");
  const [status, setStatus] = useState("disconnected");
  const [peersOnline, setPeersOnline] = useState([]);
  const [configured, setConfigured] = useState(false);
  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const reconnectRef = useRef(null);
  const myRoleRef = useRef(myRole);

  useEffect(() => { myRoleRef.current = myRole; }, [myRole]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  useEffect(scrollToBottom, [messages]);

  const addSystemMsg = useCallback((text) => {
    setMessages((prev) => [
      ...prev,
      { type: "system", content: text, timestamp: new Date().toISOString() },
    ]);
  }, []);

  const connect = useCallback((url, role) => {
    if (wsRef.current) wsRef.current.close();
    setStatus("connecting");
    const fullUrl = `${url}?role=${role}`;

    try {
      const ws = new WebSocket(fullUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
        addSystemMsg(`Connected as ${ROLE_META[role]?.label || role}`);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "connected") {
            setPeersOnline(data.peers_online || []);
            if (data.history?.length > 0) {
              setMessages((prev) => [...data.history, ...prev]);
            }
            return;
          }

          if (data.type === "system") {
            addSystemMsg(data.message);
            if (data.message?.includes("joined")) {
              const who = data.message.replace(" joined", "");
              setPeersOnline((prev) => [...new Set([...prev, who])]);
            }
            if (data.message?.includes("left")) {
              const who = data.message.replace(" left", "");
              setPeersOnline((prev) => prev.filter((p) => p !== who));
            }
            return;
          }

          if (data.type === "message") {
            if (data.meta === "typing_indicator") return;
            setMessages((prev) => [...prev, data]);
          }
        } catch (e) {
          console.error("Parse error:", e);
        }
      };

      ws.onclose = () => {
        setStatus("disconnected");
        addSystemMsg("Disconnected — reconnecting...");
        reconnectRef.current = setTimeout(() => connect(url, myRoleRef.current), 3000);
      };

      ws.onerror = () => setStatus("disconnected");
    } catch (e) {
      setStatus("disconnected");
      addSystemMsg(`Connection failed: ${e.message}`);
    }
  }, [addSystemMsg]);

  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
  }, []);

  const send = () => {
    if (!input.trim() || !wsRef.current || wsRef.current.readyState !== 1) return;
    wsRef.current.send(JSON.stringify({ content: input.trim() }));
    setMessages((prev) => [
      ...prev,
      {
        type: "message",
        from: myRole,
        content: input.trim(),
        timestamp: new Date().toISOString(),
      },
    ]);
    setInput("");
    inputRef.current?.focus();
  };

  const handleSetup = () => {
    if (!wsUrl.trim()) return;
    let url = wsUrl.trim();
    if (!url.startsWith("ws://") && !url.startsWith("wss://")) url = `ws://${url}`;
    if (!url.includes(":8765") && !url.match(/:\d+$/)) url = `${url}:8765`;
    setConfigured(true);
    connect(url, myRole);
  };

  const formatTime = (ts) => {
    try {
      return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch { return ""; }
  };

  // --- SETUP SCREEN ---
  if (!configured) {
    return (
      <div style={{
        background: COLORS.bg, minHeight: "100vh", display: "flex",
        alignItems: "center", justifyContent: "center",
        fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
        color: COLORS.textPrimary,
      }}>
        <div style={{
          background: COLORS.surface, border: `1px solid ${COLORS.border}`,
          borderRadius: 12, padding: 40, width: "100%", maxWidth: 480,
        }}>
          <div style={{ marginBottom: 8, fontSize: 11, letterSpacing: 3, color: COLORS.textDim, textTransform: "uppercase" }}>
            ZeroShot Studio
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: "0 0 6px 0" }}>ZeroRelay</h1>
          <p style={{ fontSize: 13, color: COLORS.textSecondary, margin: "0 0 32px 0", lineHeight: 1.5 }}>
            Three-way Claude chat relay
          </p>

          {/* Role selector */}
          <label style={{ fontSize: 11, color: COLORS.textSecondary, textTransform: "uppercase", letterSpacing: 1 }}>
            Connect as
          </label>
          <div style={{ display: "flex", gap: 8, marginTop: 8, marginBottom: 20 }}>
            {["jimmy", "claude_ai"].map((role) => {
              const meta = ROLE_META[role];
              const selected = myRole === role;
              return (
                <button
                  key={role}
                  onClick={() => setMyRole(role)}
                  style={{
                    flex: 1, padding: "10px 0",
                    background: selected ? `${meta.color}22` : COLORS.bg,
                    border: `1px solid ${selected ? meta.color : COLORS.border}`,
                    borderRadius: 8, cursor: "pointer",
                    color: selected ? meta.color : COLORS.textSecondary,
                    fontSize: 13, fontWeight: selected ? 600 : 400,
                    fontFamily: "inherit", transition: "all 0.15s ease",
                  }}
                >
                  {meta.icon} {meta.label}
                </button>
              );
            })}
          </div>

          {/* URL input */}
          <label style={{ fontSize: 11, color: COLORS.textSecondary, textTransform: "uppercase", letterSpacing: 1 }}>
            VPS Tailscale IP
          </label>
          <input
            type="text"
            value={wsUrl}
            onChange={(e) => setWsUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSetup()}
            placeholder="100.x.y.z:8765"
            style={{
              width: "100%", padding: "12px 14px", marginTop: 8,
              background: COLORS.bg, border: `1px solid ${COLORS.border}`,
              borderRadius: 8, color: COLORS.textPrimary, fontSize: 14,
              fontFamily: "inherit", outline: "none", boxSizing: "border-box",
            }}
          />
          <button
            onClick={handleSetup}
            style={{
              width: "100%", marginTop: 16, padding: "12px 0",
              background: ROLE_META[myRole].color, color: "#fff",
              border: "none", borderRadius: 8, fontSize: 14,
              fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
            }}
          >
            Connect as {ROLE_META[myRole].label}
          </button>

          <div style={{
            marginTop: 24, padding: 16, background: COLORS.bg,
            borderRadius: 8, border: `1px solid ${COLORS.border}`,
          }}>
            <div style={{ fontSize: 11, color: COLORS.textDim, marginBottom: 8, textTransform: "uppercase", letterSpacing: 1 }}>
              On VPS
            </div>
            <code style={{ fontSize: 12, color: COLORS.textSecondary, lineHeight: 1.8, display: "block" }}>
              python3 zerorelay.py --host TAILSCALE_IP &<br />
              python3 zerobridge.py --relay ws://TAILSCALE_IP:8765
            </code>
          </div>
        </div>
      </div>
    );
  }

  // --- CHAT SCREEN ---
  const statusInfo = STATUS_META[status] || STATUS_META.disconnected;
  const allRoles = Object.keys(ROLE_META).filter((r) => r !== myRole);

  return (
    <div style={{
      background: COLORS.bg, height: "100vh", display: "flex",
      flexDirection: "column",
      fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
      color: COLORS.textPrimary,
    }}>
      {/* Header */}
      <div style={{
        padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 15, fontWeight: 600 }}>ZeroRelay</span>
          <span style={{
            fontSize: 10, padding: "2px 8px", borderRadius: 4,
            background: `${ROLE_META[myRole].color}22`,
            color: ROLE_META[myRole].color, fontWeight: 600,
          }}>
            {ROLE_META[myRole].label}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {allRoles.map((role) => {
            const meta = ROLE_META[role];
            const online = peersOnline.includes(role);
            return (
              <div key={role} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <div style={{
                  width: 6, height: 6, borderRadius: "50%",
                  background: online ? meta.color : COLORS.textDim,
                }} />
                <span style={{ fontSize: 10, color: online ? COLORS.textSecondary : COLORS.textDim }}>
                  {meta.label}
                </span>
              </div>
            );
          })}
          <div style={{
            width: 1, height: 14, background: COLORS.border, margin: "0 2px",
          }} />
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: statusInfo.color }} />
            <span style={{ fontSize: 10, color: COLORS.textSecondary }}>{statusInfo.label}</span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
        {messages.length === 0 && (
          <div style={{ textAlign: "center", padding: "60px 20px", color: COLORS.textDim }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>⚡</div>
            <div style={{ fontSize: 13 }}>Three-way relay active</div>
            <div style={{ fontSize: 11, marginTop: 4 }}>
              You + Claude.ai + Z (Claude Code) — all in one chat
            </div>
          </div>
        )}

        {messages.map((msg, i) => {
          if (msg.type === "system") {
            return (
              <div key={i} style={{
                textAlign: "center", padding: "8px 0", fontSize: 11, color: COLORS.textDim,
              }}>
                — {msg.content || msg.message} —
              </div>
            );
          }

          const isMe = msg.from === myRole;
          const meta = ROLE_META[msg.from] || { label: msg.from, color: COLORS.textSecondary, icon: "?" };

          return (
            <div key={i} style={{
              marginBottom: 16, display: "flex", flexDirection: "column",
              alignItems: isMe ? "flex-end" : "flex-start",
            }}>
              <div style={{
                fontSize: 10, color: COLORS.textDim, marginBottom: 4,
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <span style={{
                  color: meta.color, fontWeight: 600,
                  textTransform: "uppercase", letterSpacing: 1,
                }}>
                  {meta.icon} {meta.label}
                </span>
                <span>{formatTime(msg.timestamp)}</span>
              </div>
              <div style={{
                background: isMe ? `${meta.color}11` : COLORS.surface,
                border: `1px solid ${isMe ? `${meta.color}33` : COLORS.border}`,
                borderRadius: 10, padding: "10px 14px",
                maxWidth: "85%", fontSize: 13, lineHeight: 1.6,
                color: COLORS.textPrimary, whiteSpace: "pre-wrap", wordBreak: "break-word",
              }}>
                {msg.content}
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: "12px 20px", borderTop: `1px solid ${COLORS.border}`,
        display: "flex", gap: 10, flexShrink: 0,
      }}>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={`Message as ${ROLE_META[myRole].label}...`}
          style={{
            flex: 1, padding: "10px 14px",
            background: COLORS.surface, border: `1px solid ${COLORS.border}`,
            borderRadius: 8, color: COLORS.textPrimary,
            fontSize: 13, fontFamily: "inherit", outline: "none",
          }}
        />
        <button
          onClick={send}
          disabled={!input.trim() || status === "disconnected"}
          style={{
            padding: "10px 20px",
            background: input.trim() && status !== "disconnected"
              ? ROLE_META[myRole].color : COLORS.border,
            color: input.trim() && status !== "disconnected" ? "#fff" : COLORS.textDim,
            border: "none", borderRadius: 8, fontSize: 13,
            fontWeight: 600, fontFamily: "inherit",
            cursor: input.trim() && status !== "disconnected" ? "pointer" : "default",
          }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
