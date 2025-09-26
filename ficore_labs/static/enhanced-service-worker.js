/**
 * Enhanced Service Worker for FiCore Africa
 * Implements advanced caching strategies and offline functionality
 */

const CACHE_VERSION = 'v2.0.0';
const STATIC_CACHE = `ficore-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `ficore-dynamic-${CACHE_VERSION}`;
const API_CACHE = `ficore-api-${CACHE_VERSION}`;

// Assets to cache immediately
const STATIC_ASSETS = [
    '/',
    '/static/css/styles.css',
    '/static/css/newbasefilelooks.css',
    '/static/css/iconslooks.css',
    '/static/css/profile_css.css',
    '/static/css/navigation_enhancements.css',
    '/static/css/dark_mode_enhancements.css',
    '/static/js/offline-manager.js',
    '/static/js/offline-ui.js',
    '/static/manifest.json',
    '/static/img/favicon.ico',
    '/static/img/apple-touch-icon.png',
    '/static/img/favicon-32x32.png',
    '/static/img/favicon-16x16.png',
    '/static/img/default_profile.png',
    '/static/img/ficore_africa_logo.png',
    '/static/img/icons/icon-192x192.png',
    '/static/img/icons/icon-512x512.png'
];

// Routes that should always try network first
const NETWORK_FIRST_ROUTES = [
    '/users/login',
    '/users/logout',
    '/users/signup',
    '/api/',
    '/admin/',
    '/payments/',
    '/receipts/'
];

// Routes that can be served from cache first
const CACHE_FIRST_ROUTES = [
    '/static/',
    '/general/home',
    '/general/about',
    '/general/contact'
];

// API endpoints to cache
const CACHEABLE_APIS = [
    '/api/notifications/count',
    '/api/dashboard/summary',
    '/api/reports/summary'
];

// Install event - cache static assets
self.addEventListener('install', event => {
    console.log('Enhanced Service Worker installing...');
    
    event.waitUntil(
        Promise.all([
            caches.open(STATIC_CACHE).then(cache => {
                console.log('Caching static assets...');
                return cache.addAll(STATIC_ASSETS);
            }),
            caches.open(DYNAMIC_CACHE),
            caches.open(API_CACHE)
        ]).then(() => {
            console.log('All caches initialized');
            return self.skipWaiting();
        }).catch(error => {
            console.error('Cache installation failed:', error);
        })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    console.log('Enhanced Service Worker activating...');
    
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames
                    .filter(cacheName => 
                        cacheName.startsWith('ficore-') && 
                        !cacheName.includes(CACHE_VERSION)
                    )
                    .map(cacheName => {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    })
            );
        }).then(() => {
            console.log('Old caches cleaned up');
            return self.clients.claim();
        }).then(() => {
            // Notify clients about cache update
            return self.clients.matchAll().then(clients => {
                clients.forEach(client => {
                    client.postMessage({
                        type: 'CACHE_UPDATED',
                        version: CACHE_VERSION
                    });
                });
            });
        })
    );
});

// Fetch event - implement caching strategies
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip non-GET requests and chrome-extension requests
    if (request.method !== 'GET' || url.protocol === 'chrome-extension:') {
        return;
    }
    
    // Determine caching strategy based on request
    if (isStaticAsset(url.pathname)) {
        event.respondWith(cacheFirstStrategy(request));
    } else if (isNetworkFirstRoute(url.pathname)) {
        event.respondWith(networkFirstStrategy(request));
    } else if (isApiRequest(url.pathname)) {
        event.respondWith(apiCachingStrategy(request));
    } else {
        event.respondWith(staleWhileRevalidateStrategy(request));
    }
});

// Caching Strategies

// Cache First - for static assets
async function cacheFirstStrategy(request) {
    try {
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        const networkResponse = await fetch(request);
        if (networkResponse.ok) {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(request, networkResponse.clone());
        }
        return networkResponse;
        
    } catch (error) {
        console.error('Cache first strategy failed:', error);
        return await caches.match('/static/img/offline-fallback.png') || 
               new Response('Offline', { status: 503 });
    }
}

// Network First - for dynamic content
async function networkFirstStrategy(request) {
    try {
        const networkResponse = await fetch(request);
        if (networkResponse.ok) {
            const cache = await caches.open(DYNAMIC_CACHE);
            cache.put(request, networkResponse.clone());
        }
        return networkResponse;
        
    } catch (error) {
        console.log('Network failed, trying cache:', request.url);
        const cachedResponse = await caches.match(request);
        
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Return offline page for navigation requests
        if (request.mode === 'navigate') {
            return await caches.match('/general/home') || 
                   createOfflineResponse();
        }
        
        return new Response('Offline', { status: 503 });
    }
}

// API Caching Strategy
async function apiCachingStrategy(request) {
    const url = new URL(request.url);
    
    // For cacheable APIs, use stale-while-revalidate
    if (CACHEABLE_APIS.some(api => url.pathname.startsWith(api))) {
        return staleWhileRevalidateStrategy(request, API_CACHE);
    }
    
    // For other APIs, try network first with short cache fallback
    try {
        const networkResponse = await fetch(request);
        if (networkResponse.ok) {
            const cache = await caches.open(API_CACHE);
            // Cache API responses for 5 minutes
            const responseToCache = networkResponse.clone();
            responseToCache.headers.set('sw-cache-timestamp', Date.now().toString());
            cache.put(request, responseToCache);
        }
        return networkResponse;
        
    } catch (error) {
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            // Check if cached response is still fresh (5 minutes)
            const cacheTimestamp = cachedResponse.headers.get('sw-cache-timestamp');
            if (cacheTimestamp && (Date.now() - parseInt(cacheTimestamp)) < 300000) {
                return cachedResponse;
            }
        }
        
        return new Response(JSON.stringify({
            error: 'Offline',
            message: 'This feature requires an internet connection'
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

// Stale While Revalidate - for regular pages
async function staleWhileRevalidateStrategy(request, cacheName = DYNAMIC_CACHE) {
    const cachedResponse = await caches.match(request);
    
    const fetchPromise = fetch(request).then(networkResponse => {
        if (networkResponse.ok) {
            const cache = caches.open(cacheName);
            cache.then(c => c.put(request, networkResponse.clone()));
        }
        return networkResponse;
    }).catch(error => {
        console.log('Network fetch failed:', error);
        return null;
    });
    
    // Return cached response immediately if available
    if (cachedResponse) {
        // Update cache in background
        fetchPromise;
        return cachedResponse;
    }
    
    // Wait for network if no cache available
    const networkResponse = await fetchPromise;
    return networkResponse || createOfflineResponse();
}

// Helper Functions

function isStaticAsset(pathname) {
    return CACHE_FIRST_ROUTES.some(route => pathname.startsWith(route));
}

function isNetworkFirstRoute(pathname) {
    return NETWORK_FIRST_ROUTES.some(route => pathname.startsWith(route));
}

function isApiRequest(pathname) {
    return pathname.startsWith('/api/');
}

function createOfflineResponse() {
    const offlineHTML = `
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Offline - FiCore Africa</title>
            <style>
                body {
                    font-family: 'Poppins', sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-align: center;
                }
                .offline-container {
                    max-width: 400px;
                    padding: 2rem;
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 15px;
                    backdrop-filter: blur(10px);
                }
                .offline-icon {
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }
                .retry-btn {
                    background: #007bff;
                    color: white;
                    border: none;
                    padding: 0.75rem 1.5rem;
                    border-radius: 25px;
                    cursor: pointer;
                    margin-top: 1rem;
                    font-size: 1rem;
                }
                .retry-btn:hover {
                    background: #0056b3;
                }
            </style>
        </head>
        <body>
            <div class="offline-container">
                <div class="offline-icon">📱</div>
                <h1>You're Offline</h1>
                <p>It looks like you've lost your internet connection. Don't worry, you can still use some features of FiCore Africa offline.</p>
                <button class="retry-btn" onclick="window.location.reload()">Try Again</button>
            </div>
        </body>
        </html>
    `;
    
    return new Response(offlineHTML, {
        status: 200,
        headers: { 'Content-Type': 'text/html' }
    });
}

// Background Sync
self.addEventListener('sync', event => {
    console.log('Background sync triggered:', event.tag);
    
    if (event.tag === 'background-sync') {
        event.waitUntil(doBackgroundSync());
    }
});

async function doBackgroundSync() {
    try {
        // Notify clients to sync their offline data
        const clients = await self.clients.matchAll();
        clients.forEach(client => {
            client.postMessage({
                type: 'BACKGROUND_SYNC',
                action: 'sync-offline-data'
            });
        });
    } catch (error) {
        console.error('Background sync failed:', error);
    }
}

// Push notifications
self.addEventListener('push', event => {
    if (!event.data) return;
    
    const data = event.data.json();
    const options = {
        body: data.body,
        icon: '/static/img/icons/icon-192x192.png',
        badge: '/static/img/icons/icon-192x192.png',
        vibrate: [100, 50, 100],
        data: data.data || {},
        actions: [
            {
                action: 'view',
                title: 'View',
                icon: '/static/img/icons/view-icon.png'
            },
            {
                action: 'dismiss',
                title: 'Dismiss',
                icon: '/static/img/icons/dismiss-icon.png'
            }
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// Notification click handling
self.addEventListener('notificationclick', event => {
    event.notification.close();
    
    if (event.action === 'view') {
        event.waitUntil(
            clients.openWindow(event.notification.data.url || '/')
        );
    }
});

// Message handling from main thread
self.addEventListener('message', event => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    if (event.data && event.data.type === 'GET_VERSION') {
        event.ports[0].postMessage({ version: CACHE_VERSION });
    }
});