import pandas as pd
import numpy as np
import pickle
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

print("Loading genuine blockchain dataset...")
# Load genuine data
data = pd.read_csv("../data/old_data/final_transactions.csv")

# We will use 5 specific features for the model:
# 1. amount: Transaction amount
# 2. hour: Hour of the day (0-23)
# 3. is_night: Flag if transaction happened at night
# 4. amount_cat: Categorical representation of amount
# 5. high_gas: Flag for unusually high gas fees

features = ['amount', 'hour', 'is_night', 'amount_cat', 'high_gas']

X = data[features]
y = data['is_fraud']

print(f"Training on {len(X)} transactions...")

# Train model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X, y)

# Save model
with open("fraud_model.pkl", "wb") as f:
    pickle.dump(model, f)

print("Model trained and saved as fraud_model.pkl!")