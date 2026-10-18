from Transaction import Transaction

the_mempool = None
def get_mempool():
    global the_mempool
    if the_mempool == None:
        the_mempool = Mempool()
    return the_mempool

class Mempool:
    def __init__(self):
        self.tx = []

    def insert_transaction(self, tx):
        assert isinstance(tx, Transaction)
        assert tx.is_valid()
        self.tx.append(tx)

    def remove_transactions(self, txs):
        """Entfernt alle Transaktionen, die in einem angenommenen Block stehen."""
        hashes = set()
        for tx in txs:
            hashes.add(tx.get_hash())
        self.tx = [t for t in self.tx if t.get_hash() not in hashes]