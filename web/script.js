
document.addEventListener("DOMContentLoaded", () => {
    // Check if Plotly is loaded
    if (typeof Plotly === 'undefined') {
        console.error('Plotly is not loaded!');
        // Try to load Plotly dynamically
        const script = document.createElement('script');
        script.src = 'https://cdn.plot.ly/plotly-latest.min.js';
        script.onload = () => {
            console.log('Plotly loaded successfully');
            initializeApp();
        };
        script.onerror = () => {
            console.error('Failed to load Plotly');
        };
        document.head.appendChild(script);
    } else {
        console.log('Plotly is already loaded');
        initializeApp();
    }
});

function initializeApp() {
    fetch("/api/data")
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                document.getElementById("table-container").innerText = data.error;
                return;
            }
            const table = createTable(data);
            document.getElementById("table-container").appendChild(table);
            addEventListeners();

            // Load charts for the first stock by default
            const firstRow = document.querySelector("tbody tr");
            if (firstRow) {
                loadCharts(firstRow.dataset.stockId);
                highlightSelectedRow(firstRow);
            }
        });
}

function createTable(data) {
    const dates = Object.keys(data.dates).sort().reverse();
    const latestDate = dates[0];
    
    // Add future empty dates for planning (after the latest date) - only weekdays
    const futureDates = [];
    if (latestDate) {
        const lastDate = new Date(latestDate);
        let daysAdded = 0;
        let dayOffset = 1;
        
        while (daysAdded < 5) {
            const futureDate = new Date(lastDate);
            futureDate.setDate(lastDate.getDate() + dayOffset);
            
            // Skip weekends (Saturday = 6, Sunday = 0)
            if (futureDate.getDay() !== 0 && futureDate.getDay() !== 6) {
                futureDates.push(futureDate.toISOString().split('T')[0]);
                daysAdded++;
            }
            dayOffset++;
        }
    }
    
    // Combine existing dates with future dates (chronological order)
    const allDates = [...dates, ...futureDates];
    const all_stocks = {};

    // Aggregate all stocks and their momentum scores
    dates.forEach(date => {
        const stocks_on_date = data.dates[date];
        for (const stock_id in stocks_on_date) {
            if (!all_stocks[stock_id]) {
                all_stocks[stock_id] = {
                    name: stocks_on_date[stock_id].stock_name,
                    scores: {}
                };
            }
            all_stocks[stock_id].scores[date] = stocks_on_date[stock_id].momentum;
        }
    });

    // Sort stocks by the latest day's momentum score
    const sorted_stocks = Object.keys(all_stocks).sort((a, b) => {
        const score_a = all_stocks[a].scores[latestDate] || -Infinity;
        const score_b = all_stocks[b].scores[latestDate] || -Infinity;
        return score_b - score_a;
    });

    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const tbody = document.createElement("tbody");

    // Header
    const header_row = document.createElement("tr");
    const stock_header = document.createElement("th");
    stock_header.innerText = "Stock";
    header_row.appendChild(stock_header);
    allDates.forEach(date => {
        const date_header = document.createElement("th");
        date_header.innerText = date;
        // Style future dates differently
        if (futureDates.includes(date)) {
            date_header.style.color = "#888";
            date_header.style.fontStyle = "italic";
        }
        header_row.appendChild(date_header);
    });
    thead.appendChild(header_row);

    // Body
    sorted_stocks.forEach(stock_id => {
        const row = document.createElement("tr");
        row.dataset.stockId = stock_id;
        const stock_name_cell = document.createElement("td");
        stock_name_cell.innerHTML = `<div class="stock-name">${all_stocks[stock_id].name}</div><div>${stock_id}</div>`;
        row.appendChild(stock_name_cell);

        allDates.forEach(date => {
            const cell = document.createElement("td");
            const score = all_stocks[stock_id].scores[date];
            cell.innerText = score ? score.toFixed(2) : "";
            // Style future date cells differently
            if (futureDates.includes(date)) {
                cell.style.backgroundColor = "#1a1a1a";
                cell.style.border = "1px dashed #444";
            }
            row.appendChild(cell);
        });
        tbody.appendChild(row);
    });

    table.appendChild(thead);
    table.appendChild(tbody);

    return table;
}

function loadCharts(stockId) {
    loadKlineChart(stockId);
    loadIndicatorsChart(stockId);
}

function loadKlineChart(stockId) {
    const klineContainer = document.getElementById("kline-container");
    klineContainer.innerHTML = "<h3>K線圖 (90天)</h3><p>Loading K-line chart...</p>";

    if (typeof Plotly === 'undefined') {
        klineContainer.innerHTML = "<h3>K線圖 (90天)</h3><p>Plotly library not loaded</p>";
        return;
    }

    fetch(`/api/kline/${stockId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(chartData => {
            if (chartData.error) {
                klineContainer.innerHTML = `<h3>K線圖 (90天)</h3><p>Error: ${chartData.error}</p>`;
                return;
            }

            // Clear container and add title
            klineContainer.innerHTML = `<h3>K線圖 (90天)</h3>`;
            
            // Create new chart div
            const chartDiv = document.createElement('div');
            chartDiv.id = `kline-${stockId}-${Date.now()}`;
            chartDiv.style.height = 'calc(100% - 40px)';
            chartDiv.style.width = '100%';
            klineContainer.appendChild(chartDiv);
            
            // Create Plotly chart
            Plotly.newPlot(chartDiv.id, chartData.data, chartData.layout, chartData.config);
        })
        .catch(error => {
            console.error('Error loading K-line chart:', error);
            klineContainer.innerHTML = `<h3>K線圖 (90天)</h3><p>Could not load K-line chart: ${error.message}</p>`;
        });
}

function loadIndicatorsChart(stockId) {
    const indicatorContainer = document.getElementById("indicator-container");
    indicatorContainer.innerHTML = "<h3>技術指標 (MACD & RSI)</h3><p>Loading indicators...</p>";

    if (typeof Plotly === 'undefined') {
        indicatorContainer.innerHTML = "<h3>技術指標 (MACD & RSI)</h3><p>Plotly library not loaded</p>";
        return;
    }

    fetch(`/api/indicators/${stockId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(chartData => {
            if (chartData.error) {
                indicatorContainer.innerHTML = `<h3>技術指標 (MACD & RSI)</h3><p>Error: ${chartData.error}</p>`;
                return;
            }

            // Clear container and add title
            indicatorContainer.innerHTML = `<h3>技術指標 (MACD & RSI)</h3>`;
            
            // Create new chart div
            const chartDiv = document.createElement('div');
            chartDiv.id = `indicators-${stockId}-${Date.now()}`;
            chartDiv.style.height = 'calc(100% - 40px)';
            chartDiv.style.width = '100%';
            indicatorContainer.appendChild(chartDiv);
            
            // Create Plotly chart
            Plotly.newPlot(chartDiv.id, chartData.data, chartData.layout, chartData.config);
        })
        .catch(error => {
            console.error('Error loading indicators chart:', error);
            indicatorContainer.innerHTML = `<h3>技術指標 (MACD & RSI)</h3><p>Could not load indicators: ${error.message}</p>`;
        });
}

function highlightSelectedRow(selectedRow) {
    // Remove previous selection
    document.querySelectorAll("tbody tr").forEach(row => {
        row.classList.remove("selected");
    });
    
    // Add selection to current row
    selectedRow.classList.add("selected");
}

function addEventListeners() {
    document.querySelectorAll("tbody tr").forEach(row => {
        row.addEventListener("click", () => {
            loadCharts(row.dataset.stockId);
            highlightSelectedRow(row);
        });
    });
}
