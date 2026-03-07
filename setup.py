#!/usr/bin/env python3
"""
ZeroRelay Setup - Interactive installer with multiple modes.

One script to configure, install dependencies, and deploy ZeroRelay
as systemd services on your server.

Usage:
  python3 setup.py              # Interactive setup
  python3 setup.py --auto       # Auto-detect and configure
  python3 setup.py --from-env   # Unattended (all config from env vars)
  python3 setup.py --upgrade    # Upgrade existing install
  python3 setup.py --uninstall  # Remove ZeroRelay
  python3 setup.py --check      # Verify existing install
"""

import os, sys, subprocess, shutil, uuid, platform, socket, time, json
from pathlib import Path

BOLD = "\033[1m"; DIM = "\033[2m"; GREEN = "\033[32m"
YELLOW = "\033[33m"; RED = "\033[31m"; CYAN = "\033[36m"; RESET = "\033[0m"

def p(t, c=""): print(f"{c}{t}{RESET}")
def ok(t): p(f"  \u2713 {t}", GREEN)
def warn(t): p(f"  ! {t}", YELLOW)
def err(t): p(f"  \u2717 {t}", RED)
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

# ---------------------------------------------------------------------------
# Virtual environment helpers
# ---------------------------------------------------------------------------

def venv_dir():
    """Return the venv path: /opt/zerorelay/venv when root, else repo-local."""
    if IS_ROOT:
        return INSTALL_DIR / "venv"
    return SCRIPT_DIR / "venv"

def venv_python():
    """Return the python binary inside the venv (or sys.executable as fallback)."""
    vd = venv_dir()
    py = vd / "bin" / "python3"
    if py.exists():
        return str(py)
    return sys.executable

def create_venv():
    """Create the virtualenv if it does not exist."""
    vd = venv_dir()
    if (vd / "bin" / "python3").exists():
        dim(f"venv already exists at {vd}")
        return True
    p(f"  Creating virtualenv at {vd} ...")
    r = subprocess.run([sys.executable, "-m", "venv", str(vd)], capture_output=True, text=True)
    if r.returncode != 0:
        err(f"Failed to create venv: {r.stderr.strip()}")
        return False
    ok(f"venv created at {vd}")
    return True

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight(auto=False):
    """Step 0: Validate environment before proceeding."""
    header("Preflight Check")
    issues = 0; warnings = 0

    v = get_python_version()
    if v >= (3, 12):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    elif v >= (3, 10):
        warn(f"Python {v.major}.{v.minor} - works but 3.12+ recommended")
        warnings += 1
    else:
        err(f"Python {v.major}.{v.minor} - need 3.12+")
        issues += 1

    if check_cmd("pip") or check_cmd("pip3"):
        ok("pip available")
    else:
        err("pip not found - install with: sudo apt install python3-pip")
        issues += 1

    if platform.system() == "Linux":
        ok(f"Linux ({platform.release()[:20]})")
    elif platform.system() == "Darwin":
        warn("macOS - systemd not available, CLI/manual mode only")
        warnings += 1
    else:
        warn(f"{platform.system()} - systemd not available")
        warnings += 1

    if check_cmd("systemctl"):
        ok("systemd available")
    else:
        warn("systemd not found - services won't auto-start")
        warnings += 1

    if IS_ROOT:
        ok("Running as root - can install systemd services")
    else:
        warn("Not root - systemd install unavailable (run with sudo for full install)")
        warnings += 1

    if check_cmd("git"):
        ok("git available")
    else:
        warn("git not found - not required but useful")
        warnings += 1

    ts = detect_tailscale()
    if ts:
        ok(f"Tailscale active ({ts})")
    else:
        dim("Tailscale not found - relay will use public/localhost binding")

    core = SCRIPT_DIR / "core" / "zerorelay.py"
    if core.exists():
        ok("ZeroRelay source files found")
    else:
        err(f"core/zerorelay.py not found in {SCRIPT_DIR}")
        err("Are you running setup.py from the ZeroRelay directory?")
        issues += 1

    extras = []
    if check_cmd("claude"): extras.append("Claude Code CLI")
    if check_cmd("ollama"): extras.append("Ollama")
    if check_cmd("docker"): extras.append("Docker")
    if extras:
        dim(f"Also found: {', '.join(extras)}")

    if issues > 0:
        p(f"\n  {RED}{BOLD}{issues} issue(s) must be fixed before continuing.{RESET}")
        return False
    elif warnings > 0:
        if auto:
            warn(f"{warnings} warning(s) - continuing in auto mode")
            return True
        p(f"\n  {YELLOW}{warnings} warning(s) - setup can continue but some features may be limited.{RESET}")
        cont = input(f"  {BOLD}Continue anyway? [Y/n]{RESET} ").strip().lower()
        return cont != "n"
    else:
        ok("All checks passed!")
        return True

# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------

def multi_select(title, options, defaults=None):
    selected = set(defaults or []); keys = list(options.keys())
    print(f"\n  {BOLD}{title}{RESET}")
    print(f"  {DIM}Enter numbers to toggle, 'a' all, 'n' none, Enter to confirm{RESET}")
    while True:
        for i, k in enumerate(keys):
            m = f"{GREEN}\u25cf{RESET}" if k in selected else f"{DIM}\u25cb{RESET}"
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

# ---------------------------------------------------------------------------
# Data: AI backends and chat interfaces
# ---------------------------------------------------------------------------

AI_BACKENDS = {
    "anthropic_api": {"label": "Claude (Anthropic API)", "bridge": "bridges/ai/anthropic_api.py",
        "pip": ["anthropic"], "prompts": [("ANTHROPIC_API_KEY", "Anthropic API key", "")],
        "defaults": {"ANTHROPIC_MODEL": "claude-sonnet-4-20250514", "ANTHROPIC_TAGS": "@claude,@c", "ANTHROPIC_ROLE": "claude"},
        "service": "zerorelay-claude", "tags": "@claude @c",
        "env_keys": ["ANTHROPIC_API_KEY"]},
    "claude_code": {"label": "Claude Code CLI", "bridge": "bridges/ai/claude_code.py",
        "pip": [], "prompts": [],
        "defaults": {"CLAUDE_MODEL": "sonnet", "CLAUDE_TAGS": "@claude,@c", "CLAUDE_ROLE": "claude"},
        "service": "zerorelay-claude", "tags": "@claude @c", "requires": "claude",
        "env_keys": []},
    "openai_api": {"label": "GPT (OpenAI API)", "bridge": "bridges/ai/openai_api.py",
        "pip": ["openai"], "prompts": [("OPENAI_API_KEY", "OpenAI API key", "")],
        "defaults": {"OPENAI_MODEL": "gpt-4o", "OPENAI_TAGS": "@gpt,@g", "OPENAI_ROLE": "gpt"},
        "service": "zerorelay-gpt", "tags": "@gpt @g",
        "env_keys": ["OPENAI_API_KEY"]},
    "gemini_api": {"label": "Gemini (Google)", "bridge": "bridges/ai/gemini_api.py",
        "pip": ["google-genai"], "prompts": [("GOOGLE_API_KEY", "Google API key", "")],
        "defaults": {"GEMINI_MODEL": "gemini-2.5-flash", "GEMINI_TAGS": "@gemini,@gem", "GEMINI_ROLE": "gemini"},
        "service": "zerorelay-gemini", "tags": "@gemini @gem",
        "env_keys": ["GOOGLE_API_KEY"]},
    "ollama": {"label": "Ollama (local)", "bridge": "bridges/ai/ollama.py",
        "pip": [], "prompts": [("OLLAMA_MODEL", "Ollama model", "llama3.2")],
        "defaults": {"OLLAMA_HOST": "http://localhost:11434", "OLLAMA_TAGS": "@ollama,@local", "OLLAMA_ROLE": "ollama"},
        "service": "zerorelay-ollama", "tags": "@ollama @local", "requires": "ollama",
        "env_keys": ["OLLAMA_MODEL"]},
    "openclaw": {"label": "OpenClaw (GPT via Docker)", "bridge": "bridges/ai/openclaw.py",
        "pip": [], "prompts": [("OPENCLAW_TOKEN", "OpenClaw gateway value", ""), ("OPENCLAW_CONTAINER", "Docker container", "openclaw-openclaw-gateway-1")],
        "defaults": {"OPENCLAW_AGENT_ID": "main", "OPENCLAW_SESSION": "agent:main:zerorelay", "OPENCLAW_GATEWAY": "ws://127.0.0.1:18789", "OPENCLAW_TAGS": "@z,@zee", "OPENCLAW_ROLE": "zee"},
        "service": "zerorelay-zee", "tags": "@z @zee", "requires": "docker",
        "env_keys": ["OPENCLAW_TOKEN"]},
}

CHATS = {
    "telegram": {"label": "Telegram Bot", "bridge": "bridges/chat/telegram.py", "pip": ["httpx"],
        "prompts": [("TELEGRAM_BOT_TOKEN", "Bot value (@BotFather)", ""), ("TELEGRAM_CHAT_ID", "Chat ID (@userinfobot)", "")],
        "service": "zerorelay-telegram",
        "env_keys": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]},
    "discord": {"label": "Discord Bot", "bridge": "bridges/chat/discord.py", "pip": ["discord.py"],
        "prompts": [("DISCORD_BOT_TOKEN", "Discord bot value", ""), ("DISCORD_CHANNEL_ID", "Channel ID", "")],
        "service": "zerorelay-discord",
        "env_keys": ["DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID"]},
    "slack": {"label": "Slack Bot", "bridge": "bridges/chat/slack.py", "pip": ["slack-bolt"],
        "prompts": [("SLACK_BOT_TOKEN", "Bot value (xoxb-)", ""), ("SLACK_APP_TOKEN", "App value (xapp-)", ""), ("SLACK_CHANNEL_ID", "Channel ID", "")],
        "service": "zerorelay-slack",
        "env_keys": ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_CHANNEL_ID"]},
    "cli": {"label": "Terminal CLI", "bridge": "bridges/chat/cli.py", "pip": [], "prompts": [], "service": None,
        "env_keys": []},
}

ICONS = {"claude": "\U0001f9e0 Claude", "gpt": "\U0001f916 GPT", "gemini": "\U0001f48e Gemini", "ollama": "\U0001f999 Ollama", "zee": "\u26a1 Zee"}

# ---------------------------------------------------------------------------
# Credential validation
# ---------------------------------------------------------------------------

def validate_anthropic(key):
    """Test Anthropic API key with a minimal request."""
    try:
        import anthropic
        c = anthropic.Anthropic(api_key=key)
        c.messages.create(model="claude-sonnet-4-20250514", max_tokens=1, messages=[{"role": "user", "content": "hi"}])
        return True
    except ImportError:
        dim("anthropic SDK not installed - skipping validation")
        return None
    except Exception as e:
        return str(e)

def validate_openai(key):
    """Test OpenAI API key."""
    try:
        import openai
        c = openai.OpenAI(api_key=key)
        c.models.list()
        return True
    except ImportError:
        dim("openai SDK not installed - skipping validation")
        return None
    except Exception as e:
        return str(e)

def validate_gemini(key):
    """Test Google Gemini API key."""
    try:
        from google import genai
        c = genai.Client(api_key=key)
        c.models.list()
        return True
    except ImportError:
        dim("google-genai SDK not installed - skipping validation")
        return None
    except Exception as e:
        return str(e)

def validate_ollama(model="llama3.2"):
    """Test Ollama connectivity and model availability."""
    if not check_cmd("ollama"):
        return "ollama not in PATH"
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return "ollama not running"
        return True
    except Exception as e:
        return str(e)

def validate_telegram(bot_tok):
    """Test Telegram bot validity via getMe API."""
    try:
        import httpx
        resp = httpx.get(f"https://api.telegram.org/bot{bot_tok}/getMe", timeout=10)
        data = resp.json()
        if data.get("ok"):
            return True
        return data.get("description", "invalid response")
    except ImportError:
        dim("httpx not installed - skipping Telegram validation")
        return None
    except Exception as e:
        return str(e)

def validate_credentials(env, sel_ai, sel_chats):
    """Validate all collected credentials. Warns on failure but does not block."""
    header("Validating Credentials")
    validators = {
        "ANTHROPIC_API_KEY": ("Anthropic API", validate_anthropic),
        "OPENAI_API_KEY": ("OpenAI API", validate_openai),
        "GOOGLE_API_KEY": ("Gemini API", validate_gemini),
    }
    for key_name, (label, fn) in validators.items():
        val = env.get(key_name)
        if not val:
            continue
        result = fn(val)
        if result is True:
            ok(f"{label} key valid")
        elif result is None:
            pass
        else:
            warn(f"{label}: {result}")

    if env.get("OLLAMA_MODEL"):
        result = validate_ollama(env["OLLAMA_MODEL"])
        if result is True:
            ok("Ollama reachable")
        elif result is None:
            pass
        else:
            warn(f"Ollama: {result}")

    for ck in sel_chats:
        if ck == "telegram" and env.get("TELEGRAM_BOT_TOKEN"):
            result = validate_telegram(env["TELEGRAM_BOT_TOKEN"])
            if result is True:
                ok("Telegram bot valid")
            elif result is None:
                pass
            else:
                warn(f"Telegram: {result}")

# ---------------------------------------------------------------------------
# Ollama model management
# ---------------------------------------------------------------------------

def ollama_check_model(model, auto=False):
    """Check if an Ollama model is available; offer to pull if missing."""
    if not check_cmd("ollama"):
        return
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            warn("Ollama not running - cannot check model")
            return
        if model in r.stdout:
            ok(f"Ollama model '{model}' available")
            return
        # Model not found
        if auto:
            p(f"  Pulling Ollama model '{model}' ...")
            subprocess.run(["ollama", "pull", model], timeout=600)
            return
        ans = input(f"  Model '{model}' not found. Pull it now? [Y/n] ").strip().lower()
        if ans != "n":
            subprocess.run(["ollama", "pull", model], timeout=600)
    except Exception as e:
        warn(f"Ollama model check failed: {e}")

# ---------------------------------------------------------------------------
# Sudoers for service management
# ---------------------------------------------------------------------------

def install_sudoers():
    """Create /etc/sudoers.d/zerorelay for service management."""
    if not IS_ROOT:
        return
    content = (
        "# Allow zerorelay user to manage its own services\n"
        "zerorelay ALL=(root) NOPASSWD: "
        "/usr/bin/systemctl stop zerorelay*, "
        "/usr/bin/systemctl start zerorelay*, "
        "/usr/bin/systemctl restart zerorelay*, "
        "/usr/bin/systemctl is-active zerorelay*\n"
    )
    path = Path("/etc/sudoers.d/zerorelay")
    path.write_text(content)
    os.chmod(path, 0o440)
    ok("Sudoers rules installed for zerorelay user")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def health_check(host, port, services):
    """Post-install: verify relay is listening and services are running."""
    header("Health Check")
    relay_ok = False
    p(f"  Waiting for relay on {host}:{port} ...")
    for attempt in range(15):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            check_host = "127.0.0.1" if host not in ("127.0.0.1", "0.0.0.0") else host
            if host == "0.0.0.0":
                check_host = "127.0.0.1"
            s.connect((check_host, int(port)))
            s.close()
            relay_ok = True
            break
        except (ConnectionRefusedError, OSError, socket.timeout):
            time.sleep(1)
        finally:
            try: s.close()
            except: pass

    if relay_ok:
        ok(f"Relay listening on port {port}")
    else:
        warn(f"Relay not responding on port {port} after 15s")

    running = 0; total = len(services)
    for svc in services:
        r = subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True)
        st = r.stdout.strip()
        if st == "active":
            ok(f"{svc}: active")
            running += 1
        else:
            warn(f"{svc}: {st}")

    if running == total:
        ok(f"All {total}/{total} services running")
    else:
        warn(f"{running}/{total} services running")
    return running == total

# ---------------------------------------------------------------------------
# Tag / icon builder
# ---------------------------------------------------------------------------

def build_tags(sel_ai, env):
    """Build tag patterns and icons for the env dict."""
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

# ---------------------------------------------------------------------------
# Service file helpers
# ---------------------------------------------------------------------------

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
User=zerorelay
Group=zerorelay
ExecStart={exec_cmd}
WorkingDirectory={install_path}
EnvironmentFile={install_path}/.env
Restart=on-failure
RestartSec=5
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
ReadWritePaths={install_path}

[Install]
WantedBy=multi-user.target
"""

# ---------------------------------------------------------------------------
# Shared install logic
# ---------------------------------------------------------------------------

def do_install(env, sel_ai, sel_chats, host, port, url, auto=False):
    """Core install logic shared by all modes."""
    header("Creating Virtual Environment")
    if not create_venv():
        err("Cannot proceed without a virtualenv")
        return False

    py = venv_python()

    header("Installing Dependencies")
    pkgs = list(set(
        ["websockets"]
        + sum([AI_BACKENDS[k].get("pip", []) for k in sel_ai], [])
        + sum([CHATS[c].get("pip", []) for c in sel_chats], [])
    ))
    p(f"  pip install {' '.join(pkgs)}")
    r = subprocess.run([py, "-m", "pip", "install", *pkgs], capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run([py, "-m", "pip", "install", "--break-system-packages", *pkgs], capture_output=True, text=True)
    ok("Dependencies installed") if r.returncode == 0 else warn("pip had issues - install manually")

    validate_credentials(env, sel_ai, sel_chats)

    if "ollama" in sel_ai and env.get("OLLAMA_MODEL"):
        ollama_check_model(env["OLLAMA_MODEL"], auto=auto)

    idir = INSTALL_DIR if IS_ROOT else SCRIPT_DIR
    if IS_ROOT:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        for sub in ["core", "bridges/ai", "bridges/chat"]:
            src, dst = SCRIPT_DIR / sub, INSTALL_DIR / sub
            dst.mkdir(parents=True, exist_ok=True)
            if src.exists():
                for f in src.iterdir():
                    if f.is_file(): shutil.copy2(f, dst / f.name)
        ok(f"Files -> {INSTALL_DIR}")

    env_path = idir / ".env"
    env_path.write_text("# ZeroRelay config - generated by setup.py\n" + "\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
    os.chmod(env_path, 0o600)
    ok(f"Config -> {env_path}")

    svcs = []
    has_service_chat = any(CHATS[c]["service"] is not None for c in sel_chats)
    all_cli = all(c == "cli" for c in sel_chats)

    if IS_ROOT and has_service_chat and check_cmd("systemctl"):
        header("systemd Services")
        r = subprocess.run(["id", "zerorelay"], capture_output=True)
        if r.returncode != 0:
            subprocess.run(["useradd", "-r", "-s", "/usr/sbin/nologin", "-d", str(idir), "zerorelay"], capture_output=True)
            ok("Created zerorelay service user")
        else:
            dim("zerorelay user already exists")

        if any(AI_BACKENDS[k].get("requires") == "docker" for k in sel_ai):
            subprocess.run(["usermod", "-aG", "docker", "zerorelay"], capture_output=True)
            dim("Added zerorelay to docker group")

        subprocess.run(["chown", "-R", "zerorelay:zerorelay", str(idir)], capture_output=True)
        subprocess.run(["chmod", "700", str(idir)], capture_output=True)
        subprocess.run(["chmod", "600", str(env_path)], capture_output=True)
        ok("Ownership -> zerorelay:zerorelay")

        install_sudoers()

        write_service("zerorelay", make_service("Broker", f"{py} {idir}/core/zerorelay.py --host {host} --port {port}", idir, "network.target"))
        svcs.append("zerorelay")

        for k in sel_ai:
            b = AI_BACKENDS[k]
            write_service(b["service"], make_service(b["label"], f"{py} {idir}/{b['bridge']} --relay {url}", idir))
            svcs.append(b["service"])

        for c in sel_chats:
            ch = CHATS[c]
            if ch["service"]:
                write_service(ch["service"], make_service(ch["label"], f"{py} {idir}/{ch['bridge']} --relay {url}", idir))
                svcs.append(ch["service"])

        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        ok("systemd reloaded")

        if auto or input(f"\n  {BOLD}Start now? [Y/n]{RESET} ").strip().lower() != "n":
            for s in svcs:
                r = subprocess.run(["systemctl", "enable", "--now", s], capture_output=True, text=True)
                ok(f"Started {s}") if r.returncode == 0 else err(f"Failed: {s}")
            health_check(host, port, svcs)

    elif all_cli:
        header("Launch Commands")
        dim(f"python3 {idir}/core/zerorelay.py --host {host} --port {port} &")
        for k in sel_ai: dim(f"python3 {idir}/{AI_BACKENDS[k]['bridge']} --relay {url} &")
        for c in sel_chats:
            dim(f"python3 {idir}/{CHATS[c]['bridge']} --relay {url} --role operator")
    else:
        header("Manual Launch")
        if not IS_ROOT: warn("Not root - systemd services unavailable")
        if not check_cmd("systemctl"): warn("systemd not available")
        dim("Start manually:")
        dim(f"  python3 {idir}/core/zerorelay.py --host {host} --port {port} &")
        for k in sel_ai: dim(f"  python3 {idir}/{AI_BACKENDS[k]['bridge']} --relay {url} &")
        for c in sel_chats:
            dim(f"  python3 {idir}/{CHATS[c]['bridge']} --relay {url}")

    return True

# ---------------------------------------------------------------------------
# Env collection: interactive, auto, from-env
# ---------------------------------------------------------------------------

def collect_env_interactive():
    """Full interactive mode (original flow)."""
    header("Step 1: Choose AI Backends")
    sel_ai = multi_select("Which AI models?", {k: v["label"] for k, v in AI_BACKENDS.items()}, ["anthropic_api"])
    if not sel_ai: err("Need at least one AI backend."); return None
    for k in list(sel_ai):
        b = AI_BACKENDS[k]
        if b.get("requires") and not check_cmd(b["requires"]):
            req = b["requires"]
            warn(f"{b['label']} needs '{req}' - not found in PATH")
            cont = input(f"  {DIM}Continue without it? [Y/n]{RESET} ").strip().lower()
            if cont == "n":
                sel_ai.remove(k)
    if not sel_ai: err("No backends selected."); return None

    header("Step 2: Choose Chat Interfaces")
    sel_chats = multi_select("Which chat interfaces?", {k: v["label"] for k, v in CHATS.items()}, ["telegram"])
    if not sel_chats: err("Need at least one chat interface."); return None

    header("Step 3: Network")
    ts_ip = detect_tailscale()
    if ts_ip: ok(f"Tailscale: {ts_ip}")
    opts = {}
    if ts_ip: opts["ts"] = f"Tailscale ({ts_ip}) - recommended"
    opts["lo"] = "localhost - testing"; opts["all"] = "0.0.0.0 - needs firewall"
    bind = single_select("Bind relay to:", opts)
    host = ts_ip if bind == "ts" else ("127.0.0.1" if bind == "lo" else "0.0.0.0")
    port = ask("Port", "8765")
    url = f"ws://{host}:{port}"

    header("Step 4: Configuration")
    env = {"ZERORELAY_URL": url, "RELAY_TOKEN": str(uuid.uuid4())}
    dim(f"Auth: {env['RELAY_TOKEN'][:8]}...")

    for k in sel_ai:
        b = AI_BACKENDS[k]; p(f"\n  {BOLD}{b['label']}{RESET}")
        for ek, pr, df in b.get("prompts", []):
            v = ask(pr, df)
            if v: env[ek] = v
        for dk, dv in b["defaults"].items(): env.setdefault(dk, dv)

    for c in sel_chats:
        ch = CHATS[c]
        if ch["prompts"]:
            p(f"\n  {BOLD}{ch['label']}{RESET}")
            for ek, pr, df in ch["prompts"]:
                v = ask(pr, df)
                if v: env[ek] = v

    build_tags(sel_ai, env)

    header("Step 5: Review")
    p(f"  AI: {', '.join(AI_BACKENDS[k]['label'] for k in sel_ai)}")
    p(f"  Chat: {', '.join(CHATS[c]['label'] for c in sel_chats)}")
    p(f"  Relay: {url}")
    p(f"  Install: {INSTALL_DIR if IS_ROOT else SCRIPT_DIR}")
    if input(f"\n  {BOLD}Proceed? [Y/n]{RESET} ").strip().lower() == "n": return None

    return {"env": env, "sel_ai": sel_ai, "sel_chats": sel_chats, "host": host, "port": port, "url": url}

def collect_env_auto():
    """Auto-detect available tools and configure with minimal prompts."""
    header("Auto-Detect Mode")
    sel_ai = []
    env = {}

    for key, backend in AI_BACKENDS.items():
        req = backend.get("requires")
        if req and not check_cmd(req):
            continue
        env_keys = backend.get("env_keys", [])
        if env_keys:
            has_key = all(os.environ.get(ek) for ek in env_keys)
            if has_key:
                sel_ai.append(key)
                for ek in env_keys:
                    env[ek] = os.environ[ek]
                ok(f"Found: {backend['label']}")
            else:
                dim(f"Skipping {backend['label']} (no API key in env)")
        else:
            sel_ai.append(key)
            ok(f"Found: {backend['label']}")

    if not sel_ai:
        err("No AI backends available. Set API keys in environment or install tools.")
        return None

    for k in sel_ai:
        for dk, dv in AI_BACKENDS[k]["defaults"].items():
            env.setdefault(dk, dv)
        for ek, pr, df in AI_BACKENDS[k].get("prompts", []):
            if ek not in env and df:
                env[ek] = df

    sel_chats = []
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        sel_chats.append("telegram")
        env["TELEGRAM_BOT_TOKEN"] = os.environ["TELEGRAM_BOT_TOKEN"]
        env["TELEGRAM_CHAT_ID"] = os.environ["TELEGRAM_CHAT_ID"]
        ok("Found: Telegram bot credentials")
    if os.environ.get("DISCORD_BOT_TOKEN"):
        sel_chats.append("discord")
        env["DISCORD_BOT_TOKEN"] = os.environ["DISCORD_BOT_TOKEN"]
        env["DISCORD_CHANNEL_ID"] = os.environ.get("DISCORD_CHANNEL_ID", "")
    if not sel_chats:
        sel_chats.append("cli")
        dim("No chat bot credentials found - using CLI")

    ts_ip = detect_tailscale()
    host = ts_ip if ts_ip else "127.0.0.1"
    port = os.environ.get("ZERORELAY_PORT", "8765")
    url = f"ws://{host}:{port}"

    env["ZERORELAY_URL"] = url
    env["RELAY_TOKEN"] = os.environ.get("RELAY_TOKEN", str(uuid.uuid4()))

    build_tags(sel_ai, env)

    for k in sel_ai:
        for ek, pr, df in AI_BACKENDS[k].get("prompts", []):
            if ek not in env and not df:
                env[ek] = ask(f"[needed] {pr}", df)

    header("Auto Config Summary")
    p(f"  AI: {', '.join(AI_BACKENDS[k]['label'] for k in sel_ai)}")
    p(f"  Chat: {', '.join(CHATS[c]['label'] for c in sel_chats)}")
    p(f"  Relay: {url}")

    return {"env": env, "sel_ai": sel_ai, "sel_chats": sel_chats, "host": host, "port": port, "url": url}

def collect_env_from_env():
    """Fully unattended mode: all config from environment variables."""
    header("Unattended Mode (--from-env)")
    env = {}
    errors = []

    for req in ["RELAY_TOKEN", "ZERORELAY_URL"]:
        val = os.environ.get(req)
        if not val:
            if req == "RELAY_TOKEN":
                env[req] = str(uuid.uuid4())
                dim(f"Generated {req}")
            else:
                errors.append(req)
        else:
            env[req] = val

    url = env.get("ZERORELAY_URL", os.environ.get("ZERORELAY_URL", "ws://127.0.0.1:8765"))
    env["ZERORELAY_URL"] = url
    hp = url.replace("ws://", "").replace("wss://", "")
    host = hp.rsplit(":", 1)[0] if ":" in hp else hp
    port = hp.rsplit(":", 1)[1] if ":" in hp else "8765"

    sel_ai = []
    ai_list = os.environ.get("ZERORELAY_BACKENDS", "").split(",")
    if ai_list and ai_list[0]:
        for name in ai_list:
            name = name.strip()
            if name in AI_BACKENDS:
                sel_ai.append(name)
    else:
        for key, backend in AI_BACKENDS.items():
            env_keys = backend.get("env_keys", [])
            if env_keys and all(os.environ.get(ek) for ek in env_keys):
                sel_ai.append(key)
            elif not env_keys and backend.get("requires") and check_cmd(backend["requires"]):
                sel_ai.append(key)

    if not sel_ai:
        errors.append("ZERORELAY_BACKENDS (or set API keys in env)")

    sel_chats = []
    chat_list = os.environ.get("ZERORELAY_CHATS", "").split(",")
    if chat_list and chat_list[0]:
        for name in chat_list:
            name = name.strip()
            if name in CHATS:
                sel_chats.append(name)
    else:
        if os.environ.get("TELEGRAM_BOT_TOKEN"):
            sel_chats.append("telegram")
        if os.environ.get("DISCORD_BOT_TOKEN"):
            sel_chats.append("discord")
        if not sel_chats:
            sel_chats.append("cli")

    if errors:
        for e in errors:
            err(f"Missing required env var: {e}")
        return None

    for k in sel_ai:
        b = AI_BACKENDS[k]
        for ek, pr, df in b.get("prompts", []):
            val = os.environ.get(ek, df)
            if val: env[ek] = val
        for dk, dv in b["defaults"].items():
            env.setdefault(dk, os.environ.get(dk, dv))

    for c in sel_chats:
        ch = CHATS[c]
        for ek, pr, df in ch["prompts"]:
            val = os.environ.get(ek, df)
            if val:
                env[ek] = val
            else:
                err(f"Missing env var: {ek} (needed for {ch['label']})")
                return None

    build_tags(sel_ai, env)

    ok(f"AI: {', '.join(AI_BACKENDS[k]['label'] for k in sel_ai)}")
    ok(f"Chat: {', '.join(CHATS[c]['label'] for c in sel_chats)}")

    return {"env": env, "sel_ai": sel_ai, "sel_chats": sel_chats, "host": host, "port": port, "url": url}

# ---------------------------------------------------------------------------
# Mode: upgrade
# ---------------------------------------------------------------------------

def main_upgrade():
    """Upgrade existing install: pull, copy, install deps, restart."""
    header("Upgrade Mode")

    if not INSTALL_DIR.exists():
        err(f"{INSTALL_DIR} not found - nothing to upgrade")
        return

    if (SCRIPT_DIR / ".git").exists():
        p("  Pulling latest source ...")
        r = subprocess.run(["git", "pull"], cwd=str(SCRIPT_DIR), capture_output=True, text=True)
        if r.returncode == 0:
            ok("Source updated")
        else:
            warn(f"git pull issue: {r.stderr.strip()}")

    if IS_ROOT:
        for sub in ["core", "bridges/ai", "bridges/chat"]:
            src, dst = SCRIPT_DIR / sub, INSTALL_DIR / sub
            dst.mkdir(parents=True, exist_ok=True)
            if src.exists():
                for f in src.iterdir():
                    if f.is_file(): shutil.copy2(f, dst / f.name)
        ok(f"Files updated in {INSTALL_DIR}")

    if not create_venv():
        warn("venv creation failed - trying existing python")
    py = venv_python()

    env_path = INSTALL_DIR / ".env"
    if env_path.exists():
        dim("Existing config preserved (not re-prompting)")
    else:
        warn("No .env found - config unchanged")

    all_pkgs = set(["websockets"])
    for b in AI_BACKENDS.values():
        all_pkgs.update(b.get("pip", []))
    for c in CHATS.values():
        all_pkgs.update(c.get("pip", []))
    pkgs = [pkg for pkg in all_pkgs if pkg]
    if pkgs:
        p(f"  pip install {' '.join(pkgs)}")
        subprocess.run([py, "-m", "pip", "install", "--upgrade", *pkgs], capture_output=True, text=True)
        ok("Dependencies updated")

    if IS_ROOT and check_cmd("systemctl"):
        header("Restarting Services")
        import glob
        svcs = []
        for svc_file in sorted(glob.glob("/etc/systemd/system/zerorelay*.service")):
            svcs.append(Path(svc_file).stem)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        for svc in svcs:
            r = subprocess.run(["systemctl", "restart", svc], capture_output=True, text=True)
            ok(f"Restarted {svc}") if r.returncode == 0 else warn(f"Failed to restart {svc}: {r.stderr.strip()}")

        if svcs:
            h, pt = "127.0.0.1", "8765"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("ZERORELAY_URL="):
                        u = line.split("=", 1)[1].replace("ws://", "").replace("wss://", "")
                        if ":" in u:
                            h = u.rsplit(":", 1)[0]
                            pt = u.rsplit(":", 1)[1]
            health_check(h, pt, svcs)
    else:
        ok("Upgrade complete (no systemd - restart services manually)")

# ---------------------------------------------------------------------------
# Mode: uninstall
# ---------------------------------------------------------------------------

def main_uninstall():
    """Remove ZeroRelay: stop services, remove files."""
    header("Uninstall ZeroRelay")

    if not IS_ROOT:
        err("Uninstall requires root")
        return

    ans = input(f"  {RED}{BOLD}This will remove ZeroRelay. Continue? [y/N]{RESET} ").strip().lower()
    if ans != "y":
        dim("Cancelled.")
        return

    if check_cmd("systemctl"):
        import glob
        for svc_file in sorted(glob.glob("/etc/systemd/system/zerorelay*.service")):
            svc = Path(svc_file).stem
            subprocess.run(["systemctl", "stop", svc], capture_output=True)
            subprocess.run(["systemctl", "disable", svc], capture_output=True)
            ok(f"Stopped and disabled {svc}")
            Path(svc_file).unlink()
            ok(f"Removed {svc_file}")
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        ok("systemd reloaded")

    sudoers = Path("/etc/sudoers.d/zerorelay")
    if sudoers.exists():
        sudoers.unlink()
        ok("Removed sudoers rules")

    if INSTALL_DIR.exists():
        ans = input(f"  Remove {INSTALL_DIR}? [y/N] ").strip().lower()
        if ans == "y":
            shutil.rmtree(INSTALL_DIR)
            ok(f"Removed {INSTALL_DIR}")
        else:
            dim(f"Kept {INSTALL_DIR}")

    r = subprocess.run(["id", "zerorelay"], capture_output=True)
    if r.returncode == 0:
        ans = input("  Remove zerorelay user? [y/N] ").strip().lower()
        if ans == "y":
            subprocess.run(["userdel", "zerorelay"], capture_output=True)
            ok("Removed zerorelay user")
        else:
            dim("Kept zerorelay user")

    ok("Uninstall complete")

# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def main():
    p(f"\n{BOLD}{'='*50}", CYAN)
    p(f"  ZeroRelay Setup", BOLD)
    p(f"  Multi-agent AI relay chat", DIM)
    p(f"{'='*50}{RESET}", CYAN)

    if "--check" in sys.argv:
        return check_install()
    if "--upgrade" in sys.argv:
        return main_upgrade()
    if "--uninstall" in sys.argv:
        return main_uninstall()

    auto_mode = "--auto" in sys.argv
    from_env_mode = "--from-env" in sys.argv

    if not preflight(auto=auto_mode or from_env_mode):
        p("\n  Fix the issues above and re-run setup.", DIM)
        return

    if from_env_mode:
        cfg = collect_env_from_env()
    elif auto_mode:
        cfg = collect_env_auto()
    else:
        cfg = collect_env_interactive()

    if cfg is None:
        return

    header("Installing")
    success = do_install(
        env=cfg["env"],
        sel_ai=cfg["sel_ai"],
        sel_chats=cfg["sel_chats"],
        host=cfg["host"],
        port=cfg["port"],
        url=cfg["url"],
        auto=auto_mode or from_env_mode,
    )

    if success:
        header("Setup Complete!")
        tags = " or ".join(f"{BOLD}{AI_BACKENDS[k]['tags']}{RESET}" for k in cfg["sel_ai"])
        p(f"\n  Chat with: {tags} + your message")
        all_cli = all(c == "cli" for c in cfg["sel_chats"])
        if not all_cli:
            p(f"  Check status: {BOLD}systemctl status zerorelay{RESET}")
            p(f"  Verify install: {BOLD}python3 setup.py --check{RESET}")
        p("")

# ---------------------------------------------------------------------------
# Check install
# ---------------------------------------------------------------------------

def check_install():
    header("ZeroRelay Install Check")
    for d in ["core", "bridges/ai", "bridges/chat"]:
        path = INSTALL_DIR / d
        ok(f"{path}") if path.exists() else err(f"{path} missing")

    vd = venv_dir()
    if (vd / "bin" / "python3").exists():
        ok(f"venv: {vd}")
    else:
        warn(f"venv not found at {vd}")

    env = INSTALL_DIR / ".env"
    if env.exists():
        ok(f".env (perms: {oct(env.stat().st_mode)[-3:]})")
        content = env.read_text()
        for key in ["ZERORELAY_URL", "RELAY_TOKEN"]:
            if key in content: ok(f"  {key} set")
            else: warn(f"  {key} missing")
    else:
        err(".env missing")

    sudoers = Path("/etc/sudoers.d/zerorelay")
    if sudoers.exists():
        ok("Sudoers rules installed")
    else:
        dim("No sudoers rules (optional)")

    header("Services")
    import glob
    for pattern in ["zerorelay", "zerorelay-*"]:
        for svc_file in sorted(glob.glob(f"/etc/systemd/system/{pattern}.service")):
            svc = Path(svc_file).stem
            r = subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True)
            st = r.stdout.strip()
            ok(f"{svc}: {st}") if st == "active" else warn(f"{svc}: {st}")

    header("Dependencies")
    py = venv_python()
    for pkg in ["websockets"]:
        try: __import__(pkg); ok(f"{pkg}")
        except ImportError: err(f"{pkg} - not installed")
    for pkg, mod in [("anthropic", "anthropic"), ("openai", "openai"), ("google-genai", "google.genai"),
                     ("httpx", "httpx"), ("discord.py", "discord"), ("slack-bolt", "slack_bolt")]:
        try: __import__(mod); dim(f"{pkg} installed")
        except ImportError: pass

    header("Network")
    ts = detect_tailscale()
    ok(f"Tailscale: {ts}") if ts else dim("Tailscale: not found")

    v = get_python_version()
    ok(f"Python {v.major}.{v.minor}.{v.micro}") if v >= (3, 12) else warn(f"Python {v.major}.{v.minor}")
    p("")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: p("\n  Cancelled.", DIM); sys.exit(0)
