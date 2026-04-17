import random
import time
import uuid

# Create fake wallets
wallets = [f"wallet_{i}" for i in range(100)]

def generate_transaction():
    sender = random.choice(wallets)
    receiver = random.choice(wallets)

    # Ensure sender != receiver
    while receiver == sender:
        receiver = random.choice(wallets)

    amount = round(random.uniform(0.01, 5), 4)
    gas_fee = round(random.uniform(0.0001, 0.01), 5)
    timestamp = int(time.time())

    is_fraud = 0

    # 🚨 Fraud Rule 1: High amount
    if amount > 4.5:
        is_fraud = 1

    # 🚨 Fraud Rule 2: Suspicious wallet
    if random.random() < 0.05:
        sender = "fraud_wallet"
        is_fraud = 1

    # 🚨 Fraud Rule 3: Very low gas fee
    if gas_fee < 0.0002:
        is_fraud = 1

    # Fraud Pattern 4: Rapid transactions (bot behavior)
    if random.random() < 0.03:
        amount = round(random.uniform(0.001, 0.01), 5)
        is_fraud = 1

    # Fraud Pattern 5: Same receiver repeatedly (scam wallet)
    if random.random() < 0.03:
        receiver = "scam_wallet"
        is_fraud = 1    

    transaction = {
        "tx_id": str(uuid.uuid4()),
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
        "gas_fee": gas_fee,
        "timestamp": timestamp,
        "is_fraud": is_fraud
    }

    return transaction


# ✅ THIS PART IS IMPORTANT (for testing)
if __name__ == "__main__":
    print("Sample Transaction:")
    print(generate_transaction())

# ✅ STEP 2.5 ADD HERE 👇
def generate_live_transaction():
    return generate_transaction()


# (optional testing block)
if __name__ == "__main__":
    print(generate_transaction())    