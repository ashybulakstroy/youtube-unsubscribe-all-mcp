# yt-feed

CLI-инструмент для работы с YouTube: получение списка последних видео из каналов, просмотр подписок и массовая отписка от всех каналов через автоматизацию браузера.

## Возможности

- **feed** — получить N последних видео из списка YouTube-каналов (через yt-dlp, без API-ключа)
- **list-subs** — показать все каналы, на которые подписан аккаунт
- **unsub** — отписаться от ВСЕХ каналов разом через InnerTube API
- **MCP сервер** —暴露 инструменты отписки через Model Context Protocol (для AI-ассистентов вроде opencode)

## Установка

```bash
python -m venv .venv
.venv\Scripts\pip install yt-dlp requests playwright mcp
.venv\Scripts\playwright install chromium
```

Или для разработки:

```bash
.venv\Scripts\pip install -e .
```

## Использование

### Получить ленту видео

```bash
.venv\Scripts\python -m yt_feed.cli feed channels.txt -n 5 -o out.txt
# или после pip install -e .:
yt-feed feed channels.txt -n 5
```

Файл `channels.txt` — список URL каналов (по одному на строку, `#` — комментарий).

### Список подписок

```bash
yt-feed list-subs --browser edge
```

### Отписка от всех каналов

```bash
# Просмотр, от чего отпишемся (без изменений)
yt-feed unsub --browser edge --dry-run

# Реальная отписка (запросит подтверждение)
yt-feed unsub --browser edge

# Без подтверждения
yt-feed unsub --browser edge --yes

# Свой путь к профилю браузера
yt-feed unsub --browser chrome --profile-dir "D:\User Data" --yes
```

**Важно:** Перед `unsub` закройте браузер — Playwright не сможет открыть профиль, если он уже используется.

### MCP сервер

Запуск через stdio:

```bash
yt-feed-mcp
```

Подключение в `opencode.json`:

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

Инструменты MCP:

| Инструмент | Описание |
|------------|----------|
| `list_subscriptions` | Показать все подписки |
| `unsubscribe_all` | Отписаться от всех каналов (требует `confirm=True`) |
| `unsubscribe_channels` | Отписаться от конкретных каналов по ID |
| `close_browser` | Закрыть браузер (освободить ресурсы) |

## Поддерживаемые браузеры

| Флаг | Браузер |
|------|---------|
| `--browser edge` | Microsoft Edge (по умолчанию) |
| `--browser chrome` | Google Chrome |

## Пути к профилям

Инструмент автоопределяет директорию профиля браузера. Переопределить можно через `--profile-dir <путь>` (укажите директорию `User Data`, а не `Default`).

| Браузер | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Edge | `%LOCALAPPDATA%\Microsoft\Edge\User Data` | `~/Library/Application Support/Microsoft Edge` | `~/.config/microsoft-edge` |
| Chrome | `%LOCALAPPDATA%\Google\Chrome\User Data` | `~/Library/Application Support/Google/Chrome` | `~/.config/google-chrome` |

## Как работает отписка (unsub)

1. **Playwright** запускает браузер с вашим профилем (`launch_persistent_context`) — это даёт доступ к сессии YouTube
2. Страница `/feed/channels` загружается и скроллится до конца; из DOM извлекаются **реальные UC-идентификаторы** каналов (`el.data.channelId`)
3. Для каждого канала через `fetch()` из контекста браузера отправляется POST-запрос к InnerTube API `/subscription/unsubscribe`
4. Авторизация: заголовок `Authorization: SAPISIDHASH <ts>_<sha1>` вычисляется на клиенте из SAPISID-cookie через `crypto.subtle.digest('SHA-1', ...)`

### Ключевые детали

- Куки **не экспортируются** — браузер сам их отправляет через `credentials: 'include'`
- yt-dlp **не может** расшифровать DPAPI-зашифрованные куки Edge на Windows — используется Playwright
- Channel ID должен быть в формате `UCxxxxx` (не `@handle`)
- Между запросами пауза 300 мс, чтобы не получить rate-limit

## Требования

- Python ≥ 3.10
- Браузер Edge или Chrome с залогиненным YouTube
- Windows, macOS или Linux

## Структура проекта

```
yt-feed/
├── yt_feed/
│   ├── __init__.py
│   ├── cli.py          # Точка входа CLI (argparse, команды feed, list-subs, unsub)
│   ├── feed.py         # Получение видео через yt-dlp
│   ├── unsub.py        # Массовая отписка через Playwright + InnerTube API
│   └── mcp_server.py   # MCP сервер (инструменты через Model Context Protocol)
├── channels.txt        # Список каналов для feed
├── pyproject.toml      # Конфигурация пакета
├── AGENTS.md           # Инструкции для opencode-агента
├── README.md           # Документация (английский)
└── README.ru.md        # Документация (русский)
```
