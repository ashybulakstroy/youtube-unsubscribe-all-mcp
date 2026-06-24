# AGENTS.md — yt-feed

## Project

CLI tool that fetches latest videos from YouTube channels via yt-dlp, and can unsubscribe from all subscribed channels using browser cookies.

## Setup

```bash
python -m venv .venv
.venv\Scripts\pip install yt-dlp requests
```

Add channel URLs to `channels.txt` (one per line). See sample in file.

## Usage

```bash
.venv\Scripts\python -m yt_feed.cli feed channels.txt -n 5
# or via pip install -e .:
yt-feed feed channels.txt -n 5
```

## Commands

| Action | Command |
|--------|---------|
| Fetch feed | `.venv\Scripts\python -m yt_feed.cli feed [channels.txt] [-n N] [-o out.txt]` |
| List subscriptions | `.venv\Scripts\python -m yt_feed.cli list-subs [--browser chrome] [--profile-dir <path>]` |
| Dry-run unsubscribe | `.venv\Scripts\python -m yt_feed.cli unsub --dry-run [--browser chrome] [--profile-dir <path>]` |
| Unsubscribe from all | `.venv\Scripts\python -m yt_feed.cli unsub [--browser chrome] [--profile-dir <path>]` |
| MCP server (stdio) | `.venv\Scripts\python -m yt_feed.mcp_server` |
| Install dev | `.venv\Scripts\pip install -e .` |

## Structure

- `yt_feed/cli.py` — CLI entry point (argparse, subcommands: `feed`, `unsub`, `list-subs`)
- `yt_feed/feed.py` — yt-dlp fetching and output formatting
- `yt_feed/unsub.py` — cookie export, channel listing, InnerTube API unsubscription
- `yt_feed/mcp_server.py` — MCP server exposing unsub tools via Model Context Protocol
- `channels.txt` — channel list (one per line, `#` comments)
- `.venv/` — virtual environment (do not commit)

## Architecture (unsub)

1. `Playwright` + `launch_persistent_context(channel="msedge", headless=True)` — запуск Edge с профилем пользователя
2. `el.data.channelId` — извлечение реальных UC-айди каналов из DOM (не handle `@name`)
3. `fetch()` из контекста браузера + `SAPISIDHASH` (SHA1(timestamp + SAPISID + origin)) — отписка через InnerTube API

Ключевые моменты:
- Куки НЕ экспортируются — браузер сам их предоставляет через `credentials: 'include'`
- SAPISIDHASH вычисляется на клиенте через `crypto.subtle.digest('SHA-1', ...)`
- Заголовки: `Authorization: SAPISIDHASH <ts>_<hash>`, `X-Origin: https://www.youtube.com`
- Channel ID должен быть UCxxxxx, не handle (@name)
- `launch_persistent_context` не работает если Edge уже запущен; перед запуском убивать `taskkill /f /im msedge.exe`
- При зависании: убить python.exe процессы

## Notes

- Always use `.venv\Scripts\python` or activate `.venv\Scripts\activate` before running
- `cmd /c` prefix needed in opencode-shell for Windows commands with quotes
- yt-dlp is scraped (no API key needed); quota limits do not apply
- `unsub --yes` для пропуска подтверждения (иначе `input()` не работает через трубу)
- `--dry-run` показывает что будет отписано без изменений
- yt-dlp не может расшифровать DPAPI-куки Edge на Windows — всегда использовать Playwright

## Profile paths (cross-platform)

`_default_profile_dir()` in `unsub.py` auto-detects the browser profile directory:

| Browser | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Edge | `%LOCALAPPDATA%\Microsoft\Edge\User Data` | `~/Library/Application Support/Microsoft Edge` | `~/.config/microsoft-edge` |
| Chrome | `%LOCALAPPDATA%\Google\Chrome\User Data` | `~/Library/Application Support/Google/Chrome` | `~/.config/google-chrome` |

Override with `--profile-dir <path>` (points to `User Data` directory, not `Default` subfolder).

## Agent instructions

- Пиши ответы на русском языке
- Всегда проверяй результат перед тем, как сообщить о готовности
- Записывай новые инструкции в AGENTS.md сразу после получения
