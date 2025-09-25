/**
 * Dashboard Real-time Data Management
 * Handles real-time updates for dashboard statistics and data
 */

class DashboardRealtime {
    constructor() {
        this.refreshInterval = null;
        this.refreshRate = 30000; // 30 seconds
        this.isRefreshing = false;
        this.retryCount = 0;
        this.maxRetries = 3;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.startAutoRefresh();
        this.setupVisibilityHandler();
    }

    setupEventListeners() {
        // Manual refresh button
        const refreshBtn = document.getElementById('dashboard-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshData());
        }

        // Auto-refresh toggle
        const autoRefreshToggle = document.getElementById('auto-refresh-toggle');
        if (autoRefreshToggle) {
            autoRefreshToggle.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.startAutoRefresh();
                } else {
                    this.stopAutoRefresh();
                }
            });
        }

        // Refresh rate selector
        const refreshRateSelect = document.getElementById('refresh-rate-select');
        if (refreshRateSelect) {
            refreshRateSelect.addEventListener('change', (e) => {
                this.refreshRate = parseInt(e.target.value) * 1000;
                if (this.refreshInterval) {
                    this.stopAutoRefresh();
                    this.startAutoRefresh();
                }
            });
        }
    }

    setupVisibilityHandler() {
        // Pause refresh when tab is not visible
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopAutoRefresh();
            } else {
                this.startAutoRefresh();
                this.refreshData(); // Immediate refresh when tab becomes visible
            }
        });
    }

    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        this.refreshInterval = setInterval(() => {
            this.refreshData();
        }, this.refreshRate);
        
        console.log(`Dashboard auto-refresh started (${this.refreshRate / 1000}s interval)`);
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
        console.log('Dashboard auto-refresh stopped');
    }

    async refreshData() {
        if (this.isRefreshing) {
            console.log('Refresh already in progress, skipping...');
            return;
        }

        this.isRefreshing = true;
        this.showRefreshIndicator();

        try {
            const response = await fetch('/dashboard/api/refresh_data', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.success) {
                this.updateDashboardStats(data.stats);
                this.updateLastRefreshTime(data.timestamp);
                this.retryCount = 0; // Reset retry count on success
                this.showRefreshSuccess();
            } else {
                throw new Error(data.error || 'Unknown error occurred');
            }

        } catch (error) {
            console.error('Error refreshing dashboard data:', error);
            this.handleRefreshError(error);
        } finally {
            this.isRefreshing = false;
            this.hideRefreshIndicator();
        }
    }

    updateDashboardStats(stats) {
        // Update stat cards
        const statMappings = {
            'total_receipts': 'receipts-count',
            'total_receipts_amount': 'receipts-amount',
            'total_payments': 'payments-count', 
            'total_payments_amount': 'payments-amount',
            'total_debtors': 'debtors-count',
            'total_debtors_amount': 'debtors-amount',
            'total_creditors': 'creditors-count',
            'total_creditors_amount': 'creditors-amount',
            'total_inventory': 'inventory-count',
            'total_inventory_cost': 'inventory-cost',
            'gross_profit': 'gross-profit',
            'true_profit': 'true-profit'
        };

        Object.entries(statMappings).forEach(([statKey, elementId]) => {
            const element = document.getElementById(elementId);
            if (element && stats[statKey] !== undefined) {
                // Animate the update
                this.animateValueUpdate(element, stats[statKey]);
            }
        });

        // Update profit summary card
        this.updateProfitSummary(stats);
    }

    updateProfitSummary(stats) {
        const profitElement = document.querySelector('.profit-summary-value');
        if (profitElement) {
            const taxPrepMode = document.getElementById('taxPrepToggle')?.checked;
            const profitValue = taxPrepMode ? stats.true_profit : stats.gross_profit;
            this.animateValueUpdate(profitElement, profitValue);
        }
    }

    animateValueUpdate(element, newValue) {
        // Add update animation class
        element.classList.add('updating');
        
        // Update the value
        element.textContent = newValue;
        
        // Remove animation class after animation completes
        setTimeout(() => {
            element.classList.remove('updating');
        }, 300);
    }

    updateLastRefreshTime(timestamp) {
        const refreshTimeElement = document.getElementById('last-refresh-time');
        if (refreshTimeElement) {
            const date = new Date(timestamp);
            refreshTimeElement.textContent = `Last updated: ${date.toLocaleTimeString()}`;
        }
    }

    showRefreshIndicator() {
        const indicator = document.getElementById('refresh-indicator');
        if (indicator) {
            indicator.style.display = 'inline-block';
        }

        const refreshBtn = document.getElementById('dashboard-refresh-btn');
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i> Refreshing...';
        }
    }

    hideRefreshIndicator() {
        const indicator = document.getElementById('refresh-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }

        const refreshBtn = document.getElementById('dashboard-refresh-btn');
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Refresh';
        }
    }

    showRefreshSuccess() {
        this.showToast('Dashboard data updated successfully', 'success');
    }

    handleRefreshError(error) {
        this.retryCount++;
        
        if (this.retryCount <= this.maxRetries) {
            console.log(`Retrying refresh (${this.retryCount}/${this.maxRetries})...`);
            setTimeout(() => this.refreshData(), 2000 * this.retryCount);
        } else {
            this.showToast('Failed to refresh dashboard data. Please check your connection.', 'error');
            this.retryCount = 0;
        }
    }

    showToast(message, type = 'info') {
        // Create toast element if it doesn't exist
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = '9999';
            document.body.appendChild(toastContainer);
        }

        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        toastContainer.appendChild(toast);

        // Initialize and show toast
        const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
        bsToast.show();

        // Remove toast element after it's hidden
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }

    // Public methods for external control
    forceRefresh() {
        this.refreshData();
    }

    setRefreshRate(seconds) {
        this.refreshRate = seconds * 1000;
        if (this.refreshInterval) {
            this.stopAutoRefresh();
            this.startAutoRefresh();
        }
    }

    destroy() {
        this.stopAutoRefresh();
        // Remove event listeners if needed
    }
}

// Initialize dashboard real-time updates when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize on dashboard pages
    if (document.querySelector('[data-user-id]')) {
        window.dashboardRealtime = new DashboardRealtime();
        console.log('Dashboard real-time updates initialized');
    }
});

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardRealtime;
}