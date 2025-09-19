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

let stockPriceData = {};

function initializeApp() {
    // Load momentum data
    fetch("historical_data.json")
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                document.getElementById("table-container").innerText = data.error;
                return;
            }
            const table = createTable(data);
            document.getElementById("table-container").appendChild(table);
            
            // Load stock price data
            return fetch("stock_price_data.json");
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(priceData => {
            stockPriceData = priceData;
            addEventListeners();
            
            // Load charts for the first stock by default
            const firstRow = document.querySelector("tbody tr");
            if (firstRow) {
                const stockId = firstRow.dataset.stockId;
                if (stockPriceData[stockId]) {
                    loadCharts(stockId);
                    highlightSelectedRow(firstRow);
                } else {
                    showNoDataMessage();
                }
            }
        })
        .catch(error => {
            console.error('Error loading data:', error);
            document.getElementById("table-container").innerHTML = `
                <p style="text-align: center; padding: 40px; color: #ff6b6b;">
                    ❌ 無法載入數據: ${error.message}<br>
                    <small>請檢查瀏覽器開發者工具的Console面板查看詳細錯誤</small><br><br>
                    <small>GitHub Pages URL: ${window.location.href}</small>
                </p>`;
        });
}

function createTable(data) {
    const dates = Object.keys(data.dates).sort().reverse();
    const latestDate = dates[0];
    
    // Add future empty dates for planning (after the latest date)
    const futureDates = [];
    if (latestDate) {
        const lastDate = new Date(latestDate);
        for (let i = 1; i <= 5; i++) {
            const futureDate = new Date(lastDate);
            futureDate.setDate(lastDate.getDate() + i);
            futureDates.push(futureDate.toISOString().split('T')[0]);
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
        
        // Add indicator if stock has price data
        const hasData = stockPriceData[stock_id] ? " 📊" : " ⚪";
        const stock_name_cell = document.createElement("td");
        stock_name_cell.innerHTML = `<div class="stock-name">${all_stocks[stock_id].name}${hasData}</div><div>${stock_id}</div>`;
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
    if (stockPriceData[stockId]) {
        loadKlineChart(stockId);
        loadIndicatorsChart(stockId);
    } else {
        showNoDataMessage();
    }
}

function loadKlineChart(stockId) {
    const klineContainer = document.getElementById("kline-container");
    klineContainer.innerHTML = "<h3>K線圖 (90天)</h3><p>Loading K-line chart...</p>";

    if (typeof Plotly === 'undefined') {
        klineContainer.innerHTML = "<h3>K線圖 (90天)</h3><p>Plotly library not loaded</p>";
        return;
    }

    try {
        const stockData = stockPriceData[stockId];
        if (!stockData) {
            throw new Error(`Stock data not found for ${stockId}`);
        }
        const priceData = stockData.price_data;
        console.log('Loading K-line for:', stockId, 'Data points:', priceData.dates.length);
        
        // Create subplot data for K-line and volume
        const trace1 = {
            x: priceData.dates,
            open: priceData.open,
            high: priceData.high,
            low: priceData.low,
            close: priceData.close,
            type: 'candlestick',
            name: 'K線',
            increasing: { line: { color: '#ff6b6b' } },
            decreasing: { line: { color: '#4ecdc4' } },
            yaxis: 'y',
            showlegend: false
        };

        const trace2 = {
            x: priceData.dates,
            y: priceData.volume,
            type: 'bar',
            name: '成交量',
            marker: {
                color: priceData.close.map((close, i) => 
                    close >= priceData.open[i] ? '#ff6b6b' : '#4ecdc4'
                ),
                opacity: 0.7
            },
            yaxis: 'y2',
            showlegend: false
        };

        const layout = {
            title: `${stockId} K線圖`,
            xaxis: { 
                rangeslider: { visible: false },
                domain: [0, 1],
                anchor: 'y2'
            },
            yaxis: { 
                title: '價格 (TWD)',
                domain: [0.3, 1],
                anchor: 'x'
            },
            yaxis2: { 
                title: '成交量',
                domain: [0, 0.25],
                anchor: 'x'
            },
            showlegend: false,
            template: 'plotly_dark',
            font: { size: 12 },
            margin: { l: 50, r: 50, t: 50, b: 50 },
            height: 400
        };

        const config = { responsive: true };
        const fig = { data: [trace1, trace2], layout: layout, config: config };

        // Clear container and add title
        klineContainer.innerHTML = `<h3>K線圖 (90天)</h3>`;
        
        // Create new chart div
        const chartDiv = document.createElement('div');
        chartDiv.id = `kline-${stockId}-${Date.now()}`;
        chartDiv.style.height = 'calc(100% - 40px)';
        chartDiv.style.width = '100%';
        klineContainer.appendChild(chartDiv);
        
        // Create Plotly chart
        Plotly.newPlot(chartDiv.id, fig.data, fig.layout, {responsive: true});
        
    } catch (error) {
        console.error('Error loading K-line chart:', error);
        klineContainer.innerHTML = `<h3>K線圖 (90天)</h3><p>Could not load K-line chart: ${error.message}</p>`;
    }
}

function loadIndicatorsChart(stockId) {
    const indicatorContainer = document.getElementById("indicator-container");
    indicatorContainer.innerHTML = "<h3>技術指標 (MACD & RSI)</h3><p>Loading indicators...</p>";

    if (typeof Plotly === 'undefined') {
        indicatorContainer.innerHTML = "<h3>技術指標 (MACD & RSI)</h3><p>Plotly library not loaded</p>";
        return;
    }

    try {
        const stockData = stockPriceData[stockId];
        if (!stockData) {
            throw new Error(`Stock data not found for ${stockId}`);
        }
        const indicators = stockData.indicators;
        console.log('Loading indicators for:', stockId, 'MACD points:', indicators.macd.length);
        
        // Create traces for MACD and RSI
        const macdTrace = {
            x: indicators.dates,
            y: indicators.macd,
            type: 'scatter',
            mode: 'lines',
            name: 'MACD',
            line: { color: '#ff6b6b', width: 2 },
            yaxis: 'y'
        };

        const signalTrace = {
            x: indicators.dates,
            y: indicators.signal,
            type: 'scatter',
            mode: 'lines',
            name: 'Signal',
            line: { color: '#4ecdc4', width: 2 },
            yaxis: 'y'
        };

        const histogramTrace = {
            x: indicators.dates,
            y: indicators.histogram,
            type: 'bar',
            name: 'Histogram',
            marker: { color: 'gray', opacity: 0.5 },
            yaxis: 'y'
        };

        const rsiTrace = {
            x: indicators.dates,
            y: indicators.rsi,
            type: 'scatter',
            mode: 'lines',
            name: 'RSI',
            line: { color: '#ffa726', width: 2 },
            yaxis: 'y2'
        };

        const layout = {
            xaxis: { 
                domain: [0, 1],
                anchor: 'y2'
            },
            yaxis: { 
                title: 'MACD',
                domain: [0.55, 1],
                anchor: 'x'
            },
            yaxis2: { 
                title: 'RSI',
                domain: [0, 0.45],
                range: [0, 100],
                anchor: 'x'
            },
            showlegend: true,
            template: 'plotly_dark',
            font: { size: 12 },
            margin: { l: 50, r: 50, t: 20, b: 50 },
            height: 400,
            shapes: [
                // MACD zero line
                {
                    type: 'line',
                    x0: 0,
                    x1: 1,
                    xref: 'paper',
                    y0: 0,
                    y1: 0,
                    yref: 'y',
                    line: { color: 'white', width: 1, dash: 'dash' }
                },
                // RSI lines
                {
                    type: 'line',
                    x0: 0,
                    x1: 1,
                    xref: 'paper',
                    y0: 70,
                    y1: 70,
                    yref: 'y2',
                    line: { color: 'red', width: 1, dash: 'dash' }
                },
                {
                    type: 'line',
                    x0: 0,
                    x1: 1,
                    xref: 'paper',
                    y0: 30,
                    y1: 30,
                    yref: 'y2',
                    line: { color: 'green', width: 1, dash: 'dash' }
                },
                {
                    type: 'line',
                    x0: 0,
                    x1: 1,
                    xref: 'paper',
                    y0: 50,
                    y1: 50,
                    yref: 'y2',
                    line: { color: 'white', width: 1, dash: 'solid', opacity: 0.3 }
                }
            ]
        };

        const config = { responsive: true };
        const fig = { 
            data: [macdTrace, signalTrace, histogramTrace, rsiTrace], 
            layout: layout, 
            config: config 
        };

        // Clear container and add title
        indicatorContainer.innerHTML = `<h3>技術指標 (MACD & RSI)</h3>`;
        
        // Create new chart div
        const chartDiv = document.createElement('div');
        chartDiv.id = `indicators-${stockId}-${Date.now()}`;
        chartDiv.style.height = 'calc(100% - 40px)';
        chartDiv.style.width = '100%';
        indicatorContainer.appendChild(chartDiv);
        
        // Create Plotly chart
        Plotly.newPlot(chartDiv.id, fig.data, fig.layout, {responsive: true});
        
    } catch (error) {
        console.error('Error loading indicators chart:', error);
        indicatorContainer.innerHTML = `<h3>技術指標 (MACD & RSI)</h3><p>Could not load indicators: ${error.message}</p>`;
    }
}

function showNoDataMessage() {
    document.getElementById("kline-container").innerHTML = `
        <h3>K線圖 (90天)</h3>
        <p style="text-align: center; padding: 40px; color: #888;">
            📊 此股票暫無價格數據<br>
            <small>請選擇有 📊 標記的股票</small>
        </p>`;
    
    document.getElementById("indicator-container").innerHTML = `
        <h3>技術指標 (MACD & RSI)</h3>
        <p style="text-align: center; padding: 40px; color: #888;">
            📈 此股票暫無技術指標數據<br>
            <small>請選擇有 📊 標記的股票</small>
        </p>`;
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