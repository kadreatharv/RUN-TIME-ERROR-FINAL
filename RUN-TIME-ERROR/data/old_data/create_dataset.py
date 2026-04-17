import pandas as pd
from generator import generate_transaction

print("🚀 Generating dataset...")

data = []

# Generate 5000 transactions
for _ in range(5000):
    txn = generate_transaction()
    data.append(txn)

# Convert to DataFrame
df = pd.DataFrame(data)

# Add extra features
df["hour"] = pd.to_datetime(df["timestamp"], unit='s').dt.hour

df["amount_category"] = df["amount"].apply(
    lambda x: "low" if x < 1 else ("medium" if x < 3 else "high")
)

df["is_night"] = df["hour"].apply(
    lambda x: 1 if x < 6 or x > 22 else 0
)

# Advanced features

# Amount category (numeric for ML)
df["amount_cat"] = df["amount"].apply(
    lambda x: 0 if x < 1 else (1 if x < 3 else 2)
)

# Night transaction flag
df["is_night"] = df["hour"].apply(
    lambda x: 1 if x < 6 or x > 22 else 0
)

# High gas anomaly
df["high_gas"] = df["gas_fee"].apply(
    lambda x: 1 if x > 0.008 else 0
)
# Final ML dataset
df.to_csv("final_transactions.csv", index=False)

# Fraud only (for demo)
df[df["is_fraud"] == 1].to_csv("fraud_only.csv", index=False)

# Network graph (for Arnav)
df[["sender", "receiver"]].to_csv("network.csv", index=False)

print("✅ Dataset created successfully!")