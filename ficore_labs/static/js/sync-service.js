/**
 * Data Synchronization Service for FiCore Africa
 * Handles background sync, conflict resolution, and data consistency
 */

class SyncService {
    constructor() {
        this.syncEndpoints = {
            debtors: '/api/debtors/sync',
            creditors: '/api/creditors/sync',
            inventory: '/api/inventory/sync',
            transactions: '/api/transactions/sync'
        };
        this.conflictResolutionStrategy = 'client-wins'; // 'client-wins', 'server-wins', 'merge'
        this.maxRetries = 3;
        this.retryDelay = 1000; // 1 second
        this.init();
    }

    init() {
        this.setupBackgroundSync();
        this.setupConflictResolution();
        this.setupPeriodicHealthCheck();
    }

    // Background sync registration
    setupBackgroundSync() {
        if ('serviceWorker' in navigator && 'sync' in window.ServiceWorkerRegistration.prototype) {
            navigator.serviceWorker.ready.then(registration => {
                // Register for background sync
                return registration.sync.register('background-sync');
            }).catch(error => {
                console.error('Background sync registration failed:', error);
            });
        }
    }

    // Sync data with server
    async syncData(storeName, data, action = 'create') {
        const endpoint = this.syncEndpoints[storeName];
        if (!endpoint) {
            throw new Error(`No sync endpoint configured for ${storeName}`);
        }

        let attempt = 0;
        while (attempt < this.maxRetries) {
            try {
                const response = await this.performSync(endpoint, data, action);
                return response;
            } catch (error) {
                attempt++;
                if (attempt >= this.maxRetries) {
                    throw error;
                }
                
                // Exponential backoff
                await this.delay(this.retryDelay * Math.pow(2, attempt - 1));
            }
        }
    }

    async performSync(endpoint, data, action) {
        const method = action === 'create' ? 'POST' : action === 'update' ? 'PUT' : 'DELETE';
        
        const response = await fetch(endpoint, {
            method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken(),
                'X-Sync-Timestamp': new Date().toISOString()
            },
            body: JSON.stringify({
                ...data,
                clientTimestamp: data.timestamp,
                action
            })
        });

        if (!response.ok) {
            if (response.status === 409) {
                // Conflict detected
                const conflictData = await response.json();
                return await this.resolveConflict(data, conflictData);
            }
            throw new Error(`Sync failed: ${response.status} ${response.statusText}`);
        }

        return await response.json();
    }

    // Conflict resolution
    setupConflictResolution() {
        this.conflictResolvers = {
            'client-wins': this.clientWinsResolver.bind(this),
            'server-wins': this.serverWinsResolver.bind(this),
            'merge': this.mergeResolver.bind(this)
        };
    }

    async resolveConflict(clientData, serverConflictData) {
        const resolver = this.conflictResolvers[this.conflictResolutionStrategy];
        if (!resolver) {
            throw new Error(`Unknown conflict resolution strategy: ${this.conflictResolutionStrategy}`);
        }

        const resolvedData = await resolver(clientData, serverConflictData);
        
        // Show conflict resolution notification
        this.showConflictNotification(clientData, serverConflictData.serverData, resolvedData);
        
        return resolvedData;
    }

    clientWinsResolver(clientData, serverConflictData) {
        // Client data takes precedence
        return {
            ...clientData,
            resolvedBy: 'client-wins',
            conflictTimestamp: new Date().toISOString()
        };
    }

    serverWinsResolver(clientData, serverConflictData) {
        // Server data takes precedence
        return {
            ...serverConflictData.serverData,
            resolvedBy: 'server-wins',
            conflictTimestamp: new Date().toISOString()
        };
    }

    async mergeResolver(clientData, serverConflictData) {
        const serverData = serverConflictData.serverData;
        
        // Smart merge based on field timestamps or user preference
        const merged = { ...serverData };
        
        // Merge strategy: take the most recent value for each field
        Object.keys(clientData).forEach(key => {
            if (key === 'id' || key === 'timestamp') return;
            
            const clientTimestamp = new Date(clientData.timestamp || 0);
            const serverTimestamp = new Date(serverData.timestamp || 0);
            
            if (clientTimestamp > serverTimestamp) {
                merged[key] = clientData[key];
            }
        });

        merged.resolvedBy = 'merge';
        merged.conflictTimestamp = new Date().toISOString();
        
        return merged;
    }

    showConflictNotification(clientData, serverData, resolvedData) {
        const notification = document.createElement('div');
        notification.className = 'alert alert-warning alert-dismissible fade show conflict-notification';
        notification.innerHTML = `
            <div class="d-flex align-items-start">
                <i class="bi bi-exclamation-triangle-fill me-2 mt-1"></i>
                <div class="flex-grow-1">
                    <strong>Data Conflict Resolved</strong>
                    <p class="mb-2">A conflict was detected while syncing your data. It has been resolved using the "${resolvedData.resolvedBy}" strategy.</p>
                    <button class="btn btn-sm btn-outline-warning" onclick="syncService.showConflictDetails('${JSON.stringify(clientData)}', '${JSON.stringify(serverData)}', '${JSON.stringify(resolvedData)}')">
                        View Details
                    </button>
                </div>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;

        const container = document.querySelector('.alert-container') || document.body;
        container.appendChild(notification);

        // Auto-remove after 10 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 10000);
    }

    showConflictDetails(clientData, serverData, resolvedData) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Data Conflict Details</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-4">
                                <h6>Your Changes</h6>
                                <pre class="bg-light p-2 rounded"><code>${JSON.stringify(JSON.parse(clientData), null, 2)}</code></pre>
                            </div>
                            <div class="col-md-4">
                                <h6>Server Version</h6>
                                <pre class="bg-light p-2 rounded"><code>${JSON.stringify(JSON.parse(serverData), null, 2)}</code></pre>
                            </div>
                            <div class="col-md-4">
                                <h6>Resolved Version</h6>
                                <pre class="bg-success bg-opacity-10 p-2 rounded"><code>${JSON.stringify(JSON.parse(resolvedData), null, 2)}</code></pre>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();

        // Clean up modal after hiding
        modal.addEventListener('hidden.bs.modal', () => {
            modal.remove();
        });
    }

    // Batch sync for multiple items
    async batchSync(items) {
        const batchSize = 10;
        const batches = [];
        
        for (let i = 0; i < items.length; i += batchSize) {
            batches.push(items.slice(i, i + batchSize));
        }

        const results = [];
        for (const batch of batches) {
            const batchPromises = batch.map(item => 
                this.syncData(item.storeName, item.data, item.action)
                    .then(result => ({ success: true, item, result }))
                    .catch(error => ({ success: false, item, error }))
            );
            
            const batchResults = await Promise.allSettled(batchPromises);
            results.push(...batchResults.map(r => r.value));
        }

        return results;
    }

    // Health check and connectivity monitoring
    setupPeriodicHealthCheck() {
        setInterval(async () => {
            if (navigator.onLine) {
                await this.performHealthCheck();
            }
        }, 60000); // Check every minute
    }

    async performHealthCheck() {
        try {
            const response = await fetch('/api/health', {
                method: 'GET',
                headers: {
                    'Cache-Control': 'no-cache'
                }
            });

            if (response.ok) {
                const health = await response.json();
                this.updateHealthStatus(health);
            }
        } catch (error) {
            console.warn('Health check failed:', error);
            this.updateHealthStatus({ status: 'unhealthy', error: error.message });
        }
    }

    updateHealthStatus(health) {
        const event = new CustomEvent('healthStatusUpdate', {
            detail: health
        });
        document.dispatchEvent(event);
    }

    // Data validation before sync
    validateData(storeName, data) {
        const validators = {
            debtors: this.validateDebtor.bind(this),
            creditors: this.validateCreditor.bind(this),
            inventory: this.validateInventoryItem.bind(this),
            transactions: this.validateTransaction.bind(this)
        };

        const validator = validators[storeName];
        if (!validator) {
            return { valid: true };
        }

        return validator(data);
    }

    validateDebtor(data) {
        const errors = [];
        
        if (!data.name || data.name.trim().length === 0) {
            errors.push('Name is required');
        }
        
        if (data.amount && (isNaN(data.amount) || data.amount < 0)) {
            errors.push('Amount must be a positive number');
        }
        
        if (data.phone && !/^\+?[\d\s\-\(\)]+$/.test(data.phone)) {
            errors.push('Invalid phone number format');
        }

        return {
            valid: errors.length === 0,
            errors
        };
    }

    validateCreditor(data) {
        return this.validateDebtor(data); // Same validation rules
    }

    validateInventoryItem(data) {
        const errors = [];
        
        if (!data.name || data.name.trim().length === 0) {
            errors.push('Item name is required');
        }
        
        if (data.quantity && (isNaN(data.quantity) || data.quantity < 0)) {
            errors.push('Quantity must be a positive number');
        }
        
        if (data.price && (isNaN(data.price) || data.price < 0)) {
            errors.push('Price must be a positive number');
        }

        return {
            valid: errors.length === 0,
            errors
        };
    }

    validateTransaction(data) {
        const errors = [];
        
        if (!data.type || !['income', 'expense'].includes(data.type)) {
            errors.push('Transaction type must be income or expense');
        }
        
        if (!data.amount || isNaN(data.amount) || data.amount <= 0) {
            errors.push('Amount must be a positive number');
        }
        
        if (!data.description || data.description.trim().length === 0) {
            errors.push('Description is required');
        }

        return {
            valid: errors.length === 0,
            errors
        };
    }

    // Utility methods
    getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Data integrity checks
    async verifyDataIntegrity(storeName) {
        try {
            const localData = await window.offlineManager?.getOfflineData(storeName) || [];
            const response = await fetch(`/api/${storeName}/checksum`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    localChecksum: this.calculateChecksum(localData)
                })
            });

            if (response.ok) {
                const result = await response.json();
                if (!result.match) {
                    console.warn(`Data integrity mismatch detected for ${storeName}`);
                    return false;
                }
            }
            return true;
        } catch (error) {
            console.error('Data integrity check failed:', error);
            return false;
        }
    }

    calculateChecksum(data) {
        // Simple checksum calculation
        const str = JSON.stringify(data.sort((a, b) => (a.id || 0) - (b.id || 0)));
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32-bit integer
        }
        return hash.toString();
    }
}

// Initialize sync service
document.addEventListener('DOMContentLoaded', () => {
    window.syncService = new SyncService();
});