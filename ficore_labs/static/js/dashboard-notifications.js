/**
 * Dashboard Notifications Manager
 * Handles dismissable notifications that persist until user dismisses them
 */

class DashboardNotifications {
    constructor() {
        this.storageKey = 'dashboard_dismissed_notifications';
        this.init();
    }
    
    init() {
        this.loadDismissedNotifications();
        this.bindEvents();
        this.showNotifications();
    }
    
    loadDismissedNotifications() {
        try {
            const dismissed = localStorage.getItem(this.storageKey);
            this.dismissedNotifications = dismissed ? JSON.parse(dismissed) : {};
        } catch (error) {
            console.error('Error loading dismissed notifications:', error);
            this.dismissedNotifications = {};
        }
    }
    
    saveDismissedNotifications() {
        try {
            localStorage.setItem(this.storageKey, JSON.stringify(this.dismissedNotifications));
        } catch (error) {
            console.error('Error saving dismissed notifications:', error);
        }
    }
    
    bindEvents() {
        // Handle dismiss buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('notification-dismiss') || 
                e.target.closest('.notification-dismiss')) {
                
                const button = e.target.classList.contains('notification-dismiss') ? 
                              e.target : e.target.closest('.notification-dismiss');
                
                const notificationId = button.getAttribute('data-notification-id');
                const notification = button.closest('.dashboard-notification');
                
                if (notificationId && notification) {
                    this.dismissNotification(notificationId, notification);
                }
            }
        });
    }
    
    dismissNotification(notificationId, notificationElement) {
        // Mark as dismissed
        this.dismissedNotifications[notificationId] = {
            dismissedAt: Date.now(),
            userId: this.getCurrentUserId()
        };
        
        this.saveDismissedNotifications();
        
        // Animate out
        notificationElement.style.transition = 'all 0.3s ease-out';
        notificationElement.style.opacity = '0';
        notificationElement.style.transform = 'translateX(100%)';
        
        setTimeout(() => {
            if (notificationElement.parentNode) {
                notificationElement.remove();
            }
        }, 300);
    }
    
    isNotificationDismissed(notificationId) {
        const dismissed = this.dismissedNotifications[notificationId];
        if (!dismissed) return false;
        
        // Check if it's for the current user
        const currentUserId = this.getCurrentUserId();
        if (dismissed.userId !== currentUserId) return false;
        
        // Check if it was dismissed recently (within 24 hours for some notifications)
        const dismissedAt = dismissed.dismissedAt;
        const now = Date.now();
        const hoursSinceDismissed = (now - dismissedAt) / (1000 * 60 * 60);
        
        // Different notifications have different persistence rules
        switch (notificationId) {
            case 'inventory_loss':
                // Show again after 6 hours
                return hoursSinceDismissed < 6;
            case 'unpaid_debts':
            case 'unpaid_credits':
                // Show again after 24 hours
                return hoursSinceDismissed < 24;
            default:
                // Default: show again after 12 hours
                return hoursSinceDismissed < 12;
        }
    }
    
    getCurrentUserId() {
        // Try to get user ID from various sources
        const userIdElement = document.querySelector('[data-user-id]');
        if (userIdElement) {
            return userIdElement.getAttribute('data-user-id');
        }
        
        // Fallback to a session-based identifier
        let sessionId = sessionStorage.getItem('dashboard_session_id');
        if (!sessionId) {
            sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            sessionStorage.setItem('dashboard_session_id', sessionId);
        }
        return sessionId;
    }
    
    showNotifications() {
        // Check each notification type and show if not dismissed
        this.checkInventoryLossNotification();
        this.checkDebtNotifications();
    }
    
    checkInventoryLossNotification() {
        const inventoryLossData = window.dashboardData?.inventoryLoss;
        if (!inventoryLossData || this.isNotificationDismissed('inventory_loss')) {
            return;
        }
        
        this.createNotification({
            id: 'inventory_loss',
            type: 'danger',
            icon: 'bi-exclamation-octagon',
            title: 'Inventory Loss Detected!',
            message: 'Your inventory cost exceeds expected margins. Please review your stock and pricing.',
            actions: [{
                text: 'View Inventory',
                url: '/inventory',
                class: 'btn-outline-danger'
            }]
        });
    }
    
    checkDebtNotifications() {
        const debtData = window.dashboardData?.debts;
        if (!debtData) return;
        
        // Check unpaid debts (people owe you)
        if (debtData.unpaidDebtors && debtData.unpaidDebtors.length > 0 && 
            !this.isNotificationDismissed('unpaid_debts')) {
            
            this.createNotification({
                id: 'unpaid_debts',
                type: 'warning',
                icon: 'bi-exclamation-triangle',
                title: 'Unpaid Debts',
                message: `${debtData.unpaidDebtors.length} people owe you money!`,
                actions: [{
                    text: 'View Debtors',
                    url: '/debtors',
                    class: 'btn-outline-warning'
                }]
            });
        }
        
        // Check unpaid credits (you owe people)
        if (debtData.unpaidCreditors && debtData.unpaidCreditors.length > 0 && 
            !this.isNotificationDismissed('unpaid_credits')) {
            
            this.createNotification({
                id: 'unpaid_credits',
                type: 'info',
                icon: 'bi-info-circle',
                title: 'Unpaid Credits',
                message: `${debtData.unpaidCreditors.length} people you owe!`,
                actions: [{
                    text: 'View Creditors',
                    url: '/creditors',
                    class: 'btn-outline-info'
                }]
            });
        }
    }
    
    createNotification(config) {
        const container = document.getElementById('dashboard-notifications-container');
        if (!container) {
            console.error('Dashboard notifications container not found');
            return;
        }
        
        const notification = document.createElement('div');
        notification.className = `alert alert-${config.type} alert-dismissible dashboard-notification mb-3`;
        notification.setAttribute('role', 'alert');
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(-100%)';
        notification.style.transition = 'all 0.3s ease-in';
        
        const actionsHtml = config.actions ? config.actions.map(action => 
            `<a href="${action.url}" class="btn btn-sm ${action.class} ms-2">${action.text}</a>`
        ).join('') : '';
        
        notification.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi ${config.icon} me-2"></i>
                <div class="flex-grow-1">
                    <strong>${config.title}</strong>
                    <span class="ms-2">${config.message}</span>
                    ${actionsHtml}
                </div>
                <button type="button" 
                        class="btn-close notification-dismiss" 
                        data-notification-id="${config.id}"
                        aria-label="Dismiss notification">
                </button>
            </div>
        `;
        
        container.appendChild(notification);
        
        // Animate in
        setTimeout(() => {
            notification.style.opacity = '1';
            notification.style.transform = 'translateX(0)';
        }, 100);
    }
    
    // Public method to manually trigger notifications (for testing)
    triggerNotification(type, data) {
        switch (type) {
            case 'inventory_loss':
                window.dashboardData = window.dashboardData || {};
                window.dashboardData.inventoryLoss = data || true;
                this.checkInventoryLossNotification();
                break;
            case 'debts':
                window.dashboardData = window.dashboardData || {};
                window.dashboardData.debts = data || {
                    unpaidDebtors: [1],
                    unpaidCreditors: [1]
                };
                this.checkDebtNotifications();
                break;
        }
    }
    
    // Clear all dismissed notifications (for testing)
    clearDismissedNotifications() {
        this.dismissedNotifications = {};
        this.saveDismissedNotifications();
        console.log('All dismissed notifications cleared');
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.dashboardNotifications = new DashboardNotifications();
});

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardNotifications;
}