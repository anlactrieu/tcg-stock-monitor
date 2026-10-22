# HANDOFF – 22.10.2026 (spät)

## Stand
- Repo live: https://github.com/anlactrieu/tcg-stock-monitor (öffentlich), Secret `NTFY_TOPIC=pkmntcgping` gesetzt, Workflow-Rechte write, `notify-test` grün, `monitor` läuft alle 10 Min ohne Fehler.
- 41 Tests grün. Aktive Quellen: **mueller** (voller Status), **rossmann** + **mightycards** (`discovery_only`, nur „neu gelistet“). Aus: smyths, thalia (Bot-Schutz), watchlist (leer).
- Noch nie ein echter Fund-Ping beobachtet (Müller/Rossmann haben aktuell keine Karten-Produkte).

## Letzte 3 Entscheidungen
1. **`discovery_only`-Option** (`runner._report_new_only`, `config.DEFAULTS`) – Rossmann-Produktseiten liefern JS-„Client Challenge“, Mighty-Cards ist Ecwid-JS-App ohne Status im HTML. Nur Sitemap lesen, nie Produktseiten → legal, aber ohne Lagerstatus.
2. **Rossmann zuerst aus, dann als discovery_only wieder an** – Challenge-Marker (`<title>client challenge</title>`, `/_fs-ch-`) in `fetcher.CHALLENGE_MARKERS` + Test.
3. **Mighty-Cards aufgenommen, Gate-to-the-Games nicht** – GTTG: 88k URLs/12-MB-Sitemaps, fast nur Einzelkarten, zu schwer für den Takt.

## Offene TODOs
- Nutzer: ntfy-App-Ping vom `notify-test` bestätigen; Topic `pkmntcgping` ist erratbar → besser Zufallssuffix (Secret + App-Abo tauschen).
- Watchlist mit konkreten MediaMarkt/Saturn/anderen Produkt-URLs füllen (Nutzer liefert Links), je `check-url` prüfen.
- Hamburger Läden/weitere Shops (Spiele Max, Alternate, Fantasywelt, Hugendubel, Netto, Rewe nicht geprüft/ohne Namen in Sitemap) sichten.
- Optional: Statusseite (GitHub Pages) aus `state`-Branch; Nutzer hat Rückfrage („Frontend“) offen gelassen.
- Ping-Kette mit echtem Fund bleibt unbelegt; Statuserkennung nur an Müller-Zubehör gesehen.

## Relevante Stellen
`monitor/runner.py` (`run_source`, `check_products`, `_report_new_only`, `_apply`), `monitor/fetcher.py` (`CHALLENGE_MARKERS`, `looks_like_challenge`, `PoliteClient.get`), `config/sources.yaml`, `config/settings.yaml` (`matching.exclude_any`), `tests/test_runner.py::DiscoveryOnlyTest`.

## Learnings
- `looks_like_challenge` schlägt bei MediaMarkt/Saturn-robots.txt an (`/cdn-cgi/challenge-platform/` steht in Disallow) → robots.txt-Text nie auf Marker prüfen, falls MediaMarkt je aufgenommen wird.
- Bot-Challenges kommen oft als HTTP 200 (Rossmann), nicht 403 – `check-url` auf echte Produktseite vor Aufnahme einer Quelle ist Pflicht; Sitemap-Erfolg beweist nichts.
- Sitemap-Einträge können Produkte enthalten, die im Shop-Frontend noch nicht sichtbar sind (Vorab-Anlage).
- Pokémon Center bleibt bewusst ausgeschlossen (Leitplanke 7); nur Newsletter/Benachrichtigen-Button.
