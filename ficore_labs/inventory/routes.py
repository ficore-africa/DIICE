from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from translations import trans
import utils
from datetime import datetime, timezone

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')

@inventory_bp.route('/')
@login_required
def index():
    db = utils.get_mongo_db()
    user_id = str(current_user.id)
    inventory_items = list(db.records.find({'user_id': user_id, 'type': 'inventory'}))
    return render_template('inventory/index.html', inventory_items=inventory_items)

@inventory_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        db = utils.get_mongo_db()
        user_id = str(current_user.id)
        name = request.form.get('name')
        cost = float(request.form.get('cost', 0))
        expected_margin = float(request.form.get('expected_margin', 0))
        db.records.insert_one({
            'user_id': user_id,
            'type': 'inventory',
            'name': name,
            'cost': cost,
            'expected_margin': expected_margin,
            'created_at': datetime.now(timezone.utc)
        })
        flash(trans('inventory_added', default='Inventory item added!'), 'success')
        return redirect(url_for('inventory.index'))
    return render_template('inventory/add.html')
