// Global function to toggle the dashboard sidebar/panel and update the server
function toggleSidebarSetting(value) {
    // Show or hide the sidebar/panel immediately in the UI
    var sidebar = document.getElementById('dashboardSidebar'); // Adjust ID as needed
    if (sidebar) {
        if (value) {
            sidebar.style.display = '';
        } else {
            sidebar.style.display = 'none';
        }
    }
    // Send the setting to the server
    fetch('/update_sidebar_setting', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ sidebar_enabled: value })
    })
    .then(response => response.json())
    .then(data => {
        // Optionally handle server response
        if (data.success) {
            // Success feedback if needed
        }
    })
    .catch(error => {
        // Optionally handle error
        console.error('Sidebar setting update failed:', error);
    });
}

// Attach event listener for the activitySidebarToggle checkbox if present
const activitySidebarToggle = document.getElementById('activitySidebarToggle');
if (activitySidebarToggle) {
    activitySidebarToggle.addEventListener('change', function() {
        if (typeof toggleSidebarSetting === 'function') {
            toggleSidebarSetting(this.checked);
        } else {
            // Fallback: just send to server
            fetch('/update_sidebar_setting', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ sidebar_enabled: this.checked })
            });
        }
    });
}
