"""CLI entry point for yt-feed."""

import argparse

from yt_feed.feed import fetch_subscriptions_feed
from yt_feed.unsub import cmd_list, cmd_unsub


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube tools: fetch feed or unsubscribe from channels.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fetch_parser = sub.add_parser("feed", help="Fetch latest videos from channels")
    fetch_parser.add_argument(
        "channels_file",
        nargs="?",
        default="channels.txt",
        help="File with one YouTube channel URL per line (default: channels.txt)",
    )
    fetch_parser.add_argument("-n", "--num", type=int, default=5, help="Videos per channel (default: 5)")
    fetch_parser.add_argument("-o", "--output", default=None, help="Save output to file")

    unsub_parser = sub.add_parser("unsub", help="Unsubscribe from channels (by name, metadata filter, or all)")
    unsub_parser.add_argument("--browser", default="edge", help="Browser to use: edge or chrome (default: edge)")
    unsub_parser.add_argument("--profile-dir", default=None, help="Path to browser profile User Data directory (auto-detected if omitted)")
    unsub_parser.add_argument("--dry-run", action="store_true", help="List channels without unsubscribing")
    unsub_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    unsub_parser.add_argument("--name", action="append", dest="name_patterns", default=None,
                              help="Channel name pattern (supports * wildcard, repeatable). Omit to unsubscribe from ALL.")
    unsub_parser.add_argument("--subs-below", type=int, default=None,
                              help="Unsubscribe from channels with fewer than N subscribers")
    unsub_parser.add_argument("--inactive", type=int, default=None, dest="inactive_days",
                              help="Unsubscribe from channels with no video in N days")
    unsub_parser.add_argument("--desc", action="append", dest="desc_patterns", default=None,
                              help="Unsubscribe from channels whose description matches pattern (* wildcard, repeatable)")

    list_parser = sub.add_parser("list-subs", help="List subscribed channels")
    list_parser.add_argument("--browser", default="edge", help="Browser to use: edge or chrome (default: edge)")
    list_parser.add_argument("--profile-dir", default=None, help="Path to browser profile User Data directory (auto-detected if omitted)")

    args = parser.parse_args()

    if args.command == "feed":
        fetch_subscriptions_feed(args.channels_file, args.num, args.output)
    elif args.command == "list-subs":
        cmd_list(args.browser, args.profile_dir)
    elif args.command == "unsub":
        cmd_unsub(args.browser, args.dry_run, args.yes, args.profile_dir,
                  args.name_patterns, args.subs_below, args.inactive_days,
                  args.desc_patterns)


if __name__ == "__main__":
    main()
