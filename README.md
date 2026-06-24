# yt-feed

CLI tool for YouTube: fetch latest videos from channels, list subscriptions, and mass-unsubscribe from all channels using browser automation.

## Features

- **feed** — get N latest videos from a list of YouTube channels (via yt-dlp, no API key)
- **list-subs** — list every channel your account is subscribed to
- **unsub** — unsubscribe from ALL channels at once via YouTube's InnerTube API
- **MCP server** — expose unsub tools via Model Context Protocol (for AI assistants like opencode)

## Installation

```bash
python -m venv .venv
.venv\Scripts\pip install yt-dlp requests playwright mcp
.venv\Scripts\playwright install chromium
```

Or install in editable mode:

```bash
.venv\Scripts\pip install -e .
```

## Usage

### Fetch video feed

```bash
.venv\Scripts\python -m yt_feed.cli feed channels.txt -n 5 -o out.txt
# or after pip install -e .:
yt-feed feed channels.txt -n 5
```

`channels.txt` — one channel URL per line (`#` for comments).

### List subscriptions

```bash
yt-feed list-subs --browser edge
```

### Unsubscribe from all channels

```bash
# Preview only (no changes)
yt-feed unsub --browser edge --dry-run

# Real unsubscribe (prompts for confirmation)
yt-feed unsub --browser edge

# Skip confirmation
yt-feed unsub --browser edge --yes

# Custom profile directory
yt-feed unsub --browser chrome --profile-dir "D:\User Data" --yes
```

**Note:** Close the browser before running `unsub` — Playwright's `launch_persistent_context` cannot open a profile that's already in use.

### MCP server

Run the MCP server via stdio:

```bash
yt-feed-mcp
```

Then configure in `opencode.json`:

```json
{
  "mcp": {
    "yt-unsub": {
      "type": "local",
      "command": [".venv\\Scripts\\python", "-m", "yt_feed.mcp_server"],
      "enabled": true
    }
  }
}
```

Available tools:

| Tool | Description |
|------|-------------|
| `list_subscriptions` | List all subscribed channels |
| `unsubscribe_all` | Unsubscribe from all channels (requires `confirm=True`) |
| `unsubscribe_channels` | Unsubscribe from specific channel IDs |
| `close_browser` | Close the managed browser (free resources) |

## Browsers

| Flag | Browser |
|------|---------|
| `--browser edge` | Microsoft Edge (default) |
| `--browser chrome` | Google Chrome |

## Profile paths

The tool auto-detects the browser profile directory. Override with `--profile-dir <path>` (points to the `User Data` directory, not the `Default` subfolder).

| Browser | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Edge | `%LOCALAPPDATA%\Microsoft\Edge\User Data` | `~/Library/Application Support/Microsoft Edge` | `~/.config/microsoft-edge` |
| Chrome | `%LOCALAPPDATA%\Google\Chrome\User Data` | `~/Library/Application Support/Google/Chrome` | `~/.config/google-chrome` |

## How the unsubscribe works

1. **Playwright** launches the browser with your profile (`launch_persistent_context`) — this gives access to your YouTube session
2. The `/feed/channels` page is loaded and scrolled to the bottom; **real UC channel IDs** are extracted from the DOM (`el.data.channelId`)
3. For each channel, a `POST` request is sent to InnerTube API `/subscription/unsubscribe` from within the browser context
4. **Authorization:** the `Authorization: SAPISIDHASH <ts>_<sha1>` header is computed client-side from the SAPISID cookie via `crypto.subtle.digest('SHA-1', ...)`

### Key details

- Cookies are never exported — the browser sends them natively via `credentials: 'include'`
- yt-dlp **cannot** decrypt DPAPI-encrypted Edge cookies on Windows — Playwright is required
- Channel IDs must be `UCxxxxx` (not `@handle`)
- 300 ms delay between requests to avoid rate limiting

## Requirements

- Python ≥ 3.10
- Edge or Chrome browser with a logged-in YouTube account
- Windows, macOS, or Linux

## Project structure

```
yt-feed/
├── yt_feed/
│   ├── __init__.py
│   ├── cli.py          # CLI entry point (argparse, commands: feed, list-subs, unsub)
│   ├── feed.py         # Video feed via yt-dlp
│   ├── unsub.py        # Mass unsubscribe via Playwright + InnerTube API
│   └── mcp_server.py   # MCP server exposing tools via Model Context Protocol
├── channels.txt        # Channel list for the feed command
├── pyproject.toml      # Package config
├── AGENTS.md           # Agent instructions (opencode)
└── README.md
```
