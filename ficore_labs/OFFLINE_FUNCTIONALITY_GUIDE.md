# FiCore Africa - Comprehensive Offline Functionality Guide

## Overview

FiCore Africa now includes robust offline functionality that allows users to continue working even without an internet connection. All data is stored locally and automatically synchronized when the connection is restored.

## Features

### 🔄 **Automatic Data Synchronization**
- Background sync when connection is restored
- Conflict resolution for simultaneous edits
- Retry mechanism with exponential backoff
- Data integrity verification

### 💾 **Local Data Storage**
- IndexedDB for structured data storage
- Supports debtors, creditors, inventory, and transactions
- Automatic data validation before storage
- Efficient querying and filtering

### 🎯 **Smart Caching Strategy**
- Cache-first for static assets
- Network-first for dynamic content
- Stale-while-revalidate for regular pages
- API response caching with TTL

### 🔔 **User Experience Enhancements**
- Real-time network status indicators
- Offline banners and notifications
- Form adaptations for offline mode
- Sync progress indicators

## Technical Implementation

### Service Worker (`enhanced-service-worker.js`)

The enhanced service worker implements multiple caching strategies:

```javascript
// Cache strategies based on request type
- Static assets: Cache-first
- Dynamic content: Network-first with cache fallback
- API requests: Stale-while-revalidate with conflict detection
- Navigation: Network-first with offline page fallback
```

**Key Features:**
- Version-based cache management
- Background sync registration
- Push notification support
- Automatic cache cleanup

### Offline Manager (`offline-manager.js`)

Handles all offline data operations:

```javascript
// Core functionality
- IndexedDB initialization and management
- Data storage and retrieval
- Sync queue management
- Network status monitoring
- Form handling for offline mode
```

**Data Stores:**
- `transactions`: Financial transactions
- `debtors`: Customer debt records
- `creditors`: Supplier credit records
- `inventory`: Product inventory
- `syncQueue`: Pending sync operations
- `userSettings`: User preferences

### Sync Service (`sync-service.js`)

Manages data synchronization and conflict resolution:

```javascript
// Sync strategies
- Client-wins: Local changes take precedence
- Server-wins: Server data takes precedence
- Merge: Smart field-level merging based on timestamps
```

**Conflict Resolution:**
- Automatic detection of data conflicts
- User notification with resolution details
- Configurable resolution strategies
- Data integrity verification

### Offline UI (`offline-ui.js`)

Provides user interface enhancements:

```javascript
// UI Components
- Network status indicators
- Offline banners and notifications
- Form adaptations
- Sync status displays
- Offline data viewer modal
```

## API Endpoints

### Sync Endpoints

All sync endpoints support conflict detection and resolution:

- `POST/PUT /api/debtors/sync` - Sync debtor data
- `POST/PUT /api/creditors/sync` - Sync creditor data
- `POST/PUT /api/inventory/sync` - Sync inventory data
- `POST/PUT /api/transactions/sync` - Sync transaction data

### Utility Endpoints

- `GET /api/health` - Health check for connectivity monitoring
- `POST /api/{collection}/checksum` - Data integrity verification

### Request Format

```json
{
  "name": "John Doe",
  "amount": 1000,
  "phone": "+1234567890",
  "clientTimestamp": "2024-01-01T12:00:00Z",
  "action": "create"
}
```

### Response Format

```json
{
  "success": true,
  "data": {
    "id": "507f1f77bcf86cd799439011",
    "name": "John Doe",
    "amount": 1000,
    "synced": true
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### Conflict Response

```json
{
  "conflict": true,
  "serverData": {
    "id": "507f1f77bcf86cd799439011",
    "name": "John Smith",
    "amount": 1500,
    "last_modified": "2024-01-01T11:30:00Z"
  },
  "message": "Data has been modified on server since last sync"
}
```

## Usage Guide

### For Developers

#### 1. Enable Offline Mode for Forms

Add the `data-offline-enabled` attribute to forms:

```html
<form action="/debtors/add" method="POST" data-offline-enabled="true" data-store-name="debtors">
  <!-- form fields -->
</form>
```

#### 2. Handle Offline Data in Templates

Use offline indicators in your templates:

```html
<!-- Offline indicator -->
<div class="offline-indicator" style="display: none;">
  <span class="badge bg-warning">Offline Mode</span>
</div>

<!-- Data table with sync status -->
<tr class="{% if not item.synced %}table-warning{% endif %}">
  <td>{{ item.name }}</td>
  <td>
    {% if not item.synced %}
      <span class="badge bg-warning">Pending Sync</span>
    {% endif %}
  </td>
</tr>
```

#### 3. Custom Offline Handling

```javascript
// Check if offline manager is available
if (window.offlineManager) {
  // Save data offline
  await window.offlineManager.saveOfflineData('debtors', {
    name: 'John Doe',
    amount: 1000
  });
  
  // Get offline data
  const debtors = await window.offlineManager.getOfflineData('debtors');
  
  // Trigger manual sync
  await window.offlineManager.syncOfflineData();
}
```

### For Users

#### 1. Working Offline

When offline, users can:
- Add new debtors, creditors, and inventory items
- Record transactions
- View existing data
- Generate basic reports

#### 2. Sync Status

Users can monitor sync status through:
- Network status indicator in the header
- Offline banner when disconnected
- Sync progress notifications
- Offline data viewer modal

#### 3. Viewing Offline Data

Click "View Offline Data" to see:
- All locally stored data
- Sync status for each item
- Pending sync queue
- Manual sync option

## Configuration

### Service Worker Registration

The service worker is automatically registered in the base template:

```html
<script src="{{ url_for('static', filename='js/offline-manager.js') }}"></script>
<script src="{{ url_for('static', filename='js/offline-ui.js') }}"></script>
<script src="{{ url_for('static', filename='js/sync-service.js') }}"></script>
```

### Conflict Resolution Strategy

Configure in `sync-service.js`:

```javascript
// Options: 'client-wins', 'server-wins', 'merge'
this.conflictResolutionStrategy = 'client-wins';
```

### Cache Configuration

Modify cache settings in `enhanced-service-worker.js`:

```javascript
const CACHE_VERSION = 'v2.0.0';
const STATIC_CACHE = `ficore-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `ficore-dynamic-${CACHE_VERSION}`;
```

## Troubleshooting

### Common Issues

1. **Service Worker Not Registering**
   - Check browser console for errors
   - Ensure HTTPS is enabled (required for service workers)
   - Verify service worker file path

2. **Data Not Syncing**
   - Check network connectivity
   - Verify API endpoints are accessible
   - Check browser console for sync errors

3. **IndexedDB Errors**
   - Clear browser data and reload
   - Check browser IndexedDB support
   - Verify database schema version

### Debug Mode

Enable debug logging:

```javascript
// In browser console
localStorage.setItem('offline-debug', 'true');
```

### Performance Monitoring

Monitor offline functionality performance:

```javascript
// Check cache usage
navigator.storage.estimate().then(estimate => {
  console.log('Storage used:', estimate.usage);
  console.log('Storage quota:', estimate.quota);
});

// Check sync queue size
console.log('Sync queue:', window.offlineManager?.syncQueue.length);
```

## Security Considerations

### Data Validation

All data is validated both client-side and server-side:
- Input sanitization
- Type checking
- Business rule validation
- CSRF protection

### Sync Security

- CSRF tokens for all sync requests
- User authentication required
- Data ownership verification
- Encrypted data transmission

## Browser Support

### Minimum Requirements

- **Service Workers**: Chrome 40+, Firefox 44+, Safari 11.1+
- **IndexedDB**: Chrome 24+, Firefox 16+, Safari 10+
- **Background Sync**: Chrome 49+, Firefox 81+

### Progressive Enhancement

The app gracefully degrades for unsupported browsers:
- Falls back to regular form submission
- Shows appropriate error messages
- Maintains core functionality

## Performance Optimization

### Cache Management

- Automatic cleanup of old cache versions
- Selective caching based on request patterns
- Compression for cached responses

### Data Storage

- Efficient IndexedDB queries with indexes
- Batch operations for better performance
- Automatic data cleanup for old records

### Network Usage

- Smart sync scheduling
- Batch sync operations
- Retry with exponential backoff

## Future Enhancements

### Planned Features

1. **Advanced Conflict Resolution**
   - Visual diff viewer
   - Field-level conflict resolution
   - User-guided merge options

2. **Enhanced Offline Reports**
   - Offline chart generation
   - PDF export capabilities
   - Advanced filtering options

3. **Background Sync Improvements**
   - Periodic background sync
   - Smart sync scheduling
   - Bandwidth-aware syncing

4. **Data Compression**
   - Client-side data compression
   - Optimized sync payloads
   - Reduced storage usage

## Support

For technical support or questions about offline functionality:

1. Check the browser console for error messages
2. Review this documentation
3. Contact the development team with specific error details
4. Include browser version and network conditions in bug reports

---

**Last Updated:** January 2024  
**Version:** 2.0.0  
**Compatibility:** All modern browsers with service worker support