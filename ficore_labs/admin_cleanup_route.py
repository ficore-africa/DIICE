"""
Admin route to manually trigger data cleanup for users experiencing the backslash error.
Add this to your admin blueprint or create a separate admin utility.
"""

from flask import Blueprint, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
import utils
import logging

logger = logging.getLogger(__name__)

# This can be added to your existing admin blueprint
def add_cleanup_routes(admin_bp):
    """Add cleanup routes to an existing admin blueprint."""
    
    @admin_bp.route('/cleanup-user-data', methods=['POST'])
    @login_required
    @utils.requires_role(['admin'])
    def cleanup_user_data():
        """Manually trigger data cleanup for a specific user."""
        try:
            user_id = request.form.get('user_id') or request.json.get('user_id')
            
            if not user_id:
                return jsonify({'success': False, 'message': 'User ID is required'}), 400
            
            # Sanitize the user_id input
            user_id = utils.sanitize_input(user_id, max_length=50)
            
            logger.info(f"Admin {current_user.id} triggered cleanup for user {user_id}")
            
            # Perform the emergency cleanup
            success = utils.emergency_clean_user_data(user_id)
            
            if success:
                message = f"Successfully cleaned data for user {user_id}"
                logger.info(message)
                return jsonify({'success': True, 'message': message})
            else:
                message = f"Failed to clean data for user {user_id}"
                logger.error(message)
                return jsonify({'success': False, 'message': message}), 500
                
        except Exception as e:
            error_msg = f"Error during cleanup: {str(e)}"
            logger.error(error_msg)
            return jsonify({'success': False, 'message': error_msg}), 500
    
    @admin_bp.route('/bulk-cleanup', methods=['POST'])
    @login_required
    @utils.requires_role(['admin'])
    def bulk_cleanup():
        """Trigger bulk cleanup of all cashflow data."""
        try:
            logger.info(f"Admin {current_user.id} triggered bulk cleanup")
            
            db = utils.get_mongo_db()
            if not db:
                return jsonify({'success': False, 'message': 'Database connection failed'}), 500
            
            cleaned_count = utils.bulk_clean_cashflow_data(db)
            
            message = f"Bulk cleanup completed. Cleaned {cleaned_count} records."
            logger.info(message)
            return jsonify({'success': True, 'message': message, 'cleaned_count': cleaned_count})
            
        except Exception as e:
            error_msg = f"Error during bulk cleanup: {str(e)}"
            logger.error(error_msg)
            return jsonify({'success': False, 'message': error_msg}), 500

# Standalone blueprint if you want to create a separate admin utility
cleanup_bp = Blueprint('cleanup', __name__, url_prefix='/admin/cleanup')

@cleanup_bp.route('/user/<user_id>', methods=['POST'])
@login_required
@utils.requires_role(['admin'])
def cleanup_specific_user(user_id):
    """Clean data for a specific user via URL parameter."""
    try:
        # Sanitize the user_id input
        user_id = utils.sanitize_input(user_id, max_length=50)
        
        logger.info(f"Admin {current_user.id} triggered cleanup for user {user_id}")
        
        # Perform the emergency cleanup
        success = utils.emergency_clean_user_data(user_id)
        
        if success:
            flash(f"Successfully cleaned data for user {user_id}", 'success')
        else:
            flash(f"Failed to clean data for user {user_id}", 'danger')
            
        return redirect(request.referrer or url_for('admin.index'))
        
    except Exception as e:
        logger.error(f"Error during cleanup for user {user_id}: {str(e)}")
        flash(f"Error during cleanup: {str(e)}", 'danger')
        return redirect(request.referrer or url_for('admin.index'))

# Quick fix function that can be called directly
def quick_fix_hassan():
    """Quick fix specifically for user hassan."""
    try:
        logger.info("Running quick fix for user hassan")
        success = utils.emergency_clean_user_data('hassan')
        
        if success:
            logger.info("Quick fix for hassan completed successfully")
            return True
        else:
            logger.error("Quick fix for hassan failed")
            return False
            
    except Exception as e:
        logger.error(f"Error in quick fix for hassan: {str(e)}")
        return False

if __name__ == "__main__":
    # Can be run directly to fix hassan's data
    quick_fix_hassan()