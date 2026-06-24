"""Fetch and display the latest videos from a list of YouTube channels."""

import sys

import yt_dlp


def read_channels(path: str) -> list[str]:
    with open(path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def fetch_latest(channel_url: str, num: int) -> list[dict]:
    ydl_opts = {
        "quiet": True,
        "extract_flat": "in_playlist",
        "playlistend": num,
        "default_search": "ytsearch",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        entries = info.get("entries", [])
        return [
            {
                "title": e.get("title"),
                "url": f"https://youtube.com/watch?v={e.get('id')}",
                "uploader": info.get("uploader") or info.get("channel", ""),
                "upload_date": e.get("upload_date", ""),
            }
            for e in entries
            if e
        ]


def search_videos(query: str, num: int = 10) -> list[dict]:
    ydl_opts = {
        "quiet": True,
        "extract_flat": "in_playlist",
        "playlistend": num,
        "default_search": "ytsearch",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch{num}:{query}", download=False)
        entries = info.get("entries", [])
        return [
            {
                "title": e.get("title"),
                "url": f"https://youtube.com/watch?v={e.get('id')}",
                "channel": e.get("channel") or e.get("uploader", ""),
                "channel_url": e.get("channel_url", ""),
                "upload_date": e.get("upload_date", ""),
            }
            for e in entries
            if e
        ]


def fetch_subscriptions_feed(channels_file: str, num: int = 5, output: str | None = None) -> None:
    urls = read_channels(channels_file)
    if not urls:
        print("No channels found. Add URLs to channels.txt (one per line).", file=sys.stderr)
        sys.exit(1)

    all_videos: list[dict] = []
    for url in urls:
        try:
            videos = fetch_latest(url, num)
            all_videos.extend(videos)
        except Exception as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)

    all_videos.sort(key=lambda v: v.get("upload_date", ""), reverse=True)

    out_lines = []
    for v in all_videos:
        line = f"[{v['uploader']}] {v['title']}  {v['url']}  ({v['upload_date']})"
        out_lines.append(line)

    text = "\n".join(out_lines)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"Written to {output}")
    else:
        print(text)
