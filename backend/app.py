import os
import sqlite3
import pickle
import numpy as np
import datetime
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Database Setup
DB_FILE = "transactions.db"
DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = DATABASE_URL is not None

def get_db_connection():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    global USE_POSTGRES
    try:
        conn = get_db_connection()
        c = conn.cursor()
        if USE_POSTGRES:
            c.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT,
                    amount REAL,
                    prediction TEXT,
                    probability REAL,
                    risk_level TEXT
                )
            ''')
        else:
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
        print("Database initialized successfully.")
    except Exception as e:
        print(f"CRITICAL ERROR INITIALIZING DATABASE: {e}")
        if USE_POSTGRES:
            print("Postgres connection failed! Falling back to SQLite.")
            USE_POSTGRES = False
            # Re-run init_db with SQLite
            init_db()

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
        # Expected input: [avg_val_sent, sent_tnx, avg_min_between_sent_tnx, num_created_contracts]
        features_list = data.get("features", [])
        if not features_list or len(features_list) != 4:
            return jsonify({"error": "Must provide exactly 4 features"}), 400

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

        conn = get_db_connection()
        c = conn.cursor()
        if USE_POSTGRES:
            c.execute('''
                INSERT INTO history (timestamp, amount, prediction, probability, risk_level)
                VALUES (%s, %s, %s, %s, %s)
            ''', (timestamp, float(amount), label, float(fraud_probability), risk_level))
        else:
            c.execute('''
                INSERT INTO history (timestamp, amount, prediction, probability, risk_level)
                VALUES (?, ?, ?, ?, ?)
            ''', (timestamp, float(amount), label, float(fraud_probability), risk_level))
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
        conn = get_db_connection()
        if USE_POSTGRES:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            c = conn.cursor()
            
        c.execute('SELECT * FROM history ORDER BY id DESC LIMIT 50')
        rows = c.fetchall()
        
        # Get actual total counts from entire DB
        c.execute('SELECT COUNT(*) as total FROM history')
        total_count = c.fetchone()['total'] if not USE_POSTGRES else c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) as fraud FROM history WHERE prediction = 'Fraud'")
        fraud_count = c.fetchone()['fraud'] if not USE_POSTGRES else c.fetchone()[0]
        
        conn.close()
        
        history_list = [dict(row) for row in rows]
        return jsonify({
            "history": history_list,
            "total_count": total_count,
            "fraud_count": fraud_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

import pandas as pd
import io

@app.route("/predict_bulk", methods=["POST"])
def predict_bulk():
    if model is None:
        return jsonify({"error": "Model not loaded"}), 500

    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.endswith('.csv'):
        return jsonify({"error": "Only CSV files are supported"}), 400

    try:
        # Read CSV
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        df = pd.read_csv(stream)
        
        # Required columns mapping
        features = ['avg val sent', 'Sent tnx', 'Avg min between sent tnx', 'Number of Created Contracts']
        
        # Check if features exist
        missing = [f for f in features if f not in df.columns]
        if missing:
            # If standard features are missing, try to just take the first 4 numeric columns as fallback for demo
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if len(numeric_cols) >= 4:
                df = df[numeric_cols[:4]]
                df.columns = features
            else:
                return jsonify({"error": f"Missing required columns: {missing}"}), 400

        # Fill NaNs
        X = df[features].fillna(0).values

        # Predict all rows
        predictions = model.predict(X)
        probabilities = model.predict_proba(X)[:, 1]

        total_tx = len(predictions)
        fraud_tx = int(np.sum(predictions == 1))
        safe_tx = total_tx - fraud_tx
        
        high_risk = int(np.sum(probabilities > 0.7))
        avg_risk = round(float(np.mean(probabilities)) * 100, 2)

        return jsonify({
            "status": "success",
            "total_transactions": total_tx,
            "fraud_detected": fraud_tx,
            "safe_transactions": safe_tx,
            "high_risk_wallets": high_risk,
            "average_risk_score": avg_risk
        })

    except Exception as e:
        print(f"Bulk Prediction Error: {e}")
        return jsonify({"error": f"Failed to process CSV: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)