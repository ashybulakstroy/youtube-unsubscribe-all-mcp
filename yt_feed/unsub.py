"""Unsubscribe from all YouTube channels using Playwright (browser context)."""

import sys
import time
from pathlib import Path

API_VERSION = "2.20230530.01.00"
YT_API_BASE = "https://www.youtube.com/youtubei/v1"


def _browser_channel(browser: str) -> str:
    return {"edge": "msedge", "chrome": "chrome"}.get(browser, browser)


def _default_profile_dir(browser: str) -> str:
    home = Path.home()
    plat = sys.platform
    paths = {
        ("edge", "win32"): home / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data",
        ("edge", "darwin"): home / "Library" / "Application Support" / "Microsoft Edge",
        ("edge", "linux"):  home / ".config" / "microsoft-edge",
        ("chrome", "win32"): home / "AppData" / "Local" / "Google" / "Chrome" / "User Data",
        ("chrome", "darwin"): home / "Library" / "Application Support" / "Google" / "Chrome",
        ("chrome", "linux"):  home / ".config" / "google-chrome",
    }
    key = (browser, plat)
    if key not in paths:
        print(f"Unsupported browser/platform: {browser}/{plat}", file=sys.stderr)
        sys.exit(1)
    return str(paths[key])


def _resolve_browser(browser: str, profile_dir: str | None = None):
    udir = profile_dir or _default_profile_dir(browser)
    return udir, _browser_channel(browser)


def _get_channels(page) -> list[dict]:
    """Extract subscribed channels from the page."""
    # From DOM (using el.data for real UC channel IDs)
    items = page.evaluate("""() => {
        const items = document.querySelectorAll('ytd-channel-renderer');
        return Array.from(items).map(el => {
            const data = el.data || el.__data;
            const channelId = data?.channelId || '';
            const name = data?.title?.simpleText
                || data?.title?.runs?.[0]?.text
                || '';
            const url = data?.navigationEndpoint?.commandMetadata?.webCommandMetadata?.url
                || '';
            return { id: channelId, name, url: url ? 'https://www.youtube.com' + url : '' };
        }).filter(c => c.id && c.id.startsWith('UC'));
    }""")
    if items:
        return items

    # Fallback: ytInitialData
    return page.evaluate("""() => {
        const data = window.ytInitialData;
        if (!data) return [];
        const tabs = data.contents?.twoColumnBrowseResultsRenderer?.tabs || [];
        for (const tab of tabs) {
            const sl = tab?.tabRenderer?.content?.sectionListRenderer;
            if (!sl) continue;
            const contents = sl.contents?.[0]?.itemSectionRenderer?.contents || [];
            const result = contents
                .filter(i => i.channelRenderer)
                .map(i => {
                    const r = i.channelRenderer;
                    const id = r.channelId || '';
                    const name = r.title?.simpleText || r.title?.runs?.[0]?.text || '';
                    const url = r.navigationEndpoint?.commandMetadata?.webCommandMetadata?.url || '';
                    return { id, name, url: url ? 'https://www.youtube.com' + url : '' };
                });
            if (result.length) return result;
        }
        return [];
    }""")


def _scroll_to_bottom(page, max_scrolls=50):
    prev = 0
    for _ in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        time.sleep(0.5)
        curr = page.evaluate("document.documentElement.scrollHeight")
        if curr == prev:
            break
        prev = curr


def _unsubscribe(page, channel_id: str) -> dict:
    """Unsubscribe via InnerTube API using browser fetch with SAPISIDHASH."""
    return page.evaluate(f"""
        async () => {{
            try {{
                // Get SAPISID from cookies
                const cookies = document.cookie.split(';').reduce((acc, c) => {{
                    const [k, v] = c.trim().split('=');
                    acc[k] = v;
                    return acc;
                }}, {{}});
                const sapisid = cookies['__Secure-3PSAPISID'] || cookies['SAPISID'];
                if (!sapisid) {{
                    return {{ ok: false, status: 0, error: 'No SAPISID cookie' }};
                }}

                // Compute SAPISIDHASH
                const timestamp = Math.floor(Date.now() / 1000);
                const origin = 'https://www.youtube.com';
                const hash = await crypto.subtle.digest('SHA-1',
                    new TextEncoder().encode(timestamp + ' ' + sapisid + ' ' + origin)
                ).then(h => Array.from(new Uint8Array(h)).map(b => b.toString(16).padStart(2,'0')).join(''));

                const resp = await fetch('{YT_API_BASE}/subscription/unsubscribe', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'SAPISIDHASH ' + timestamp + '_' + hash,
                        'X-Origin': 'https://www.youtube.com',
                    }},
                    credentials: 'include',
                    body: JSON.stringify({{
                        context: {{
                            client: {{
                                clientName: 'WEB',
                                clientVersion: '{API_VERSION}',
                            }}
                        }},
                        channelIds: ['{channel_id}']
                    }})
                }});
                return {{ ok: resp.ok, status: resp.status }};
            }} catch (e) {{
                return {{ ok: false, error: e.message }};
            }}
        }}
    """)


def cmd_list(browser: str, profile_dir: str | None = None) -> None:
    user_data, channel = _resolve_browser(browser, profile_dir)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=user_data, channel=channel, headless=True,
        )
        page = context.new_page()
        print("Opening browser to fetch subscriptions...", file=sys.stderr)
        page.goto("https://www.youtube.com/feed/channels", wait_until="networkidle")
        time.sleep(2)
        _scroll_to_bottom(page)
        channels = _deduplicate(_get_channels(page))
        context.close()

    print(f"Found {len(channels)} subscribed channels:\n")
    for ch in sorted(channels, key=lambda x: x["name"].lower()):
        print(f"  {ch['name']} — https://www.youtube.com/channel/{ch['id']}")


def cmd_unsub(browser: str, dry_run: bool, yes: bool = False, profile_dir: str | None = None) -> None:
    user_data, channel = _resolve_browser(browser, profile_dir)
    from playwright.sync_api import sync_playwright

    import os
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

    max_passes = 5
    total_ok = 0
    total_fail = 0
    confirmed = dry_run or yes

    print("Launching browser...", file=sys.stderr, flush=True)
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=user_data, channel=channel, headless=True,
        )
        page = context.new_page()

        for attempt in range(1, max_passes + 1):
            if attempt > 1:
                print(f"\n--- Pass {attempt} (verification) ---", file=sys.stderr, flush=True)

            # Step 1: get channels
            print("Loading subscriptions page...", file=sys.stderr, flush=True)
            page.goto("https://www.youtube.com/feed/channels", wait_until="domcontentloaded", timeout=30000)
            print("Scrolling...", file=sys.stderr, flush=True)
            time.sleep(2)
            _scroll_to_bottom(page)

            channels = _deduplicate(_get_channels(page))

            if not channels:
                print("No more subscriptions found!", file=sys.stderr, flush=True)
                break

            print(f"Found {len(channels)} subscribed channels.", file=sys.stderr, flush=True)

            if attempt == 1 and not confirmed:
                print(f"\nThis will unsubscribe from ALL {len(channels)} channels!")
                confirm = input("Type 'yes' to continue: ")
                if confirm.lower() != "yes":
                    print("Cancelled.")
                    context.close()
                    sys.exit(0)

            if dry_run:
                for ch in channels:
                    print(f"  {ch['name']} — https://www.youtube.com/channel/{ch['id']}")
                context.close()
                return

            # Step 2: unsubscribe
            ok = fail = 0
            for i, ch in enumerate(channels, 1):
                name = ch.get("name", "") or ch.get("id", "")
                sys.stdout.write(f"[{i}/{len(channels)}] {name} ({ch['id']})")
                sys.stdout.flush()

                result = _unsubscribe(page, ch["id"])
                if result.get("ok"):
                    sys.stdout.write(" OK\n")
                    ok += 1
                else:
                    sys.stdout.write(f" FAIL (status={result.get('status','?')})\n")
                    fail += 1
                time.sleep(0.3)

            total_ok += ok
            total_fail += fail

            if fail == 0:
                break

            if attempt < max_passes:
                print(f"\n{len(channels)} channels remain ({ok} OK / {fail} FAIL). Re-checking...", file=sys.stderr, flush=True)

        context.close()

    if not dry_run:
        print(f"\nAll passes done. Total OK={total_ok}, Failed={total_fail}")


def _deduplicate(channels: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for ch in channels:
        cid = ch.get("id", "")
        if cid and cid not in seen:
            seen[cid] = ch
    return list(seen.values())
