// Global function to toggle the dashboard sidebar/panel and update the server
function toggleSidebarSetting(value) {
    // Update local state and localStorage
    const sidebar = document.getElementById('recentActivitySidebar');
    const persistentToggle = document.getElementById('sidebarPersistentToggle');
    let sidebarDisabled = !value;
    localStorage.setItem('sidebarDisabled', sidebarDisabled);

    // Update sidebar visibility
    if (sidebar && persistentToggle) {
        if (sidebarDisabled) {
            sidebar.classList.add('disabled');
            sidebar.classList.remove('expanded');
            persistentToggle.classList.add('hidden');
            localStorage.setItem('sidebarExpanded', false);
        } else {
            sidebar.classList.remove('disabled');
            persistentToggle.classList.remove('hidden');
            // Auto-expand on desktop if enabled
            if (window.innerWidth > 768) {
                setTimeout(() => toggleActivitySidebar(), 100);
            }
        }
    }

    // Send the setting to the server
    fetch('/settings/api/update-user-setting', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({
            setting: 'activitySidebarToggle',
            value: value
        })
    })
    .then(response => response.json())
    .then(data => {
        if (!data.success) {
            console.error('Sidebar setting update failed:', data.message);
            // Revert checkbox state on failure
            const toggle = document.getElementById('activitySidebarToggle');
            if (toggle) {
                toggle.checked = !value;
            }
            alert(data.message || 'Failed to update setting');
            // Revert UI changes
            updateSidebarVisibility();
        }
    })
    .catch(error => {
        console.error('Error updating sidebar setting:', error);
        // Revert checkbox state on failure
        const toggle = document.getElementById('activitySidebarToggle');
        if (toggle) {
            toggle.checked = !value;
        }
        alert('An error occurred. Please try again.');
        // Revert UI changes
        updateSidebarVisibility();
    });
}

// Function to update sidebar visibility
function updateSidebarVisibility() {
    const sidebar = document.getElementById('recentActivitySidebar');
    const persistentToggle = document.getElementById('sidebarPersistentToggle');
    const sidebarDisabled = localStorage.getItem('sidebarDisabled') === 'true';

    if (sidebar && persistentToggle) {
        if (sidebarDisabled) {
            sidebar.classList.add('disabled');
            persistentToggle.classList.add('hidden');
            sidebar.classList.remove('expanded');
            localStorage.setItem('sidebarExpanded', false);
        } else {
            sidebar.classList.remove('disabled');
            persistentToggle.classList.remove('hidden');
        }
    }
}

// Function to toggle sidebar visibility
function toggleActivitySidebar() {
    const sidebarDisabled = localStorage.getItem('sidebarDisabled') === 'true';
    if (sidebarDisabled) return;

    const sidebar = document.getElementById('recentActivitySidebar');
    const icon = document.getElementById('sidebarToggleIcon');
    const persistentToggle = document.getElementById('sidebarPersistentToggle');
    let sidebarExpanded = localStorage.getItem('sidebarExpanded') === 'true';

    sidebarExpanded = !sidebarExpanded;
    localStorage.setItem('sidebarExpanded', sidebarExpanded);

    if (sidebar && icon && persistentToggle) {
        if (sidebarExpanded) {
            sidebar.classList.add('expanded');
            icon.className = 'bi bi-chevron-left';
            persistentToggle.classList.add('hidden');
            // Placeholder for loadRecentActivitySidebar (implement or stub as needed)
            if (typeof loadRecentActivitySidebar === 'function') {
                loadRecentActivitySidebar();
            }
        } else {
            sidebar.classList.remove('expanded');
            icon.className = 'bi bi-chevron-right';
            persistentToggle.classList.remove('hidden');
        }
    }
}

// Attach event listener for the activitySidebarToggle checkbox
document.addEventListener('DOMContentLoaded', () => {
    const activitySidebarToggle = document.getElementById('activitySidebarToggle');
    if (activitySidebarToggle) {
        activitySidebarToggle.addEventListener('change', function() {
            toggleSidebarSetting(this.checked);
        });
    }
});
