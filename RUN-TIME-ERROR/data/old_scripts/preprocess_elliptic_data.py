import pandas as pd

# File paths
features_path = "data/elliptic_bitcoin_dataset/elliptic_txs_features.csv"
classes_path = "data/elliptic_bitcoin_dataset/elliptic_txs_classes.csv"
edges_path = "data/elliptic_bitcoin_dataset/elliptic_txs_edgelist.csv"

# Load datasets
features = pd.read_csv(features_path, header=None)
classes = pd.read_csv(classes_path)
edges = pd.read_csv(edges_path)

# Rename first column as transaction ID
features.rename(columns={0: "txId"}, inplace=True)

# Merge features with class labels
data = features.merge(classes, on="txId", how="left")

print("✅ Dataset Loaded Successfully!")
print("Shape:", data.shape)
print(data.head())

# Save merged dataset
data.to_csv("data/elliptic_preprocessed.csv", index=False)
print("✅ Preprocessed dataset saved.")