# HANDOFF – 22.10.2026

## Stand
- Lokal fertig: venv (`.venv`, Python 3.9), 39 Tests grün, `validate` ok, git-Repo initialisiert, 1 Commit (`d3aa87c`).
- Noch KEIN GitHub-Repo, KEIN Secret, KEINE Pings. Wartet auf ntfy-Topic vom Nutzer + Go für Repo (öffentlich oder privat).

## Letzte 3 Entscheidungen
1. **Smyths + Thalia `enabled: false`** – Smyths liefert Bot-Challenge, Thalia 403 schon bei robots.txt. Leitplanke 3: nicht umgehen.
2. **Müller-Filter verschärft** (`matching.exclude_any` in `config/settings.yaml`) – Live-Check lieferte nur Zubehör/DVDs/Gläser/Funko.
3. **MediaMarkt/Saturn nicht als Sitemap-Quelle** – 146 Dateien × 10k URLs ohne lastmod sprengen das 420-s-Budget; nur Watchlist sinnvoll.

## Offene TODOs
- Nutzer: ntfy-Topic nennen (geheim, nur als Secret `NTFY_TOPIC`).
- `gh repo create tcg-stock-monitor --public --source . --push`, `gh secret set NTFY_TOPIC`, Workflow-Schreibrechte, `gh workflow run notify-test` / `monitor`.
- Weitere Quellen prüfen (Galeria, Spiele Max, Kaufland, lokale Hamburger TCG-Shops): robots.txt + Blockade.
- Sobald echte Karten-Produkte auftauchen: `check-url`, Fixture + Test.

## Relevante Stellen
`config/settings.yaml` (matching), `config/sources.yaml`, `monitor/runner.py` (`run_source`, `discover_sitemap`), `monitor/fetcher.py` (`PoliteClient`, Blockade-Erkennung), `monitor/__main__.py` (CLI).

## Learnings
- Rossmann hat aktuell 0 TCG-Produkte in der Sitemap; 0 Treffer ist kein Fehler.
- Filialbestand Hamburg ist nur über interne APIs abrufbar (verboten) – Meldungen zeigen nur Online-Status.
- Lokal: `timeout` fehlt auf macOS; `PYTHONWARNINGS=ignore` unterdrückt LibreSSL-Warnung; `LOG_LEVEL=DEBUG` zeigt Requests; `--state /tmp/x.json` hält den echten Zustand sauber.
