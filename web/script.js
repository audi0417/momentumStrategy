// 靜態版本的動能分析儀表板
class MomentumDashboard {
    constructor() {
        this.selectedStock = null;
        this.sortOrder = 'desc';
        this.searchQuery = '';
        this.isLoading = false;
        this.currentPeriod = '90';
        this.priceData = null;
        this.showMACD = true;
        this.showRSI = true;
        this.klinePanelOpen = false;

        this.init();
    }

    async init() {
        this.setupEventListeners();
        await this.loadData();
        this.updateMarketOverview();
        this.updateLastUpdate();
    }

    setupEventListeners() {
        // Search functionality
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchQuery = e.target.value.toLowerCase();
                this.filterTable();
            });
        }

        // Sort button
        const sortBtn = document.getElementById('sort-btn');
        if (sortBtn) {
            sortBtn.addEventListener('click', () => {
                this.toggleSort();
            });
        }

        // Refresh button
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.refreshData();
            });
        }

        // Period buttons
        document.querySelectorAll('.period-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.changePeriod(e.target.dataset.period);
            });
        });

        // Indicator toggle buttons
        document.querySelectorAll('.indicator-toggle-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const button = e.currentTarget;
                const indicator = button.dataset.indicator;
                this.toggleIndicator(indicator, button);
            });
        });

        // K-line panel toggle
        const chartToggleBtn = document.getElementById('chart-toggle-btn');
        if (chartToggleBtn) {
            chartToggleBtn.addEventListener('click', () => {
                this.toggleKlinePanel();
            });
        }

        const klineCloseBtn = document.getElementById('kline-close-btn');
        if (klineCloseBtn) {
            klineCloseBtn.addEventListener('click', () => {
                this.closeKlinePanel();
            });
        }

        // Notification button
        const notificationBtn = document.querySelector('.notification-btn');
        if (notificationBtn) {
            notificationBtn.addEventListener('click', () => {
                this.showToast('數據已是最新版本', 'info');
            });
        }
    }

    async loadData() {
        this.setLoading(true);

        try {
            // 從 JSON 文件載入數據
            const [historyResponse, priceResponse] = await Promise.all([
                fetch('historical_data.json'),
                fetch('stock_price_data.json')
            ]);

            if (!historyResponse.ok || !priceResponse.ok) {
                throw new Error('無法載入數據文件');
            }

            const data = await historyResponse.json();
            this.stockData = data;

            const priceData = await priceResponse.json();
            this.priceData = priceData;

            this.renderTable(data);
            this.updateMarketOverview();

            // Select first stock by default
            const firstRow = document.querySelector('tbody tr');
            if (firstRow) {
                this.selectStock(firstRow);
            }

            this.showToast('數據載入成功', 'success');

        } catch (error) {
            console.error('Error loading data:', error);
            this.showError('載入數據失敗: ' + error.message);
        } finally {
            this.setLoading(false);
        }
    }

    renderTable(data) {
        const dates = Object.keys(data.dates).sort().reverse();
        const latestDate = dates[0];

        // Add future planning dates
        const futureDates = this.generateFutureDates(latestDate, 3);
        const allDates = [...dates, ...futureDates];

        // Process stock data
        const stocksData = this.processStockData(data, dates, latestDate);

        // Create table
        const table = this.createTable(stocksData, allDates, futureDates);

        const container = document.getElementById('table-container');
        container.innerHTML = '';
        container.appendChild(table);

        // Add click events to rows
        this.addTableEventListeners();
    }

    processStockData(data, dates, latestDate) {
        const allStocks = {};

        dates.forEach(date => {
            const stocksOnDate = data.dates[date];
            for (const stockId in stocksOnDate) {
                if (!allStocks[stockId]) {
                    allStocks[stockId] = {
                        name: stocksOnDate[stockId].stock_name,
                        scores: {},
                        days: {}
                    };
                }
                allStocks[stockId].scores[date] = stocksOnDate[stockId].momentum;
                allStocks[stockId].days[date] = stocksOnDate[stockId].days;
            }
        });

        // Sort by latest momentum score
        return Object.keys(allStocks)
            .sort((a, b) => {
                const scoreA = allStocks[a].scores[latestDate] || -Infinity;
                const scoreB = allStocks[b].scores[latestDate] || -Infinity;
                return this.sortOrder === 'desc' ? scoreB - scoreA : scoreA - scoreB;
            })
            .map(stockId => ({
                id: stockId,
                name: allStocks[stockId].name,
                scores: allStocks[stockId].scores,
                days: allStocks[stockId].days,
                latestScore: allStocks[stockId].scores[latestDate] || 0
            }));
    }

    createTable(stocksData, allDates, futureDates) {
        const table = document.createElement('table');
        table.className = 'fade-in';

        // Create header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');

        const stockHeader = document.createElement('th');
        stockHeader.innerHTML = '<i class="fas fa-building"></i> 股票';
        headerRow.appendChild(stockHeader);

        allDates.forEach(date => {
            const dateHeader = document.createElement('th');
            dateHeader.textContent = this.formatDate(date);

            if (futureDates.includes(date)) {
                dateHeader.className = 'future-date';
                dateHeader.style.color = 'var(--muted-foreground)';
                dateHeader.style.fontStyle = 'italic';
            }

            headerRow.appendChild(dateHeader);
        });

        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create body
        const tbody = document.createElement('tbody');

        stocksData.forEach(stock => {
            const row = document.createElement('tr');
            row.dataset.stockId = stock.id;
            row.className = 'slide-up';

            // Stock name cell
            const nameCell = document.createElement('td');
            nameCell.innerHTML = `
                <div class="stock-name">${stock.name}</div>
                <div class="stock-code">${stock.id}</div>
            `;
            row.appendChild(nameCell);

            // Score cells
            allDates.forEach(date => {
                const cell = document.createElement('td');
                const score = stock.scores[date];
                const days = stock.days[date];

                if (score !== undefined) {
                    cell.innerHTML = `
                        <div class="momentum-score ${this.getScoreColorClass(score)}">${score.toFixed(2)}%</div>
                        ${days ? `<div class="momentum-days">${days}天</div>` : ''}
                    `;
                } else {
                    cell.textContent = '';
                }

                if (futureDates.includes(date)) {
                    cell.className += ' future-cell';
                    cell.style.backgroundColor = 'var(--muted)';
                    cell.style.border = '1px dashed var(--border)';
                }

                row.appendChild(cell);
            });

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        return table;
    }

    getScoreColorClass(score) {
        if (score > 20) return 'score-excellent';
        if (score > 10) return 'score-good';
        if (score > 5) return 'score-neutral';
        if (score > 0) return 'score-poor';
        return 'score-bad';
    }

    addTableEventListeners() {
        document.querySelectorAll('tbody tr').forEach(row => {
            row.addEventListener('click', () => {
                this.selectStock(row);
            });
        });
    }

    selectStock(row) {
        // Remove previous selection
        document.querySelectorAll('tbody tr').forEach(r => {
            r.classList.remove('selected');
        });

        // Add selection
        row.classList.add('selected');

        const stockId = row.dataset.stockId;
        const stockName = row.querySelector('.stock-name').textContent;

        this.selectedStock = { id: stockId, name: stockName };

        // Update stock info card
        this.updateStockInfo(stockId, stockName);

        // Load charts
        this.loadCharts(stockId);
    }

    updateStockInfo(stockId, stockName) {
        document.getElementById('selected-stock-name').textContent = stockName;
        document.getElementById('selected-stock-code').textContent = stockId;
        document.getElementById('stock-status').textContent = '已選擇';

        const stockCard = document.getElementById('stock-info-card');
        stockCard.classList.add('fade-in');
    }

    loadCharts(stockId) {
        this.loadPerformanceSummary(stockId);
        this.loadMomentumChart(stockId);
        // K-line chart loaded on demand when panel is opened
    }

    toggleKlinePanel() {
        if (this.klinePanelOpen) {
            this.closeKlinePanel();
        } else {
            this.openKlinePanel();
        }
    }

    openKlinePanel() {
        if (!this.selectedStock) {
            this.showToast('請先選擇股票', 'warning');
            return;
        }

        const panel = document.getElementById('kline-panel');
        panel.classList.add('open');
        this.klinePanelOpen = true;

        // Update panel title with stock info
        const klineStockInfo = document.getElementById('kline-stock-info');
        klineStockInfo.textContent = `${this.selectedStock.name} (${this.selectedStock.id})`;

        // Load K-line chart
        this.loadIntegratedChart(this.selectedStock.id);

        // Update toggle button
        const toggleBtn = document.getElementById('chart-toggle-btn');
        toggleBtn.classList.add('active');
        toggleBtn.querySelector('span').textContent = '關閉K線';
    }

    closeKlinePanel() {
        const panel = document.getElementById('kline-panel');
        panel.classList.remove('open');
        this.klinePanelOpen = false;

        // Update toggle button
        const toggleBtn = document.getElementById('chart-toggle-btn');
        toggleBtn.classList.remove('active');
        toggleBtn.querySelector('span').textContent = 'K線圖';
    }

    loadIntegratedChart(stockId) {
        const container = document.getElementById('integrated-chart-container');
        container.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i><span>載入圖表...</span></div>';

        setTimeout(() => {
            try {
                if (!this.priceData || !this.priceData[stockId]) {
                    container.innerHTML = `
                        <div class="chart-placeholder">
                            <i class="fas fa-exclamation-triangle"></i>
                            <p>無法找到 ${stockId} 的價格數據</p>
                        </div>
                    `;
                    return;
                }

                const stockPriceData = this.priceData[stockId].price_data;
                const period = parseInt(this.currentPeriod);

                // Filter data by period
                const dates = stockPriceData.dates.slice(-period);
                const opens = stockPriceData.open.slice(-period);
                const highs = stockPriceData.high.slice(-period);
                const lows = stockPriceData.low.slice(-period);
                const closes = stockPriceData.close.slice(-period);

                container.innerHTML = '';
                const chartDiv = document.createElement('div');
                chartDiv.id = `integrated-${stockId}-${Date.now()}`;
                chartDiv.style.height = '100%';
                chartDiv.style.width = '100%';
                container.appendChild(chartDiv);

                const traces = [];
                const layout = {
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    font: { color: 'hsl(210, 40%, 98%)' },
                    showlegend: true,
                    legend: {
                        x: 0,
                        y: 1,
                        bgcolor: 'rgba(0,0,0,0.5)',
                        font: { color: 'hsl(210, 40%, 98%)' }
                    },
                    margin: { l: 50, r: 50, t: 20, b: 50 }
                };

                // Candlestick trace (always show)
                traces.push({
                    x: dates,
                    open: opens,
                    high: highs,
                    low: lows,
                    close: closes,
                    type: 'candlestick',
                    name: 'K線',
                    increasing: { line: { color: '#ef4444' } },
                    decreasing: { line: { color: '#10b981' } },
                    xaxis: 'x',
                    yaxis: 'y'
                });

                // Setup axes
                layout.xaxis = {
                    title: '日期',
                    gridcolor: 'hsl(217, 32%, 17%)',
                    color: 'hsl(215, 20%, 65%)',
                    rangeslider: { visible: false }
                };

                layout.yaxis = {
                    title: '價格',
                    gridcolor: 'hsl(217, 32%, 17%)',
                    color: 'hsl(215, 20%, 65%)',
                    domain: [0.4, 1]
                };

                // Add technical indicators if enabled
                const indicators = stockPriceData.indicators;
                if (indicators) {
                    let currentDomain = 0.35;
                    const domainHeight = 0.15;

                    // Add MACD if enabled
                    if (this.showMACD && indicators.macd) {
                        const macdDates = dates.slice(-indicators.macd.length);

                        traces.push({
                            x: macdDates,
                            y: indicators.macd.slice(-period),
                            type: 'scatter',
                            mode: 'lines',
                            name: 'MACD',
                            line: { color: '#3b82f6', width: 2 },
                            xaxis: 'x',
                            yaxis: 'y2'
                        });

                        if (indicators.signal) {
                            traces.push({
                                x: macdDates,
                                y: indicators.signal.slice(-period),
                                type: 'scatter',
                                mode: 'lines',
                                name: 'Signal',
                                line: { color: '#f59e0b', width: 2 },
                                xaxis: 'x',
                                yaxis: 'y2'
                            });
                        }

                        layout.yaxis2 = {
                            title: 'MACD',
                            gridcolor: 'hsl(217, 32%, 17%)',
                            color: 'hsl(215, 20%, 65%)',
                            domain: [currentDomain - domainHeight, currentDomain]
                        };

                        currentDomain -= (domainHeight + 0.05);
                    }

                    // Add RSI if enabled
                    if (this.showRSI && indicators.rsi) {
                        const rsiDates = dates.slice(-indicators.rsi.length);

                        traces.push({
                            x: rsiDates,
                            y: indicators.rsi.slice(-period),
                            type: 'scatter',
                            mode: 'lines',
                            name: 'RSI',
                            line: { color: '#a855f7', width: 2 },
                            xaxis: 'x',
                            yaxis: this.showMACD ? 'y3' : 'y2'
                        });

                        // Add RSI reference lines (30 and 70)
                        traces.push({
                            x: rsiDates,
                            y: Array(rsiDates.length).fill(70),
                            type: 'scatter',
                            mode: 'lines',
                            name: 'RSI 70',
                            line: { color: '#ef4444', width: 1, dash: 'dash' },
                            xaxis: 'x',
                            yaxis: this.showMACD ? 'y3' : 'y2',
                            showlegend: false
                        });

                        traces.push({
                            x: rsiDates,
                            y: Array(rsiDates.length).fill(30),
                            type: 'scatter',
                            mode: 'lines',
                            name: 'RSI 30',
                            line: { color: '#10b981', width: 1, dash: 'dash' },
                            xaxis: 'x',
                            yaxis: this.showMACD ? 'y3' : 'y2',
                            showlegend: false
                        });

                        if (this.showMACD) {
                            layout.yaxis3 = {
                                title: 'RSI',
                                gridcolor: 'hsl(217, 32%, 17%)',
                                color: 'hsl(215, 20%, 65%)',
                                domain: [0, 0.15],
                                range: [0, 100]
                            };
                        } else {
                            layout.yaxis2 = {
                                title: 'RSI',
                                gridcolor: 'hsl(217, 32%, 17%)',
                                color: 'hsl(215, 20%, 65%)',
                                domain: [0, 0.3],
                                range: [0, 100]
                            };
                        }
                    }

                    // Adjust K-line domain based on indicators shown
                    if (this.showMACD && this.showRSI) {
                        layout.yaxis.domain = [0.45, 1];
                    } else if (this.showMACD || this.showRSI) {
                        layout.yaxis.domain = [0.35, 1];
                    }
                }

                const config = {
                    displayModeBar: false,
                    responsive: true
                };

                Plotly.newPlot(chartDiv.id, traces, layout, config);

            } catch (error) {
                console.error('Error loading integrated chart:', error);
                container.innerHTML = `
                    <div class="chart-placeholder">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>載入圖表失敗</p>
                    </div>
                `;
            }
        }, 500);
    }

    loadMomentumChart(stockId) {
        const container = document.getElementById('momentum-chart-container');
        container.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i><span>載入動能圖表...</span></div>';

        setTimeout(() => {
            try {
                // Get stock data
                const stockMomentumData = this.getStockMomentumData(stockId);

                if (!stockMomentumData || stockMomentumData.length === 0) {
                    container.innerHTML = `
                        <div class="chart-placeholder">
                            <i class="fas fa-exclamation-triangle"></i>
                            <p>無法找到 ${stockId} 的動能數據</p>
                        </div>
                    `;
                    return;
                }

                // Clear container
                container.innerHTML = '';

                // Create chart div
                const chartDiv = document.createElement('div');
                chartDiv.id = `momentum-${stockId}-${Date.now()}`;
                chartDiv.style.height = '100%';
                chartDiv.style.width = '100%';
                container.appendChild(chartDiv);

                // Create Plotly chart
                const trace = {
                    x: stockMomentumData.map(d => d.date),
                    y: stockMomentumData.map(d => d.momentum),
                    type: 'scatter',
                    mode: 'lines+markers',
                    name: '動能',
                    line: {
                        color: '#2dd4bf',  // Teal color
                        width: 3
                    },
                    marker: {
                        color: '#2dd4bf',
                        size: 8
                    }
                };

                const layout = {
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    font: { color: 'hsl(210, 40%, 98%)' },
                    xaxis: {
                        title: '日期',
                        gridcolor: 'hsl(217, 32%, 17%)',
                        color: 'hsl(215, 20%, 65%)'
                    },
                    yaxis: {
                        title: '動能 (%)',
                        gridcolor: 'hsl(217, 32%, 17%)',
                        color: 'hsl(215, 20%, 65%)'
                    },
                    margin: { l: 50, r: 50, t: 20, b: 50 },
                    showlegend: false
                };

                const config = {
                    displayModeBar: false,
                    responsive: true
                };

                Plotly.newPlot(chartDiv.id, [trace], layout, config);

            } catch (error) {
                console.error('Error loading momentum chart:', error);
                container.innerHTML = `
                    <div class="chart-placeholder">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>載入動能圖表失敗</p>
                    </div>
                `;
            }
        }, 500);
    }

    loadPerformanceSummary(stockId) {
        const container = document.getElementById('performance-container');

        setTimeout(() => {
            const stockMomentumData = this.getStockMomentumData(stockId);
            const stockName = this.selectedStock.name;

            if (!stockMomentumData || stockMomentumData.length === 0) {
                container.innerHTML = `
                    <div class="chart-placeholder">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>無法找到 ${stockId} 的績效數據</p>
                    </div>
                `;
                return;
            }

            const latestMomentum = stockMomentumData[0].momentum;
            const avgMomentum = stockMomentumData.reduce((sum, d) => sum + d.momentum, 0) / stockMomentumData.length;
            const maxMomentum = Math.max(...stockMomentumData.map(d => d.momentum));
            const minMomentum = Math.min(...stockMomentumData.map(d => d.momentum));
            const totalDays = stockMomentumData[0].days || 0;

            container.innerHTML = `
                <div class="performance-summary">
                    <div class="performance-header">
                        <h4>${stockName} (${stockId}) 績效摘要</h4>
                    </div>
                    <div class="performance-metrics">
                        <div class="metric-card">
                            <div class="metric-icon">
                                <i class="fas fa-chart-line"></i>
                            </div>
                            <div class="metric-content">
                                <div class="metric-label">當前動能</div>
                                <div class="metric-value ${this.getScoreColorClass(latestMomentum)}">
                                    ${latestMomentum.toFixed(2)}%
                                </div>
                            </div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-icon">
                                <i class="fas fa-chart-bar"></i>
                            </div>
                            <div class="metric-content">
                                <div class="metric-label">平均動能</div>
                                <div class="metric-value">
                                    ${avgMomentum.toFixed(2)}%
                                </div>
                            </div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-icon">
                                <i class="fas fa-arrow-up"></i>
                            </div>
                            <div class="metric-content">
                                <div class="metric-label">最高動能</div>
                                <div class="metric-value score-excellent">
                                    ${maxMomentum.toFixed(2)}%
                                </div>
                            </div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-icon">
                                <i class="fas fa-arrow-down"></i>
                            </div>
                            <div class="metric-content">
                                <div class="metric-label">最低動能</div>
                                <div class="metric-value score-poor">
                                    ${minMomentum.toFixed(2)}%
                                </div>
                            </div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-icon">
                                <i class="fas fa-calendar-alt"></i>
                            </div>
                            <div class="metric-content">
                                <div class="metric-label">持續天數</div>
                                <div class="metric-value">
                                    ${totalDays} 天
                                </div>
                            </div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-icon">
                                <i class="fas fa-star"></i>
                            </div>
                            <div class="metric-content">
                                <div class="metric-label">動能評級</div>
                                <div class="metric-value">
                                    ${this.getMomentumRating(latestMomentum)}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }, 300);
    }

    getStockMomentumData(stockId) {
        if (!this.stockData || !this.stockData.dates) return [];

        const dates = Object.keys(this.stockData.dates).sort().reverse();
        const result = [];

        dates.forEach(date => {
            const stockInfo = this.stockData.dates[date][stockId];
            if (stockInfo) {
                result.push({
                    date: date,
                    momentum: stockInfo.momentum,
                    days: stockInfo.days
                });
            }
        });

        return result;
    }

    getMomentumRating(momentum) {
        if (momentum > 20) return 'A+';
        if (momentum > 15) return 'A';
        if (momentum > 10) return 'B+';
        if (momentum > 5) return 'B';
        if (momentum > 0) return 'C';
        return 'D';
    }

    changePeriod(period) {
        this.currentPeriod = period;

        // Update active button
        document.querySelectorAll('.period-btn').forEach(btn => {
            btn.classList.remove('active');
        });

        document.querySelectorAll(`[data-period="${period}"]`).forEach(btn => {
            btn.classList.add('active');
        });

        // Reload integrated chart if stock is selected
        if (this.selectedStock) {
            this.loadIntegratedChart(this.selectedStock.id);
        }
    }

    toggleIndicator(indicator, button) {
        if (indicator === 'macd') {
            this.showMACD = !this.showMACD;
        } else if (indicator === 'rsi') {
            this.showRSI = !this.showRSI;
        }

        // Update button state
        button.classList.toggle('active');

        // Reload integrated chart if stock is selected
        if (this.selectedStock) {
            this.loadIntegratedChart(this.selectedStock.id);
        }

        const status = button.classList.contains('active') ? '顯示' : '隱藏';
        this.showToast(`${indicator.toUpperCase()} ${status}`, 'info');
    }

    toggleSort() {
        this.sortOrder = this.sortOrder === 'desc' ? 'asc' : 'desc';

        if (this.stockData) {
            this.renderTable(this.stockData);
        }

        const sortBtn = document.getElementById('sort-btn');
        sortBtn.innerHTML = this.sortOrder === 'desc'
            ? '<i class="fas fa-sort-amount-down"></i>'
            : '<i class="fas fa-sort-amount-up"></i>';

        this.showToast(`已切換為${this.sortOrder === 'desc' ? '降序' : '升序'}排列`, 'info');
    }

    filterTable() {
        const rows = document.querySelectorAll('tbody tr');
        let visibleCount = 0;

        rows.forEach(row => {
            const stockName = row.querySelector('.stock-name').textContent.toLowerCase();
            const stockCode = row.querySelector('.stock-code').textContent.toLowerCase();

            const matches = stockName.includes(this.searchQuery) ||
                           stockCode.includes(this.searchQuery);

            row.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
        });

        if (this.searchQuery && visibleCount === 0) {
            this.showToast('未找到匹配的股票', 'warning');
        }
    }

    async refreshData() {
        const refreshBtn = document.getElementById('refresh-btn');
        refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        await this.loadData();

        refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
        this.updateLastUpdate();
    }

    updateMarketOverview() {
        if (!this.stockData || !this.stockData.dates) return;

        const dates = Object.keys(this.stockData.dates);
        const latestDate = dates.sort().reverse()[0];
        const latestData = this.stockData.dates[latestDate];

        const scores = Object.values(latestData).map(stock => stock.momentum);
        const strongStocks = scores.filter(score => score > 10).length;
        const avgMomentum = scores.reduce((sum, score) => sum + score, 0) / scores.length;

        document.getElementById('strong-stocks').textContent = strongStocks;
        document.getElementById('avg-momentum').textContent = avgMomentum.toFixed(2);
        document.getElementById('total-stocks').textContent = scores.length;

        this.updateLastUpdate();
    }

    updateLastUpdate() {
        const now = new Date();
        const timeString = now.toLocaleTimeString('zh-TW', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit'
        });

        document.getElementById('last-update').textContent = timeString;
    }

    setLoading(loading) {
        this.isLoading = loading;
        const container = document.getElementById('table-container');

        if (loading) {
            container.innerHTML = `
                <div class="loading-spinner">
                    <i class="fas fa-spinner fa-spin"></i>
                    <span>載入數據中...</span>
                </div>
            `;
        }
    }

    showError(message) {
        const container = document.getElementById('table-container');
        container.innerHTML = `
            <div class="chart-placeholder">
                <i class="fas fa-exclamation-triangle"></i>
                <p>${message}</p>
                <button onclick="dashboard.refreshData()" class="refresh-btn">
                    <i class="fas fa-sync-alt"></i> 重試
                </button>
            </div>
        `;
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icon = this.getToastIcon(type);
        toast.innerHTML = `
            <i class="${icon}"></i>
            <span>${message}</span>
        `;

        container.appendChild(toast);

        // Auto remove after 3 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 3000);
    }

    getToastIcon(type) {
        switch (type) {
            case 'success': return 'fas fa-check-circle';
            case 'error': return 'fas fa-exclamation-circle';
            case 'warning': return 'fas fa-exclamation-triangle';
            default: return 'fas fa-info-circle';
        }
    }

    generateFutureDates(latestDate, count) {
        const futureDates = [];
        if (!latestDate) return futureDates;

        const lastDate = new Date(latestDate);
        let daysAdded = 0;
        let dayOffset = 1;

        while (daysAdded < count) {
            const futureDate = new Date(lastDate);
            futureDate.setDate(lastDate.getDate() + dayOffset);

            // Skip weekends
            if (futureDate.getDay() !== 0 && futureDate.getDay() !== 6) {
                futureDates.push(futureDate.toISOString().split('T')[0]);
                daysAdded++;
            }
            dayOffset++;
        }

        return futureDates;
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('zh-TW', {
            month: 'short',
            day: 'numeric'
        });
    }
}

// CSS for additional styling
const additionalStyles = `
.momentum-score {
    font-weight: 600;
    font-size: 0.9rem;
}

.momentum-days {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    margin-top: 2px;
}

.signal-badges {
    display: inline-flex;
    gap: 0.25rem;
    margin-left: 0.5rem;
}

.signal-badge {
    display: inline-block;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
}

.signal-badge.rsi-badge {
    background: #a855f7;
    color: white;
}

.signal-badge.macd-badge {
    background: #3b82f6;
    color: white;
}

.stock-name-cell {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.chart-panel-large {
    grid-column: 1 / -1;
    min-height: 600px;
}

.chart-content-large {
    min-height: 550px;
}

.chart-controls {
    display: flex;
    gap: 1rem;
    align-items: center;
    flex-wrap: wrap;
}

.control-group {
    display: flex;
    gap: 0.5rem;
    align-items: center;
}

.control-group label {
    font-size: 0.875rem;
    color: var(--muted-foreground);
    font-weight: 500;
}

.period-btn, .indicator-toggle-btn {
    padding: 0.375rem 0.75rem;
    border: 1px solid var(--border);
    background: var(--muted);
    color: var(--foreground);
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 0.875rem;
    transition: all 0.2s ease;
}

.period-btn:hover, .indicator-toggle-btn:hover {
    background: var(--accent);
    border-color: var(--primary);
}

.period-btn.active, .indicator-toggle-btn.active {
    background: var(--primary);
    color: var(--primary-foreground);
    border-color: var(--primary);
}

.indicator-toggle-btn i {
    margin-right: 0.25rem;
}

/* K-line Slide-out Panel */
.kline-panel {
    position: fixed;
    top: 0;
    right: -50%;
    width: 50%;
    height: 100vh;
    background: var(--background);
    border-left: 1px solid var(--border);
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
    z-index: 1000;
    transition: right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.kline-panel.open {
    right: 0;
}

.kline-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--border);
    background: var(--card);
}

.kline-panel-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.kline-panel-title i {
    font-size: 1.5rem;
    color: var(--primary);
}

.kline-panel-title h3 {
    margin: 0;
    font-size: 1.25rem;
    color: var(--foreground);
}

.kline-stock-info {
    font-size: 0.875rem;
    color: var(--muted-foreground);
    padding: 0.25rem 0.75rem;
    background: var(--muted);
    border-radius: var(--radius);
}

.kline-close-btn {
    width: 36px;
    height: 36px;
    border: none;
    background: var(--muted);
    color: var(--foreground);
    border-radius: var(--radius);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
}

.kline-close-btn:hover {
    background: var(--accent);
    color: var(--accent-foreground);
}

.kline-panel-controls {
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--border);
    background: var(--card);
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
}

.kline-panel-content {
    flex: 1;
    padding: 1rem;
    overflow: auto;
}

/* Chart toggle button in stock info card */
.stock-actions {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.chart-toggle-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: var(--muted);
    color: var(--foreground);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    transition: all 0.2s ease;
}

.chart-toggle-btn:hover {
    background: var(--accent);
    border-color: var(--primary);
}

.chart-toggle-btn.active {
    background: var(--primary);
    color: var(--primary-foreground);
    border-color: var(--primary);
}

.chart-toggle-btn i {
    font-size: 1rem;
}

/* Responsive design for slide-out panel */
@media (max-width: 1400px) {
    .kline-panel {
        width: 60%;
        right: -60%;
    }
}

@media (max-width: 1024px) {
    .kline-panel {
        width: 70%;
        right: -70%;
    }
}

@media (max-width: 768px) {
    .kline-panel {
        width: 90%;
        right: -90%;
    }
}

.score-excellent { color: #10b981; }
.score-good { color: #06b6d4; }
.score-neutral { color: var(--foreground); }
.score-poor { color: #f59e0b; }
.score-bad { color: #ef4444; }

.performance-summary {
    padding: 1rem;
    height: 100%;
}

.performance-header {
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
}

.performance-header h4 {
    margin: 0;
    font-size: 1rem;
    color: var(--foreground);
}

.performance-metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 1rem;
}

.metric-card {
    background: var(--muted);
    border-radius: var(--radius);
    padding: 1rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    transition: all 0.2s ease;
}

.metric-card:hover {
    background: var(--accent);
    transform: translateY(-2px);
}

.metric-icon {
    width: 32px;
    height: 32px;
    background: var(--primary);
    color: var(--primary-foreground);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.875rem;
    flex-shrink: 0;
}

.metric-content {
    flex: 1;
    min-width: 0;
}

.metric-label {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    margin-bottom: 0.25rem;
}

.metric-value {
    font-size: 1rem;
    font-weight: 700;
    color: var(--foreground);
}

.future-cell {
    opacity: 0.5;
}

@media (max-width: 768px) {
    .performance-metrics {
        grid-template-columns: 1fr;
    }

    .metric-card {
        padding: 0.75rem;
    }
}
`;

// Add styles to document
const styleSheet = document.createElement('style');
styleSheet.textContent = additionalStyles;
document.head.appendChild(styleSheet);

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new MomentumDashboard();
});

// Export for potential use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MomentumDashboard;
}
