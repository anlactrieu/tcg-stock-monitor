# HANDOVER – Stand 22.10.2026 (Claude Code)

Lies zuerst **AGENTS.md** (Regeln, Architektur, Rezepte). Die rechtlichen Leitplanken
in Abschnitt 1 sind verbindlich und dürfen nicht abgeschwächt werden.

## Was fertig ist
- Monitor-Engine (`monitor/`): Sitemap-/Listing-Entdeckung, Produktstatus über JSON-LD,
  Meta-Tags und Regex-Fallback, RFC-9309-robots.txt-Prüfung (inkl. Wildcards und
  Weiterleitungen), Drosselung, Erkennung von Blockaden mit 24-h-Pause, Zeitbudget
  pro Lauf, ntfy-Push.
- Konfiguration: `config/settings.yaml` (Filter) und `config/sources.yaml`
  (nur Müller aktiv; Rossmann, Smyths und Thalia wegen Bot-Schutz aus; Thalia mit Platzhalter, deaktiviert; Watchlist leer).
- GitHub-Workflows: `monitor.yml` (alle 10 Min, Zustand auf Branch `state`),
  `tests.yml`, `keepalive.yml`, `notify-test.yml`.
- 39 Unit-Tests (`python3 -m unittest discover -s tests -t .`), alle grün.
- Code-Review durch einen Opus-Agenten; alle 12 Befunde behoben.

## Nicht verifiziert (wichtig!)
Aus der Cowork-Sandbox waren die Shop-Domains nicht erreichbar. **Es gab noch keinen
einzigen echten Abruf.** Bekannt aus robots.txt bzw. Sitemaps (über ein Web-Tool gelesen):
- rossmann.de: Index `/de/sitemap_index.xml` mit `Product-0..6.xml`, kein lastmod im
  Index. URLs `/de/<kategorie>-<name>/p/<EAN>`. `/de/search/*` und `/*?*` gesperrt.
- mueller.de: `/sitemaps/sitemap.xml` mit `pdp-sitemap…`. URLs `/p/<name>-PPN…/`.
- smythstoys.com: `/de/de-de/sitemap.xml` mit `product-de-eur.xml`, selten aktualisiert.
- thalia.de: Artikel-URLs ohne Namen (`/shop/home/artikeldetails/A…`), `/suche`
  gesperrt, `/kategorie/` erlaubt. Die richtige Kategorie-URL fehlt noch.

## Live-Check 22.10.2026 (erledigt)
- venv eingerichtet, 39 Tests grün, Archiv gelöscht.
- **rossmann** (AUS seit 22.10. nachmittags): Produktseiten liefern JS-"Client Challenge" (HTTP 200, kein Status lesbar) -> Marker in `fetcher.CHALLENGE_MARKERS` ergänzt + Test, Quelle deaktiviert. Davor: robots/Sitemaps laden (7 Dateien, ~25 s). Aktuell KEINE Pokémon-Karten in der Sitemap (nur Figuren/Puzzle/Plüsch) – 0 Treffer ist korrekt. Neue Produkte würden gemeldet.
- **mueller**: Sitemap + JSON-LD-Status funktionieren (Methode jsonld). Filter war zu locker (Deck-Boxen, Hüllen, DVDs, Gläser) -> `exclude_any` ergänzt. Aktuell 0 echte Karten-Produkte.
- **smyths**: Bot-Challenge auf sitemap.xml -> `enabled: false` (nicht umgehen).
- **thalia**: 403 "Sicherheits-Check" schon bei robots.txt -> bleibt `enabled: false`.
- **MediaMarkt/Saturn**: robots erlaubt Produktseiten, aber 146 Sitemap-Dateien à 10.000 URLs ohne lastmod = zu schwer für den 10-Min-Takt. Nur sinnvoll über `watchlist` (einzelne Produkt-URLs).
- Filialbestand Hamburg ist über öffentliche Seiten nicht abrufbar (nur interne APIs, verboten). Die Meldung zeigt Online-Status + Link, Filiale in der Shop-App prüfen.

## Offene Aufgaben (in dieser Reihenfolge)
1. GitHub: öffentliches Repo anlegen + pushen, Secret `NTFY_TOPIC` (vom Nutzer), Workflow-Schreibrechte, `notify-test` und `monitor` starten (siehe Befehle unten).
2. Weitere Quellen nach AGENTS.md 3.1 prüfen (Galeria, Spiele Max, Kaufland, lokale Hamburger TCG-Shops): jeweils robots.txt + Blockade.
3. Sobald Karten-Produkte in den Sitemaps auftauchen: `check-url` auf echte Booster/Top-Trainer-Box-Seite, Fixture + Test anlegen.
4. Optional: Story-Vorlagen für Instagram (nach Rücksprache).

```
gh repo create tcg-stock-monitor --public --source . --push
gh secret set NTFY_TOPIC
gh api -X PUT repos/{owner}/tcg-stock-monitor/actions/permissions/workflow -f default_workflow_permissions=write
gh workflow run notify-test ; gh workflow run monitor ; gh run watch
```

## Nutzerwünsche
- Deutsch, prägnant. Kein Telegram, Benachrichtigung per ntfy. Kostenlose GitHub Actions.
- Die Doku soll so bleiben, dass später auch kleinere Modelle damit weiterarbeiten
  können. Neue Erkenntnisse in AGENTS.md eintragen, diese Datei hier aktuell halten.
- Strikt legal: keine Umgehung von Schutzmaßnahmen, keine internen APIs, kein Auto-Kauf.
