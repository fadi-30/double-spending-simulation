import threading
import random
import os
import json
import requests
import time
from flask import Flask, request, jsonify

from Transaction import Transaction, Coinbase
from CONFIG import *
from Blockchain import get_blockchain
from Mempool import get_mempool
from Block import Block
from UTXO import UTXO
import hashing
import socket

# --- 1. GLOBALER SIMULATIONS-ZUSTAND & CONFIG ---
app = Flask(__name__)

# Die statische PEERS-Liste fliegt raus! Stattdessen ermitteln wir die Peers live:
def get_aktuelles_netzwerk():
    """Fragt das Docker-DNS nach allen aktiven Containern der Services ab."""
    entdeckte_peers = []
    
    # Das sind die Service-Namen, die wir gleich in der docker-compose.yml definieren
    docker_services = ["honest-miner", "attacker-miner"]
    
    for service in docker_services:
        try:
            # getaddrinfo liefert uns ALLE IP-Adressen, die aktuell unter diesem Namen registriert sind!
            infos = socket.getaddrinfo(service, 5000, family=socket.AF_INET, type=socket.SOCK_STREAM)
            for item in infos:
                ip_adresse = item[4][0]
                entdeckte_peers.append(f"http://{ip_adresse}:5000")
        except socket.gaierror:
            # Falls ein Service (z.B. der Attacker) noch nicht gestartet oder offline ist
            pass

    # Optional: Eigene IP herausfinden, damit wir uns nicht selbst anfunken
    try:
        mein_name = socket.gethostname()
        meine_ip = socket.gethostbyname(mein_name)
        entdeckte_peers = [peer for peer in entdeckte_peers if meine_ip not in peer]
    except Exception:
        pass

    return list(set(entdeckte_peers)) # Duplikate entfernen und zurückgeben

# Rolle & Abbruchkriterien aus Docker-Umgebungsvariablen auslesen
MEINE_ROLLE = os.environ.get("MINER_ROLE", "honest") # 'honest' oder 'attacker'
Z_CONFIRMATIONS = int(os.environ.get("Z_CONFIRMATIONS", "3")) # z Bestätigungen
ZAHLBETRAG = int(os.environ.get("ZAHLBETRAG", "1"))    # was der Angreifer dem Händler zahlt
ANGREIFER_ANTEIL = float(os.environ.get("ANGREIFER_ANTEIL", "0.25"))   # q
MAX_RUECKSTAND = abbruch_rueckstand(ANGREIFER_ANTEIL)                  # Abbruch, sobald (q/p)^Rückstand < 0.1 %

# Spezifische Variablen für den Angreifer
IS_ATTACKING = False
PRIVATE_TIP = None       # Das geheime Ende der Angreifer-Kette
FORK_START_HASH = None   # Der Block, ab dem abgezweigt wurde
HONEST_TIP = None        # Die Spitze der öffentlichen ehrlichen Kette (aus Sicht des Angreifers)
PENDING_ATTACK_TX = None # Die betrügerische Double-Spend-Transaktion
LETZTES_ERGEBNIS = None  # "erfolg" oder "abbruch" der letzten Attacke
MINER_WALLET = None      # wird beim Start gesetzt (braucht der Angriffs-Endpunkt)
HAENDLER_WALLET = None   # der 'Händler', der die Zahlung des Angreifers erhält (einmal erzeugt)

print(f"[INITIALISIERUNG] Knoten gestartet als Rolle: '{MEINE_ROLLE.upper()}', q = {ANGREIFER_ANTEIL}, Abbruch bei Rückstand {MAX_RUECKSTAND}")


# --- 2. HELFERFUNKTIONEN FÜR DAS NETZWERK (JSON <-> OBJEKT) ---

def block_to_dict(block):
    tx_list = []
    for tx in block.transactions:
        if isinstance(tx, Coinbase):
            tx_list.append({
                "type": "coinbase",
                "receiver_public_keys": tx.receiver_public_keys,
                "messages": tx.messages,
                "hoehe": tx.hoehe
            })
        else:
            tx_list.append({
                "type": "transaction",
                "utxos": [u.get_dict() for u in tx.utxos],
                "receiver_public_keys": tx.receiver_public_keys,
                "messages": tx.messages,
                "signature": tx.signature
            })
    return {
        "hash_previous_block": block.hash_previous_block,
        "nonce": block.nonce,
        "transactions": tx_list
    }

def dict_to_block(data):
    tx_objects = []
    for tx_data in data["transactions"]:
        if tx_data["type"] == "coinbase":
            cb = Coinbase(tx_data["receiver_public_keys"][0], tx_data["hoehe"])
            tx_objects.append(cb)
        else:
            utxo_objects = []
            for u in tx_data["utxos"]:
                utxo_objects.append(UTXO(u["tx_hash"], u["public_key"], u["message"]))
            tx = Transaction(
                utxos=utxo_objects,
                receiver_public_keys=tx_data["receiver_public_keys"],
                messages=tx_data["messages"],
                signature=tx_data["signature"]
            )
            tx_objects.append(tx)
    return Block(data["hash_previous_block"], tx_objects, data["nonce"])

def broadcast_block(block):
    block_data = block_to_dict(block)
    aktuelle_peers = get_aktuelles_netzwerk() # Live-Abfrage der aktuellen Miner-Flotte
    for peer in aktuelle_peers:
        try:
            requests.post(f"{peer}/neuer_block", json=block_data, timeout=2)
        except requests.exceptions.RequestException:
            pass

def broadcast_transaction(tx):
    tx_data = {
        "type": "transaction",
        "utxos": [u.get_dict() for u in tx.utxos],
        "receiver_public_keys": tx.receiver_public_keys,
        "messages": tx.messages,
        "signature": tx.signature
    }
    aktuelle_peers = get_aktuelles_netzwerk() # Live-Abfrage
    for peer in aktuelle_peers:
        try:
            requests.post(f"{peer}/neue_transaktion", json=tx_data, timeout=2)
        except requests.exceptions.RequestException:
            pass

# --- 3. DIE API-ENDPUNKTE ---

@app.route('/status', methods=['GET'])
def gib_status():
    bc = get_blockchain()
    return jsonify({
        "honest_length": bc.get_length(HONEST_TIP) if HONEST_TIP else 0,
        "attacker_length": bc.get_length(PRIVATE_TIP) if PRIVATE_TIP else 0,
        "main_length": bc.get_length(bc.main_chain_tip),
        "main_tip": bc.main_chain_tip,
        "is_attacking": IS_ATTACKING,
        "letztes_ergebnis": LETZTES_ERGEBNIS
    }), 200

@app.route('/hole_block', methods=['POST'])
def hole_block():
    """Gibt einen Block heraus, damit ein Knoten eine Lücke schliessen kann."""
    daten = request.get_json()
    b = get_blockchain().all_blocks.get(daten.get("hash"))
    if b is None:
        return jsonify({"status": "unknown"}), 404
    return jsonify(block_to_dict(b)), 200


def fehlende_vorgaenger_holen(block):
    """Holt rekursiv die fehlenden Vorgänger vom Netzwerk. Ohne das bleibt ein
    Knoten, der einen einzigen Block verpasst, für immer abgehängt."""
    bc = get_blockchain()
    peers = get_aktuelles_netzwerk()
    fehlend = []
    aktuell = block.hash_previous_block
    while aktuell not in bc.all_blocks:
        if len(fehlend) > 10000:
            return False
        geholt = None
        for peer in peers:
            try:
                r = requests.post(f"{peer}/hole_block", json={"hash": aktuell}, timeout=10)
                if r.status_code == 200:
                    geholt = dict_to_block(r.json())
                    break
            except requests.exceptions.RequestException:
                pass
        if geholt is None:
            print("[SYNC] Vorgängerblock nicht auffindbar, Lücke bleibt bestehen.")
            return False
        fehlend.append(geholt)
        aktuell = geholt.hash_previous_block
    if fehlend:
        print(f"[SYNC] Schliesse Lücke von {len(fehlend)} Blöcken ...")
    for b in reversed(fehlend):          # ältester zuerst
        if not bc.insert_block(b):
            print("[SYNC] Nachgeholter Block ungültig, Abbruch.")
            return False
        get_mempool().remove_transactions(b.transactions)
    return True


@app.route('/neuer_block', methods=['POST'])
def empfange_block():
    global HONEST_TIP
    data = request.get_json()
    try:
        empfangener_block = dict_to_block(data)

        if empfangener_block.get_hash() in get_blockchain().all_blocks:
            return jsonify({"status": "already_have_it"}), 200

        if empfangener_block.hash_previous_block not in get_blockchain().all_blocks:
            if not fehlende_vorgaenger_holen(empfangener_block):
                return jsonify({"status": "rejected", "reason": "Vorgänger fehlen"}), 400

        success = get_blockchain().insert_block(empfangener_block)
        if success:
            get_mempool().remove_transactions(empfangener_block.transactions)
            aktueller_index = empfangener_block.height
            print(f"[API] -> Block #{aktueller_index} von Netzwerk übernommen! (Hash: {empfangener_block.get_hash()[:15]}...)")
            
            # Falls ich der Angreifer bin, halte ich so Schritt mit der ehrlichen Kette
            if MEINE_ROLLE == "attacker":
                if HONEST_TIP is None or get_blockchain().get_length(empfangener_block.get_hash()) > get_blockchain().get_length(HONEST_TIP):
                    HONEST_TIP = empfangener_block.get_hash()

            return jsonify({"status": "accepted"}), 200
        else:
            return jsonify({"status": "rejected", "reason": "Ungültiger Block"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/neue_transaktion', methods=['POST'])
def empfange_transaktion():
    data = request.get_json()
    try:
        utxo_objects = []
        for u in data["utxos"]:
            utxo_objects.append(UTXO(u["tx_hash"], u["public_key"], u["message"]))
        tx = Transaction(
            utxos=utxo_objects,
            receiver_public_keys=data["receiver_public_keys"],
            messages=data["messages"],
            signature=data["signature"]
        )
        if tx.is_valid():
            get_mempool().insert_transaction(tx)
            return jsonify({"status": "accepted"}), 200
        return jsonify({"status": "rejected"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/angriff_vorbereiten', methods=['POST'])
def angriff_vorbereiten():
    """Wird von Main.py aufgerufen. Baut die zwei Konflikt-Transaktionen und startet die Attacke."""
    global IS_ATTACKING, PRIVATE_TIP, FORK_START_HASH, PENDING_ATTACK_TX, HONEST_TIP, LETZTES_ERGEBNIS, HAENDLER_WALLET
    if MEINE_ROLLE != "attacker":
        return jsonify({"status": "error", "message": "Ich bin ein ehrlicher Miner!"}), 400
    if IS_ATTACKING:
        return jsonify({"status": "error", "message": "Attacke läuft bereits"}), 400

    bc = get_blockchain()
    utxos = MINER_WALLET.get_utxos(1)          # irgendein unverbrauchtes Guthaben des Angreifers
    if not utxos:
        return jsonify({"status": "error", "message": "Angreifer hat noch kein Guthaben"}), 400
    betrag = sum(u.message for u in utxos)

    # TX 1: Zahlung an den Händler -> geht ans ehrliche Netzwerk
    if HAENDLER_WALLET is None:
        from Wallet import Wallet
        HAENDLER_WALLET = Wallet(neu=True)   # Schlüssel nur einmal erzeugen (kostet Sekunden)
    # Nur ZAHLBETRAG geht an den Händler, der Rest kommt als Wechselgeld zurück.
    # Sonst ist nach jedem gescheiterten Angriff die ganze Belohnung verloren.
    if betrag > ZAHLBETRAG:
        empfaenger = [HAENDLER_WALLET.public_key, MINER_WALLET.public_key]
        betraege = [ZAHLBETRAG, betrag - ZAHLBETRAG]
    else:
        empfaenger = [HAENDLER_WALLET.public_key]
        betraege = [betrag]
    tx_haendler = MINER_WALLET.create_transaction(utxos, empfaenger, betraege)
    broadcast_transaction(tx_haendler)

    # TX 2: dasselbe Guthaben zurück an mich selbst -> kommt nur in meine geheime Kette
    tx_zurueck = MINER_WALLET.create_transaction(utxos, [MINER_WALLET.public_key], [betrag])

    PENDING_ATTACK_TX = tx_zurueck
    FORK_START_HASH = bc.main_chain_tip
    PRIVATE_TIP = bc.main_chain_tip
    HONEST_TIP = bc.main_chain_tip
    LETZTES_ERGEBNIS = None
    IS_ATTACKING = True
    print(f"\n[💥 ATTACKER-API] Starte Double Spend über {min(ZAHLBETRAG, betrag)} Coins! Forke ab Block #{bc.get_length(FORK_START_HASH) - 1}")
    return jsonify({"status": "attack_started"}), 200


# --- 4. DER MINER ---

class Miner:
    def __init__(self, own_public_key):
        self.public_key = own_public_key
        while True:
            self.mine()

    def check_against_target(self, hash_string):
        import base64
        try:
            raw_bytes = base64.b64decode(hash_string)
            real_hex = raw_bytes.hex()
            return real_hex.startswith("0" * mining_target)
        except Exception:
            return False

    def waehle_transaktionen(self, hash_prev):
        """Nur Transaktionen, die auf genau diesem Zweig gültig sind und sich nicht gegenseitig widersprechen."""
        bc = get_blockchain()
        history = bc.get_chain_history(hash_prev)
        erzeugt, ausgegeben = bc.utxo_zustand(history)
        gewaehlt = []
        benutzte_utxos = set()
        for tx in get_mempool().tx:
            if not tx.is_valid():
                continue
            utxo_hashes = [u.get_hash() for u in tx.utxos]
            if any(h in benutzte_utxos for h in utxo_hashes):
                continue                     # widerspricht einer schon gewählten TX
            if len(set(utxo_hashes)) != len(utxo_hashes):
                continue                     # dasselbe UTXO mehrfach in einer TX
            if not all(u.get_hash() in erzeugt and u.get_hash() not in ausgegeben
                       for u in tx.utxos):
                continue                     # auf diesem Zweig schon ausgegeben
            gewaehlt.append(tx)
            benutzte_utxos.update(utxo_hashes)
        return gewaehlt

    def mine(self):

        global IS_ATTACKING, PRIVATE_TIP, FORK_START_HASH, HONEST_TIP, PENDING_ATTACK_TX, LETZTES_ERGEBNIS

        bc = get_blockchain()
        angriff = (MEINE_ROLLE == "attacker" and IS_ATTACKING)

        # Initialisierung der Spitzen
        if HONEST_TIP is None:
            HONEST_TIP = get_blockchain().main_chain_tip
        if PRIVATE_TIP is None:
            PRIVATE_TIP = get_blockchain().main_chain_tip

        # 1. Basis-Block bestimmen
        if angriff:
            hash_prev = PRIVATE_TIP
        else:
            hash_prev = bc.main_chain_tip

        # 2. Transaktionen vorbereiten
        coinbase = Coinbase(self.public_key, get_blockchain().get_length(hash_prev))
        
        if angriff and PENDING_ATTACK_TX:
            # Der Angreifer packt exakt seine Konflikt-TX in seinen ersten geheimen Block
            txs = [coinbase, PENDING_ATTACK_TX]
        else:
            txs = self.waehle_transaktionen(hash_prev)
            txs.insert(0, coinbase)

        versuche = 0
        start = time.time()
        block = Block(hash_prev, txs, 0)                   # Blockvorlage EINMAL bauen; in der Schleife wird nur die Nonce getauscht
        
        while True:
            # Wenn sich der Modus geändert hat (Angriff gestartet/beendet), neu aufsetzen
            if (MEINE_ROLLE == "attacker" and IS_ATTACKING) != angriff:
                break
            if angriff:
                if PRIVATE_TIP != hash_prev:
                    break
                laenge_ehrlich = bc.get_length(HONEST_TIP)
                laenge_private = bc.get_length(PRIVATE_TIP)
                fork_len = bc.get_length(FORK_START_HASH)
                progress_ehrlich = laenge_ehrlich - fork_len
                vorsprung = laenge_ehrlich - laenge_private

                if progress_ehrlich >= Z_CONFIRMATIONS:
                    # Der Händler hat geliefert. Jetzt zählt, wer vorne liegt.
                    if laenge_private > laenge_ehrlich:
                        print(f"\n[💥 SIEG] Angreifer-Kette ({laenge_private}) hat ehrliche Kette ({laenge_ehrlich}) überholt! Veröffentliche geheime Kette ...")
                        for b in bc.get_chain_history(PRIVATE_TIP):
                            if bc.get_length(b.get_hash()) > fork_len:
                                broadcast_block(b)
                        LETZTES_ERGEBNIS = "erfolg"
                        IS_ATTACKING = False
                        PENDING_ATTACK_TX = None
                        break
                    if vorsprung >= MAX_RUECKSTAND:
                        print(f"\n[❌ ABBRUCH] Ehrlich hat z={Z_CONFIRMATIONS} erreicht. Rückstand {vorsprung} Blöcke: Aufholchance unter 0.1 %. Angreifer gibt auf.")
                        LETZTES_ERGEBNIS = "abbruch"
                        IS_ATTACKING = False
                        PENDING_ATTACK_TX = None
                        break
            else:
                if bc.main_chain_tip != hash_prev:
                    break

            # 4. Nonce suchen
            block.nonce = random.randint(0, 99999999999999999999999999999)
            hash_val = block.get_hash()
            versuche += 1
            if versuche % 200000 == 0:
                print(f"[HASHRATE] {versuche / (time.time() - start):,.0f} Versuche/s")
            if self.check_against_target(hash_val):
                success = get_blockchain().insert_block(block)
                if success:
                    get_mempool().remove_transactions(block.transactions)
                    if angriff:
                        PRIVATE_TIP = hash_val
                        print(f"[ATTACKER] 🤫 Geheimen Block gemint! Private Kettenlänge: {get_blockchain().get_length(PRIVATE_TIP)}")
                        PENDING_ATTACK_TX = None
                    else:
                        print(f"[MINER] $$$ BLOCK #{block.height} GEMINT! $$$ Hash: {hash_val[:15]}... -> Sende an Netzwerk...")
                        broadcast_block(block)
                    break
                else:
                    print("[MINER] Eigener Block abgelehnt, stelle Transaktionen neu zusammen.")
                    break

# --- 5. HINTERGRUND-TRANSAKTIONS-GENERATOR ---

def hintergrund_transaktions_generator(miner_wallet):
    if MEINE_ROLLE == "attacker":
        print("[TX-GEN] Angreifer erzeugt keine Hintergrund-Transaktionen (er braucht sein Guthaben für die Attacken).")
        return
    from Wallet import Wallet
    empfaenger = Wallet(neu=True)          # ein echter, fremder Empfänger; einmal erzeugt
    print("[TX-GEN] Hintergrund-Transaktions-Generator gestartet.")
    while True:
        time.sleep(random.randint(4, 8))
        try:
            unverbraucht = miner_wallet.get_utxos(1)
            if not unverbraucht:
                continue
            betrag = unverbraucht[0].message
            neue_tx = miner_wallet.send_money([empfaenger.public_key], [betrag])
            print(f"[TX-GEN] 💸 Automatische Transaktion erzeugt ({betrag} Coins)!")
            broadcast_transaction(neue_tx)
        except Exception as e:
            print(f"[TX-GEN] Fehler beim Erstellen der Hintergrund-TX: {e}")


# --- 6. STARTBLOCK (ENTRYPOINT) ---

if __name__ == "__main__":
    from Wallet import Wallet
    
    print("--- NETZWERK-MINER INITIALISIERUNG ---")
    MINER_WALLET = Wallet()
    
    # 1. Flask Server Thread starten
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    print("[SYSTEM] Flask API-Server läuft im Hintergrund auf Port 5000.")
    
    # 2. Hintergrund-Transaktions-Thread starten
    tx_thread = threading.Thread(
        target=hintergrund_transaktions_generator,
        args=(MINER_WALLET,),
        daemon=True
    )
    tx_thread.start()

    time.sleep(5) # Kurze Pause, damit Flask und TX-Generator starten können
    
    # 3. Haupt-Mining-Schleife starten (Blockiert den Hauptthread)
    miner = Miner(own_public_key=MINER_WALLET.public_key)