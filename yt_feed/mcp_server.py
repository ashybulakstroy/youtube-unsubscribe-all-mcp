"""MCP server for YouTube channel management (list subscriptions, unsubscribe).

Uses Playwright Async API to work inside the MCP asyncio event loop.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from typing import Any

from mcp.server import FastMCP

# Internal helpers — sync, imported at module level
from yt_feed.unsub import (
    _default_profile_dir,
    _browser_channel,
    _match_patterns,
    _fetch_subscriptions_metadata,
    _filter_by_metadata,
    YT_API_BASE,
    API_VERSION,
)

mcp = FastMCP("yt-unsub", instructions="Tools to list and unsubscribe from YouTube channels using browser automation (Playwright).")

# Global browser state
_playwright = None
_context = None
_page = None
_current_browser: str | None = None
_current_profile: str | None = None


def _kill_browser(browser: str) -> None:
    if sys.platform == "win32":
        exe = "msedge.exe" if browser == "edge" else "chrome.exe"
        subprocess.run(["taskkill", "/f", "/im", exe], capture_output=True)
    else:
        exe = "microsoft-edge" if browser == "edge" else "google-chrome"
        subprocess.run(["pkill", "-f", exe], capture_output=True)


async def _ensure_browser(browser: str = "edge", profile_dir: str | None = None) -> Any:
    """Lazy-init Playwright browser context; returns the active page."""
    global _playwright, _context, _page, _current_browser, _current_profile

    udir = profile_dir or _default_profile_dir(browser)
    channel = _browser_channel(browser)

    if _page is not None and _current_browser == browser and _current_profile == udir:
        return _page

    await _close_browser()

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    _kill_browser(browser)
    await asyncio.sleep(0.5)

    from playwright.async_api import async_playwright

    _playwright = await async_playwright().__aenter__()
    _context = await _playwright.chromium.launch_persistent_context(
        user_data_dir=udir, channel=channel, headless=True,
    )
    _page = await _context.new_page()
    _current_browser = browser
    _current_profile = udir
    return _page


async def _close_browser() -> None:
    global _playwright, _context, _page, _current_browser, _current_profile
    _page = None
    _current_browser = None
    _current_profile = None
    try:
        if _context is not None:
            await _context.close()
    except Exception:
        pass
    _context = None
    try:
        if _playwright is not None:
            await _playwright.__aexit__(None, None, None)
    except Exception:
        pass
    _playwright = None


async def _scroll_to_bottom_async(page, max_scrolls=50):
    prev = 0
    for _ in range(max_scrolls):
        await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        await asyncio.sleep(0.5)
        curr = await page.evaluate("document.documentElement.scrollHeight")
        if curr == prev:
            break
        prev = curr


async def _get_channels_async(page) -> list[dict]:
    items = await page.evaluate("""() => {
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
    return await page.evaluate("""() => {
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


async def _unsubscribe_async(page, channel_id: str) -> dict:
    return await page.evaluate(f"""
        async () => {{
            try {{
                const cookies = document.cookie.split(';').reduce((acc, c) => {{
                    const [k, v] = c.trim().split('=');
                    acc[k] = v;
                    return acc;
                }}, {{}});
                const sapisid = cookies['__Secure-3PSAPISID'] || cookies['SAPISID'];
                if (!sapisid) {{
                    return {{ ok: false, status: 0, error: 'No SAPISID cookie' }};
                }}
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


async def _fetch_channels(page: Any) -> list[dict]:
    await page.goto("https://www.youtube.com/feed/channels", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    await _scroll_to_bottom_async(page)
    channels = await _get_channels_async(page)
    seen: dict[str, dict] = {}
    for ch in channels:
        cid = ch.get("id", "")
        if cid and cid not in seen:
            seen[cid] = ch
    return list(seen.values())


@mcp.tool(
    description="List all subscribed YouTube channels with their IDs and names.",
)
async def list_subscriptions(
    browser: str = "edge",
    profile_dir: str | None = None,
) -> list[dict]:
    """Open YouTube /feed/channels, scroll to load all subscriptions, return channel list."""
    try:
        page = await _ensure_browser(browser, profile_dir)
        channels = await _fetch_channels(page)
        return [
            {"id": ch["id"], "name": ch.get("name", ""), "url": f"https://www.youtube.com/channel/{ch['id']}"}
            for ch in channels
        ]
    except Exception as e:
        await _close_browser()
        return [{"error": str(e)}]


@mcp.tool(
    description="Unsubscribe from YouTube channels, optionally filtered by name patterns with * wildcard or by metadata (subs/inactivity).",
)
async def unsubscribe_all(
    browser: str = "edge",
    profile_dir: str | None = None,
    confirm: bool = False,
    name_patterns: list[str] | None = None,
    subs_below: int | None = None,
    inactive_days: int | None = None,
) -> dict:
    """Unsubscribe from channels. Options:
    - name_patterns: e.g. ['*news*', '*tech'] — only matching names
    - subs_below: unsubscribe from channels with fewer than N subscribers
    - inactive_days: unsubscribe from channels with no video in N days
    Omit all filters to unsubscribe from EVERY channel."""
    if not confirm:
        return {"status": "cancelled", "message": "Set confirm=True to proceed with unsubscription."}

    max_passes = 5
    total_ok = 0
    total_fail = 0
    passes_done = 0
    need_meta = subs_below is not None or inactive_days is not None

    try:
        page = await _ensure_browser(browser, profile_dir)

        for attempt in range(1, max_passes + 1):
            passes_done = attempt
            channels = await _fetch_channels(page)

            if name_patterns:
                channels = [ch for ch in channels if _match_patterns(ch.get("name", ""), name_patterns)]

            # Metadata filter (first pass only)
            if need_meta and attempt == 1:
                need_date = inactive_days is not None
                loop = asyncio.get_event_loop()
                meta_list = await loop.run_in_executor(
                    None, lambda: _fetch_subscriptions_metadata(channels, need_date),
                )
                for ch, meta in zip(channels, meta_list):
                    ch["_meta"] = meta
                channels = _filter_by_metadata(channels, subs_below, inactive_days)

            total = len(channels)

            if total == 0:
                break

            ok = fail = 0
            for ch in channels:
                result = await _unsubscribe_async(page, ch["id"])
                if result.get("ok"):
                    ok += 1
                else:
                    fail += 1
                await asyncio.sleep(0.3)

            total_ok += ok
            total_fail += fail

            if fail == 0:
                break

        await _close_browser()
        return {
            "status": "ok",
            "passes": passes_done,
            "total_unsubscribed": total_ok,
            "total_failed": total_fail,
        }
    except Exception as e:
        await _close_browser()
        return {"status": "error", "error": str(e)}


@mcp.tool(
    description="Unsubscribe from specific YouTube channels by their channel IDs (UCxxxxx).",
)
async def unsubscribe_channels(
    channel_ids: list[str],
    browser: str = "edge",
    profile_dir: str | None = None,
) -> dict:
    """Unsubscribe from a list of specific channel IDs. Useful after calling list_subscriptions."""
    if not channel_ids:
        return {"status": "ok", "unsubscribed_count": 0, "failed_count": 0, "message": "No channel IDs provided."}
    try:
        page = await _ensure_browser(browser, profile_dir)
        ok = fail = 0
        results: list[dict] = []
        for cid in channel_ids:
            result = await _unsubscribe_async(page, cid)
            results.append({"channel_id": cid, "ok": result.get("ok", False), "error": result.get("error")})
            if result.get("ok"):
                ok += 1
            else:
                fail += 1
            await asyncio.sleep(0.3)
        return {
            "status": "ok",
            "unsubscribed_count": ok,
            "failed_count": fail,
            "results": results,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool(
    description="Close the browser if open (free up system resources).",
)
async def close_browser() -> str:
    """Explicitly close the managed browser context."""
    await _close_browser()
    return "Browser closed."


def main() -> None:
    """Run the MCP server via stdio transport (default for MCP)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
