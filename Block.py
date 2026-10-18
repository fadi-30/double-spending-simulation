import json, hashing

class Block:
    def __init__(self, hash_previous_block, transactions, nonce):
        self.transactions = transactions
        self.hash_previous_block = hash_previous_block
        self.nonce = nonce
        self.height = 0   # wird beim Einfügen in die Blockchain gesetzt (Genesis = 0)

    def get_tx_root(self):
        # Wie Bitcoins Merkle-Wurzel: fasst alle Transaktionen zu EINEM Hash zusammen.
        # Transaktionen ändern sich nach dem Erstellen nie, also genügt eine Berechnung.
        if not hasattr(self, "_tx_root"):
            hashes = [t.get_hash() for t in self.transactions]
            self._tx_root = hashing.hash(json.dumps(hashes))
        return self._tx_root

    def get_hash(self):
        return hashing.hash(json.dumps(self.get_dict()))

    def get_dict(self):
        return {
            "tx_root": self.get_tx_root(),
            "hash_previous_block": self.hash_previous_block,
            "nonce": self.nonce
        }