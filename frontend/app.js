// Configuration
// UPDATE THIS URL ONCE DEPLOYED TO RENDER
const BACKEND_URL = "http://localhost:5001"; 

// Global state
let pieChart, lineChart;

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", () => {
    // Set Date
    document.getElementById("current-date").innerText = new Date().toLocaleDateString('en-US', { 
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' 
    });

    // Init Charts
    initCharts();

    // Fetch initial data & start polling
    fetchHistory();
    setInterval(fetchHistory, 5000); // Auto-refresh every 5s
});

// Create 30 features matching credit card dataset
function convertToFeatures(amount) {
    let features = new Array(30).fill(0);
    // Time (simulated)
    features[0] = Date.now() % 100000;
    // Amount
    features[29] = parseFloat(amount);
    return features;
}

// Handle Form Submission
async function submitTransaction() {
    const amount = document.getElementById("amount").value;
    const btn = document.getElementById("submit-btn");
    const spinner = document.getElementById("loading-spinner");
    const btnText = document.querySelector(".btn-text");
    const resultBox = document.getElementById("result-box");

    // UI Loading State
    btn.disabled = true;
    spinner.classList.remove("d-none");
    btnText.innerText = "Analyzing...";
    resultBox.classList.add("d-none");

    const features = convertToFeatures(amount);

    try {
        const response = await fetch(`${BACKEND_URL}/predict`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ features: features })
        });

        if (!response.ok) throw new Error("API Error");
        const result = await response.json();

        // Update UI Result
        showResult(result);
        
        // Refresh Dashboard Data immediately
        fetchHistory();

    } catch (error) {
        console.error(error);
        alert("Failed to connect to API. Is the backend running?");
    } finally {
        // Reset UI
        btn.disabled = false;
        spinner.classList.add("d-none");
        btnText.innerText = "Analyze Transaction";
    }
}

function showResult(data) {
    const box = document.getElementById("result-box");
    const title = document.getElementById("result-prediction");
    const risk = document.getElementById("result-risk-level");
    const prob = document.getElementById("result-probability");

    box.className = "result-box"; // Reset classes
    
    if (data.prediction === "Fraud") {
        box.classList.add("fraud");
        title.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Fraud Detected';
    } else {
        box.classList.add("safe");
        title.innerHTML = '<i class="fa-solid fa-shield-check"></i> Transaction Safe';
    }

    risk.innerText = `Risk: ${data.risk_level}`;
    prob.innerText = `${data.probability}% Probability`;
    
    box.classList.remove("d-none");
}

// Fetch History for Dashboard
async function fetchHistory() {
    try {
        const response = await fetch(`${BACKEND_URL}/history`);
        if (!response.ok) throw new Error("History fetch failed");
        
        const data = await response.json();
        const history = data.history.reverse(); // oldest to newest for charts

        updateDashboardStats(history);
        updateCharts(history);

    } catch (error) {
        console.error("Dashboard update failed:", error);
        document.querySelector(".api-status").className = "api-status offline";
        document.querySelector(".api-status").innerHTML = '<i class="fa-solid fa-circle"></i> Offline';
    } else {
        document.querySelector(".api-status").className = "api-status online";
        document.querySelector(".api-status").innerHTML = '<i class="fa-solid fa-circle"></i> Connected';
    }
}

function updateDashboardStats(history) {
    const total = history.length;
    const fraud = history.filter(t => t.prediction === "Fraud").length;
    const safe = total - fraud;

    document.getElementById("total-count").innerText = total;
    document.getElementById("fraud-count").innerText = fraud;
    document.getElementById("safe-count").innerText = safe;
}

// Charts Initialization
function initCharts() {
    Chart.defaults.color = "#94a3b8";
    Chart.defaults.font.family = "'Inter', sans-serif";

    // Pie Chart
    const pieCtx = document.getElementById('fraudPieChart').getContext('2d');
    pieChart = new Chart(pieCtx, {
        type: 'doughnut',
        data: {
            labels: ['Safe', 'Fraud'],
            datasets: [{
                data: [0, 0],
                backgroundColor: ['#10b981', '#ef4444'],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' }
            },
            cutout: '70%'
        }
    });

    // Line Chart
    const lineCtx = document.getElementById('activityLineChart').getContext('2d');
    lineChart = new Chart(lineCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Risk Probability (%)',
                data: [],
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, max: 100, grid: { color: 'rgba(255,255,255,0.05)' } },
                x: { grid: { display: false }, ticks: { display: false } }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

function updateCharts(history) {
    // Update Pie Chart
    const fraud = history.filter(t => t.prediction === "Fraud").length;
    const safe = history.length - fraud;
    
    pieChart.data.datasets[0].data = [safe, fraud];
    pieChart.update();

    // Update Line Chart (Last 20 transactions)
    const recent = history.slice(-20);
    lineChart.data.labels = recent.map(t => t.timestamp.split(" ")[1]); // Time only
    lineChart.data.datasets[0].data = recent.map(t => t.probability);
    
    // Change line color based on latest risk
    if (recent.length > 0) {
        const latestProb = recent[recent.length-1].probability;
        if (latestProb > 70) {
            lineChart.data.datasets[0].borderColor = '#ef4444'; // Red
            lineChart.data.datasets[0].backgroundColor = 'rgba(239, 68, 68, 0.1)';
        } else {
            lineChart.data.datasets[0].borderColor = '#3b82f6'; // Blue
            lineChart.data.datasets[0].backgroundColor = 'rgba(59, 130, 246, 0.1)';
        }
    }
    
    lineChart.update();
}