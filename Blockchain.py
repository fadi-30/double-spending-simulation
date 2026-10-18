from Block import Block
from Genesis import genesis_coinbase
from Transaction import Transaction, Coinbase
import hashing
from CONFIG import mining_target
from UTXO import UTXO
import json

the_blockchain = None
def get_blockchain():
    global the_blockchain
    if the_blockchain == None:
        the_blockchain = Blockchain()
    return the_blockchain

class Blockchain:
    def __init__(self):
        # Wir starten mit dem Genesis-Block
        genesis_block = Block("WGKu6bQVONnhrWKY0aT3Dl/YbS49An4i49jfMTvLGVY=", [genesis_coinbase()], 0)
        genesis_block.height = 0
        genesis_hash = genesis_block.get_hash()
        
        # Ein Pool (Dictionary), der ALLE validen Blöcke speichert, die wir je gesehen haben (Key = Block-Hash)
        self.all_blocks = {genesis_hash: genesis_block}
        
        # Der Hash des Blocks, der aktuell das Ende der längsten Kette (Hauptkette) bildet
        self.main_chain_tip = genesis_hash

    @property
    def blocks(self):
        """
        Ein genialer Python-Trick für Abwärtskompatibilität!
        Jedes Mal, wenn dein restlicher Code (z.B. Miner.py) auf 'blockchain.blocks' zugreift,
        bauen wir dynamisch die Liste der Blöcke zusammen, die zur aktuell längsten Kette gehören.
        So müssen wir die anderen Dateien kaum anpassen.
        """
        return self.get_chain_history(self.main_chain_tip)

    def get_chain_history(self, tip_hash):
        """Rekonstruiert eine Kette von einem beliebigen Endblock (tip_hash) rückwärts bis zum Genesis-Block."""
        chain = []
        current_hash = tip_hash
        while current_hash in self.all_blocks:
            block = self.all_blocks[current_hash]
            chain.append(block)                       # hinten anhängen: billig
            current_hash = block.hash_previous_block
        chain.reverse()                               # einmal am Schluss umdrehen
        return chain

    def get_length(self, tip_hash):
        """Kettenlänge ab einem Block, ohne die Kette neu zu bauen."""
        if tip_hash not in self.all_blocks:
            return 0
        return self.all_blocks[tip_hash].height + 1

    def get_topmost_block(self):
        # Liefert den obersten Block der aktuell längsten Kette
        return self.all_blocks[self.main_chain_tip]


    def utxo_zustand(self, block_list):
        #"""Erzeugte und ausgegebene UTXO-Hashes dieser Kette, in einem Durchgang.
        #Die Teilmengen je Block werden gemerkt, weil ein eingefügter Block
        #sich nie mehr ändert."""
        erzeugt = set()
        ausgegeben = set()
        for block in block_list:
            if not hasattr(block, "_erzeugt"):
                b_erzeugt = set()
                b_ausgegeben = set()
                for tx in block.transactions:
                    tx_hash = tx.get_hash()
                    counter = 0
                    for pk in tx.receiver_public_keys:
                        b_erzeugt.add(UTXO(tx_hash, pk, tx.messages[counter]).get_hash())
                        counter = counter + 1
                    if isinstance(tx, Transaction):
                        for u in tx.utxos:
                            b_ausgegeben.add(u.get_hash())
                block._erzeugt = b_erzeugt
                block._ausgegeben = b_ausgegeben
            erzeugt.update(block._erzeugt)
            ausgegeben.update(block._ausgegeben)
        return erzeugt, ausgegeben
    

    def insert_block(self, block):
        if not isinstance(block, Block):
            return False
            
        # 1. Prüfen, ob uns der Vorgängerblock überhaupt bekannt ist (Verhindert verwaiste Blöcke)
        if block.hash_previous_block not in self.all_blocks:
            print(f"[BLOCKCHAIN] Block abgelehnt: Vorgänger-Hash unbekannt!")
            return False

        # 1b. Genau eine Coinbase, und die muss an erster Stelle stehen
        if len(block.transactions) == 0 or not isinstance(block.transactions[0], Coinbase):
            print("[BLOCKCHAIN] Block abgelehnt: keine Coinbase an erster Stelle.")
            return False
        for tx in block.transactions[1:]:
            if isinstance(tx, Coinbase):
                print("[BLOCKCHAIN] Block abgelehnt: mehr als eine Coinbase.")
                return False

        # 1c. Kein UTXO darf innerhalb DESSELBEN Blocks zweimal ausgegeben werden
        #     (weder in zwei Transaktionen noch zweimal in derselben Transaktion)
        gesehene_utxos = set()
        for tx in block.transactions:
            if isinstance(tx, Transaction):
                for utxo in tx.utxos:
                    if utxo.get_hash() in gesehene_utxos:
                        print("[BLOCKCHAIN] Block abgelehnt: UTXO zweimal im selben Block.")
                        return False
                    gesehene_utxos.add(utxo.get_hash())
            
        # 2. Die historische Kette bis genau zu diesem Vorgängerblock rekonstruieren
        history_branch = self.get_chain_history(block.hash_previous_block)
        
        # 3. Transaktionen NUR gegen diesen spezifischen historischen Zweig validieren
        erzeugt, ausgegeben = self.utxo_zustand(history_branch)
        for tx in block.transactions:
            if not tx.is_valid():
                return False
            if isinstance(tx, Transaction):
                for utxo in tx.utxos:
                    h = utxo.get_hash()
                    if h not in erzeugt or h in ausgegeben:
                        print(f"[BLOCKCHAIN] Block abgelehnt: UTXO ungültig auf diesem Zweig.")
                        return False
                        
        # 4. Proof of Work (Target-Kriterium) prüfen
        if not self.check_against_target(block.get_hash()):
            return False
            
        # 5. Block speichern und Höhe setzen
        vorgaenger = self.all_blocks[block.hash_previous_block]
        block.height = vorgaenger.height + 1
        self.all_blocks[block.get_hash()] = block
        
        # 6. DIE LONGEST-CHAIN-RULE, jetzt ohne Nachzählen
        if block.height > self.all_blocks[self.main_chain_tip].height:
            if self.main_chain_tip != block.hash_previous_block:
                print(f"\n[⚠️ REORGANISATION] Ein alternativer Zweig ist länger geworden! Neue Hauptkette, Länge: {block.height + 1}")
            self.main_chain_tip = block.get_hash()
            
        return True

    def check_against_target(self, hash_string):
        import base64
        try:
            raw_bytes = base64.b64decode(hash_string)
            real_hex = raw_bytes.hex()
            return real_hex.startswith("0" * mining_target)
        except Exception:
            return False

    def get_utxos(self, public_key):
        # Da self.blocks dynamisch die Hauptkette zurückgibt, 
        # sucht diese Funktion automatisch nach UTXOs auf der aktuell gültigen Kette.
        utxos = []
        for block in self.blocks:
            for tx in block.transactions:
                counter = 0
                for pk in tx.receiver_public_keys:
                    if pk in public_key:
                        utxo = UTXO(tx.get_hash(), public_key, tx.messages[counter])
                        utxos.append(utxo)
                    counter = counter + 1
        return utxos

    def is_valid_UTXO(self, utxo, block_list=None):
        """Ein Guthaben ist gültig, wenn es auf dieser Kette entstanden und
        noch nicht ausgegeben ist."""
        if block_list is None:
            block_list = self.blocks
        erzeugt, ausgegeben = self.utxo_zustand(block_list)
        h = utxo.get_hash()
        return h in erzeugt and h not in ausgegeben

    def get_json(self):
        blocks = []
        for i in self.blocks:
            blocks.append(i.get_dict())
        return json.dumps({
            "blocks": blocks
        })