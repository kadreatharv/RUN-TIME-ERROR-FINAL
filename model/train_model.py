import pandas as pd
import numpy as np
import pickle
from sklearn.ensemble import RandomForestClassifier

print("Loading Real Ethereum Fraud dataset...")
data = pd.read_csv("../data/transaction_dataset.csv")

# We use 4 real blockchain features that perfectly map to our UI:
# 1. avg val sent -> Maps to UI "Amount"
# 2. Sent tnx -> Maps to UI "Transaction Frequency"
# 3. Avg min between sent tnx -> Maps to UI "Wallet Activity"
# 4. Number of Created Contracts -> Maps to UI "Complexity Slider"

features = [
    'avg val sent',
    'Sent tnx',
    'Avg min between sent tnx',
    'Number of Created Contracts'
]

# Clean data: Fill missing values with 0
X = data[features].fillna(0)
y = data['FLAG']

print(f"Training on {len(X)} Real Ethereum transactions...")

# Train model (Random Forest is great for this tabular data)
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X, y)

# Save the real model
with open("fraud_model.pkl", "wb") as f:
    pickle.dump(model, f)

print("Real Ethereum Model trained and saved as fraud_model.pkl!")