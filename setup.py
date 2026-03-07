#!/usr/bin/env python3
"""
ZeroRelay Setup — Interactive installer.

One script to configure, install dependencies, and deploy ZeroRelay
as systemd services on your server.

Usage:
  python3 setup.py           # Interactive setup
  python3 setup.py --check   # Verify existing install
"""

import os, sys, subprocess, shutil, uuid, platform
from pathlib import Path

BOLD = "\033[1m"; DIM = "\033[2m"; GREEN = "\033[32m"
YELLOW = "\033[33m"; RED = "\033[31m"; CYAN = "\033[36m"; RESET = "\033[0m"

def p(t, c=""): print(f"{c}{t}{RESET}")
def ok(t): p(f"  ✓ {t}", GREEN)
def warn(t): p(f"  ! {t}", YELLOW)
def err(t): p(f"  ✗ {t}", RED)
def header(t): p(f"\n{BOLD}{t}{RESET}")
def dim(t): p(f"  {t}", DIM)
def ask(prompt, default=""):
    s = f" [{default}]" if default else ""
    v = input(f"  {prompt}{s}: ").strip()
    return v or default

SCRIPT_DIR = Path(__file__).parent.resolve()
INSTALL_DIR = Path("/opt/zerorelay")
IS_ROOT = os.geteuid() == 0

def check_cmd(c): return shutil.which(c) is not None

def detect_tailscale():
    try:
        r = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip().split("\n")[0] if r.returncode == 0 else None
    except Exception: return None

def get_python_version():
    return sys.version_info

def preflight():
    """Step 0: Validate environment before proceeding."""
    header("Preflight Check")
    issues = 0; warnings = 0

    # Python version
    v = get_python_version()
    if v >= (3, 12):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    elif v >= (3, 10):
        warn(f"Python {v.major}.{v.minor} — works but 3.12+ recommended")
        warnings += 1
    else:
        err(f"Python {v.major}.{v.minor} — need 3.12+")
        issues += 1

    # pip
    if check_cmd("pip") or check_cmd("pip3"):
        ok("pip available")
    else:
        err("pip not found — install with: sudo apt install python3-pip")
        issues += 1

    # OS
    if platform.system() == "Linux":
        ok(f"Linux ({platform.release()[:20]})")
    elif platform.system() == "Darwin":
        warn("macOS — systemd not available, CLI/manual mode only")
        warnings += 1
    else:
        warn(f"{platform.system()} — systemd not available")
        warnings += 1

    # systemd (for service install)
    if check_cmd("systemctl"):
        ok("systemd available")
    else:
        warn("systemd not found — services won't auto-start")
        warnings += 1

    # Root check
    if IS_ROOT:
        ok("Running as root — can install systemd services")
    else:
        warn("Not root — systemd install unavailable (run with sudo for full install)")
        warnings += 1

    # git
    if check_cmd("git"):
        ok("git available")
    else:
        warn("git not found — not required but useful")
        warnings += 1

    # Tailscale
    ts = detect_tailscale()
    if ts:
        ok(f"Tailscale active ({ts})")
    else:
        dim("Tailscale not detected — relay will use public/localhost binding")

    # Source files present
    core = SCRIPT_DIR / "core" / "zerorelay.py"
    if core.exists():
        ok("ZeroRelay source files found")
    else:
        err(f"core/zerorelay.py not found in {SCRIPT_DIR}")
        err("Are you running setup.py from the ZeroRelay directory?")
        issues += 1

    # Check for common AI tools
    extras = []
    if check_cmd("claude"): extras.append("Claude Code CLI")
    if check_cmd("ollama"): extras.append("Ollama")
    if check_cmd("docker"): extras.append("Docker")
    if extras:
        dim(f"Also detected: {', '.join(extras)}")

    # Summary
    if issues > 0:
        p(f"\n  {RED}{BOLD}{issues} issue(s) must be fixed before continuing.{RESET}")
        return False
    elif warnings > 0:
        p(f"\n  {YELLOW}{warnings} warning(s) — setup can continue but some features may be limited.{RESET}")
        cont = input(f"  {BOLD}Continue anyway? [Y/n]{RESET} ").strip().lower()
        return cont != "n"
    else:
        ok("All checks passed!")
        return True

def multi_select(title, options, defaults=None):
    selected = set(defaults or []); keys = list(options.keys())
    print(f"\n  {BOLD}{title}{RESET}")
    print(f"  {DIM}Enter numbers to toggle, 'a' all, 'n' none, Enter to confirm{RESET}")
    while True:
        for i, k in enumerate(keys):
            m = f"{GREEN}●{RESET}" if k in selected else f"{DIM}○{RESET}"
            print(f"    {m} {i+1}. {options[k]}")
        c = input("  > ").strip().lower()
        if c == "": break
        elif c == "a": selected = set(keys)
        elif c == "n": selected = set()
        else:
            for x in c.replace(",", " ").split():
                try:
                    idx = int(x) - 1
                    if 0 <= idx < len(keys):
                        k = keys[idx]
                        selected.symmetric_difference_update({k})
                except ValueError: pass
        print(f"\033[{len(keys)+1}A\033[J", end="")
    return [k for k in keys if k in selected]

def single_select(title, options):
    keys = list(options.keys())
    print(f"\n  {BOLD}{title}{RESET}")
    for i, k in enumerate(keys):
        print(f"    {i+1}. {options[k]}")
    while True:
        try:
            idx = int(input("  > ").strip()) - 1
            if 0 <= idx < len(keys): return keys[idx]
        except ValueError: pass
        print(f"  {DIM}Enter 1-{len(keys)}{RESET}")

AI_BACKENDS = {
    "anthropic_api": {"label": "Claude (Anthropic API)", "bridge": "bridges/ai/anthropic_api.py",
        "pip": ["anthropic"], "prompts": [("ANTHROPIC_API_KEY", "Anthropic API key", "")],
        "defaults": {"ANTHROPIC_MODEL": "claude-sonnet-4-20250514", "ANTHROPIC_TAGS": "@claude,@c", "ANTHROPIC_ROLE": "claude"},
        "service": "zerorelay-claude", "tags": "@claude @c"},
    "claude_code": {"label": "Claude Code CLI", "bridge": "bridges/ai/claude_code.py",
        "pip": [], "prompts": [],
        "defaults": {"CLAUDE_MODEL": "sonnet", "CLAUDE_TAGS": "@claude,@c", "CLAUDE_ROLE": "claude"},
        "service": "zerorelay-claude", "tags": "@claude @c", "requires": "claude"},
    "openai_api": {"label": "GPT (OpenAI API)", "bridge": "bridges/ai/openai_api.py",
        "pip": ["openai"], "prompts": [("OPENAI_API_KEY", "OpenAI API key", "")],
        "defaults": {"OPENAI_MODEL": "gpt-4o", "OPENAI_TAGS": "@gpt,@g", "OPENAI_ROLE": "gpt"},
        "service": "zerorelay-gpt", "tags": "@gpt @g"},
    "gemini_api": {"label": "Gemini (Google)", "bridge": "bridges/ai/gemini_api.py",
        "pip": ["google-genai"], "prompts": [("GOOGLE_API_KEY", "Google API key", "")],
        "defaults": {"GEMINI_MODEL": "gemini-2.5-flash", "GEMINI_TAGS": "@gemini,@gem", "GEMINI_ROLE": "gemini"},
        "service": "zerorelay-gemini", "tags": "@gemini @gem"},
    "ollama": {"label": "Ollama (local)", "bridge": "bridges/ai/ollama.py",
        "pip": [], "prompts": [("OLLAMA_MODEL", "Ollama model", "llama3.2")],
        "defaults": {"OLLAMA_HOST": "http://localhost:11434", "OLLAMA_TAGS": "@ollama,@local", "OLLAMA_ROLE": "ollama"},
        "service": "zerorelay-ollama", "tags": "@ollama @local", "requires": "ollama"},
    "openclaw": {"label": "OpenClaw (GPT via Docker)", "bridge": "bridges/ai/openclaw.py",
        "pip": [], "prompts": [("OPENCLAW_TOKEN", "OpenClaw gateway token", ""), ("OPENCLAW_CONTAINER", "Docker container", "openclaw-openclaw-gateway-1")],
        "defaults": {"OPENCLAW_AGENT_ID": "main", "OPENCLAW_SESSION": "agent:main:zerorelay", "OPENCLAW_GATEWAY": "ws://127.0.0.1:18789", "OPENCLAW_TAGS": "@z,@zee", "OPENCLAW_ROLE": "zee"},
        "service": "zerorelay-zee", "tags": "@z @zee", "requires": "docker"},
}

CHATS = {
    "telegram": {"label": "Telegram Bot", "bridge": "bridges/chat/telegram.py", "pip": ["httpx"],
        "prompts": [("TELEGRAM_BOT_TOKEN", "Bot token (@BotFather)", ""), ("TELEGRAM_CHAT_ID", "Chat ID (@userinfobot)", "")],
        "service": "zerorelay-telegram"},
    "discord": {"label": "Discord Bot", "bridge": "bridges/chat/discord.py", "pip": ["discord.py"],
        "prompts": [("DISCORD_BOT_TOKEN", "Discord bot token", ""), ("DISCORD_CHANNEL_ID", "Channel ID", "")],
        "service": "zerorelay-discord"},
    "slack": {"label": "Slack Bot", "bridge": "bridges/chat/slack.py", "pip": ["slack-bolt"],
        "prompts": [("SLACK_BOT_TOKEN", "Bot token (xoxb-)", ""), ("SLACK_APP_TOKEN", "App token (xapp-)", ""), ("SLACK_CHANNEL_ID", "Channel ID", "")],
        "service": "zerorelay-slack"},
    "cli": {"label": "Terminal CLI", "bridge": "bridges/chat/cli.py", "pip": [], "prompts": [], "service": None},
}

ICONS = {"claude": "🧠 Claude", "gpt": "🤖 GPT", "gemini": "💎 Gemini", "ollama": "🦙 Ollama", "zee": "⚡ Zee"}

def write_service(name, content):
    path = Path(f"/etc/systemd/system/{name}.service")
    path.write_text(content)
    ok(f"Created {path}")

def make_service(desc, exec_cmd, install_path, after="zerorelay.service"):
    return f"""[Unit]
Description=ZeroRelay {desc}
After={after}

[Service]
Type=simple
ExecStart={exec_cmd}
WorkingDirectory={install_path}
EnvironmentFile={install_path}/.env
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

def main():
    p(f"\n{BOLD}{'═'*50}", CYAN)
    p(f"  ZeroRelay Setup", BOLD)
    p(f"  Multi-agent AI relay chat", DIM)
    p(f"{'═'*50}{RESET}", CYAN)

    if "--check" in sys.argv:
        return check_install()

    # Step 0: Preflight
    if not preflight():
        p("\n  Fix the issues above and re-run setup.", DIM)
        return

    # Step 1: AI backends
    header("Step 1: Choose AI Backends")
    sel_ai = multi_select("Which AI models?", {k: v["label"] for k, v in AI_BACKENDS.items()}, ["anthropic_api"])
    if not sel_ai: err("Need at least one AI backend."); return
    for k in sel_ai:
        b = AI_BACKENDS[k]
        if b.get("requires") and not check_cmd(b["requires"]):
            warn(f"{b['label']} needs '{b['requires']}' — not found in PATH")
            cont = input(f"  {DIM}Continue without it? [Y/n]{RESET} ").strip().lower()
            if cont == "n":
                sel_ai.remove(k)
    if not sel_ai: err("No backends selected."); return

    # Step 2: Chat interface
    header("Step 2: Choose Chat Interface")
    sel_chat = single_select("How to chat?", {k: v["label"] for k, v in CHATS.items()})

    # Step 3: Network
    header("Step 3: Network")
    ts_ip = detect_tailscale()
    if ts_ip: ok(f"Tailscale: {ts_ip}")
    opts = {}
    if ts_ip: opts["ts"] = f"Tailscale ({ts_ip}) — recommended"
    opts["lo"] = "localhost — testing"; opts["all"] = "0.0.0.0 — needs firewall"
    bind = single_select("Bind relay to:", opts)
    host = ts_ip if bind == "ts" else ("127.0.0.1" if bind == "lo" else "0.0.0.0")
    port = ask("Port", "8765")
    url = f"ws://{host}:{port}"

    # Step 4: Credentials
    header("Step 4: Configuration")
    env = {"ZERORELAY_URL": url, "RELAY_TOKEN": str(uuid.uuid4())}
    dim(f"Auth token: {env['RELAY_TOKEN'][:8]}...")

    for k in sel_ai:
        b = AI_BACKENDS[k]; p(f"\n  {BOLD}{b['label']}{RESET}")
        for ek, pr, df in b.get("prompts", []):
            v = ask(pr, df)
            if v: env[ek] = v
        for dk, dv in b["defaults"].items(): env.setdefault(dk, dv)

    chat = CHATS[sel_chat]
    if chat["prompts"]:
        p(f"\n  {BOLD}{chat['label']}{RESET}")
        for ek, pr, df in chat["prompts"]:
            v = ask(pr, df)
            if v: env[ek] = v

    # Tag patterns + icons
    tp, ic = [], []
    for k in sel_ai:
        d = AI_BACKENDS[k]["defaults"]
        role = next((v for dk, v in d.items() if dk.endswith("_ROLE")), None)
        tags = next((v for dk, v in d.items() if dk.endswith("_TAGS")), None)
        if role and tags: tp.append(f"{role}:{tags}")
        if role and role in ICONS: ic.append(f"{role}={ICONS[role]}")
    if tp: env["TELEGRAM_TAG_PATTERNS"] = ";".join(tp)
    if ic: env["TELEGRAM_SENDER_ICONS"] = ",".join(ic)
    env["TELEGRAM_AI_SERVICES"] = ",".join(AI_BACKENDS[k]["service"] for k in sel_ai)

    # Step 5: Review
    header("Step 5: Review")
    p(f"  AI: {', '.join(AI_BACKENDS[k]['label'] for k in sel_ai)}")
    p(f"  Chat: {chat['label']}")
    p(f"  Relay: {url}")
    p(f"  Install: {INSTALL_DIR if IS_ROOT else SCRIPT_DIR}")
    if input(f"\n  {BOLD}Proceed? [Y/n]{RESET} ").strip().lower() == "n": return

    # Step 6: Install
    header("Step 6: Installing")
    pkgs = list(set(["websockets"] + sum([AI_BACKENDS[k].get("pip", []) for k in sel_ai], []) + chat.get("pip", [])))
    p(f"  pip install {' '.join(pkgs)}")
    r = subprocess.run([sys.executable, "-m", "pip", "install", *pkgs], capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", *pkgs], capture_output=True, text=True)
    ok("Dependencies installed") if r.returncode == 0 else warn("pip failed — install manually")

    idir = INSTALL_DIR if IS_ROOT else SCRIPT_DIR
    if IS_ROOT:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        for sub in ["core", "bridges/ai", "bridges/chat"]:
            src, dst = SCRIPT_DIR / sub, INSTALL_DIR / sub
            dst.mkdir(parents=True, exist_ok=True)
            if src.exists():
                for f in src.iterdir():
                    if f.is_file(): shutil.copy2(f, dst / f.name)
        ok(f"Files → {INSTALL_DIR}")

    env_path = idir / ".env"
    env_path.write_text("# ZeroRelay config — generated by setup.py\n" + "\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
    os.chmod(env_path, 0o600)
    ok(f"Config → {env_path}")

    # Step 7: systemd
    py = sys.executable; svcs = []
    if IS_ROOT and sel_chat != "cli" and check_cmd("systemctl"):
        header("Step 7: systemd services")
        write_service("zerorelay", make_service("Broker", f"{py} {idir}/core/zerorelay.py --host {host} --port {port}", idir, "network.target"))
        svcs.append("zerorelay")
        for k in sel_ai:
            b = AI_BACKENDS[k]
            write_service(b["service"], make_service(b["label"], f"{py} {idir}/{b['bridge']} --relay {url}", idir))
            svcs.append(b["service"])
        if chat["service"]:
            write_service(chat["service"], make_service(chat["label"], f"{py} {idir}/{chat['bridge']} --relay {url}", idir))
            svcs.append(chat["service"])
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        ok("systemd reloaded")
        if input(f"\n  {BOLD}Start now? [Y/n]{RESET} ").strip().lower() != "n":
            for s in svcs:
                r = subprocess.run(["systemctl", "enable", "--now", s], capture_output=True, text=True)
                ok(f"Started {s}") if r.returncode == 0 else err(f"Failed: {s}")
    elif sel_chat == "cli":
        header("Step 7: Launch commands")
        dim(f"python3 {idir}/core/zerorelay.py --host {host} --port {port} &")
        for k in sel_ai: dim(f"python3 {idir}/{AI_BACKENDS[k]['bridge']} --relay {url} &")
        dim(f"python3 {idir}/{chat['bridge']} --relay {url} --role operator")
    else:
        header("Step 7: Manual launch")
        if not IS_ROOT: warn("Not root — can't install systemd services")
        if not check_cmd("systemctl"): warn("systemd not available")
        dim("Start manually:")
        dim(f"  python3 {idir}/core/zerorelay.py --host {host} &")
        for k in sel_ai: dim(f"  python3 {idir}/{AI_BACKENDS[k]['bridge']} --relay {url} &")
        dim(f"  python3 {idir}/{chat['bridge']} --relay {url}")

    header("Setup Complete!")
    tags = " or ".join(f"{BOLD}{AI_BACKENDS[k]['tags']}{RESET}" for k in sel_ai)
    p(f"\n  Chat with: {tags} + your message")
    if sel_chat != "cli":
        p(f"  Check status: {BOLD}systemctl status zerorelay{RESET}")
        p(f"  Verify install: {BOLD}python3 setup.py --check{RESET}")
    p("")

def check_install():
    header("ZeroRelay Install Check")
    for d in ["core", "bridges/ai", "bridges/chat"]:
        path = INSTALL_DIR / d
        ok(f"{path}") if path.exists() else err(f"{path} missing")
    env = INSTALL_DIR / ".env"
    if env.exists():
        ok(f".env (perms: {oct(env.stat().st_mode)[-3:]})")
        # Check key env vars
        content = env.read_text()
        for key in ["ZERORELAY_URL", "RELAY_TOKEN"]:
            if key in content: ok(f"  {key} set")
            else: warn(f"  {key} missing")
    else:
        err(".env missing")

    # Check services
    header("Services")
    for pattern in ["zerorelay", "zerorelay-*"]:
        import glob
        for svc_file in sorted(glob.glob(f"/etc/systemd/system/{pattern}.service")):
            svc = Path(svc_file).stem
            r = subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True)
            st = r.stdout.strip()
            ok(f"{svc}: {st}") if st == "active" else warn(f"{svc}: {st}")

    # Python deps
    header("Dependencies")
    for pkg in ["websockets"]:
        try: __import__(pkg); ok(f"{pkg}")
        except ImportError: err(f"{pkg} — not installed")
    for pkg, mod in [("anthropic", "anthropic"), ("openai", "openai"), ("google-genai", "google.genai"),
                     ("httpx", "httpx"), ("discord.py", "discord"), ("slack-bolt", "slack_bolt")]:
        try: __import__(mod); dim(f"{pkg} installed")
        except ImportError: pass

    # Network
    header("Network")
    ts = detect_tailscale()
    ok(f"Tailscale: {ts}") if ts else dim("Tailscale: not detected")

    # Python
    v = get_python_version()
    ok(f"Python {v.major}.{v.minor}.{v.micro}") if v >= (3, 12) else warn(f"Python {v.major}.{v.minor}")
    p("")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: p("\n  Cancelled.", DIM); sys.exit(0)
