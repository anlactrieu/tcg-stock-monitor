# HANDOFF – 22.10.2026 (Abend)

## Stand
- Repo: https://github.com/anlactrieu/tcg-stock-monitor (öffentlich). Secret `NTFY_TOPIC=pkmntcgping`, Workflow läuft alle 10 Min fehlerfrei. 42 Tests grün.
- Aktive Quellen: **mueller** (Lagerstatus), **rossmann** + **mightycards** (`discovery_only`, „neu gelistet“), **mydealz** (RSS, „Community-Fund“). Aus: smyths, thalia (Bot-Schutz), watchlist (leer).
- Erster echter Ping im Actions-Log: Rossmann „Amigo Pokémon-Adventskalender“ (neu gelistet). Ankunft in der ntfy-App vom Nutzer noch nicht bestätigt.

## Letzte 3 Entscheidungen
1. **Quelltyp `rss`** (`runner.discover_rss`, `parsing.parse_rss`, Event `DEAL`) – mydealz-Feed `/rss/gruppe/pokemon` ist öffentlich, robots-erlaubt und enthält Funde von Pokémon Center DE, Thalia, Rossmann, Netto, Rewe, Expert. Legaler Ersatz für verbotenes Scraping dieser Shops.
2. **Keine „halb legalen“ Wege** – Umgehung von Bot-Schutz/interne APIs abgelehnt (Leitplanke 3/4, § 202a StGB); stattdessen Feeds, Newsletter-Weiterleitung, Affiliate-Feeds.
3. **Filter erweitert** (`settings.yaml`): Kalender/Fatale Flammen rein; Ferrero, Blu-ray, Tonie raus → RSS-Titel werden mit demselben `matching` gefiltert.

## Offene TODOs
- Nutzer: ntfy-Ankunft bestätigen; Topic `pkmntcgping` ist erratbar → Zufallssuffix (Secret + App-Abo tauschen).
- E-Mail-Weiterleitung der Shop-Benachrichtigungen (Rossmann/Thalia/Pokémon Center) nach ntfy – braucht eigene Mail-Adresse vom Nutzer.
- Weitere mydealz-Feeds (pro Händler/Gruppe), vorher `python -m monitor robots URL`.
- Watchlist mit MediaMarkt/Saturn-Links (Nutzer liefert), Affiliate-Feeds (Awin/Belboon) prüfen.
- Optional: Statusseite (GitHub Pages) aus `state`-Branch.
- Community-Funde sind ungeprüft/teils lokal in anderen Städten; ggf. Hamburg-Filter (Titel enthält „Hamburg“) als eigene höhere Priorität.

## Relevante Stellen
`monitor/runner.py` (`run_source`, `discover_rss`, `_report_new_only`, `check_products`), `monitor/parsing.py` (`parse_rss`), `monitor/notify.py` (`DEAL`), `config/sources.yaml`, `config/settings.yaml`, `tests/test_runner.py` (`RssTest`, `DiscoveryOnlyTest`).

## Learnings
- Neue Filterbegriffe lassen bereits bekannte, vorher nicht registrierte Sitemap-URLs plötzlich als „neu“ auftauchen (Rossmann-Ping nach Keyword-Änderung) – nach Filteränderungen ggf. mit einem Fehlalarm rechnen.
- RSS-guids im Test nicht per Index erzeugen (Kollision zwischen Läufen).
- `looks_like_challenge` darf nicht auf robots.txt-Text angewendet werden (MediaMarkt/Saturn: `/cdn-cgi/challenge-platform/`).
- Bot-Challenges kommen oft als HTTP 200 (Rossmann): Produktseite mit `check-url` testen, bevor eine Quelle aufgenommen wird.
