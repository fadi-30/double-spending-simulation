# Double-Spending-Simulation

Eine lauffähige Blockchain in Python, mit der sich die Erfolgswahrscheinlichkeit eines
Double-Spending-Angriffs **empirisch messen** lässt. Zwei Knoten laufen in getrennten
Docker-Containern und konkurrieren um Blöcke: ein ehrlicher Miner und ein Angreifer,
dessen Rechenanteil `q` frei einstellbar ist.

Entstanden als Maturaarbeit an der Kantonsschule Frauenfeld.

---

## Was die Simulation misst

Satoshi Nakamoto gibt im Bitcoin-Whitepaper (Abschnitt 11) an, mit welcher
Wahrscheinlichkeit ein Angreifer einen Rückstand von `n` Blöcken noch aufholt:

```
(q/p)^n     mit q = Rechenanteil des Angreifers, p = 1 − q
```

Die Simulation spielt dieses Szenario real durch:

1. Der Angreifer überweist einem Händler Geld. Diese Zahlung geht ans ehrliche Netzwerk.
2. Gleichzeitig beginnt er, **im Geheimen** eine eigene Kette zu minen, in der dasselbe
   Guthaben an ihn selbst zurückfliesst.
3. Sobald der Händler `z` Bestätigungen gesehen hat und liefern würde, zählt, wer vorne
   liegt. Ist die geheime Kette länger, veröffentlicht der Angreifer sie: Die Zahlung an
   den Händler wird aus der Geschichte gelöscht, das Geld ist zurück.
4. Fällt seine Aufholchance unter 0.1 %, gibt er auf.

Über viele Runden ergibt sich eine gemessene Erfolgsquote, die sich mit Nakamotos
Rechnung vergleichen lässt.

---

## Voraussetzungen

* **Docker Desktop** (unter Windows mit WSL2-Backend)
* Rund 1.5 Prozessorkerne und 2 GB RAM pro Simulation
* Python wird **nicht** lokal benötigt, alles läuft im Container

---

## Einrichtung

### 1. Ressourcen begrenzen (nur Windows)

Docker nimmt sich unter Windows standardmässig alle Prozessorkerne. Lege eine Datei
`C:\Users\<DeinName>\.wslconfig` an:

```ini
[wsl2]
processors=8
memory=8GB
```

Passe die Werte an deinen Rechner an und lass Windows mindestens zwei Kerne übrig.
Danach in PowerShell:

```bash
wsl --shutdown
```

Anschliessend Docker Desktop neu starten.

> Die Datei lässt sich im Windows-Explorer nicht anlegen, weil ihr Name mit einem Punkt
> beginnt. Verwende VS Code (*Datei → Ordner öffnen* auf dein Benutzerverzeichnis, dann
> *Neue Datei*) oder PowerShell.

### 2. Projekt holen

```bash
git clone <REPOSITORY-URL>
```

---

## Schnellstart

Im Projektordner, Terminal 1:

```bash
docker compose up --build
```

Warte etwa eine Minute, bis beide Knoten Blöcke austauschen. Dann Terminal 2:

```bash
docker compose exec attacker-miner python Main.py
```

Beenden mit `Strg+C` in beiden Terminals, danach:

```bash
docker compose down
```

---

## Parameter einstellen

Alle Parameter stehen in `docker-compose.yml` und müssen bei **beiden** Services
identisch gesetzt sein.

| Variable | Bedeutung |
|---|---|
| `ANGREIFER_ANTEIL` | Rechenanteil `q` des Angreifers (0 bis 1) |
| `Z_CONFIRMATIONS` | Zahl Bestätigungen `z`, die der Händler abwartet |
| `ZAHLBETRAG` | Betrag, den der Angreifer dem Händler zahlt (Standard 1) |

Dazu kommt die **tatsächliche** Rechenleistung, eingestellt über `cpus`. Der ehrliche
Knoten bekommt immer genau `1`, der Angreifer `q / (1 − q)`:

| q | `cpus` beim Angreifer | Abbruch bei Rückstand |
|---|---|---|
| 0.10 | `0.111` | 4 |
| 0.20 | `0.250` | 5 |
| 0.25 | `0.333` | 7 |
| 0.30 | `0.429` | 9 |
| 0.33 | `0.493` | 10 |
| 0.40 | `0.667` | 18 |

> **Wichtig:** `ANGREIFER_ANTEIL` und `cpus` beschreiben dasselbe `q`, werden aber
> getrennt gesetzt und von niemandem gegeneinander geprüft. Passen sie nicht zusammen,
> rechnet der Angreifer mit einer falschen Abbruchschwelle und das Ergebnis ist
> unbrauchbar. Die Startmeldung im Log ist die Kontrolle.

Die Schwierigkeit steht in `CONFIG.py` als `mining_target` (Anzahl führender Nullen im
Hash). Der Wert 5 ergibt etwa 3 bis 5 Sekunden pro Block. Geh nicht unter 4, sonst
verbreiten sich die Blöcke langsamer, als sie entstehen.

---

## Ein Messlauf

1. `docker compose down`, um Reste eines früheren Laufs zu entfernen.
2. Parameter in `docker-compose.yml` setzen (`q`, `z`, `cpus` — an beiden Stellen).
3. `docker compose up --build` und eine Minute warten.
4. In der Startmeldung prüfen, ob `q` und die Abbruchschwelle stimmen.
5. `docker compose exec attacker-miner python Main.py` im zweiten Terminal.
6. Laufen lassen. Für eine Genauigkeit von ±5 Prozentpunkten braucht es etwa
   **150 Runden** pro Messpunkt — das ist Rechenzeit über Nacht.
7. `Strg+C` in Terminal 2 gibt die Zusammenfassung mit der Erfolgsquote aus.

---

## Ausgabe verstehen

**Beim Start** (Terminal 1):

```
[INITIALISIERUNG] Knoten gestartet als Rolle: 'ATTACKER', q = 0.25, Abbruch bei Rückstand 7
```

Stimmt die Schwelle nicht mit der Tabelle oben überein, passen `ANGREIFER_ANTEIL` und
`cpus` nicht zusammen.

**Während des Laufs:**

| Zeile | Bedeutung |
|---|---|
| `[MINER] $$$ BLOCK #… GEMINT!` | Ein Block wurde gefunden und verschickt |
| `[API] -> Block #… von Netzwerk übernommen!` | Block des anderen Knotens akzeptiert |
| `[HASHRATE] … Versuche/s` | Momentane Rechenleistung |
| `[ATTACKER] 🤫 Geheimen Block gemint!` | Der Angreifer verlängert seine geheime Kette |
| `[💥 SIEG]` | Der Angriff war erfolgreich |
| `[❌ ABBRUCH]` | Die Aufholchance fiel unter 0.1 % |
| `[⚠️ REORGANISATION]` | Ein alternativer Zweig wurde zur Hauptkette |
| `[SYNC] Schliesse Lücke von N Blöcken` | Ein verpasster Block wurde nachgefordert — normal |

**Zusammenfassung** (Terminal 2 nach `Strg+C`):

```
=== SIMULATION BEENDET ===
Durchläufe gesamt: 152
Erfolgreiche Angriffe: 19
Erfolgsquote: 12.5%
```

---

## Ergebnisse überprüfen

Die eingestellte Rechenleistung und die tatsächlich erreichte können auseinanderliegen.
Gib in der Auswertung deshalb das **gemessene** `q` an, nicht das eingestellte.

```powershell
$h = (docker compose logs honest-miner   | Select-String -CaseSensitive "BLOCK #" | Measure-Object).Count
$a = (docker compose logs attacker-miner | Select-String -CaseSensitive "BLOCK #|Geheimen Block gemint" | Measure-Object).Count
"empirisches q: {0:N3}" -f ($a/($h+$a))
```

> `Select-String` unterscheidet standardmässig **nicht** zwischen Gross- und
> Kleinschreibung. Ohne `-CaseSensitive` zählt das Muster `BLOCK #` auch die Zeilen
> „Geheimen Block gemint" mit und das Ergebnis fällt zu hoch aus.

Eine Abweichung von wenigen Prozent ist normal: Der Angreifer betreibt auf seinem
Bruchteil eines Kerns auch den Webserver, der alle eingehenden Blöcke prüft.

Zusätzlich prüfen, ob Lücken offen geblieben sind:

```powershell
docker compose logs attacker-miner | Select-String "nicht auffindbar"
```

Diese Zeile darf **nicht** erscheinen. Falls doch, hat ein Knoten einen Block verpasst
und konnte ihn nicht nachfordern — alle Runden ab diesem Zeitpunkt sind unbrauchbar.

---

## Mehrere Messpunkte gleichzeitig

Zwei Simulationen parallel brauchen einen eigenen Projektnamen und einen anderen
Host-Port, sonst überschreibt die zweite die erste. Lege eine zweite Compose-Datei an
(z. B. `docker-compose-b.yml`, mit `ports: - "5001:5000"`) und starte sie so:

```bash
docker compose -p sim-b -f docker-compose-b.yml up --build
```

```bash
docker compose -p sim-b -f docker-compose-b.yml exec attacker-miner python Main.py
```

Achte darauf, dass die Summe aller `cpus`-Werte deutlich unter der Zahl der verfügbaren
Kerne bleibt. Sonst kann Docker die Quoten nicht mehr einhalten und `q` verfälscht sich.

---

## Projektstruktur

| Datei | Inhalt |
|---|---|
| `Miner.py` | Mining-Schleife, Angriffslogik, HTTP-Schnittstelle zwischen den Knoten |
| `Main.py` | Steuert die Messrunden und zählt Erfolge; läuft im Angreifer-Container |
| `Blockchain.py` | Blockprüfung, Longest-Chain-Rule, UTXO-Verwaltung |
| `Block.py` | Blockaufbau und Hash über die Transaktionswurzel |
| `Transaction.py` | Transaktionen, Signaturprüfung, Coinbase |
| `Wallet.py` | Schlüsselverwaltung, Guthabensuche, Transaktionen erstellen |
| `Mempool.py` | Warteschlange unbestätigter Transaktionen |
| `UTXO.py` | Unverbrauchte Transaktionsausgänge |
| `crypto.py` | RSA-4096-Signaturen |
| `hashing.py` | SHA3-256 |
| `Genesis.py` | Erster Block der Kette |
| `CONFIG.py` | Schwierigkeit und Abbruchkriterium |
| `docker-compose.yml` | Die zwei Knoten und ihre Rechenanteile |
| `Dockerfile` | Container-Abbild |

---

## Umsetzung und Vereinfachungen

Die Simulation bildet die wesentlichen Mechanismen von Bitcoin nach: Proof of Work,
UTXO-Modell, Signaturprüfung, die Longest-Chain-Rule mit Reorganisation, und einen
Blockkopf, dessen Hash über eine Transaktionswurzel gebildet wird (wie Bitcoins
Merkle-Root). Bewusst vereinfacht sind:

* **Zwei Parteien statt vieler Knoten.** Nakamotos Modell kennt genau `q` und `p = 1 − q`.
  Ein einzelner ehrlicher Knoten bildet das „ehrliche Netzwerk" sauberer ab als mehrere,
  die sich gegenseitig Blöcke wegschnappen.
* **Feste Schwierigkeit.** Es gibt keine Anpassung der Difficulty.
* **Verwaiste Transaktionen gehen verloren.** Echte Knoten legen die Transaktionen eines
  verworfenen Zweigs zurück in den Mempool, hier verschwinden sie.
* **Kein Transaktionsgebühren-Markt**, feste Blockbelohnung von 50 Coins.
* **Netzwerk über HTTP** statt eines echten P2P-Protokolls. Fehlende Blöcke werden beim
  Peer einzeln nachgefordert.

---

## Fehlerbehebung

**`port is already allocated`** — ein alter Container läuft noch. `docker compose down`,
dann neu starten.

**`[SIMULATION] warte, bis beide Knoten synchron sind …` hört nicht auf** — die Knoten
sehen sich nicht. Beide Logs anschauen; der Angreifer muss
`[API] -> Block #… von Netzwerk übernommen!` zeigen. Notfalls `docker compose down` und
beide zusammen neu starten.

**`Angreifer hat noch kein Guthaben`** — der Angreifer hat noch keinen Block gefunden.
Bei kleinem `q` dauert das; `Main.py` versucht es alle drei Sekunden erneut.

**Beide Knoten lehnen gegenseitig alles ab** — vermutlich derselbe Schlüssel in beiden
Containern. `private_key.json` aus dem Projektordner löschen, prüfen dass die Datei in
`.dockerignore` steht, und neu bauen.

**Die Hashrate schwankt stark** — andere Programme, Browser-Tabs, Windows-Updates. Für
eine Messreihe möglichst nichts anderes laufen lassen.

---

## Hinweis für den Nachbau

`private_key.json` entsteht, sobald ein Knoten startet, und gehört **nicht** ins
Repository. Die Datei steht bereits in `.dockerignore`, damit nicht beide Container
denselben Schlüssel erhalten. Für Git empfiehlt sich eine `.gitignore` mit:

```
private_key.json
__pycache__/
```
