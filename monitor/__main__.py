"""Kommandozeile.

  python -m monitor run [--source ID] [--dry-run] [--state PFAD]
  python -m monitor validate              Konfiguration prüfen
  python -m monitor check-url URL [--source ID]   eine Produktseite testen
  python -m monitor robots URL            darf diese URL abgerufen werden?
  python -m monitor report [--state PFAD] Übersicht: Produkte & Status je Quelle
  python -m monitor test-notify           Testnachricht an ntfy senden
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter

from . import parsing
from .config import ROOT, load_settings, load_sources, validate
from .fetcher import Blocked, Disallowed, FetchError, PoliteClient
from .matching import Matcher
from .notify import Notifier
from .runner import Runner
from .state import State, utcnow

DEFAULT_STATE = os.path.join(ROOT, "state", "state.json")


def make_client(settings: dict) -> PoliteClient:
    http = settings.get("http", {})
    return PoliteClient(
        user_agent=settings["user_agent"],
        robots_agent=settings.get("robots_agent", "tcg-stock-monitor"),
        timeout=float(http.get("timeout_seconds", 20)),
        min_delay=float(http.get("min_delay_seconds", 3)),
    )


def make_notifier(settings: dict) -> Notifier:
    n = settings.get("notify", {})
    return Notifier(
        server=os.environ.get("NTFY_SERVER") or n.get("server", "https://ntfy.sh"),
        topic=os.environ.get("NTFY_TOPIC") or None,
        token=os.environ.get("NTFY_TOKEN") or None,
        max_single=int(n.get("max_single_messages", 8)),
    )


def cmd_run(args) -> int:
    settings, sources = load_settings(), load_sources()
    errors = validate(sources)
    if errors:
        for e in errors:
            logging.error("Konfiguration: %s", e)
        return 2
    state = State.load(args.state)
    client = make_client(settings)
    runner = Runner(settings, sources, state, client, Matcher.from_config(settings.get("matching", {})), utcnow())
    events = runner.run(only=args.source)
    logging.info("Lauf fertig: %d Requests, %d Ereignisse, %d Produkte im Zustand",
                 client.request_count, len(events), len(state.products))
    for e in events:
        logging.info("EREIGNIS %s | %s | %s", e.kind, e.headline(), e.url or "")
    if args.dry_run:
        logging.info("--dry-run: keine Benachrichtigung, Zustand nicht gespeichert")
        return 0
    make_notifier(settings).send(events)
    state.save(args.state)
    return 0


def cmd_validate(args) -> int:
    errors = validate(load_sources())
    for e in errors:
        print("FEHLER:", e)
    if not errors:
        print("Konfiguration ok.")
    return 1 if errors else 0


def cmd_check_url(args) -> int:
    settings, sources = load_settings(), load_sources()
    src = next((s for s in sources if s.id == args.source), None)
    client = make_client(settings)
    print("robots.txt erlaubt:", client.allowed(args.url))
    try:
        resp = client.get(args.url)
    except (Blocked, Disallowed, FetchError) as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 1
    info = parsing.parse_product(resp.text,
                                 src.in_stock_patterns if src else (),
                                 src.out_of_stock_patterns if src else ())
    matcher = Matcher.from_config(settings.get("matching", {}))
    print(f"HTTP {resp.status}, {len(resp.text)} Zeichen")
    print("Name:   ", info.name)
    print("Status: ", info.status, f"(erkannt über: {info.method})")
    print("Preis:  ", info.price, info.currency)
    print("Relevant laut matching (URL/Name):", matcher.matches(args.url), "/", matcher.matches(info.name or ""))
    return 0


def cmd_robots(args) -> int:
    client = make_client(load_settings())
    ok = client.allowed(args.url)
    print("ERLAUBT" if ok else "VERBOTEN", args.url)
    return 0 if ok else 1


def cmd_report(args) -> int:
    state = State.load(args.state)
    by_source: dict[str, Counter] = {}
    for p in state.products.values():
        c = by_source.setdefault(p.get("source", "?"), Counter())
        c["ignoriert" if p.get("ignored") else p.get("status", "unknown")] += 1
        c[f"methode:{p.get('method', '-')}"] += 1
    for sid, sst in sorted(state.data["sources"].items()):
        print(f"== {sid}: letzter Lauf {sst.get('last_discovery', '-')}, Fehler in Folge {sst.get('fail_count', 0)}"
              + (f", PAUSIERT bis {sst['blocked_until']}" if sst.get("blocked_until") else "")
              + (f"\n   letzter Fehler: {sst['last_error']}" if sst.get("last_error") else ""))
        for k, v in sorted(by_source.get(sid, Counter()).items()):
            print(f"   {k}: {v}")
    print("Hinweis: viele 'unknown' / 'methode:none' => Seite hat kein JSON-LD, Regex-Fallbacks in sources.yaml ergänzen.")
    return 0


def cmd_test_notify(args) -> int:
    n = make_notifier(load_settings())
    if not n.topic:
        print("NTFY_TOPIC ist nicht gesetzt.")
        return 1
    n.test()
    print("Testnachricht gesendet an Topic", n.topic[:3] + "…")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="python -m monitor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run"); p.add_argument("--source"); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--state", default=DEFAULT_STATE); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("validate"); p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("check-url"); p.add_argument("url"); p.add_argument("--source"); p.set_defaults(fn=cmd_check_url)
    p = sub.add_parser("robots"); p.add_argument("url"); p.set_defaults(fn=cmd_robots)
    p = sub.add_parser("report"); p.add_argument("--state", default=DEFAULT_STATE); p.set_defaults(fn=cmd_report)
    p = sub.add_parser("test-notify"); p.set_defaults(fn=cmd_test_notify)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
