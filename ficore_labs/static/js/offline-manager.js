/**
 * Comprehensive Offline Manager for FiCore Africa
 * Handles offline data storage, synchronization, and user experience
 */

class OfflineManager {
    constructor() {
        this.dbName = 'FiCoreOfflineDB';
        this.dbVersion = 1;
        this.db = null;
        this.isOnline = navigator.onLine;
        this.syncQueue = [];
        this.offlineData = new Map();
        this.init();
    }

    async init() {
        await this.initIndexedDB();
        this.setupNetworkListeners();
        this.setupServiceWorker();
        this.loadOfflineData();
        this.startPeriodicSync();
    }

    // IndexedDB Setup
    async initIndexedDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);
            
            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                resolve(this.db);
            };
            
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                
                // Create object stores for different data types
                if (!db.objectStoreNames.contains('transactions')) {
                    const transactionStore = db.createObjectStore('transactions', { keyPath: 'id', autoIncrement: true });
                    transactionStore.createIndex('type', 'type', { unique: false });
                    transactionStore.createIndex('date', 'date', { unique: false });
                    transactionStore.createIndex('synced', 'synced', { unique: false });
                }
                
                if (!db.objectStoreNames.contains('debtors')) {
                    const debtorStore = db.createObjectStore('debtors', { keyPath: 'id', autoIncrement: true });
                    debtorStore.createIndex('name', 'name', { unique: false });
                    debtorStore.createIndex('synced', 'synced', { unique: false });
                }
                
                if (!db.objectStoreNames.contains('creditors')) {
                    const creditorStore = db.createObjectStore('creditors', { keyPath: 'id', autoIncrement: true });
                    creditorStore.createIndex('name', 'name', { unique: false });
                    creditorStore.createIndex('synced', 'synced', { unique: false });
                }
                
                if (!db.objectStoreNames.contains('inventory')) {
                    const inventoryStore = db.createObjectStore('inventory', { keyPath: 'id', autoIncrement: true });
                    inventoryStore.createIndex('name', 'name', { unique: false });
                    inventoryStore.createIndex('synced', 'synced', { unique: false });
                }
                
                if (!db.objectStoreNames.contains('syncQueue')) {
                    db.createObjectStore('syncQueue', { keyPath: 'id', autoIncrement: true });
                }
                
                if (!db.objectStoreNames.contains('userSettings')) {
                    db.createObjectStore('userSettings', { keyPath: 'key' });
                }
            };
        });
    }

    // Network Status Management
    setupNetworkListeners() {
        window.addEventListener('online', () => {
            this.isOnline = true;
            this.updateNetworkStatus();
            this.syncOfflineData();
        });
        
        window.addEventListener('offline', () => {
            this.isOnline = false;
            this.updateNetworkStatus();
        });
    }

    updateNetworkStatus() {
        const statusElement = document.getElementById('network-status');
        if (statusElement) {
            statusElement.className = this.isOnline ? 'network-online' : 'network-offline';
            statusElement.textContent = this.isOnline ? 'Online' : 'Offline';
        }
        
        // Show/hide offline indicators
        document.querySelectorAll('.offline-indicator').forEach(el => {
            el.style.display = this.isOnline ? 'none' : 'block';
        });
        
        // Update form submission buttons
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
    }

    // Service Worker Setup
    async setupServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                const registration = await navigator.serviceWorker.register('/static/enhanced-service-worker.js');
                console.log('Enhanced Service Worker registered:', registration);
                
                // Listen for messages from service worker
                navigator.serviceWorker.addEventListener('message', (event) => {
                    if (event.data.type === 'CACHE_UPDATED') {
                        this.showNotification('App updated! Refresh to see changes.', 'info');
                    }
                });
            } catch (error) {
                console.error('Service Worker registration failed:', error);
            }
        }
    }

    // Data Storage Methods
    async saveOfflineData(storeName, data) {
        if (!this.db) return false;
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);
            
            data.synced = false;
            data.timestamp = new Date().toISOString();
            
            const request = store.add(data);
            request.onsuccess = () => {
                this.addToSyncQueue(storeName, data);
                resolve(request.result);
            };
            request.onerror = () => reject(request.error);
        });
    }

    async getOfflineData(storeName, filters = {}) {
        if (!this.db) return [];
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.getAll();
            
            request.onsuccess = () => {
                let results = request.result;
                
                // Apply filters
                Object.keys(filters).forEach(key => {
                    if (filters[key] !== undefined) {
                        results = results.filter(item => item[key] === filters[key]);
                    }
                });
                
                resolve(results);
            };
            request.onerror = () => reject(request.error);
        });
    }

    async updateOfflineData(storeName, id, updates) {
        if (!this.db) return false;
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);
            const getRequest = store.get(id);
            
            getRequest.onsuccess = () => {
                const data = getRequest.result;
                if (data) {
                    Object.assign(data, updates);
                    data.synced = false;
                    data.lastModified = new Date().toISOString();
                    
                    const putRequest = store.put(data);
                    putRequest.onsuccess = () => {
                        this.addToSyncQueue(storeName, data);
                        resolve(true);
                    };
                    putRequest.onerror = () => reject(putRequest.error);
                } else {
                    reject(new Error('Record not found'));
                }
            };
            getRequest.onerror = () => reject(getRequest.error);
        });
    }

    // Sync Queue Management
    addToSyncQueue(storeName, data) {
        const syncItem = {
            storeName,
            data,
            action: data.id ? 'update' : 'create',
            timestamp: new Date().toISOString()
        };
        
        this.syncQueue.push(syncItem);
        this.saveSyncQueue();
    }

    async saveSyncQueue() {
        if (!this.db) return;
        
        const transaction = this.db.transaction(['syncQueue'], 'readwrite');
        const store = transaction.objectStore(syncQueue);
        
        // Clear existing queue and save new one
        await store.clear();
        this.syncQueue.forEach(item => store.add(item));
    }

    async loadSyncQueue() {
        if (!this.db) return;
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['syncQueue'], 'readonly');
            const store = transaction.objectStore('syncQueue');
            const request = store.getAll();
            
            request.onsuccess = () => {
                this.syncQueue = request.result;
                resolve(this.syncQueue);
            };
            request.onerror = () => reject(request.error);
        });
    }

    // Data Synchronization
    async syncOfflineData() {
        if (!this.isOnline || this.syncQueue.length === 0) return;
        
        this.showNotification('Syncing offline data...', 'info');
        
        const syncPromises = this.syncQueue.map(async (item) => {
            try {
                await this.syncSingleItem(item);
                return { success: true, item };
            } catch (error) {
                console.error('Sync failed for item:', item, error);
                return { success: false, item, error };
            }
        });
        
        const results = await Promise.allSettled(syncPromises);
        const successful = results.filter(r => r.value?.success).length;
        const failed = results.length - successful;
        
        if (successful > 0) {
            this.syncQueue = this.syncQueue.filter((_, index) => 
                !results[index].value?.success
            );
            await this.saveSyncQueue();
        }
        
        if (failed === 0) {
            this.showNotification(`Successfully synced ${successful} items`, 'success');
        } else {
            this.showNotification(`Synced ${successful} items, ${failed} failed`, 'warning');
        }
    }

    async syncSingleItem(syncItem) {
        const { storeName, data, action } = syncItem;
        const endpoint = this.getEndpointForStore(storeName);
        
        const response = await fetch(endpoint, {
            method: action === 'create' ? 'POST' : 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            throw new Error(`Sync failed: ${response.statusText}`);
        }
        
        // Mark as synced in local storage
        await this.markAsSynced(storeName, data.id);
        
        return await response.json();
    }

    getEndpointForStore(storeName) {
        const endpoints = {
            'transactions': '/api/transactions',
            'debtors': '/api/debtors',
            'creditors': '/api/creditors',
            'inventory': '/api/inventory'
        };
        return endpoints[storeName] || '/api/sync';
    }

    async markAsSynced(storeName, id) {
        if (!this.db) return;
        
        const transaction = this.db.transaction([storeName], 'readwrite');
        const store = transaction.objectStore(storeName);
        const getRequest = store.get(id);
        
        getRequest.onsuccess = () => {
            const data = getRequest.result;
            if (data) {
                data.synced = true;
                store.put(data);
            }
        };
    }

    // Form Handling
    handleOfflineForm(form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());
            const storeName = form.dataset.storeName || 'transactions';
            
            try {
                if (this.isOnline) {
                    // Try online submission first
                    const response = await fetch(form.action, {
                        method: form.method,
                        body: formData
                    });
                    
                    if (response.ok) {
                        this.showNotification('Data saved successfully!', 'success');
                        form.reset();
                        return;
                    }
                }
                
                // Save offline
                await this.saveOfflineData(storeName, data);
                this.showNotification('Data saved offline. Will sync when online.', 'warning');
                form.reset();
                
            } catch (error) {
                console.error('Form submission error:', error);
                this.showNotification('Error saving data. Please try again.', 'error');
            }
        });
    }

    // Utility Methods
    getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show offline-notification`;
        notification.innerHTML = `
            <i class="bi bi-${this.getIconForType(type)} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // Add to page
        const container = document.querySelector('.alert-container') || document.body;
        container.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
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

    // Periodic sync
    startPeriodicSync() {
        setInterval(() => {
            if (this.isOnline && this.syncQueue.length > 0) {
                this.syncOfflineData();
            }
        }, 30000); // Sync every 30 seconds when online
    }

    // Load cached data on page load
    async loadOfflineData() {
        await this.loadSyncQueue();
        
        // Load data for current page
        const currentPage = window.location.pathname;
        if (currentPage.includes('/debtors')) {
            await this.loadDebtorsData();
        } else if (currentPage.includes('/creditors')) {
            await this.loadCreditorsData();
        } else if (currentPage.includes('/inventory')) {
            await this.loadInventoryData();
        }
    }

    async loadDebtorsData() {
        const debtors = await this.getOfflineData('debtors');
        if (debtors.length > 0) {
            this.populateDebtorsTable(debtors);
        }
    }

    async loadCreditorsData() {
        const creditors = await this.getOfflineData('creditors');
        if (creditors.length > 0) {
            this.populateCreditorsTable(creditors);
        }
    }

    async loadInventoryData() {
        const inventory = await this.getOfflineData('inventory');
        if (inventory.length > 0) {
            this.populateInventoryTable(inventory);
        }
    }

    populateDebtorsTable(debtors) {
        const tableBody = document.querySelector('#debtors-table tbody');
        if (!tableBody) return;
        
        tableBody.innerHTML = '';
        debtors.forEach(debtor => {
            const row = document.createElement('tr');
            row.className = debtor.synced ? '' : 'table-warning';
            row.innerHTML = `
                <td>${debtor.name}</td>
                <td>${debtor.amount || 0}</td>
                <td>${debtor.phone || ''}</td>
                <td>
                    ${!debtor.synced ? '<span class="badge bg-warning">Offline</span>' : ''}
                </td>
            `;
            tableBody.appendChild(row);
        });
    }

    populateCreditorsTable(creditors) {
        const tableBody = document.querySelector('#creditors-table tbody');
        if (!tableBody) return;
        
        tableBody.innerHTML = '';
        creditors.forEach(creditor => {
            const row = document.createElement('tr');
            row.className = creditor.synced ? '' : 'table-warning';
            row.innerHTML = `
                <td>${creditor.name}</td>
                <td>${creditor.amount || 0}</td>
                <td>${creditor.phone || ''}</td>
                <td>
                    ${!creditor.synced ? '<span class="badge bg-warning">Offline</span>' : ''}
                </td>
            `;
            tableBody.appendChild(row);
        });
    }

    populateInventoryTable(inventory) {
        const tableBody = document.querySelector('#inventory-table tbody');
        if (!tableBody) return;
        
        tableBody.innerHTML = '';
        inventory.forEach(item => {
            const row = document.createElement('tr');
            row.className = item.synced ? '' : 'table-warning';
            row.innerHTML = `
                <td>${item.name}</td>
                <td>${item.quantity || 0}</td>
                <td>${item.price || 0}</td>
                <td>
                    ${!item.synced ? '<span class="badge bg-warning">Offline</span>' : ''}
                </td>
            `;
            tableBody.appendChild(row);
        });
    }
}

// Initialize offline manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.offlineManager = new OfflineManager();
});