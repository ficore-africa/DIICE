# URL Redirect Configuration Documentation

## Overview
This document outlines all URL redirects, domain configurations, and deployment-specific settings in the Flask application. This is essential for deploying on different URLs or testing environments.

## 🔧 Core Configuration Files

### 1. `app.py` - Main Application Configuration
**Location**: Root directory
**Key Configurations**:

```python
# URL generation configurations (Lines 280-283)
app.config['SERVER_NAME'] = os.getenv('SERVER_NAME', 'business.ficoreafrica.com')
app.config['APPLICATION_ROOT'] = os.getenv('APPLICATION_ROOT', '/')
app.config['PREFERRED_URL_SCHEME'] = os.getenv('PREFERRED_URL_SCHEME', 'https')
```

**Domain Redirect Logic (Lines 488-507)**:
```python
@app.before_request
def handle_redirects():
    host = request.host
    
    # Redirect onrender.com to custom domain
    if host.endswith("onrender.com"):
        new_url = request.url.replace("onrender.com", "business.ficoreafrica.com")
        return redirect(new_url, code=301)
    
    # Redirect www to root domain
    if host.startswith("www."):
        new_url = request.url.replace("www.", "", 1)
        return redirect(new_url, code=301)
    
    # Redirect ficoreafrica.com to business.ficoreafrica.com
    if host == 'ficoreafrica.com':
        new_url = request.url.replace('ficoreafrica.com', 'business.ficoreafrica.com')
        return redirect(new_url, code=301)
```

### 2. `render.yaml` - Render.com Deployment Configuration
**Location**: Root directory
**Configuration**:
```yaml
services:
  - type: web
    name: bizcore-app
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn --bind 0.0.0.0:$PORT app:app
    envVars:
      - key: PYTHON_VERSION
        value: 3.10.0
      - key: FLASK_ENV
        value: production
```

### 3. `wsgi.py` - WSGI Entry Point
**Location**: Root directory
**Configuration**:
```python
# Production host binding (Line 45)
app.run(host='0.0.0.0', port=port, debug=False)
```

## 🌐 Environment Variables Required

### Production Environment Variables
```bash
# Core Configuration
SECRET_KEY=your_secret_key_here
MONGO_URI=your_mongodb_connection_string

# URL Configuration
SERVER_NAME=business.ficoreafrica.com  # Your custom domain
APPLICATION_ROOT=/                      # Application root path
PREFERRED_URL_SCHEME=https             # URL scheme (https for production)

# Environment
FLASK_ENV=production
PORT=5000  # Render.com sets this automatically
```

### Development Environment Variables
```bash
# Core Configuration
SECRET_KEY=dev_secret_key
MONGO_URI=your_dev_mongodb_connection_string

# URL Configuration (for local testing)
SERVER_NAME=localhost:5000             # Local development
APPLICATION_ROOT=/
PREFERRED_URL_SCHEME=http              # HTTP for local development

# Environment
FLASK_ENV=development
```

## 📁 Files with Hardcoded URLs (Need Manual Updates)

### 1. `static/js/interactivity.js` (Lines 92-96)
**Issue**: Contains hardcoded Render.com URLs
```javascript
const toolUrls = [
    'https://ficore-africa.onrender.com/receipt/',
    'https://ficore-africa.onrender.com/creditors/',
    'https://ficore-africa.onrender.com/credits/history',
    'https://ficore-africa.onrender.com/debtors/'
];
```

**Action Required**: Update these URLs when deploying to different domains.

## 🔄 Redirect Flow Logic

### Current Production Flow:
1. **onrender.com** → **business.ficoreafrica.com** (301 redirect)
2. **www.business.ficoreafrica.com** → **business.ficoreafrica.com** (301 redirect)
3. **ficoreafrica.com** → **business.ficoreafrica.com** (301 redirect)

### User Authentication Redirects:
Located in `blueprints/users/routes.py`:

```python
def get_post_login_redirect(user_role):
    """Determine where to redirect user after login based on their role."""
    return url_for('general_bp.home')  # All users go to home

def get_explore_tools_redirect(user_role):
    """Determine where to redirect user when they click 'Explore Your Tools'."""
    if user_role == 'trader':
        return url_for('general_bp.home')
    elif user_role == 'startup':
        return url_for('dashboard.index')
    elif user_role == 'admin':
        return url_for('admin.dashboard')
    else:
        return url_for('users.logout')
```

## 🚀 Deployment Checklist for New URLs

### For Testing on Different Render URLs:
1. **Update Environment Variables**:
   - Set `SERVER_NAME` to your test Render URL (e.g., `your-test-app.onrender.com`)
   - Set `PREFERRED_URL_SCHEME` to `https`

2. **Modify Redirect Logic** (Temporary for testing):
   - Comment out or modify the `handle_redirects()` function in `app.py`
   - Or add your test domain to the allowed domains

3. **Update Hardcoded URLs**:
   - Update `static/js/interactivity.js` with your test domain URLs

### For Production Deployment:
1. **Environment Variables**: Set all production environment variables
2. **DNS Configuration**: Point your custom domain to Render
3. **SSL Certificate**: Ensure HTTPS is properly configured
4. **Test Redirects**: Verify all redirect chains work correctly

## 🔍 Blueprint URL Prefixes

All blueprints are registered with URL prefixes in `app.py`:

```python
app.register_blueprint(users_bp, url_prefix='/users')
app.register_blueprint(debtors_bp, url_prefix='/debtors')
app.register_blueprint(creditors_bp, url_prefix='/creditors')
app.register_blueprint(payments_bp, url_prefix='/payments')
app.register_blueprint(receipts_bp, url_prefix='/receipts')
app.register_blueprint(reports_bp, url_prefix='/reports')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(subscribe_bp, url_prefix='/subscribe')
app.register_blueprint(general_bp, url_prefix='/general')
app.register_blueprint(business, url_prefix='/business')
app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
app.register_blueprint(notifications)  # No prefix
app.register_blueprint(kyc_bp, url_prefix='/kyc')
app.register_blueprint(settings_bp, url_prefix='/settings')
app.register_blueprint(inventory_bp, url_prefix='/inventory')
app.register_blueprint(rewards_bp, url_prefix='/rewards')
app.register_blueprint(tax_bp, url_prefix='/tax')
app.register_blueprint(education_bp, url_prefix='/education')
```

## ⚠️ Important Notes

1. **Session Configuration**: Uses MongoDB for session storage in production
2. **CORS**: Configured for API routes (`/api/*`)
3. **Rate Limiting**: Applied globally (200/day, 50/hour)
4. **Security**: CSRF protection enabled
5. **Logging**: Comprehensive logging with session tracking

## 🛠️ Quick Fix for Test Deployments

To quickly deploy on a test Render URL without redirects:

1. **Temporarily disable redirects** in `app.py`:
```python
@app.before_request
def handle_redirects():
    # Comment out for testing
    pass
```

2. **Set environment variables**:
```bash
SERVER_NAME=your-test-app.onrender.com
PREFERRED_URL_SCHEME=https
```

3. **Update JavaScript URLs** in `static/js/interactivity.js`

## 📝 Maintenance

- Review this configuration when adding new domains
- Update hardcoded URLs when changing primary domain
- Test redirect chains after DNS changes
- Monitor redirect performance and SEO impact

---
**Last Updated**: Generated by Kiro AI Assistant
**Next Review**: Update when deploying to new environments