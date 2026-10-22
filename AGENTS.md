# AGENTS.md – Arbeitsanleitung für KI-Assistenten (auch kleine Modelle)

Dieses Repo ist ein **legaler** Verfügbarkeits-Monitor für Pokémon-TCG-Produkte
(Region: Hamburg). Er läuft alle 10 Minuten in GitHub Actions und schickt
Push-Nachrichten über **ntfy**.

Lies diese Datei komplett, bevor du etwas änderst. Die meisten Aufgaben sind
**reine Konfigurationsänderungen** in `config/` – Code musst du fast nie anfassen.

---

## 1. Rechtliche Leitplanken (NIEMALS ändern oder umgehen)

Wenn eine Aufgabe einen dieser Punkte verletzen würde: **nicht umsetzen**,
sondern dem Nutzer erklären, warum, und die legale Alternative nennen.

1. **robots.txt wird immer befolgt.** `fetcher.PoliteClient.get()` prüft das vor
   jedem Abruf. Diese Prüfung nie entfernen, nie `allowed()` überschreiben.
2. **Ehrlicher User-Agent** (`settings.yaml: user_agent`). Keinen Browser-UA
   (z. B. "Mozilla/5.0 … Chrome") eintragen, keine Rotation.
3. **Keine Umgehung von Schutzmaßnahmen**: keine Proxys, keine IP-Rotation,
   keine Captcha-Löser, kein "undetected-chromedriver", keine Cookies/Logins
   fremder Konten, keine Header-Tricks. Blockade (401/403/429/Captcha) ⇒ die
   Quelle wird automatisch pausiert. Das ist gewollt. (§ 202a StGB, AGB)
4. **Keine nicht-öffentlichen/internen APIs** ("Backend", `/api/`-Pfade,
   GraphQL-Endpunkte aus den DevTools). Nur öffentliche Seiten, Sitemaps und
   offiziell dokumentierte APIs.
5. **Last begrenzen**: `min_delay_seconds` ≥ 3, `every_minutes` und
   `product_every_minutes` ≥ 5, `max_product_checks` ≤ 60. `validate` prüft das.
6. **Kein automatisches Kaufen** (kein Warenkorb, kein Checkout, keine Bots).
   Der Monitor meldet nur.
7. **Pokémon Center** (pokemoncenter.com) wird nicht automatisiert – nur
   Newsletter/"Benachrichtigen"-Button. `validate` lehnt es ab.
8. **Nicht massenhaft Daten speichern/weitergeben** (Datenbankrecht § 87b UrhG):
   nur Pokémon-TCG-Produkte, nur Status/Preis/Name.

---

## 2. Aufbau

```
config/settings.yaml   globale Einstellungen + Relevanzfilter (matching)
config/sources.yaml    die Shops/Quellen  <- hier passieren 90 % der Änderungen
monitor/
  __main__.py          CLI: run | validate | check-url | robots | report | test-notify
  runner.py            Ablauf eines Laufs (Entdecken -> Produktprüfung -> Ereignisse)
  fetcher.py           höflicher HTTP-Client (robots.txt, Drosselung, Blockade-Erkennung)
  robots.py            robots.txt-Parser nach RFC 9309 (mit * und $ – urllib kann das nicht)
  parsing.py           Sitemap-, Listing-, Produktseiten-Parser (rein, ohne Netzwerk)
  matching.py          Ist URL/Name ein Pokémon-TCG-Produkt?
  notify.py            ntfy-Push (Einzel- oder Sammelmeldung)
  state.py             Zustand (JSON) + Zeitfunktionen
tests/                 unittest + Fixtures (kein Netzwerk)
.github/workflows/
  monitor.yml          alle 10 Min; Zustand auf Branch `state`
  tests.yml            Tests bei jedem Push
  keepalive.yml        monatlicher Commit, damit GitHub den Cron nicht abschaltet
```

### Ablauf eines Laufs
1. Für jede aktive Quelle: wenn pausiert (`blocked_until`) ⇒ überspringen.
2. **Entdecken** (nur wenn `every_minutes` vorbei):
   - `sitemap`: Index laden ⇒ Unter-Sitemaps nach `child_include` filtern ⇒
     unveränderte (gleiches `lastmod`) überspringen ⇒ URLs mit `matching` filtern.
   - `listing`: Übersichtsseiten laden ⇒ Links nach `link_pattern`.
   - Erster Lauf einer Quelle = **Baseline** (keine "Neu"-Meldungen).
3. **Produktprüfung**: bis zu `max_product_checks` fällige Produktseiten laden,
   Status ermitteln: JSON-LD `offers.availability` ⇒ Meta-Tag ⇒ Regex-Fallback.
4. **Ereignisse**: `available` (war ausverkauft/vorbestellbar ⇒ jetzt kaufbar),
   `preorder`, `new_listing` (neu gefunden), `blocked`, `error` (nach 3 Fehlern).
5. ntfy senden, Zustand speichern.

Status-Werte: `available`, `preorder`, `unavailable`, `unknown`.

---

## 3. Häufige Aufgaben (Rezepte)

Nach JEDER Änderung ausführen:
```bash
python -m monitor validate
python -m unittest discover -s tests -t .
```

### 3.1 Neue Quelle (Shop) hinzufügen
1. `https://SHOP/robots.txt` öffnen: `Sitemap:`-Zeilen notieren, `Disallow`-Regeln
   lesen. Einzelne URLs prüfen mit `python -m monitor robots <URL>`.
2. Hat der Shop eine Sitemap, deren Produkt-URLs den Namen enthalten
   (z. B. `/p/pokemon-booster-display-123`)? ⇒ Typ `sitemap`.
   Sonst eine öffentliche, per robots.txt erlaubte Kategorieseite ⇒ Typ `listing`.
   **Suchseiten sind meist per robots.txt gesperrt – dann nicht verwenden.**
3. Eine echte Produktseite testen:
   `python -m monitor check-url https://SHOP/produkt-url`
   - `Status: available/unavailable (jsonld)` ⇒ perfekt, nichts weiter nötig.
   - `Status: unknown (none)` ⇒ im HTML einen eindeutigen Text für "ausverkauft"
     bzw. "in den Warenkorb" suchen und als Regex in `out_of_stock_patterns` /
     `in_stock_patterns` eintragen.
   - `Blocked` ⇒ Shop blockt Bots. **Quelle nicht hinzufügen.**
4. Block in `config/sources.yaml` kopieren (z. B. den von `mueller`), `id`,
   `name`, URLs, `child_include`, `region_hint` anpassen. Kommentar mit Datum der
   robots.txt-Prüfung dazuschreiben.
5. `validate` + Tests, committen. Im GitHub-Tab "Actions" ⇒ `monitor` ⇒
   "Run workflow" mit `source = <id>` manuell testen.

### 3.2 Thalia aktivieren
In `sources.yaml` bei `thalia` die Platzhalter-URL durch die echte
Kategorie-URL ersetzen (muss `/kategorie/` enthalten, NICHT `/suche`) und
`enabled: true` setzen.

### 3.3 Falsche oder fehlende Treffer
- Unerwünschtes Produkt gemeldet ⇒ Begriff zu `matching.exclude_any` (settings.yaml).
- Produkt fehlt ⇒ prüfen, ob URL/Name einen Begriff aus `required_any` UND
  `product_any` enthält; ggf. Begriff zu `product_any` ergänzen.
- Vergleiche sind klein geschrieben und ohne Akzente (`normalize()`):
  "Plüsch" ⇒ "plusch", "Pokémon" ⇒ "pokemon".
- Neuer Testfall dazu in `tests/test_units.py::MatchingTest`.

### 3.4 Quelle ist "pausiert" / "blockiert"
Nicht umgehen (siehe Leitplanke 3). Optionen: `every_minutes` erhöhen,
`max_product_checks` senken, oder Quelle mit `enabled: false` abschalten.
Die Pause hebt sich nach `block_pause_hours` von selbst auf.

### 3.5 Status wird nicht erkannt (viele `unknown`)
`python -m monitor report` zeigt `methode:none`. Dann wie in 3.1 Schritt 3
Regex-Fallbacks ergänzen. Für neue Seitentypen: HTML als Fixture in
`tests/fixtures/` speichern und einen Test in `ParsingTest` schreiben.

### 3.6 Zustand zurücksetzen
Branch `state` auf GitHub löschen ⇒ nächster Lauf startet mit neuer Baseline.

---

## 4. Code-Regeln
- Python 3.12, nur Abhängigkeiten aus `requirements.txt` (requests, PyYAML,
  defusedxml). Keine neuen Abhängigkeiten ohne Grund; **kein Selenium/Playwright**.
- Tests nur mit `unittest` und `tests/helpers.FakeSession` – Tests dürfen nie
  ins Internet.
- Neue Shop-Logik bevorzugt als Konfiguration, nicht als Sonderfall im Code.
- Ein Fehler in einer Quelle darf nie den ganzen Lauf abbrechen (`run_source`).
- Lauf muss in < 8 Minuten fertig sein (Workflow-Timeout 9 Min). Grob:
  Sekunden ≈ (Sitemap-Dateien + Σ max_product_checks) × 3.
- Commit-Nachrichten kurz auf Deutsch.

## 5. Benachrichtigungen (ntfy)
GitHub-Secrets: `NTFY_TOPIC` (Pflicht, geheim halten), optional `NTFY_SERVER`,
`NTFY_TOKEN`, `CONTACT` (Kontakt im User-Agent). Test lokal:
`NTFY_TOPIC=... python -m monitor test-notify`.
Prioritäten: available 5, preorder 4, new_listing 3, blocked/error 2.
