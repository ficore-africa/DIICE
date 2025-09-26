# Ficore Labs Business Management Platform

## Overview

Ficore Labs is a comprehensive, modern business management platform designed specifically for African entrepreneurs and traders. It provides real-time profit tracking, daily-use incentives, actionable insights, and a robust set of tools to help users manage finances, inventory, compliance, taxation, and business growth—all in a secure, mobile-friendly, and extensible environment.

The platform features a streamlined user experience for entrepreneurs/traders with dedicated admin capabilities for system management, comprehensive tax calculation tools, real-time profit display functionality, and educational resources to help users understand Nigerian tax compliance.

## Key Highlights

- **Real-time Profit Display**: Toggle between gross profit and true profit (tax prep mode) with one click
- **Smart Dashboard**: Interactive profit summaries with visual indicators and real-time calculations
- **Tax Preparation Mode**: Instantly calculate true profit by subtracting all expenses and inventory costs from income
- **Comprehensive Financial Tracking**: Complete cashflow management with expense categorization
- **Mobile-First Design**: Responsive interface optimized for African entrepreneurs on-the-go

## Key Features

### 🎯 Core Business Management
- **Smart Reminders**: Daily log reminders with customizable debt aging alerts
- **Quick Log Buttons**: Fast entry for sales, expenses, and inventory transactions
- **Visual Progress & Charts**: Dashboard with profit/loss tracking, streaks, and financial health visualization (Chart.js)
- **Streaks & Gamification**: Track daily usage streaks with rewards (up to 30% discount on 100-day streaks)
- **Profit Summary PDF**: Downloadable profit/loss reports with detailed breakdowns (ReportLab)

### 💰 Advanced Financial Management
- **Real-time Profit Tracking**: 
  - Instant profit calculations with visual indicators
  - Toggle between gross profit and true profit views
  - Tax preparation mode for accurate profit assessment
  - Interactive profit summary cards on dashboard

- **Expense Categorization System**: 8 comprehensive expense categories with tax deductibility tracking:
  - Office & Admin (tax-deductible)
  - Staff & Wages (tax-deductible)
  - Business Travel & Transport (tax-deductible)
  - Rent & Utilities (tax-deductible)
  - Marketing & Sales (tax-deductible)
  - Cost of Goods Sold - COGS (tax-deductible)
  - Personal Expenses (non-deductible)
  - Statutory & Legal Contributions (tax-deductible, special handling)

- **Smart Financial Insights**:
  - Debt & Credit Tracking with comprehensive alerts
  - Inventory Loss Detection with smart alerts
  - Real-time cashflow summaries
  - Automated profit/loss calculations

### 🧮 Tax Calculation Engine
- **Dual Entity Type Support**: 
  - Sole Proprietor (Personal Income Tax - PIT)
  - Limited Liability Company (Companies Income Tax - CIT)
- **Four-Step PIT Calculation**:
  1. Net Business Profit calculation using 6 deductible categories
  2. Statutory & Legal Contributions deduction
  3. Rent Relief calculation (lesser of 20% rent or ₦500,000)
  4. Progressive tax band application (NTA 2025 rates: 15%, 18%, 21%, 24%, 25%)
- **CIT Calculation**: 0% for companies ≤₦50M revenue, 30% for >₦50M revenue
- **Real-time Tax Calculator**: Interactive interface with detailed breakdown displays

### 📚 Education & Compliance
- **Tax Education System**: Personalized learning paths based on user type:
  - Employee (PAYE focus)
  - Entrepreneur Unregistered (formalization benefits)
  - Sole Proprietor (PIT requirements)
  - Company (CIT requirements)
- **Interactive Learning Modules**: Understanding tax types, filing requirements, deductions & reliefs
- **Compliance Tracking**: Tools to help users stay compliant with Nigerian tax regulations

### 📊 Inventory & Operations
- **Full Inventory Management**: Complete CRUD operations with dedicated module and UI
- **Loss Detection**: Automated alerts for inventory cost anomalies
- **Margin Tracking**: Monitor profitability across inventory items

### 👥 User Management & Security
- **Secure Authentication**: Flask-Login with session management
- **Trial/Subscription Logic**: Flexible subscription system with trial periods
- **Admin Dashboard**: Dedicated admin account for user monitoring, KYC management, and system oversight
- **Role-based Access Control**: Separate interfaces for traders and administrators

### 🌍 Internationalization & Accessibility
- **Multi-language Support**: English and Hausa translations (Flask-Babel)
- **PWA Support**: Installable, offline-capable web app with manifest and service worker
- **Responsive Design**: Mobile-first, Bootstrap 5-based interface
- **Accessibility Compliance**: ARIA labels, keyboard navigation, screen reader support

### 🔔 Notifications & Engagement
- **In-app Notifications**: Real-time alerts for key events and reminders
- **Engagement Banners**: Contextual prompts to encourage platform usage
- **Reward System**: Streak-based incentives and discount programs

### 📋 Compliance & Documentation
- **KYC Management**: Upload and manage compliance documents
- **Audit Logging**: Comprehensive activity tracking for compliance
- **Report Generation**: Detailed financial reports for tax and business purposes

## Tech Stack

### Backend
- **Python 3** with **Flask** framework
- **Flask Extensions**: Login, Session, Babel, Limiter, CORS, WTF, Compress
- **Database**: MongoDB with PyMongo driver
- **Authentication**: Flask-Login with secure session management
- **PDF Generation**: ReportLab for financial reports

### Frontend
- **Templates**: Jinja2 with Bootstrap 5
- **Charts**: Chart.js for financial visualizations
- **PWA**: Manifest.json and Service Worker (sw.js)
- **Styling**: Custom CSS with responsive design

### Infrastructure
- **Deployment**: WSGI (wsgi.py) compatible with Render.com/Heroku/Cloud platforms
- **Configuration**: Environment variables with dotenv
- **Logging**: Comprehensive logging with session tracking
- **Security**: CSRF protection, CORS handling, rate limiting

## Application Modules

### Core Modules
- **Dashboard**: Central hub with reminders, charts, streaks, and financial alerts
- **Payments & Receipts**: Record and manage all cashflows with expense categorization
- **Inventory**: Add, view, and manage inventory items with loss detection
- **Debtors & Creditors**: Track receivables and payables with aging alerts

### Financial & Tax Modules
- **Tax Calculator**: Interactive tax calculation with entity type support
- **Reports**: Generate and download comprehensive profit/loss summaries
- **Education**: Tax education system with personalized learning paths

### Management Modules
- **Admin**: User monitoring, KYC management, subscription oversight (admin only)
- **Settings**: User profile, preferences, language selection, entity type management
- **KYC & Compliance**: Document upload and compliance management
- **Subscribe**: Trial and subscription plan management

### Engagement Modules
- **Notifications**: In-app alerts and reminder system
- **Rewards**: Streak tracking and reward management

## Directory Structure

```
ficore_labs/
├── app.py                 # App factory and blueprint registration
├── models.py              # Data models and database initialization
├── utils.py               # Utility functions (DB, logging, expense categories)
├── tax_calculation_engine.py  # Tax calculation logic for PIT and CIT
├── wsgi.py               # WSGI entry point
├── requirements.txt      # Python dependencies
├── blueprints/           # Flask blueprints for modular architecture
│   ├── admin/           # Admin management interface
│   ├── business/        # Business logic and operations
│   ├── creditors/       # Creditor management
│   ├── dashboard/       # Main dashboard
│   ├── debtors/         # Debtor management
│   ├── education/       # Tax education system
│   ├── general/         # General pages and landing
│   ├── inventory/       # Inventory management
│   ├── kyc/            # KYC and compliance
│   ├── payments/        # Payment processing with categories
│   ├── receipts/        # Receipt management
│   ├── reports/         # Financial reporting
│   ├── rewards/         # Reward and streak system
│   ├── settings/        # User settings and preferences
│   ├── subscribe/       # Subscription management
│   ├── tax/            # Tax calculator interface
│   └── users/          # User authentication and management
├── helpers/             # Custom business logic
├── templates/           # Jinja2 templates (modular by section)
├── static/             # CSS, JS, images, manifest, service worker
├── translations/        # Multi-language support files
└── notifications/       # Notification system
```

## Getting Started

### Prerequisites
- Python 3.8+
- MongoDB database
- Environment variables for configuration

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ficore_labs
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   Create a `.env` file with:
   ```
   SECRET_KEY=your_secret_key_here
   MONGO_URI=your_mongodb_connection_string
   FLASK_ENV=development
   ```

4. **Run the application**
   ```bash
   python -m ficore_labs.app
   # or
   flask run
   ```

5. **Access the application**
   Open http://localhost:5000 in your browser

### Default Admin Account
- **Username**: admin
- **Password**: Admin123!

This account is auto-created for system management, user monitoring, KYC oversight, and subscription management. All other users are entrepreneurs/traders by default.

## Key Features in Detail

### Real-time Profit Display System
The platform features an advanced profit tracking system with multiple viewing modes:

- **Gross Profit Mode**: Shows simple Income - Expenses calculation
- **Tax Prep Mode**: Calculates true profit by subtracting all expenses AND inventory costs from income
- **Interactive Toggle**: One-click switching between profit views
- **Visual Indicators**: Color-coded profit displays (green for positive, red for negative)
- **Dashboard Integration**: Prominent profit summary cards with real-time updates
- **PDF Export**: Downloadable profit/loss summaries for tax preparation

### Expense Categorization System
The platform includes a sophisticated 8-category expense system designed for Nigerian tax compliance:

- **6 Tax-Deductible Categories**: Office & Admin, Staff & Wages, Business Travel, Rent & Utilities, Marketing & Sales, COGS
- **1 Non-Deductible Category**: Personal Expenses
- **1 Special Category**: Statutory & Legal Contributions (handled separately in tax calculations)

### Tax Calculation Engine
- **Automatic Entity Type Detection**: Routes calculations based on user's business structure
- **PIT Four-Step Process**: Compliant with Nigeria Tax Act 2025
- **CIT Revenue Threshold**: Automatic 0% vs 30% rate application
- **Rent Relief Calculation**: Automatic application of rent relief benefits
- **Progressive Tax Bands**: Accurate application of multiple tax rates

### Education System
- **Personalized Learning**: Content adapts based on user's business type
- **Interactive Modules**: Step-by-step guidance through tax concepts
- **Practical Examples**: Real-world scenarios relevant to Nigerian businesses
- **Compliance Tracking**: Tools to help users stay compliant

## Contributing

We welcome contributions! Please follow these guidelines:

1. **Code Style**: Follow PEP8 standards
2. **Modular Design**: Keep features modular using the blueprint system
3. **Translations**: Update relevant files in `translations/` for new features
4. **Testing**: Include tests for new functionality
5. **Documentation**: Update README and inline documentation

### Adding New Blueprints
1. Create blueprint under `blueprints/<name>/`
2. Import in `app.py`: `from blueprints.<name>.routes import <name>_bp`
3. Register: `app.register_blueprint(<name>_bp, url_prefix='/<name>')`

### Translation Updates
- Update files in `translations/general_features/` and `translations/trader/`
- Use translation keys in templates: `{{ trans('key_name', default='Default Text') }}`

## Deployment

The application is designed for easy deployment on cloud platforms with idempotent migrations:

- **Render.com**: Use `wsgi.py` as entry point (recommended)
- **Heroku**: Compatible with Heroku's Python buildpack
- **Cloud Platforms**: Standard WSGI deployment

### Render.com Deployment Features
- **Idempotent Migrations**: All database migrations are designed to run safely on every deployment
- **Automatic Restarts**: Render handles app restarts without data loss
- **Environment Variables**: Secure configuration management
- **Zero-Downtime Deployments**: Seamless updates without service interruption

### Environment Configuration
Ensure these environment variables are set in production:
- `SECRET_KEY`: Strong secret key for session security
- `MONGO_URI`: MongoDB connection string
- `FLASK_ENV`: Set to 'production'
- `SERVER_NAME`: Your domain name
- `PREFERRED_URL_SCHEME`: 'https' for production

### Migration Safety
All migrations in this application are idempotent and safe to run multiple times:
- Database initialization checks for existing data
- Migration flags prevent duplicate operations
- Graceful handling of missing collections
- No data loss on redeployments

## License

This project is proprietary software developed by Ficore Labs for African entrepreneurs and traders.

## Support

For support, feature requests, or bug reports, please contact the development team or create an issue in the project repository.

## Development History & Critical Fixes

### Major System Fixes & Enhancements

#### JSON Serialization & Data Integrity
- **Fixed ObjectId JSON serialization errors** across all dashboard and API routes
- **Resolved datetime serialization issues** with proper timezone handling
- **Enhanced data cleaning functions** with comprehensive fallback mechanisms
- **Implemented safe query functions** to handle corrupted data gracefully

#### Real-time Tax Calculator
- **Added real-time calculations** with 800ms debounced updates
- **Enhanced user experience** with live expense totals and visual feedback
- **Implemented comprehensive tax breakdown modal** with detailed step-by-step calculations
- **Added missing translation keys** to eliminate warning messages

#### Dashboard Improvements
- **Cleaned up contradictory information** by removing conflicting bottom cards
- **Enhanced real-time data fetching** with robust error handling
- **Implemented dismissable notifications system** with smart persistence
- **Added comprehensive DIICE module integration** (Debtors, Inventory, Income, Creditors, Expenses)

#### Data Safety & Migration
- **Implemented idempotent migrations** safe for Render deployment
- **Enhanced cashflow data cleaning** with backslash character handling
- **Added comprehensive data validation** and sanitization
- **Created emergency cleanup utilities** for data maintenance

#### Offline Functionality
- **Comprehensive offline support** with IndexedDB storage
- **Automatic data synchronization** with conflict resolution
- **Smart caching strategies** for optimal performance
- **Progressive Web App features** with service worker implementation

#### Admin Management System
- **44 comprehensive admin routes** for complete system oversight
- **User management with CRUD operations** and subscription handling
- **Tax configuration management** compliant with NTA 2025 rates
- **Analytics dashboard** with comprehensive reporting
- **Audit logging** and security features

### Deployment Optimizations

#### Render.com Compatibility
- **Idempotent database migrations** that run safely on every deployment
- **Environment variable configuration** for production settings
- **Automatic domain redirects** from onrender.com to custom domain
- **WSGI configuration** optimized for cloud deployment

#### Performance Enhancements
- **Optimized database queries** with aggregation pipelines
- **Efficient caching strategies** for static and dynamic content
- **Real-time updates** with minimal API calls
- **Memory management** and cleanup procedures

#### Security Improvements
- **Enhanced input sanitization** preventing XSS and injection attacks
- **CSRF protection** on all forms and API endpoints
- **Rate limiting** to prevent abuse
- **Comprehensive audit logging** for compliance

### Code Quality & Maintenance

#### Clean Architecture
- **Modular blueprint system** for organized code structure
- **Comprehensive error handling** with graceful degradation
- **Consistent coding standards** following PEP8 guidelines
- **Extensive documentation** for developer onboarding

#### Testing & Validation
- **Comprehensive test coverage** for critical functions
- **Data integrity validation** across all operations
- **Error scenario testing** with fallback mechanisms
- **Performance testing** for optimization

#### Internationalization
- **Multi-language support** with English and Hausa translations
- **Complete translation coverage** for all user-facing text
- **Cultural adaptation** for Nigerian business practices
- **Accessibility compliance** with WCAG guidelines

### Technical Debt Resolution

#### Legacy Code Cleanup
- **Removed redundant test files** for cleaner deployment
- **Consolidated documentation** into comprehensive README
- **Eliminated deprecated functions** and unused imports
- **Optimized database connections** and resource usage

#### Modern Standards Adoption
- **ES6+ JavaScript features** for better performance
- **Bootstrap 5 integration** for modern UI components
- **Progressive Web App standards** for mobile experience
- **RESTful API design** for consistent endpoints

## Dashboard Stats Fix Implementation

### Problem Resolution
Fixed critical dashboard template errors where `stats.total_sales_amount` and `stats.total_expenses_amount` were undefined, causing Jinja2 `UndefinedError`. The solution involved:

- **Template Compatibility**: Added aliases mapping `total_sales_amount` to `total_receipts_amount` and `total_expenses_amount` to `total_payments_amount`
- **Defensive Programming**: Implemented comprehensive key validation ensuring all required stats keys are present with safe defaults
- **Error Resilience**: Dashboard displays with default values even if database operations fail

### Stats Standardization System
Implemented comprehensive utility functions in `utils.py` for consistent stats handling:

- **`standardize_stats_dictionary()`**: Ensures all required stats keys are present with safe defaults
- **`format_stats_for_template()`**: Formats currency values and preserves raw data for templates  
- **`validate_stats_completeness()`**: Validates stats dictionaries and provides debugging info

### Benefits Achieved
- **Consistency**: All stats dictionaries have the same structure across routes
- **Error Prevention**: Missing keys automatically filled with safe defaults
- **Template Safety**: Templates can access any stats key without errors
- **Debugging**: Detailed logging when defaults are used
- **Maintainability**: Centralized stats structure management

## Current State of the Codebase

Based on the latest development cycle, the following key components are now in place:

### Centralized Datetime Handling ✅
- **`normalize_datetime` in utils.py**: Ensures all datetimes are UTC-aware and serialized as ISO strings
- **Consistent Implementation**: Used across `clean_cashflow_record`, `aggressively_clean_record`, `clean_record`, `create_cashflow`, `create_record`, `to_dict_cashflow`, and `to_dict_record`
- **UTC Enforcement**: All datetime operations standardized to UTC timezone

### Consistent Serialization ✅
- **Standardized Output**: `to_dict_cashflow` and `to_dict_record` in models.py provide consistent output with ISO-formatted `created_at` and `updated_at`
- **Route Integration**: Applied in `fetch_payments_with_fallback`, `view`, `generate_pdf`, and `edit` routes
- **Legacy Cleanup**: Replaced `bulk_clean_documents_for_json` and `clean_document_for_json` with new standardized functions

### Robust Query Functions ✅
- **Safe Query Operations**: `safe_find_cashflows` and `safe_find_records` in utils.py handle queries with fallback logic, cleaning, and normalization
- **Optimized Performance**: `fetch_payments_with_fallback` now uses `sort_field` and `to_dict_cashflow` with optimized indexes
- **Database Optimization**: Compound indexes on (`user_id`, `type`, `user_id`, `created_at`) and `maxTimeMS` for query timeout handling

### UTC Enforcement at Insertion ✅
- **Data Integrity**: `create_cashflow` and `create_record` enforce UTC-aware `created_at` using `normalize_datetime`
- **Form Processing**: `add` and `edit` routes in payments/routes.py use `create_cashflow` and `update_cashflow`
- **Date Normalization**: All form date inputs processed through `normalize_datetime` for consistency

### Proactive Monitoring ✅
- **Audit Functions**: `audit_datetime_fields` runs in index route and `initialize_app_data`, logging any naive or non-datetime `created_at` values
- **Migration Handling**: `check_and_migrate_naive_datetimes` handles new records post-migration
- **Comprehensive Logging**: Detailed logging for datetime-related operations and anomalies

### Optimized Database Indexes ✅
- **Cashflows Collection**: Compound indexes on (`user_id`, `created_at`) and (`user_id`, `type`, `created_at`) for improved query performance
- **Records Collection**: Compound indexes on (`user_id`, `created_at`) for efficient data retrieval
- **Performance Monitoring**: Query optimization with timeout handling and fallback mechanisms

### Enhanced Error Handling ✅
- **Comprehensive Coverage**: All routes (`index`, `manage`, `view`, `add`, `edit`, `delete`, `generate_pdf`, `share`) include comprehensive logging
- **User-Friendly Messages**: Error messages processed through translation system (`trans`) for multi-language support
- **Graceful Degradation**: Fallback mechanisms ensure system stability even with data inconsistencies

## Deployment Status: Production Ready

### Cleanup Completed ✅
- **Test Files Removed**: All development test files cleaned up
- **Documentation Consolidated**: All summary files merged into comprehensive README
- **Cache Cleanup**: All `__pycache__` directories and .pyc files removed
- **Models Cleaned**: Removed forecast, fund, and investor_report references

### Production-Ready Features ✅
- **Real-time Profit Tracking**: Toggle between gross profit and tax prep mode
- **Smart Dashboard**: Interactive elements with comprehensive stats
- **Tax Calculation Engine**: PIT & CIT calculations compliant with NTA 2025
- **Advanced Expense Categorization**: 8 categories with tax deductibility tracking
- **Multi-language Support**: English and Hausa translations
- **PWA Support**: Offline functionality with service worker
- **Admin Management**: 44 comprehensive admin routes

### Deployment Configuration ✅
- **Render.com Ready**: Idempotent migrations for safe deployment
- **Environment Variables**: Secure configuration management
- **WSGI Optimization**: Cloud deployment ready
- **Domain Redirects**: Automatic redirect configuration

---

**Ficore Labs** - Empowering African entrepreneurs with modern business management tools and tax compliance education.