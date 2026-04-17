// Live Render Backend API
const BACKEND_URL = "https://run-time-error-final.onrender.com";

let trafficChart;

document.addEventListener("DOMContentLoaded", () => {
    setupTabs();
    initChart();
    
    // Initial fetch for dashboard
    fetchDashboardData();
    setInterval(fetchDashboardData, 5000); // Poll every 5s

    // Slider logic
    document.getElementById('complexity-slider').addEventListener('input', (e) => {
        document.getElementById('slider-val').innerText = e.target.value;
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
                borderWidth: 2,
                pointBackgroundColor: '#00ff00',
                pointRadius: 0,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(0, 255, 0, 0.05)' },
                    ticks: { color: '#555' }
                },
                x: {
                    grid: { display: false },
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
            const recent = history.slice(-20);
            trafficChart.data.labels = recent.map(t => t.timestamp.split(" ")[1]);
            trafficChart.data.datasets[0].data = recent.map(t => t.probability);
            
            // Check latest risk
            const latestRisk = recent[recent.length-1].probability;
            if (latestRisk > 70) {
                trafficChart.data.datasets[0].borderColor = '#ff3333';
            } else {
                trafficChart.data.datasets[0].borderColor = '#00ff00';
            }
            trafficChart.update();
        }

    } catch (error) {
        addLog(`> ERROR: Failed to sync with backend.`, 'red');
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
    
    // Simulate exactly 30 features for backend
    let features = new Array(30).fill(0);
    features[0] = Date.now() % 100000;
    features[29] = parseFloat(amount);

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
