import time
import requests

# Dieses Skript läuft IM Angreifer-Container:
#   docker compose exec attacker-miner python Main.py
ANGREIFER = "http://localhost:5000"
EHRLICH   = "http://honest-miner:5000"

def status(url):
    try:
        return requests.get(f"{url}/status", timeout=2).json()
    except requests.exceptions.RequestException:
        return None

def warte_auf_sync():
    """Wartet, bis beide Knoten dieselbe Kettenspitze haben."""
    while True:
        a, e = status(ANGREIFER), status(EHRLICH)
        if a and e and a["main_tip"] == e["main_tip"]:
            return a["main_length"]
        print("[SIMULATION] warte, bis beide Knoten synchron sind ...")
        time.sleep(3)

if __name__ == "__main__":
    print("=== DOUBLE SPENDING SIMULATION MANAGER ===")
    durchlaeufe = 0
    erfolge = 0
    try:
        while True:
            # Erst nachsehen, ob schon eine Attacke laeuft (z.B. nach einem Timeout).
            # Waehrend einer Attacke sind die Knoten nie synchron, deshalb VOR warte_auf_sync.
            s = status(ANGREIFER)
            if s and s["is_attacking"]:
                durchlaeufe += 1
                print(f"\n--- RUNDE {durchlaeufe} lief bereits, wird mitverfolgt ---")
            else:
                laenge = warte_auf_sync()
                try:
                    antwort = requests.post(f"{ANGREIFER}/angriff_vorbereiten", timeout=180).json()
                except requests.exceptions.RequestException as e:
                    print(f"[SIMULATION] Angreifer antwortet nicht ({e}) -> warte 3 s")
                    time.sleep(3)
                    continue
                if antwort.get("status") != "attack_started":
                    print(f"[SIMULATION] noch kein Angriff möglich: {antwort.get('message')} -> warte 3 s")
                    time.sleep(3)
                    continue
                durchlaeufe += 1
                print(f"\n--- RUNDE {durchlaeufe} gestartet (Kettenlänge {laenge}) ---")

            while True:
                time.sleep(2)
                s = status(ANGREIFER)
                if not s:
                    continue
                if not s["is_attacking"]:
                    break
                print(f"[SIMULATION] ehrlich: {s['honest_length']}  geheim: {s['attacker_length']}")

            if s["letztes_ergebnis"] == "erfolg":
                erfolge += 1
                print(f"[SIMULATION] 💥 Runde {durchlaeufe}: ATTACKE ERFOLGREICH")
            else:
                print(f"[SIMULATION] ❌ Runde {durchlaeufe}: Angriff gescheitert")
            print(f"[SIMULATION] Zwischenstand: {erfolge} von {durchlaeufe} erfolgreich")
    except KeyboardInterrupt:
        print("\n\n=== SIMULATION BEENDET ===")
        print(f"Durchläufe gesamt: {durchlaeufe}")
        print(f"Erfolgreiche Angriffe: {erfolge}")
        if durchlaeufe:
            print(f"Erfolgsquote: {erfolge / durchlaeufe:.1%}")
