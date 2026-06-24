"""Unsubscribe from all YouTube channels using Playwright (browser context)."""

import concurrent.futures
import fnmatch
import sys
import time
from datetime import datetime, timezone
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


def _extract_ytdlp(url: str, extract_flat: bool = True, playlistend: int = 1) -> dict | None:
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({
            "quiet": True,
            "extract_flat": extract_flat,
            "playlistend": playlistend,
            "skip_download": True,
        }) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception:
        return None


def _fetch_channel_metadata(channel: dict, need_video_date: bool = False) -> dict:
    url = channel.get("url") or f"https://www.youtube.com/channel/{channel['id']}"
    info = _extract_ytdlp(url, extract_flat=True, playlistend=1)
    if not info:
        return {
            "id": channel["id"],
            "name": channel.get("name", ""),
            "subs": None,
            "tags": [],
            "description": "",
            "last_video_date": None,
            "last_video_title": None,
        }

    meta = {
        "id": info.get("channel_id") or channel["id"],
        "name": info.get("channel") or channel.get("name", ""),
        "subs": info.get("channel_follower_count"),
        "tags": info.get("tags", []),
        "description": (info.get("description") or "")[:500],
        "last_video_date": None,
        "last_video_title": None,
    }

    entries = info.get("entries")
    if entries and need_video_date:
        first_id = entries[0].get("id")
        if first_id:
            vinfo = _extract_ytdlp(f"https://www.youtube.com/watch?v={first_id}", extract_flat=False)
            if vinfo:
                meta["last_video_date"] = vinfo.get("upload_date")
                meta["last_video_title"] = vinfo.get("title")

    return meta


def _fetch_subscriptions_metadata(channels: list[dict], need_video_date: bool = False) -> list[dict]:
    total = len(channels)
    print(f"Fetching metadata for {total} channels...", file=sys.stderr, flush=True)
    result: list[dict] = [None] * total

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        fut_map = {}
        for i, ch in enumerate(channels):
            fut_map[pool.submit(_fetch_channel_metadata, ch, need_video_date)] = i

        done = 0
        for future in concurrent.futures.as_completed(fut_map):
            idx = fut_map[future]
            result[idx] = future.result()
            done += 1
            if done % 10 == 0 or done == total:
                print(f"  metadata {done}/{total}", file=sys.stderr, flush=True)

    return result


def _filter_by_metadata(
    channels: list[dict],
    subs_below: int | None = None,
    inactive_days: int | None = None,
) -> list[dict]:
    """Filter channels list, keeping only those that match unsubscribe criteria.

    subs_below: keep channels with subs < subs_below (low-subs → unsubscribe)
    inactive_days: keep channels with last video older than inactive_days
    Returns the filtered (to-unsubscribe) list.
    """
    if subs_below is None and inactive_days is None:
        return channels  # no metadata filter

    now = datetime.now(timezone.utc)
    result = []

    for ch in channels:
        meta = ch.get("_meta", {})
        reasons = []

        if subs_below is not None:
            subs = meta.get("subs")
            if subs is None:
                reasons.append("subs unknown")
            elif subs < subs_below:
                reasons.append(f"{subs} subs < {subs_below}")

        if inactive_days is not None:
            ud = meta.get("last_video_date")
            if ud is None:
                reasons.append("last video unknown")
            else:
                try:
                    last = datetime.strptime(ud, "%Y%m%d").replace(tzinfo=timezone.utc)
                    days = (now - last).days
                    if days > inactive_days:
                        reasons.append(f"{days}d inactive > {inactive_days}d")
                except ValueError:
                    reasons.append("invalid date")

        if reasons:
            ch["_filter_reason"] = "; ".join(reasons)
            result.append(ch)

    return result


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


def cmd_unsub(
    browser: str, dry_run: bool, yes: bool = False,
    profile_dir: str | None = None,
    name_patterns: list[str] | None = None,
    subs_below: int | None = None,
    inactive_days: int | None = None,
) -> None:
    user_data, channel = _resolve_browser(browser, profile_dir)
    from playwright.sync_api import sync_playwright

    import os
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

    max_passes = 5
    total_ok = 0
    total_fail = 0
    confirmed = dry_run or yes
    need_meta = subs_below is not None or inactive_days is not None

    label = "ALL"
    if name_patterns:
        label = f"matching {name_patterns}"
    if need_meta:
        label += f" [subs<{subs_below or '∞'}, inactive>{inactive_days or '∞'}d]"

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

            # Filter by name patterns
            if name_patterns:
                before = len(channels)
                channels = [ch for ch in channels if _match_patterns(ch.get("name", ""), name_patterns)]
                print(f"Found {before} subscribed, {len(channels)} match name patterns.", file=sys.stderr, flush=True)
            else:
                print(f"Found {len(channels)} subscribed channels.", file=sys.stderr, flush=True)

            if not channels:
                print("No channels match the given patterns.", file=sys.stderr, flush=True)
                break

            # Fetch metadata and filter (only on first pass)
            if need_meta and attempt == 1:
                need_date = inactive_days is not None
                meta_list = _fetch_subscriptions_metadata(channels, need_video_date=need_date)
                for ch, meta in zip(channels, meta_list):
                    ch["_meta"] = meta

                before = len(channels)
                channels = _filter_by_metadata(channels, subs_below, inactive_days)
                if before != len(channels):
                    print(f"Metadata filter: {len(channels)} of {before} match criteria.", file=sys.stderr, flush=True)

            if not channels:
                print("No channels match the given criteria.", file=sys.stderr, flush=True)
                break

            if attempt == 1 and not confirmed:
                print(f"\nThis will unsubscribe from {label} ({len(channels)} channels)!")
                confirm = input("Type 'yes' to continue: ")
                if confirm.lower() != "yes":
                    print("Cancelled.")
                    context.close()
                    sys.exit(0)

            if dry_run:
                for ch in channels:
                    reason = ch.get("_filter_reason", "")
                    extra = f"  [{reason}]" if reason else ""
                    print(f"  {ch['name']} — {ch['id']}{extra}")
                    meta = ch.get("_meta", {})
                    if meta.get("subs") is not None:
                        print(f"      subs: {meta['subs']}, last video: {meta.get('last_video_date', '?')}")
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


def _match_patterns(name: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return True
    name_lower = name.lower()
    return any(fnmatch.fnmatch(name_lower, p.lower()) for p in patterns)
