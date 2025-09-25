#!/usr/bin/env python3
"""
Setup script for FiCore Africa Offline Functionality
This script helps configure and verify the offline functionality setup.
"""

import os
import sys
import json
from pathlib import Path

def check_file_exists(file_path, description):
    """Check if a file exists and report status"""
    if os.path.exists(file_path):
        print(f"✅ {description}: {file_path}")
        return True
    else:
        print(f"❌ {description}: {file_path} (MISSING)")
        return False

def check_directory_structure():
    """Verify the required directory structure exists"""
    print("🔍 Checking directory structure...")
    
    required_dirs = [
        "static/js",
        "static/css",
        "static/img/icons",
        "blueprints/api",
        "templates"
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"✅ Directory: {dir_path}")
        else:
            print(f"❌ Directory: {dir_path} (MISSING)")
            all_exist = False
    
    return all_exist

def check_offline_files():
    """Check if all offline functionality files are present"""
    print("\n🔍 Checking offline functionality files...")
    
    required_files = [
        ("static/enhanced-service-worker.js", "Enhanced Service Worker"),
        ("static/js/offline-manager.js", "Offline Manager"),
        ("static/js/offline-ui.js", "Offline UI Components"),
        ("static/js/sync-service.js", "Sync Service"),
        ("static/manifest.json", "Web App Manifest"),
        ("blueprints/api/__init__.py", "API Blueprint Init"),
        ("blueprints/api/routes.py", "API Routes"),
        ("templates/offline.html", "Offline Page Template"),
        ("OFFLINE_FUNCTIONALITY_GUIDE.md", "Documentation")
    ]
    
    all_exist = True
    for file_path, description in required_files:
        if not check_file_exists(file_path, description):
            all_exist = False
    
    return all_exist

def validate_manifest():
    """Validate the web app manifest"""
    print("\n🔍 Validating web app manifest...")
    
    manifest_path = "static/manifest.json"
    if not os.path.exists(manifest_path):
        print("❌ Manifest file not found")
        return False
    
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        required_fields = ['name', 'short_name', 'start_url', 'display', 'icons']
        missing_fields = [field for field in required_fields if field not in manifest]
        
        if missing_fields:
            print(f"❌ Manifest missing required fields: {missing_fields}")
            return False
        
        print("✅ Manifest is valid")
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Manifest JSON is invalid: {e}")
        return False

def check_app_integration():
    """Check if the offline functionality is properly integrated into app.py"""
    print("\n🔍 Checking app.py integration...")
    
    if not os.path.exists("app.py"):
        print("❌ app.py not found")
        return False
    
    with open("app.py", 'r') as f:
        app_content = f.read()
    
    checks = [
        ("from blueprints.api.routes import api_bp", "API Blueprint Import"),
        ("app.register_blueprint(api_bp, url_prefix='/api')", "API Blueprint Registration")
    ]
    
    all_integrated = True
    for check_string, description in checks:
        if check_string in app_content:
            print(f"✅ {description}")
        else:
            print(f"❌ {description} (MISSING)")
            all_integrated = False
    
    return all_integrated

def check_template_integration():
    """Check if offline scripts are included in base template"""
    print("\n🔍 Checking template integration...")
    
    base_template = "templates/base.html"
    if not os.path.exists(base_template):
        print("❌ base.html template not found")
        return False
    
    with open(base_template, 'r') as f:
        template_content = f.read()
    
    checks = [
        ("offline-manager.js", "Offline Manager Script"),
        ("offline-ui.js", "Offline UI Script"),
        ("sync-service.js", "Sync Service Script")
    ]
    
    all_integrated = True
    for check_string, description in checks:
        if check_string in template_content:
            print(f"✅ {description}")
        else:
            print(f"❌ {description} (MISSING)")
            all_integrated = False
    
    return all_integrated

def create_missing_directories():
    """Create any missing directories"""
    print("\n🔧 Creating missing directories...")
    
    required_dirs = [
        "static/js",
        "static/css", 
        "static/img/icons",
        "blueprints/api",
        "templates"
    ]
    
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            print(f"✅ Created directory: {dir_path}")

def generate_setup_report():
    """Generate a comprehensive setup report"""
    print("\n" + "="*60)
    print("📋 FICORE AFRICA OFFLINE FUNCTIONALITY SETUP REPORT")
    print("="*60)
    
    # Check all components
    dir_check = check_directory_structure()
    files_check = check_offline_files()
    manifest_check = validate_manifest()
    app_check = check_app_integration()
    template_check = check_template_integration()
    
    # Overall status
    all_good = all([dir_check, files_check, manifest_check, app_check, template_check])
    
    print("\n" + "="*60)
    if all_good:
        print("🎉 SETUP COMPLETE! Offline functionality is ready to use.")
        print("\nNext steps:")
        print("1. Restart your Flask application")
        print("2. Test offline functionality in your browser")
        print("3. Check browser console for any errors")
        print("4. Review OFFLINE_FUNCTIONALITY_GUIDE.md for usage instructions")
    else:
        print("⚠️  SETUP INCOMPLETE! Please address the missing components above.")
        print("\nTo fix issues:")
        print("1. Ensure all required files are present")
        print("2. Update app.py with API blueprint registration")
        print("3. Include offline scripts in base.html template")
        print("4. Run this script again to verify")
    
    print("\n📚 Documentation: OFFLINE_FUNCTIONALITY_GUIDE.md")
    print("🔧 Support: Check browser console for debugging")
    print("="*60)
    
    return all_good

def main():
    """Main setup function"""
    print("🚀 FiCore Africa Offline Functionality Setup")
    print("This script will verify your offline functionality setup.\n")
    
    # Create missing directories first
    create_missing_directories()
    
    # Generate comprehensive report
    success = generate_setup_report()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()