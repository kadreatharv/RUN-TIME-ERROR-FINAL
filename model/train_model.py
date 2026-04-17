import pandas as pd
import numpy as np
import pickle
from sklearn.ensemble import RandomForestClassifier

print("Generating synthetic dataset...")
# Create synthetic data with 30 features (Time, V1-V28, Amount) + Class
np.random.seed(42)
n_samples = 1000

# Feature columns
columns = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount", "Class"]

# Generate random data
data = pd.DataFrame(np.random.randn(n_samples, 31), columns=columns)

# Make "Class" binary
data["Class"] = np.random.choice([0, 1], size=n_samples, p=[0.9, 0.1])

# Scale Time and Amount to realistic values
data["Time"] = np.random.randint(0, 100000, n_samples)
data["Amount"] = np.abs(data["Amount"]) * 100

# Features & target
X = data.drop("Class", axis=1)
y = data["Class"]

# Train model
model = RandomForestClassifier(n_estimators=50)
model.fit(X, y)

# Save model
with open("fraud_model.pkl", "wb") as f:
    pickle.dump(model, f)

print("Model trained!")