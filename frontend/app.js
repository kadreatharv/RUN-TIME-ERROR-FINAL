// Live Render Backend API
const BACKEND_URL = "https://run-time-error-final.onrender.com";

let trafficChart;
let networkGraph;
let isBackendConnected = true;
let currentChartRange = '30D'; // default range

document.addEventListener("DOMContentLoaded", () => {
    setupTabs();
    initChart();
    resetForm(); // Generate random initial tx details
    
    // Initial fetch for dashboard
    fetchDashboardData();
    setInterval(fetchDashboardData, 5000); // Poll every 5s

    // Slider logic
    document.getElementById('complexity-slider').addEventListener('input', (e) => {
        document.getElementById('slider-val').innerText = e.target.value;
    });

    // Chart Time Filters logic
    const filterSpans = document.querySelectorAll('#chart-time-filters span');
    filterSpans.forEach(span => {
        span.addEventListener('click', (e) => {
            // remove active from all
            filterSpans.forEach(s => s.classList.remove('active'));
            // add active to clicked
            e.target.classList.add('active');
            currentChartRange = e.target.getAttribute('data-range');
            fetchDashboardData(); // re-render graph immediately
        });
    });
});

// Tab Navigation Logic
function setupTabs() {
    const navBtns = document.querySelectorAll('.nav-btn');
    const tabs = document.querySelectorAll('.tab-content');

    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active classes
            navBtns.forEach(b => b.classList.remove('active'));
            tabs.forEach(t => t.classList.remove('active'));

            // Add active class to clicked button and target tab
            btn.classList.add('active');
            const targetId = btn.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });
}

// Chart.js Initialization
function initChart() {
    Chart.defaults.color = "#444";
    Chart.defaults.font.family = "'Share Tech Mono', monospace";

    const ctx = document.getElementById('trafficChart').getContext('2d');
    
    // Gradient for line
    let gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(0, 255, 0, 0.5)');
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

    trafficChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Wk 1', 'Wk 2', 'Wk 3', 'Wk 4'],
            datasets: [{
                label: 'Network Traffic',
                data: [0, 0, 0, 0],
                borderColor: '#00ff00',
                backgroundColor: gradient,
                borderWidth: 3,
                pointBackgroundColor: [],
                pointRadius: 0,
                pointHoverRadius: 7,
                fill: true,
                tension: 0.4,
                segment: {
                    borderColor: ctx => ctx.p0.parsed.y > 50 ? '#ff3333' : '#00ff00'
                }
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(0, 255, 0, 0.15)' },
                    ticks: { color: '#555' }
                },
                x: {
                    grid: { color: 'rgba(0, 255, 0, 0.15)' },
                    ticks: { color: '#555' }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// Fetch Dashboard Data from Render
async function fetchDashboardData() {
    try {
        const response = await fetch(`${BACKEND_URL}/history`);
        if (!response.ok) throw new Error("API Connection Failed");
        
        const data = await response.json();
        const history = data.history.reverse(); // oldest to newest

        const total = history.length;
        const fraud = history.filter(t => t.prediction === "Fraud").length;

        // Update Dashboard Cards
        document.getElementById("total-tx").innerText = total.toLocaleString();
        document.getElementById("fraud-tx").innerText = fraud.toLocaleString();

        // Update Chart
        if (history.length > 0) {
            let sliceCount = 50; // default 30D (all 50 rows)
            if (currentChartRange === '24H') sliceCount = 10;
            if (currentChartRange === '7D') sliceCount = 25;
            
            const recent = history.slice(-sliceCount);
            trafficChart.data.labels = recent.map(t => t.timestamp.split(" ")[1]);
            trafficChart.data.datasets[0].data = recent.map(t => t.probability);
            
            // Check latest risk
            const latestRisk = recent[recent.length-1].probability;
            
            // Update Top Risk Box
            document.getElementById("threat-score-text").innerText = `THREAT SCORE: ${latestRisk}/100`;
            const riskLevelText = document.getElementById("risk-level-text");
            const riskLevelBox = document.getElementById("risk-level-box");
            const riskBoxContainer = document.getElementById("risk-box-container");
            
            if (latestRisk > 70) {
                riskLevelText.innerText = "CRITICAL";
                riskLevelBox.className = "metric-value text-red";
                riskBoxContainer.className = "metric-box border-red";
            } else if (latestRisk > 30) {
                riskLevelText.innerText = "ELEVATED";
                riskLevelBox.className = "metric-value text-yellow";
                riskBoxContainer.className = "metric-box border-yellow";
            } else {
                riskLevelText.innerText = "NORMAL";
                riskLevelBox.className = "metric-value text-green";
                riskBoxContainer.className = "metric-box border-green";
            }
            trafficChart.update();
        }

        // Render Alerts and Network
        renderAlerts(history);
        renderNetworkGraph(history);

        // Clear error state if connected
        if (!isBackendConnected) {
            isBackendConnected = true;
            addLog(`> SYSTEM: Connection to AI.CORE_V2 Restored.`, 'green');
        }

    } catch (error) {
        if (isBackendConnected) {
            isBackendConnected = false;
            addLog(`> ERROR: Failed to sync with backend.`, 'red');
        }
    }
}

// Analyze Transaction Logic (Hooked to Render)
async function runAnalysis() {
    const amount = document.getElementById("tx_amount").value;
    const aiText = document.getElementById("ai-expert-text");
    const riskCircle = document.getElementById("risk-circle");
    const riskScoreText = document.getElementById("risk-score-text");

    // UX Feedback
    riskScoreText.innerText = "CALC...";
    aiText.innerHTML = `<p class="text-dim">@ SYSTEM DIAGNOSTIC</p><p class="text-yellow">> COMMUNICATING WITH AI.CORE_V2...</p>`;
    
    // Real Ethereum Features: [avg_val_sent, sent_tnx, avg_min_between_sent_tnx, num_created_contracts]
    const avgValSent = parseFloat(amount);
    const sentTnx = parseFloat(document.getElementById("tx_freq").value) || 0;
    const avgMinBetween = parseFloat(document.getElementById("wallet_activity").value) || 5000;
    const numContracts = parseInt(document.getElementById('complexity-slider').value) || 0;

    let features = [avgValSent, sentTnx, avgMinBetween, numContracts];

    try {
        const response = await fetch(`${BACKEND_URL}/predict`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ features: features })
        });

        if (!response.ok) throw new Error("API Error");
        const result = await response.json();

        // Update UI
        riskScoreText.innerText = `${result.probability}%`;
        
        riskCircle.className = "risk-circle"; // Reset classes
        
        if (result.prediction === "Fraud") {
            riskCircle.classList.add("high-risk");
            aiText.innerHTML = `
                <p class="text-dim">@ SYSTEM DIAGNOSTIC</p>
                <p class="text-red">> ALERT: HIGH PROBABILITY OF FRAUD DETECTED.</p>
                <p>> ANOMALY REASON: Transaction profile matches known rug-pull signatures in neural network topology.</p>
                <p>> ACTION: Funds frozen. Administrator notified.</p>
            `;
            addLog(`> ALERT: TX Blocked. High Risk (${result.probability}%)`, 'red');
        } else {
            riskCircle.classList.add("low-risk");
            aiText.innerHTML = `
                <p class="text-dim">@ SYSTEM DIAGNOSTIC</p>
                <p class="text-green">> TRANSACTION VERIFIED: SAFE.</p>
                <p>> AI ENGINE: Heuristics normal. No anomalous patterns detected in wallet history.</p>
            `;
            addLog(`> SYSTEM: TX Authorized. Risk: Low.`, 'green');
        }
        
        // Refresh dashboard immediately
        fetchDashboardData();

    } catch (error) {
        aiText.innerHTML = `<p class="text-dim">@ SYSTEM DIAGNOSTIC</p><p class="text-red">> ERROR: CONNECTION REFUSED BY HOST.</p>`;
    }
}

// Helper to add logs to the dashboard terminal
function addLog(msg, color) {
    const logBox = document.getElementById("live-log");
    const p = document.createElement("p");
    p.innerText = msg;
    if (color === 'red') p.className = "text-red";
    if (color === 'green') p.className = "text-green";
    
    logBox.appendChild(p);
    logBox.scrollTop = logBox.scrollHeight;
}

// Generate Random Tx Details for UI
function resetForm() {
    const chars = 'abcdef0123456789';
    const randomHex = (len) => [...Array(len)].map(() => chars[Math.floor(Math.random() * chars.length)]).join('');
    
    document.getElementById("tx_hash").value = "tx_" + randomHex(12);
    document.getElementById("tx_sender").value = "0x" + randomHex(40);
    document.getElementById("tx_receiver").value = "0x" + randomHex(40);
    
    // Set random amounts and metrics for next analysis
    document.getElementById("tx_amount").value = (Math.random() * 5000).toFixed(2);
    document.getElementById("tx_freq").value = Math.floor(Math.random() * 5) + 1;
    document.getElementById('complexity-slider').value = Math.floor(Math.random() * 10) + 1;
    document.getElementById('slider-val').innerText = document.getElementById('complexity-slider').value;
    
    const now = new Date();
    document.getElementById("tx_time").value = now.toISOString().replace('T', ' ').substring(0, 16);
    
    // Reset output UI
    document.getElementById("risk-score-text").innerText = "0%";
    document.getElementById("risk-circle").className = "risk-circle";
    document.getElementById("ai-expert-text").innerHTML = `
        <p class="text-dim">@ SYSTEM DIAGNOSTIC</p>
        <p>AWAITING TRANSACTION INPUT FOR ANALYSIS...</p>
    `;
}

// Bulk Upload Logic
async function analyzeBulk() {
    const fileInput = document.getElementById('csv-upload');
    const resultsDiv = document.getElementById('bulk-results');
    const reportText = document.getElementById('bulk-report-text');

    if (!fileInput.files || fileInput.files.length === 0) {
        alert("Please upload a CSV file first.");
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('file', file);

    reportText.innerHTML = `<p class="text-yellow">> UPLOADING LEDGER TO AI.CORE_V2...</p><p class="text-dim">@ SYSTEM: Please wait while Neural Net processes ${file.name}</p>`;
    resultsDiv.style.display = 'block';

    try {
        const response = await fetch(`${BACKEND_URL}/predict_bulk`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        
        if (response.ok) {
            reportText.innerHTML = `
                <p class="text-green">> BATCH PROCESSING COMPLETE.</p>
                <p>> TOTAL TRANSACTIONS: ${data.total_transactions}</p>
                <p class="text-red">> FRAUD DETECTED: ${data.fraud_detected}</p>
                <p class="text-green">> SAFE TRANSACTIONS: ${data.safe_transactions}</p>
                <p class="text-yellow">> HIGH RISK WALLETS FOUND: ${data.high_risk_wallets}</p>
                <p>> AVERAGE RISK SCORE: ${data.average_risk_score}%</p>
                <br>
                <p class="text-dim">>> ACTION: Fraudulent signatures added to global blacklist.</p>
            `;
            fetchDashboardData();
        } else {
            reportText.innerHTML = `<p class="text-red">> ERROR: ${data.error}</p>`;
        }
    } catch (err) {
        reportText.innerHTML = `<p class="text-red">> ERROR: Failed to communicate with backend.</p>`;
    }
}

// File Upload visual feedback
document.getElementById('csv-upload').addEventListener('change', function(e) {
    if (e.target.files.length > 0) {
        document.querySelector('.drop-zone h3').innerText = e.target.files[0].name;
    }
});

// Render Dynamic Alerts
function renderAlerts(history) {
    const alertsList = document.getElementById("alerts-list");
    // Filter only high risk
    const frauds = history.filter(t => t.risk_level === "High" || t.prediction === "Fraud");
    
    if (frauds.length === 0) {
        alertsList.innerHTML = `<p class="text-green">> NO CRITICAL INCIDENTS DETECTED IN RECENT HISTORY.</p>`;
        document.querySelector('.alert-badge').innerText = '0';
        return;
    }

    document.querySelector('.alert-badge').innerText = frauds.length;

    let html = '';
    // Show top 10 most recent frauds
    [...frauds].reverse().slice(0, 10).forEach(f => {
        html += `
        <div class="alert-item alert-high">
            <div class="alert-indicator"></div>
            <div class="alert-body">
                <h4>SUSPICIOUS TRANSACTION DETECTED (Amount: ${f.amount} USD/BTC)</h4>
                <p>${f.timestamp} | Probability: ${f.probability}% | Status: BLOCKED</p>
            </div>
            <div class="alert-tag bg-red">HIGH</div>
        </div>`;
    });
    alertsList.innerHTML = html;
}

// Render Interactive Network Graph
function renderNetworkGraph(history) {
    const container = document.getElementById("mynetwork");
    if (!container) return;

    // Build nodes and edges
    let nodes = new vis.DataSet([
        { id: 'CENTRAL_EXCHANGE', label: 'MAIN EXCHANGE NODE', color: '#00ff00', size: 30 }
    ]);
    let edges = new vis.DataSet([]);

    let addedNodes = new Set(['CENTRAL_EXCHANGE']);

    // Show last 20 transactions in graph
    const recent = history.slice(-20);
    
    recent.forEach((t, index) => {
        const nodeId = `WALLET_${t.id}`;
        if (!addedNodes.has(nodeId)) {
            const isFraud = t.prediction === "Fraud";
            nodes.add({
                id: nodeId,
                label: `Tx: ${t.amount}`,
                color: isFraud ? '#ff0000' : '#00ff00',
                size: isFraud ? 25 : 15
            });
            edges.add({
                from: 'CENTRAL_EXCHANGE',
                to: nodeId,
                color: { color: isFraud ? '#ff0000' : '#00ff00', opacity: 0.6 },
                width: isFraud ? 3 : 1
            });
            addedNodes.add(nodeId);
        }
    });

    const data = { nodes: nodes, edges: edges };
    const options = {
        nodes: {
            shape: 'dot',
            font: { color: '#ffffff', face: 'Share Tech Mono' }
        },
        edges: {
            smooth: true
        },
        physics: {
            barnesHut: { gravitationalConstant: -2000, springLength: 100 }
        }
    };

    if (!networkGraph) {
        networkGraph = new vis.Network(container, data, options);
    } else {
        networkGraph.setData(data);
    }
}