# TCG-Stock-Monitor (Hamburg)

Meldet per Push aufs Handy, wenn bei **Rossmann, Müller, Smyths Toys und Thalia**
neue Pokémon-TCG-Produkte gelistet werden oder wieder verfügbar sind.
Läuft kostenlos alle 10 Minuten in **GitHub Actions**. Benachrichtigt wird über **ntfy**,
eine kostenlose Push-App ohne Account.

**Legal by design:** Der Monitor liest nur öffentliche Seiten und Sitemaps. robots.txt
wird automatisch befolgt, der User-Agent ist ehrlich und die Abrufe sind gedrosselt.
Schutzmaßnahmen werden nicht umgangen, gekauft wird nicht automatisch. Blockt ein Shop,
pausiert die Quelle von selbst. Details: [AGENTS.md](AGENTS.md#1-rechtliche-leitplanken-niemals-ändern-oder-umgehen).

---

## Einrichtung (ca. 15 Minuten, einmalig)

### 1. ntfy-App einrichten
1. App **„ntfy“** installieren (iOS App Store / Google Play, kostenlos).
2. Einen geheimen, zufälligen Topic-Namen erzeugen. Er funktioniert wie ein Passwort,
   denn jeder, der ihn kennt, kann mitlesen. Im Mac-Terminal:
   ```bash
   echo "tcg-hh-$(openssl rand -hex 8)"
   ```
3. In der App: **+** → **Subscribe to topic** → Namen eintragen → Subscribe.

### 2. GitHub-Repository anlegen
1. Auf github.com: **New repository** → Name `tcg-stock-monitor` → **Public** →
   *ohne* README → Create.
   > Warum öffentlich? GitHub Actions ist für öffentliche Repos unbegrenzt kostenlos.
   > Private Repos haben 2.000 Minuten pro Monat, das reicht für einen Lauf alle
   > 10 Minuten nicht. Geheimnisse (dein ntfy-Topic) liegen trotzdem sicher in den Secrets.
2. Im Mac-Terminal im Projektordner:
   ```bash
   cd ~/Projekte/tcg-stock-monitor
   git init -b main
   git add .
   git commit -m "TCG-Monitor: erste Version"
   git remote add origin https://github.com/DEIN-NAME/tcg-stock-monitor.git
   git push -u origin main
   ```

### 3. Secrets & Rechte setzen
Im Repo: **Settings → Secrets and variables → Actions → New repository secret**
| Name | Wert |
|---|---|
| `NTFY_TOPIC` | dein Topic aus Schritt 1 (Pflicht) |
| `CONTACT` | optional: Kontakt für den User-Agent, z. B. deine E-Mail |

Dann **Settings → Actions → General → Workflow permissions** auf
**„Read and write permissions“** stellen → Save.

### 4. Testen
1. Tab **Actions** → Workflow **notify-test** → **Run workflow**. Dein Handy sollte
   „Benachrichtigungen funktionieren ✅“ zeigen.
2. Workflow **monitor** → **Run workflow**. Der erste Lauf legt nur eine
   **Baseline** an (keine Meldungen). Ab dann meldet er Neues.
3. Im Log von „Übersicht“ siehst du, wie viele Produkte je Shop erkannt wurden.

### 5. Thalia aktivieren (optional)
Thalia-URLs enthalten keine Produktnamen, deshalb braucht es eine Kategorieseite.
Öffne thalia.de → Spielwaren → Sammelkarten → Pokémon, kopiere die URL (sie muss
`/kategorie/` enthalten) und trage sie in `config/sources.yaml` bei `thalia` ein.
Dann `enabled: true` setzen und committen.

---

## Was du gemeldet bekommst
| Meldung | Bedeutung | Priorität |
|---|---|---|
| 🟢 **Jetzt verfügbar** | war ausverkauft/vorbestellbar und ist jetzt online kaufbar | dringend |
| 🔵 **Vorbestellbar** | Vorbestellung möglich | hoch |
| 🆕 **Neu gelistet** | neue Produktseite aufgetaucht (oft vor Verkaufsstart) | normal |
| ⚠️ **Quelle pausiert / fehlerhaft** | Shop blockt oder Seite geändert, siehe Logs | niedrig |

Jede Meldung hat einen Link zum Produkt und einen Hinweis für Hamburg, z. B. wo du den
Filialbestand prüfst.

## Grenzen (ehrlich)
- **Filialbestand Hamburg**: Ein Echtzeit-Bestand pro Filiale wäre nur über interne
  Shop-Schnittstellen abrufbar, und die nutzt dieser Monitor bewusst nicht. Gemeldet
  wird die öffentliche Online-Verfügbarkeit. Den Filialbestand prüfst du danach in
  der App bzw. auf der Produktseite.
- **Pokémon Center** wird nicht automatisiert, dort gilt starker Bot-Schutz und es
  gibt Nutzungsbedingungen. Nutze deren Newsletter und den „Benachrichtigen“-Button.
- **GitHub-Cron** läuft nicht auf die Minute genau, Verzögerungen von 5–15 Minuten
  sind normal.
- Manche Shops blocken Server-IPs (auch die von GitHub). Die Quelle pausiert dann
  automatisch. Das ist gewollt.
- GitHubs Nutzungsbedingungen sehen Actions für Aufgaben rund um das Software-Projekt
  vor. Kleine Monitoring-Jobs wie dieser sind verbreitet, ein Restrisiko bleibt
  aber. Ausweichoption: dasselbe Projekt per `cron` auf einem Raspberry Pi.

## Lokal ausführen (optional)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m monitor validate
python -m monitor run --dry-run --source rossmann     # ohne Push, ohne Speichern
python -m monitor check-url "https://www.rossmann.de/de/…/p/…"
python -m unittest discover -s tests -t .
```

## Weiterentwickeln mit KI
Alle Regeln, die Architektur und Schritt-für-Schritt-Rezepte stehen in
[AGENTS.md](AGENTS.md). Gib einem Assistenten (auch einem kleinen Modell) einfach
den Auftrag, z. B. „Füge Galeria als Quelle hinzu, folge AGENTS.md“.
