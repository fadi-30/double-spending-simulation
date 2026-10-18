import os
import crypto
from Blockchain import get_blockchain
from Transaction import UnsignedTransaction, Transaction
from Mempool import get_mempool
import json
from UTXO import UTXO

class Wallet:
    def __init__(self, neu=False):
        if neu:
            # Frischer Schlüssel, der NICHT gespeichert wird (z.B. für einen Empfänger)
            self.password = crypto.generate_password()
            self.private_key = crypto.generate_private_pem_string(self.password)
        elif os.path.isfile("private_key.json"):
            self.private_key, self.password = self.load_from_file()
        else:
            self.password = crypto.generate_password()
            self.private_key = crypto.generate_private_pem_string(self.password)
            self.save_to_file()
        self.public_key = crypto.generate_public_pem_string(self.private_key, self.password)

    def send_money(self, receiver_pks, msgs):
        money_to_send = 0
        for m in msgs:
            money_to_send = money_to_send + m
        tx = self.create_transaction(self.get_utxos(money_to_send), receiver_pks, msgs)
        self.insert_to_mempool(tx)
        return tx

    def get_utxos(self, money):
        blockchain = get_blockchain()
        erzeugt, ausgegeben = blockchain.utxo_zustand(blockchain.blocks)
        needed_utxos = []
        total_amount = 0
        for i in blockchain.get_utxos(self.public_key):
            h = i.get_hash()
            if h not in erzeugt or h in ausgegeben:
                continue
            needed_utxos.append(i)
            total_amount = total_amount + i.message
            if total_amount >= money:
                break
        return needed_utxos

    def create_transaction(self, utxos, receiver_pks, msgs):
        unsigned = UnsignedTransaction(utxos=utxos, receiver_public_keys=receiver_pks, messages=msgs)
        tx = Transaction(utxos=utxos, receiver_public_keys=receiver_pks, messages=msgs, signature=unsigned.sign(self.private_key, self.password))
        return tx

    def insert_to_mempool(self, tx):
        get_mempool().insert_transaction(tx)

    def save_to_file(self):
        data = {
            "private_key": self.private_key,
            "password": self.password
        }
        with open("private_key.json", "w") as output:
            output.write(json.dumps(data))

    def load_from_file(self):
        with open("private_key.json", "r") as input_file:
            data = json.loads(input_file.read())
            return data["private_key"], data["password"]
