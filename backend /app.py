import os
import sqlite3
import pickle
import numpy as np
import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Database Setup
DB_FILE = "transactions.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            amount REAL,
            prediction TEXT,
            probability REAL,
            risk_level TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Load trained model safely
MODEL_PATH = os.path.join(os.path.dirname(__file__), "../model/fraud_model.pkl")
try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
except Exception as e:
    print(f"Warning: Model not found at {MODEL_PATH}. Starting without model for now. Error: {e}")
    model = None

@app.route("/")
def home():
    return jsonify({"status": "Live", "message": "Fraud Detection API Running 🚀"})

@app.route("/predict", methods=["POST"])
def predict():
    if model is None:
        return jsonify({"error": "Model not loaded"}), 500

    data = request.json
    try:
        # Expected input: [amount, hour, is_night, amount_cat, high_gas]
        features_list = data.get("features", [])
        if not features_list or len(features_list) != 5:
            return jsonify({"error": "Must provide exactly 5 features"}), 400

        features = np.array(features_list).reshape(1, -1)

        # Prediction
        prediction = model.predict(features)[0]
        
        # Probability
        prob = model.predict_proba(features)[0]
        fraud_probability = round(prob[1] * 100, 2)

        # Labels & Risk Level
        is_fraud = int(prediction) == 1
        label = "Fraud" if is_fraud else "Not Fraud"
        
        if fraud_probability < 20:
            risk_level = "Low"
        elif fraud_probability < 70:
            risk_level = "Medium"
        else:
            risk_level = "High"

        # Log to Database
        amount = features_list[0] # Amount is index 0 now
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO history (timestamp, amount, prediction, probability, risk_level)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, amount, label, fraud_probability, risk_level))
        conn.commit()
        conn.close()

        return jsonify({
            "prediction": label,
            "probability": fraud_probability,
            "risk_level": risk_level
        })

    except Exception as e:
        print(f"Prediction Error: {e}")
        return jsonify({"error": "Server error processing transaction"}), 500

@app.route("/history", methods=["GET"])
def history():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        # Get latest 50 transactions
        c.execute('SELECT * FROM history ORDER BY id DESC LIMIT 50')
        rows = c.fetchall()
        conn.close()
        
        history_list = [dict(row) for row in rows]
        return jsonify({"history": history_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
