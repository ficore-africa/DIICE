/**
 * Offline UI Components for FiCore Africa
 * Handles offline indicators, sync status, and user feedback
 */

class OfflineUI {
    constructor() {
        this.isOnline = navigator.onLine;
        this.syncInProgress = false;
        this.init();
    }

    init() {
        this.createOfflineIndicators();
        this.setupNetworkListeners();
        this.setupSyncStatusListener();
        this.enhanceFormsForOffline();
        this.createOfflineDataViewer();
    }

    // Create offline status indicators
    createOfflineIndicators() {
        // Network status indicator in header
        const headerRight = document.querySelector('.header-right');
        if (headerRight) {
            const networkStatus = document.createElement('div');
            networkStatus.id = 'network-status';
            networkStatus.className = this.isOnline ? 'network-online' : 'network-offline';
            networkStatus.innerHTML = `
                <i class="bi ${this.isOnline ? 'bi-wifi' : 'bi-wifi-off'}"></i>
                <span>${this.isOnline ? 'Online' : 'Offline'}</span>
            `;
            headerRight.insertBefore(networkStatus, headerRight.firstChild);
        }

        // Offline banner
        this.createOfflineBanner();

        // Sync status indicator
        this.createSyncStatusIndicator();
    }

    createOfflineBanner() {
        const banner = document.createElement('div');
        banner.id = 'offline-banner';
        banner.className = 'offline-banner';
        banner.style.display = this.isOnline ? 'none' : 'block';
        banner.innerHTML = `
            <div class="container-fluid">
                <div class="d-flex align-items-center justify-content-between">
                    <div class="d-flex align-items-center">
                        <i class="bi bi-wifi-off me-2"></i>
                        <span>You're offline. Changes will be saved locally and synced when you're back online.</span>
                    </div>
                    <button class="btn btn-sm btn-outline-light" onclick="offlineUI.showOfflineData()">
                        View Offline Data
                    </button>
                </div>
            </div>
        `;

        // Insert after header
        const header = document.querySelector('header');
        if (header) {
            header.insertAdjacentElement('afterend', banner);
        }
    }

    createSyncStatusIndicator() {
        const syncStatus = document.createElement('div');
        syncStatus.id = 'sync-status';
        syncStatus.className = 'sync-status';
        syncStatus.innerHTML = `
            <div class="sync-indicator">
                <i class="bi bi-arrow-repeat"></i>
                <span>Syncing...</span>
            </div>
        `;
        document.body.appendChild(syncStatus);
    }

    // Network status listeners
    setupNetworkListeners() {
        window.addEventListener('online', () => {
            this.isOnline = true;
            this.updateNetworkStatus();
            this.showConnectionRestored();
        });

        window.addEventListener('offline', () => {
            this.isOnline = false;
            this.updateNetworkStatus();
            this.showConnectionLost();
        });
    }

    updateNetworkStatus() {
        const networkStatus = document.getElementById('network-status');
        const offlineBanner = document.getElementById('offline-banner');

        if (networkStatus) {
            networkStatus.className = this.isOnline ? 'network-online' : 'network-offline';
            networkStatus.innerHTML = `
                <i class="bi ${this.isOnline ? 'bi-wifi' : 'bi-wifi-off'}"></i>
                <span>${this.isOnline ? 'Online' : 'Offline'}</span>
            `;
        }

        if (offlineBanner) {
            offlineBanner.style.display = this.isOnline ? 'none' : 'block';
        }

        // Update form buttons
        this.updateFormButtons();

        // Update offline indicators on data tables
        this.updateDataTableIndicators();
    }

    showConnectionRestored() {
        this.showToast('Connection restored! Syncing your offline data...', 'success');
        
        // Trigger sync if offline manager is available
        if (window.offlineManager) {
            window.offlineManager.syncOfflineData();
        }
    }

    showConnectionLost() {
        this.showToast('Connection lost. You can continue working offline.', 'warning');
    }

    // Sync status management
    setupSyncStatusListener() {
        // Listen for sync events from offline manager
        document.addEventListener('syncStart', () => {
            this.showSyncStatus(true);
        });

        document.addEventListener('syncComplete', (event) => {
            this.showSyncStatus(false);
            const { successful, failed } = event.detail;
            
            if (failed === 0) {
                this.showToast(`Successfully synced ${successful} items`, 'success');
            } else {
                this.showToast(`Synced ${successful} items, ${failed} failed`, 'warning');
            }
        });

        document.addEventListener('syncError', (event) => {
            this.showSyncStatus(false);
            this.showToast('Sync failed. Will retry automatically.', 'error');
        });
    }

    showSyncStatus(show) {
        const syncStatus = document.getElementById('sync-status');
        if (syncStatus) {
            syncStatus.style.display = show ? 'block' : 'none';
        }
        this.syncInProgress = show;
    }

    // Form enhancements for offline
    enhanceFormsForOffline() {
        document.querySelectorAll('form[data-offline-enabled]').forEach(form => {
            this.enhanceForm(form);
        });

        // Auto-enhance common forms
        document.querySelectorAll('form[action*="/debtors"], form[action*="/creditors"], form[action*="/inventory"]').forEach(form => {
            form.setAttribute('data-offline-enabled', 'true');
            this.enhanceForm(form);
        });
    }

    enhanceForm(form) {
        const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
        if (submitBtn) {
            submitBtn.dataset.onlineText = submitBtn.textContent;
            submitBtn.dataset.offlineText = 'Save Offline';
            submitBtn.classList.add('form-submit-btn');
        }

        // Add offline indicator to form
        const offlineIndicator = document.createElement('div');
        offlineIndicator.className = 'offline-form-indicator';
        offlineIndicator.style.display = this.isOnline ? 'none' : 'block';
        offlineIndicator.innerHTML = `
            <div class="alert alert-warning alert-sm">
                <i class="bi bi-wifi-off me-2"></i>
                <small>Offline mode: Data will be saved locally and synced when online.</small>
            </div>
        `;
        form.insertBefore(offlineIndicator, form.firstChild);

        // Register with offline manager
        if (window.offlineManager) {
            window.offlineManager.handleOfflineForm(form);
        }
    }

    updateFormButtons() {
        document.querySelectorAll('.form-submit-btn').forEach(btn => {
            if (!this.isOnline) {
                btn.textContent = btn.dataset.offlineText || 'Save Offline';
                btn.classList.add('btn-warning');
                btn.classList.remove('btn-primary');
            } else {
                btn.textContent = btn.dataset.onlineText || 'Submit';
                btn.classList.add('btn-primary');
                btn.classList.remove('btn-warning');
            }
        });

        // Show/hide offline form indicators
        document.querySelectorAll('.offline-form-indicator').forEach(indicator => {
            indicator.style.display = this.isOnline ? 'none' : 'block';
        });
    }

    // Data table indicators
    updateDataTableIndicators() {
        document.querySelectorAll('table tbody tr').forEach(row => {
            const offlineBadge = row.querySelector('.badge-offline');
            if (offlineBadge && this.isOnline) {
                // Fade out offline badges when back online
                offlineBadge.style.opacity = '0.5';
            }
        });
    }

    // Offline data viewer
    createOfflineDataViewer() {
        const modal = document.createElement('div');
        modal.id = 'offline-data-modal';
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Offline Data</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-3">
                                <div class="nav flex-column nav-pills" role="tablist">
                                    <button class="nav-link active" data-bs-toggle="pill" data-bs-target="#offline-debtors" role="tab">
                                        Debtors <span class="badge bg-secondary" id="debtors-count">0</span>
                                    </button>
                                    <button class="nav-link" data-bs-toggle="pill" data-bs-target="#offline-creditors" role="tab">
                                        Creditors <span class="badge bg-secondary" id="creditors-count">0</span>
                                    </button>
                                    <button class="nav-link" data-bs-toggle="pill" data-bs-target="#offline-inventory" role="tab">
                                        Inventory <span class="badge bg-secondary" id="inventory-count">0</span>
                                    </button>
                                    <button class="nav-link" data-bs-toggle="pill" data-bs-target="#sync-queue" role="tab">
                                        Sync Queue <span class="badge bg-warning" id="sync-queue-count">0</span>
                                    </button>
                                </div>
                            </div>
                            <div class="col-md-9">
                                <div class="tab-content">
                                    <div class="tab-pane fade show active" id="offline-debtors">
                                        <div class="table-responsive">
                                            <table class="table table-sm">
                                                <thead>
                                                    <tr>
                                                        <th>Name</th>
                                                        <th>Amount</th>
                                                        <th>Status</th>
                                                    </tr>
                                                </thead>
                                                <tbody id="offline-debtors-list"></tbody>
                                            </table>
                                        </div>
                                    </div>
                                    <div class="tab-pane fade" id="offline-creditors">
                                        <div class="table-responsive">
                                            <table class="table table-sm">
                                                <thead>
                                                    <tr>
                                                        <th>Name</th>
                                                        <th>Amount</th>
                                                        <th>Status</th>
                                                    </tr>
                                                </thead>
                                                <tbody id="offline-creditors-list"></tbody>
                                            </table>
                                        </div>
                                    </div>
                                    <div class="tab-pane fade" id="offline-inventory">
                                        <div class="table-responsive">
                                            <table class="table table-sm">
                                                <thead>
                                                    <tr>
                                                        <th>Name</th>
                                                        <th>Quantity</th>
                                                        <th>Price</th>
                                                        <th>Status</th>
                                                    </tr>
                                                </thead>
                                                <tbody id="offline-inventory-list"></tbody>
                                            </table>
                                        </div>
                                    </div>
                                    <div class="tab-pane fade" id="sync-queue">
                                        <div id="sync-queue-list">
                                            <p class="text-muted">No items in sync queue</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        <button type="button" class="btn btn-primary" onclick="offlineUI.syncNow()" ${!this.isOnline ? 'disabled' : ''}>
                            <i class="bi bi-arrow-repeat me-2"></i>Sync Now
                        </button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    async showOfflineData() {
        const modal = new bootstrap.Modal(document.getElementById('offline-data-modal'));
        
        // Load offline data
        if (window.offlineManager) {
            await this.loadOfflineDataCounts();
            await this.loadOfflineDataLists();
        }
        
        modal.show();
    }

    async loadOfflineDataCounts() {
        if (!window.offlineManager) return;

        try {
            const [debtors, creditors, inventory] = await Promise.all([
                window.offlineManager.getOfflineData('debtors'),
                window.offlineManager.getOfflineData('creditors'),
                window.offlineManager.getOfflineData('inventory')
            ]);

            document.getElementById('debtors-count').textContent = debtors.length;
            document.getElementById('creditors-count').textContent = creditors.length;
            document.getElementById('inventory-count').textContent = inventory.length;
            document.getElementById('sync-queue-count').textContent = window.offlineManager.syncQueue.length;
        } catch (error) {
            console.error('Error loading offline data counts:', error);
        }
    }

    async loadOfflineDataLists() {
        if (!window.offlineManager) return;

        try {
            // Load debtors
            const debtors = await window.offlineManager.getOfflineData('debtors');
            const debtorsList = document.getElementById('offline-debtors-list');
            debtorsList.innerHTML = debtors.map(debtor => `
                <tr>
                    <td>${debtor.name}</td>
                    <td>₦${debtor.amount || 0}</td>
                    <td>
                        <span class="badge ${debtor.synced ? 'bg-success' : 'bg-warning'}">
                            ${debtor.synced ? 'Synced' : 'Pending'}
                        </span>
                    </td>
                </tr>
            `).join('');

            // Load creditors
            const creditors = await window.offlineManager.getOfflineData('creditors');
            const creditorsList = document.getElementById('offline-creditors-list');
            creditorsList.innerHTML = creditors.map(creditor => `
                <tr>
                    <td>${creditor.name}</td>
                    <td>₦${creditor.amount || 0}</td>
                    <td>
                        <span class="badge ${creditor.synced ? 'bg-success' : 'bg-warning'}">
                            ${creditor.synced ? 'Synced' : 'Pending'}
                        </span>
                    </td>
                </tr>
            `).join('');

            // Load inventory
            const inventory = await window.offlineManager.getOfflineData('inventory');
            const inventoryList = document.getElementById('offline-inventory-list');
            inventoryList.innerHTML = inventory.map(item => `
                <tr>
                    <td>${item.name}</td>
                    <td>${item.quantity || 0}</td>
                    <td>₦${item.price || 0}</td>
                    <td>
                        <span class="badge ${item.synced ? 'bg-success' : 'bg-warning'}">
                            ${item.synced ? 'Synced' : 'Pending'}
                        </span>
                    </td>
                </tr>
            `).join('');

            // Load sync queue
            const syncQueueList = document.getElementById('sync-queue-list');
            if (window.offlineManager.syncQueue.length === 0) {
                syncQueueList.innerHTML = '<p class="text-muted">No items in sync queue</p>';
            } else {
                syncQueueList.innerHTML = window.offlineManager.syncQueue.map(item => `
                    <div class="card mb-2">
                        <div class="card-body py-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <strong>${item.storeName}</strong> - ${item.action}
                                    <br><small class="text-muted">${new Date(item.timestamp).toLocaleString()}</small>
                                </div>
                                <span class="badge bg-warning">Pending</span>
                            </div>
                        </div>
                    </div>
                `).join('');
            }
        } catch (error) {
            console.error('Error loading offline data lists:', error);
        }
    }

    async syncNow() {
        if (!this.isOnline || !window.offlineManager) {
            this.showToast('Cannot sync while offline', 'error');
            return;
        }

        try {
            this.showSyncStatus(true);
            await window.offlineManager.syncOfflineData();
            
            // Refresh the offline data modal
            await this.loadOfflineDataCounts();
            await this.loadOfflineDataLists();
        } catch (error) {
            console.error('Manual sync failed:', error);
            this.showToast('Sync failed. Please try again.', 'error');
        } finally {
            this.showSyncStatus(false);
        }
    }

    // Utility methods
    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="bi ${this.getIconForType(type)} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        // Add to toast container
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            document.body.appendChild(container);
        }

        container.appendChild(toast);
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();

        // Remove from DOM after hiding
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }

    getIconForType(type) {
        const icons = {
            'info': 'info-circle-fill',
            'success': 'check-circle-fill',
            'warning': 'exclamation-triangle-fill',
            'error': 'exclamation-circle-fill'
        };
        return icons[type] || 'info-circle-fill';
    }
}

// Initialize offline UI when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.offlineUI = new OfflineUI();
});

// Add CSS styles for offline components
const offlineStyles = `
<style>
.network-status {
    display: flex;
    align-items: center;
    padding: 0.25rem 0.5rem;
    border-radius: 15px;
    font-size: 0.8rem;
    margin-right: 0.5rem;
}

.network-online {
    background-color: #d4edda;
    color: #155724;
}

.network-offline {
    background-color: #f8d7da;
    color: #721c24;
}

.offline-banner {
    background: linear-gradient(135deg, #ff6b6b, #ee5a24);
    color: white;
    padding: 0.75rem 0;
    text-align: center;
    position: sticky;
    top: 0;
    z-index: 1030;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.sync-status {
    position: fixed;
    bottom: 20px;
    left: 20px;
    background: #007bff;
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 25px;
    display: none;
    z-index: 1050;
    box-shadow: 0 2px 10px rgba(0,0,0,0.2);
}

.sync-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.sync-indicator i {
    animation: spin 1s linear infinite;
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.offline-form-indicator {
    margin-bottom: 1rem;
}

.offline-form-indicator .alert {
    margin-bottom: 0;
    padding: 0.5rem 0.75rem;
}

.badge-offline {
    background-color: #ffc107 !important;
    color: #212529 !important;
}

.table-warning {
    background-color: rgba(255, 193, 7, 0.1);
}

@media (max-width: 768px) {
    .offline-banner {
        font-size: 0.9rem;
        padding: 0.5rem 0;
    }
    
    .network-status {
        font-size: 0.7rem;
        padding: 0.2rem 0.4rem;
    }
    
    .sync-status {
        bottom: 80px; /* Above mobile nav */
        left: 10px;
        font-size: 0.8rem;
        padding: 0.4rem 0.8rem;
    }
}
</style>
`;

// Inject styles
document.head.insertAdjacentHTML('beforeend', offlineStyles);