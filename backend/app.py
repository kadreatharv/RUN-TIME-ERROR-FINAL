import os
import sqlite3
import pickle
import numpy as np
import datetime
import requests
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── Database Setup ──────────────────────────────────────────
DB_FILE     = "transactions.db"
DB_HOST     = os.environ.get("DB_HOST")
DB_PORT     = os.environ.get("DB_PORT", "5432")
DB_NAME     = os.environ.get("DB_NAME", "postgres")
DB_USER     = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
USE_POSTGRES = all([DB_HOST, DB_USER, DB_PASSWORD])

# Etherscan API key (set as ETHERSCAN_API_KEY env var on Render)
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
ETHERSCAN_BASE    = "https://api.etherscan.io/api"

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

# ── DB Connection ────────────────────────────────────────────
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

# ── Load ML Model ────────────────────────────────────────────
MODEL_PATH = os.path.join(os.path.dirname(__file__), "../model/fraud_model.pkl")
try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    print("[MODEL] Fraud model loaded!")
except Exception as e:
    print(f"[MODEL] Model not found: {e}")
    model = None

# ── Known Scam Addresses (public blacklist) ───────────────────
KNOWN_SCAM_ADDRESSES = {
    "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae",
    "0xb3764761e297d6f121e79c32a65829cd1ddb4d32",
    "0xd882cfc20f52f2599d84b8e8d58c7fb62cfe344b",
    "0x7f268357a8c2552623316e2562d90e642bb538e5",
    "0xa090e606e30bd747d4e6245a1517ebe430f0057e",
    "0x00000000219ab540356cbb839cbe05303d7705fa",
}

# ── Etherscan Helper ─────────────────────────────────────────
def fetch_etherscan(params):
    params["apikey"] = ETHERSCAN_API_KEY
    try:
        r = requests.get(ETHERSCAN_BASE, params=params, timeout=10)
        return r.json()
    except Exception as e:
        print(f"[ETHERSCAN] Request failed: {e}")
        return {"status": "0", "result": []}

# ── Risk Scoring Engine (8 signals) ─────────────────────────
def calculate_risk_score(address):
    address = address.lower().strip()
    flags   = []
    score   = 0
    data    = {}

    # Signal 1: Known Blacklist
    if address in KNOWN_SCAM_ADDRESSES:
        flags.append("ADDRESS ON KNOWN SCAM BLACKLIST")
        score += 60

    # Signal 2: ETH Balance
    bal = fetch_etherscan({"module": "account", "action": "balance",
                            "address": address, "tag": "latest"})
    eth_balance = int(bal.get("result", 0) or 0) / 1e18
    data["eth_balance"] = round(eth_balance, 4)
    if eth_balance == 0:
        flags.append("Zero ETH balance (wallet drained or unused)")
        score += 5

    # Signal 3: Transaction History & Wallet Age
    tx_data = fetch_etherscan({"module": "account", "action": "txlist",
                                "address": address, "startblock": 0,
                                "endblock": 99999999, "sort": "asc",
                                "offset": 100, "page": 1})
    txs      = tx_data.get("result", []) or []
    tx_count = len(txs) if isinstance(txs, list) else 0
    data["tx_count"] = tx_count

    wallet_age_days = 0
    if isinstance(txs, list) and tx_count > 0:
        first_ts = int(txs[0].get("timeStamp", 0))
        if first_ts > 0:
            wallet_age_days = (datetime.datetime.now().timestamp() - first_ts) / 86400
        data["wallet_age_days"] = int(wallet_age_days)
        if wallet_age_days < 7:
            flags.append(f"Very new wallet (created {int(wallet_age_days)} days ago)")
            score += 25
        elif wallet_age_days < 30:
            flags.append(f"New wallet (created {int(wallet_age_days)} days ago)")
            score += 10
        if tx_count < 5:
            flags.append(f"Very low transaction count ({tx_count} txns)")
            score += 15

    # Signal 4: Failed Transaction Ratio
    if isinstance(txs, list) and tx_count > 0:
        failed = [t for t in txs if t.get("isError") == "1"]
        fail_ratio = len(failed) / tx_count
        data["failed_tx_ratio"] = round(fail_ratio * 100, 1)
        if fail_ratio > 0.3:
            flags.append(f"High failed tx ratio ({round(fail_ratio*100)}%) - bot/scammer pattern")
            score += 20

    # Signal 5: Scam Address Interactions
    if isinstance(txs, list):
        scam_hits = [t for t in txs if
                     t.get("to", "").lower() in KNOWN_SCAM_ADDRESSES or
                     t.get("from", "").lower() in KNOWN_SCAM_ADDRESSES]
        if scam_hits:
            flags.append(f"Interacted with {len(scam_hits)} known scam address(es)")
            score += 35

    # Signal 6: Drainer Pattern (sends >> receives)
    if isinstance(txs, list) and tx_count > 3:
        sent     = [t for t in txs if t.get("from", "").lower() == address]
        received = [t for t in txs if t.get("to",   "").lower() == address]
        data["sent_count"]     = len(sent)
        data["received_count"] = len(received)
        if len(received) > 0 and (len(sent) / len(received)) > 5:
            flags.append(f"Drainer pattern - sends {round(len(sent)/len(received))}x more than receives")
            score += 20

    # Signal 7: Token Activity (phishing exposure)
    tok = fetch_etherscan({"module": "account", "action": "tokentx",
                            "address": address, "startblock": 0,
                            "endblock": 99999999, "sort": "desc",
                            "offset": 50, "page": 1})
    token_txs = tok.get("result", []) or []
    data["token_tx_count"] = len(token_txs) if isinstance(token_txs, list) else 0
    if isinstance(token_txs, list) and len(token_txs) > 30:
        flags.append(f"High token activity ({len(token_txs)} txns) - verify approvals")
        score += 10

    # Signal 8: Contract Creations
    if isinstance(txs, list):
        contracts = [t for t in txs if not t.get("to")]
        data["contracts_created"] = len(contracts)
        if len(contracts) > 3:
            flags.append(f"Created {len(contracts)} contracts - verify legitimacy")
            score += 10

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

    return {
        "address":        address,
        "risk_score":     score,
        "risk_level":     risk_level,
        "flags":          flags,
        "wallet_data":    data,
        "wallet_age_days": int(wallet_age_days),
        "tx_count":       tx_count,
        "eth_balance":    data.get("eth_balance", 0),
        "scanned_at":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

# ═══════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def home():
    return jsonify({"status": "Live", "message": "ChainGuard AI - Fraud Detection API"})

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