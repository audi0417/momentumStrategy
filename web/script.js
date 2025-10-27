// Modern JavaScript for Momentum Analysis Dashboard
class MomentumDashboard {
    constructor() {
        this.selectedStock = null;
        this.stockData = null;
        this.sortOrder = 'desc';
        this.currentPeriod = '90';
        this.searchQuery = '';
        this.isLoading = false;
        
        this.init();
    }

    async init() {
        // Check if Plotly is available
        if (typeof Plotly === 'undefined') {
            await this.loadPlotly();
        }
        
        this.setupEventListeners();
        await this.loadData();
        this.updateMarketOverview();
    }

    async loadPlotly() {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.plot.ly/plotly-latest.min.js';
            script.onload = () => {
                console.log('Plotly loaded successfully');
                resolve();
            };
            script.onerror = () => {
                console.error('Failed to load Plotly');
                this.showToast('無法載入圖表庫', 'error');
                reject();
            };
            document.head.appendChild(script);
        });
    }

    setupEventListeners() {
        // Search functionality
        const searchInput = document.getElementById('search-input');
        searchInput.addEventListener('input', (e) => {
            this.searchQuery = e.target.value.toLowerCase();
            this.filterTable();
        });

        // Sort button
        const sortBtn = document.getElementById('sort-btn');
        sortBtn.addEventListener('click', () => {
            this.toggleSort();
        });

        // Refresh button
        const refreshBtn = document.getElementById('refresh-btn');
        refreshBtn.addEventListener('click', () => {
            this.refreshData();
        });

        // Period buttons
        document.querySelectorAll('.period-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.changePeriod(e.target.dataset.period);
            });
        });

        // Notification button
        const notificationBtn = document.querySelector('.notification-btn');
        notificationBtn.addEventListener('click', () => {
            this.showToast('通知功能開發中...', 'info');
        });
    }

    async loadData() {
        this.setLoading(true);
        
        try {
            const response = await fetch('/api/data');
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            this.stockData = data;
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
        const futureDates = this.generateFutureDates(latestDate, 5);
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
                        scores: {}
                    };
                }
                allStocks[stockId].scores[date] = stocksOnDate[stockId].momentum;
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
                
                if (score !== undefined) {
                    cell.textContent = score.toFixed(2);
                    cell.className = this.getScoreColorClass(score);
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
        if (score > 5) return 'score-excellent';
        if (score > 2) return 'score-good';
        if (score > -2) return 'score-neutral';
        if (score > -5) return 'score-poor';
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

    async loadCharts(stockId) {
        await Promise.all([
            this.loadKlineChart(stockId),
            this.loadIndicatorsChart(stockId)
        ]);
    }

    async loadKlineChart(stockId) {
        const container = document.getElementById('kline-container');
        container.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i><span>載入K線圖...</span></div>';
        
        try {
            const response = await fetch(`/api/kline/${stockId}?period=${this.currentPeriod}`);
            
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            
            const chartData = await response.json();
            
            if (chartData.error) {
                throw new Error(chartData.error);
            }
            
            // Clear container
            container.innerHTML = '';
            
            // Create chart div
            const chartDiv = document.createElement('div');
            chartDiv.id = `kline-${stockId}-${Date.now()}`;
            chartDiv.style.height = '100%';
            chartDiv.style.width = '100%';
            container.appendChild(chartDiv);
            
            // Customize layout for dark theme
            const layout = {
                ...chartData.layout,
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: { color: 'hsl(210, 40%, 98%)' },
                xaxis: {
                    ...chartData.layout.xaxis,
                    gridcolor: 'hsl(217, 32%, 17%)',
                    color: 'hsl(215, 20%, 65%)'
                },
                yaxis: {
                    ...chartData.layout.yaxis,
                    gridcolor: 'hsl(217, 32%, 17%)',
                    color: 'hsl(215, 20%, 65%)'
                }
            };
            
            const config = {
                ...chartData.config,
                displayModeBar: false,
                responsive: true
            };
            
            // Create chart
            await Plotly.newPlot(chartDiv.id, chartData.data, layout, config);
            
        } catch (error) {
            console.error('Error loading K-line chart:', error);
            container.innerHTML = `
                <div class="chart-placeholder">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>載入K線圖失敗: ${error.message}</p>
                </div>
            `;
        }
    }

    async loadIndicatorsChart(stockId) {
        const container = document.getElementById('indicator-container');
        container.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i><span>載入技術指標...</span></div>';
        
        try {
            const response = await fetch(`/api/indicators/${stockId}`);
            
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            
            const chartData = await response.json();
            
            if (chartData.error) {
                throw new Error(chartData.error);
            }
            
            // Clear container
            container.innerHTML = '';
            
            // Create chart div
            const chartDiv = document.createElement('div');
            chartDiv.id = `indicators-${stockId}-${Date.now()}`;
            chartDiv.style.height = '100%';
            chartDiv.style.width = '100%';
            container.appendChild(chartDiv);
            
            // Customize layout for dark theme
            const layout = {
                ...chartData.layout,
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: { color: 'hsl(210, 40%, 98%)' },
                xaxis: {
                    ...chartData.layout.xaxis,
                    gridcolor: 'hsl(217, 32%, 17%)',
                    color: 'hsl(215, 20%, 65%)'
                },
                yaxis: {
                    ...chartData.layout.yaxis,
                    gridcolor: 'hsl(217, 32%, 17%)',
                    color: 'hsl(215, 20%, 65%)'
                }
            };
            
            const config = {
                ...chartData.config,
                displayModeBar: false,
                responsive: true
            };
            
            // Create chart
            await Plotly.newPlot(chartDiv.id, chartData.data, layout, config);
            
        } catch (error) {
            console.error('Error loading indicators chart:', error);
            container.innerHTML = `
                <div class="chart-placeholder">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>載入技術指標失敗: ${error.message}</p>
                </div>
            `;
        }
    }

    changePeriod(period) {
        this.currentPeriod = period;
        
        // Update active button
        document.querySelectorAll('.period-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        
        document.querySelector(`[data-period="${period}"]`).classList.add('active');
        
        // Reload chart if stock is selected
        if (this.selectedStock) {
            this.loadKlineChart(this.selectedStock.id);
        }
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
    }

    filterTable() {
        const rows = document.querySelectorAll('tbody tr');
        
        rows.forEach(row => {
            const stockName = row.querySelector('.stock-name').textContent.toLowerCase();
            const stockCode = row.querySelector('.stock-code').textContent.toLowerCase();
            
            const matches = stockName.includes(this.searchQuery) || 
                           stockCode.includes(this.searchQuery);
            
            row.style.display = matches ? '' : 'none';
        });
    }

    async refreshData() {
        const refreshBtn = document.getElementById('refresh-btn');
        refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        
        await this.loadData();
        
        refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i>';
        this.updateLastUpdate();
    }

    updateMarketOverview() {
        if (!this.stockData) return;
        
        const dates = Object.keys(this.stockData.dates);
        const latestDate = dates.sort().reverse()[0];
        const latestData = this.stockData.dates[latestDate];
        
        const scores = Object.values(latestData).map(stock => stock.momentum);
        const strongStocks = scores.filter(score => score > 2).length;
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

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new MomentumDashboard();
});

// Export for potential use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MomentumDashboard;
}