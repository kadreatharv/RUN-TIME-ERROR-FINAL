import random
import time
import uuid

# Fake wallets
wallets = [f"wallet_{i}" for i in range(100)]

# 🔥 MAIN FUNCTION (IMPORTANT)
def generate():
    sender = random.choice(wallets)
    receiver = random.choice(wallets)

    # Ensure sender != receiver
    while receiver == sender:
        receiver = random.choice(wallets)

    amount = round(random.uniform(0.01, 5), 4)
    gas_fee = round(random.uniform(0.0001, 0.01), 5)
    timestamp = int(time.time())

    is_fraud = 0

    # 🚨 Fraud Rules
    if amount > 4.5:
        is_fraud = 1

    if random.random() < 0.05:
        sender = "fraud_wallet"
        is_fraud = 1

    if gas_fee < 0.0002:
        is_fraud = 1

    if random.random() < 0.03:
        amount = round(random.uniform(0.001, 0.01), 5)
        is_fraud = 1

    if random.random() < 0.03:
        receiver = "scam_wallet"
        is_fraud = 1

    # 🔥 IMPORTANT: Backend ke liye required fields
    transaction = {
        "tx_id": str(uuid.uuid4()),
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
        "frequency": random.randint(1, 20),  # ✅ ADD THIS (backend needs it)
        "gas_fee": gas_fee,
        "timestamp": timestamp,
        "is_fraud": is_fraud
    }

    return transaction


# 🔥 Live use ke liye (optional)
def generate_live_transaction():
    return generate()


# 🧪 Testing
if __name__ == "__main__":
    print("Sample Transaction:")
    print(generate())