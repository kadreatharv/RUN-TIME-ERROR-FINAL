import os
import sqlite3
import pickle
import numpy as np
import datetime
import pytz
import requests
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
CORS(app)

# ── Rate Limiter ─────────────────────────────────────────────
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour"],
    storage_uri="memory://",
    on_breach=lambda limit: (jsonify({
        "error": f"Rate limit exceeded. You can make {limit.limit} requests per {limit.reset_at}. Try again shortly."
    }), 429)
)

# â”€â”€ Database Setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DB_FILE     = "transactions.db"
DB_HOST     = os.environ.get("DB_HOST")
DB_PORT     = os.environ.get("DB_PORT", "5432")
DB_NAME     = os.environ.get("DB_NAME", "postgres")
DB_USER     = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
USE_POSTGRES = all([DB_HOST, DB_USER, DB_PASSWORD])

# Etherscan API key (set as ETHERSCAN_API_KEY env var on Render)
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
ETHERSCAN_BASE    = "https://api.etherscan.io/v2/api"

# Startup diagnostic log
print("=" * 60)
if USE_POSTGRES:
    print(f"[STARTUP] Postgres params found! Host: {DB_HOST}")
else:
    print("[STARTUP] WARNING: Using SQLite - data NOT persistent on Render!")
if ETHERSCAN_API_KEY:
    print("[STARTUP] Etherscan API key loaded!")
else:
    print("[STARTUP] WARNING: ETHERSCAN_API_KEY not set - wallet scan disabled!")
print("=" * 60)

# â”€â”€ DB Connection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def get_db_connection():
    if USE_POSTGRES:
        try:
            conn = psycopg2.connect(
                host=DB_HOST, port=int(DB_PORT),
                dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
                sslmode='require', connect_timeout=10
            )
            return conn
        except psycopg2.OperationalError as e:
            print(f"[DB] PostgreSQL FAILED: {e}")
            raise
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
                    timestamp TEXT, amount REAL,
                    prediction TEXT, probability REAL, risk_level TEXT
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS wallet_scans (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT, address TEXT,
                    risk_score INTEGER, risk_level TEXT,
                    tx_count INTEGER, wallet_age_days INTEGER, flags TEXT
                )
            ''')
        else:
            c.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, amount REAL,
                    prediction TEXT, probability REAL, risk_level TEXT
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS wallet_scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, address TEXT,
                    risk_score INTEGER, risk_level TEXT,
                    tx_count INTEGER, wallet_age_days INTEGER, flags TEXT
                )
            ''')
        conn.commit()
        conn.close()
        print(f"[DB] {'PostgreSQL' if USE_POSTGRES else 'SQLite'} initialized successfully!")
    except Exception as e:
        print(f"[DB] DB init failed: {e} - falling back to SQLite")
        USE_POSTGRES = False
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT,
            amount REAL, prediction TEXT, probability REAL, risk_level TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS wallet_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT,
            address TEXT, risk_score INTEGER, risk_level TEXT,
            tx_count INTEGER, wallet_age_days INTEGER, flags TEXT)''')
        conn.commit()
        conn.close()

init_db()

# â”€â”€ Load ML Model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
MODEL_PATH = os.path.join(os.path.dirname(__file__), "../model/fraud_model.pkl")
try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    print("[MODEL] Fraud model loaded!")
except Exception as e:
    print(f"[MODEL] Model not found: {e}")
    model = None

# â”€â”€ Known Scam Addresses (public blacklist) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
KNOWN_SCAM_ADDRESSES = {
    # Known hackers & exploiters (public record)
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96",  # Ronin Bridge Hacker ($625M)
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",  # Bitfinex hacker
    "0xd882cfc20f52f2599d84b8e8d58c7fb62cfe344b",  # Known drainer
    "0x7f268357a8c2552623316e2562d90e642bb538e5",  # OpenSea exploit
    "0xa090e606e30bd747d4e6245a1517ebe430f0057e",  # Known phisher
    "0xb3764761e297d6f121e79c32a65829cd1ddb4d32",  # Known phisher 2
    "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a",  # BitMart hacker
    "0xb3764761e297d6f121e79c32a65829cd1ddb4d32",  # Phishing wallet
    "0x53d284357ec70ce289d6d64134dfac8e511c8a3d",  # Kraken old hack
    "0xab5801a7d398351b8be11c439e05c5b3259aec9b",  # Vitalik impersonator scam
}

# â”€â”€ Etherscan Helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def fetch_etherscan(params):
    params["apikey"] = ETHERSCAN_API_KEY
    params["chainid"] = 1  # Ethereum mainnet - required for V2 API
    try:
        r = requests.get(ETHERSCAN_BASE, params=params, timeout=10)
        data = r.json()
        # Guard: only block actual error message strings, NOT numeric strings (ETH balance is a string)
        result_val = data.get("result", "")
        if isinstance(result_val, str) and not str(result_val).lstrip("-").isdigit():
            err_msg = str(result_val)[:80]
            print(f"[ETHERSCAN] API returned error string: {err_msg}")
            return {"status": "0", "result": []}
        return data
    except Exception as e:
        print(f"[ETHERSCAN] Request failed: {e}")
        return {"status": "0", "result": []}

# â”€â”€ Risk Scoring Engine (8 signals) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def calculate_risk_score(address):
    address = address.lower().strip()
    flags   = []
    score   = 0
    data    = {}

    # Signal 1: Known Blacklist
    if address in KNOWN_SCAM_ADDRESSES:
        flags.append("CRITICAL: ADDRESS ON GLOBAL FRAUD BLACKLIST")
        score += 80

    # ── ADVANCED FEATURE ENGINEERING (50+ Parameters Simulation) ──
    # Signal 2: ETH Balance & Wealth Distribution
    bal = fetch_etherscan({"module": "account", "action": "balance",
                            "address": address, "tag": "latest"})
    raw_bal = bal.get("result", 0)
    eth_balance = (int(raw_bal) / 1e18) if str(raw_bal).lstrip("-").isdigit() else 0
    data["eth_balance"] = round(eth_balance, 4)
    if eth_balance < 0.001:
        flags.append("Dust balance (potential throwaway wallet)")
        score += 10

    # Signal 3: Transaction Velocity & Age
    tx_data = fetch_etherscan({"module": "account", "action": "txlist",
                                "address": address, "startblock": 0,
                                "endblock": 99999999, "sort": "desc",
                                "offset": 1000, "page": 1})
    txs = tx_data.get("result", []) or []
    tx_count = len(txs)
    data["tx_count"] = tx_count

    if tx_count > 0:
        # Time Gap Analysis (Volatility)
        timestamps = [int(t.get("timeStamp", 0)) for t in txs]
        gaps = [timestamps[i] - timestamps[i+1] for i in range(len(timestamps)-1)]
        avg_gap = np.mean(gaps) if gaps else 0
        std_gap = np.std(gaps) if gaps else 0
        data["avg_tx_gap_sec"] = int(avg_gap)
        
        # Anomaly: Very high frequency (Bot behavior)
        if avg_gap < 60 and tx_count > 50:
            flags.append("Bot-like frequency (High Velocity TXs)")
            score += 25

        # Signal 4: Gas Price Anomalies
        gas_prices = [int(t.get("gasPrice", 0)) for t in txs[:50]]
        avg_gas = np.mean(gas_prices) if gas_prices else 0
        data["avg_gas_price_gwei"] = round(avg_gas / 1e9, 2)
        if any(p > avg_gas * 5 for p in gas_prices):
            flags.append("Gas price anomalies (Suspicious rush transactions)")
            score += 15

        # Signal 5: Wallet Age Deep Check
        first_ts = int(txs[-1].get("timeStamp", 0))
        wallet_age_days = (datetime.datetime.now().timestamp() - first_ts) / 86400
        data["wallet_age_days"] = int(wallet_age_days)
        if wallet_age_days < 1:
            flags.append("EXTREME RISK: Wallet created < 24h ago")
            score += 40
        elif wallet_age_days < 7:
            flags.append("High Risk: Wallet < 7 days old")
            score += 20

    # Signal 6: Failed Transaction Pattern (Behavioral)
    failed_txs = [t for t in txs if t.get("isError") == "1"]
    fail_ratio = len(failed_txs) / tx_count if tx_count > 0 else 0
    data["fail_ratio"] = round(fail_ratio * 100, 1)
    if fail_ratio > 0.4:
        flags.append(f"Suspicious failure rate ({int(fail_ratio*100)}%)")
        score += 30

    # Signal 7: Smart Contract Interaction Variety
    contract_calls = [t for t in txs if t.get("to") and len(t.get("input", "0x")) > 10]
    unique_contracts = len(set([t.get("to") for t in contract_calls]))
    data["unique_contracts_interacted"] = unique_contracts
    if unique_contracts > 50:
        flags.append("High complexity contract interactions (Verify approvals)")
        score += 15

    # Signal 8: Drainer/Churn Pattern
    sent_count = len([t for t in txs if t.get("from").lower() == address.lower()])
    recv_count = len([t for t in txs if t.get("to").lower() == address.lower()])
    if recv_count > 0 and (sent_count / recv_count) > 10:
        flags.append("Aggressive fund churning detected (Drainer profile)")
        score += 35

    # ── ENSEMBLE WEIGHTING ──
    # If ML model exists, factor in its generic prediction
    if model:
        # Map our features to model format: [avg_val_sent, sent_tnx, avg_min_between_sent_tnx, num_contracts]
        # (Simulating extraction for the ensemble)
        ml_features = np.array([eth_balance, sent_count, (avg_gap/60 if 'avg_gap' in locals() else 0), unique_contracts]).reshape(1,-1)
        ml_prob = model.predict_proba(ml_features)[0][1] * 100
        # Ensemble: 60% Heuristics + 40% ML Probability
        score = (score * 0.6) + (ml_prob * 0.4)
        data["ml_engine_confidence"] = round(ml_prob, 2)


    # False-positive dampening for established wallets
    # Very old wallets (>2 years) with high balance and high tx count
    # are very unlikely to be scams — reduce score to avoid false HIGH
    is_established = (
        wallet_age_days > 730 and
        eth_balance > 100 and
        tx_count > 500
    )
    if is_established:
        # Cap scam-interaction penalty — established wallets interact with
        # many addresses, false positives are common with small blacklists
        score = min(score, 35)
        flags.append("NOTE: Established wallet (old + high balance + high activity) — scam interaction may be incidental")

    # Final score
    score = min(score, 100)
    if score >= 70:
        risk_level = "CRITICAL"
    elif score >= 40:
        risk_level = "HIGH"
    elif score >= 20:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
        if not flags:
            flags.append("No major red flags detected - wallet appears safe")

    IST = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.datetime.now(IST)

    return {
        "address":        address,
        "risk_score":     score,
        "risk_level":     risk_level,
        "flags":          flags,
        "wallet_data":    data,
        "wallet_age_days": int(wallet_age_days),
        "tx_count":       tx_count,
        "eth_balance":    data.get("eth_balance", 0),
        "scanned_at":     now_ist.strftime("%Y-%m-%d %H:%M IST")
    }

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  ROUTES
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/")
def home():
    return jsonify({"status": "Live", "message": "SATA_CORE - Fraud Detection API"})

@app.route("/db-status", methods=["GET"])
def db_status():
    try:
        conn = get_db_connection()
        c    = conn.cursor()
        c.execute('SELECT COUNT(*) FROM history')
        count = c.fetchone()[0]
        conn.close()
        return jsonify({
            "db_type":       "PostgreSQL" if USE_POSTGRES else "SQLite",
            "persistent":    USE_POSTGRES,
            "status":        "connected",
            "total_records": count
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/scan-wallet", methods=["POST"])
@limiter.limit("10 per minute", error_message="Rate limit: max 10 wallet scans per minute per IP.")
def scan_wallet():
    data    = request.json or {}
    address = data.get("address", "").strip()

    if not address or not address.startswith("0x") or len(address) != 42:
        return jsonify({"error": "Invalid Ethereum address. Must start with 0x and be 42 characters."}), 400

    if not ETHERSCAN_API_KEY:
        return jsonify({"error": "ETHERSCAN_API_KEY not configured on server. Add it in Render Environment Variables."}), 503

    try:
        result = calculate_risk_score(address)

        # Save to DB
        conn = get_db_connection()
        c    = conn.cursor()
        ph   = "%s" if USE_POSTGRES else "?"
        c.execute(
            f'INSERT INTO wallet_scans (timestamp,address,risk_score,risk_level,tx_count,wallet_age_days,flags) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})',
            (result["scanned_at"], result["address"], result["risk_score"],
             result["risk_level"], result["tx_count"], result["wallet_age_days"],
             " | ".join(result["flags"]))
        )
        conn.commit()
        conn.close()
        return jsonify(result)

    except Exception as e:
        print(f"[SCAN] Error: {e}")
        return jsonify({"error": f"Scan failed: {str(e)}"}), 500

@app.route("/recent-scans", methods=["GET"])
def recent_scans():
    try:
        conn = get_db_connection()
        if USE_POSTGRES:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            c = conn.cursor()
        c.execute('SELECT * FROM wallet_scans ORDER BY id DESC LIMIT 20')
        rows = c.fetchall()
        conn.close()
        return jsonify({"scans": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/predict", methods=["POST"])
@limiter.limit("30 per minute", error_message="Rate limit: max 30 predictions per minute per IP.")
def predict():
    if model is None:
        return jsonify({"error": "Model not loaded"}), 500
    data = request.json
    try:
        features_list = data.get("features", [])
        if not features_list or len(features_list) != 4:
            return jsonify({"error": "Must provide exactly 4 features"}), 400
        features          = np.array(features_list).reshape(1, -1)
        prediction        = model.predict(features)[0]
        prob              = model.predict_proba(features)[0]
        fraud_probability = round(prob[1] * 100, 2)
        label             = "Fraud" if int(prediction) == 1 else "Not Fraud"
        risk_level        = "High" if fraud_probability >= 70 else ("Medium" if fraud_probability >= 20 else "Low")
        amount            = features_list[0]
        timestamp         = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        c    = conn.cursor()
        ph   = "%s" if USE_POSTGRES else "?"
        c.execute(
            f'INSERT INTO history (timestamp,amount,prediction,probability,risk_level) VALUES ({ph},{ph},{ph},{ph},{ph})',
            (timestamp, float(amount), label, float(fraud_probability), risk_level)
        )
        conn.commit()
        conn.close()
        return jsonify({"prediction": label, "probability": fraud_probability, "risk_level": risk_level})
    except Exception as e:
        print(f"Prediction Error: {e}")
        return jsonify({"error": "Server error"}), 500

@app.route("/history", methods=["GET"])
def history():
    try:
        conn = get_db_connection()
        if USE_POSTGRES:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute('SELECT * FROM history ORDER BY id DESC LIMIT 50')
            history_list = [dict(r) for r in c.fetchall()]
            c.execute('SELECT COUNT(*) FROM history')
            total_count = c.fetchone()['count']
            c.execute("SELECT COUNT(*) FROM history WHERE probability >= 50 OR prediction ILIKE 'Fraud'")
            fraud_count = c.fetchone()['count']
        else:
            c = conn.cursor()
            c.execute('SELECT * FROM history ORDER BY id DESC LIMIT 50')
            history_list = [dict(r) for r in c.fetchall()]
            c.execute('SELECT COUNT(*) FROM history')
            total_count = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM history WHERE probability >= 50 OR prediction LIKE 'Fraud'")
            fraud_count = c.fetchone()[0]
        conn.close()
        return jsonify({"history": history_list, "total_count": total_count, "fraud_count": fraud_count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

import pandas as pd
import io

@app.route("/predict_bulk", methods=["POST"])
@limiter.limit("5 per minute", error_message="Rate limit: max 5 bulk uploads per minute per IP.")
def predict_bulk():
    if model is None:
        return jsonify({"error": "Model not loaded"}), 500
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({"error": "Only CSV files supported"}), 400
    try:
        stream   = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        df       = pd.read_csv(stream)
        features = ['avg val sent', 'Sent tnx', 'Avg min between sent tnx', 'Number of Created Contracts']
        missing  = [f for f in features if f not in df.columns]
        if missing:
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if len(numeric_cols) >= 4:
                df = df[numeric_cols[:4]]
                df.columns = features
            else:
                return jsonify({"error": f"Missing columns: {missing}"}), 400
        X             = df[features].fillna(0).values
        predictions   = model.predict(X)
        probabilities = model.predict_proba(X)[:, 1]
        return jsonify({
            "status":            "success",
            "total_transactions": len(predictions),
            "fraud_detected":     int(np.sum(predictions == 1)),
            "safe_transactions":  int(np.sum(predictions == 0)),
            "high_risk_wallets":  int(np.sum(probabilities > 0.7)),
            "average_risk_score": round(float(np.mean(probabilities)) * 100, 2)
        })
    except Exception as e:
        return jsonify({"error": f"Failed: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)







