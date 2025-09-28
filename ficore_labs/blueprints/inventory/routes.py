from bson import ObjectId
from utils import INVENTORY_CATEGORIES, INVENTORY_UNITS
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField
from wtforms.validators import DataRequired, NumberRange
from translations import trans
import utils
from datetime import datetime, timezone

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')

class InventoryForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    cost = FloatField('Cost', validators=[DataRequired(), NumberRange(min=0)])
    expected_margin = FloatField('Expected Margin', validators=[DataRequired(), NumberRange(min=0)])
    stock_qty = FloatField('Stock Quantity', validators=[NumberRange(min=0)], default=None)
    quantity_in_stock = FloatField('Quantity in Stock', validators=[NumberRange(min=0)], default=None)
    reorder_level = FloatField('Reorder Level', validators=[NumberRange(min=0)], default=None)
    restock_date = StringField('Restock Date', default=None)
    status = StringField('Status', default='Active')
    vendor_id = StringField('Vendor ID', default=None)
    selling_price = FloatField('Selling Price', validators=[NumberRange(min=0)], default=None)
    manual_price_override = StringField('Manual Price Override', default='False')
    category = StringField('Category', default=None)
    unit = StringField('Unit', default=None)
    submit = SubmitField('Add Item')

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
    form = InventoryForm()
    try:
        can_interact = utils.can_user_interact(current_user)  # Updated to use can_user_interact
    except AttributeError:
        flash(trans('server_error', default='Server configuration error. Please contact support.'), 'error')
        return render_template('inventory/add.html', form=form, can_interact=False)
    
    if form.validate_on_submit() and can_interact:
        try:
            db = utils.get_mongo_db()
            user_id = str(current_user.id)
            inventory_data = {
                'user_id': user_id,
                'type': 'inventory',
                'name': form.name.data,
                'cost': form.cost.data,
                'expected_margin': form.expected_margin.data,
                'created_at': datetime.now(timezone.utc)
            }
            # Add new optional fields if provided
            if form.stock_qty.data is not None:
                inventory_data['stock_qty'] = form.stock_qty.data
            if form.quantity_in_stock.data is not None:
                inventory_data['quantity_in_stock'] = form.quantity_in_stock.data
            if form.reorder_level.data is not None:
                inventory_data['reorder_level'] = form.reorder_level.data
            if form.restock_date.data:
                inventory_data['restock_date'] = form.restock_date.data
            if form.status.data:
                inventory_data['status'] = form.status.data
            if form.vendor_id.data:
                inventory_data['vendor_id'] = form.vendor_id.data
            if form.category.data:
                inventory_data['category'] = form.category.data
            if form.unit.data:
                inventory_data['unit'] = form.unit.data
            # Selling price logic
            manual_override = (form.manual_price_override.data == 'True')
            if manual_override and form.selling_price.data is not None:
                inventory_data['selling_price'] = form.selling_price.data
                inventory_data['manual_price_override'] = True
            else:
                # Auto-calculate selling price if not manually overridden
                if form.cost.data is not None and form.expected_margin.data is not None:
                    inventory_data['selling_price'] = float(form.cost.data) + float(form.expected_margin.data)
                    inventory_data['manual_price_override'] = False

            db.records.insert_one(inventory_data)

            # --- COGS Expense Automation ---
            cogs_data = {
                'user_id': user_id,
                'type': 'payment',
                'party_name': form.name.data,
                'amount': form.cost.data,
                'expense_category': 'cogs',
                'description': f"COGS for inventory item: {form.name.data}",
                'created_at': datetime.now(timezone.utc)
            }
            db.cashflows.insert_one(cogs_data)

            # --- Inventory Movement Logging ---
            movement_data = {
                'inventory_item_id': str(inventory_data.get('name', '')),
                'change_type': 'add',
                'quantity': inventory_data.get('quantity_in_stock', inventory_data.get('stock_qty', 0)),
                'date': datetime.now(timezone.utc),
                'notes': 'Initial stock addition'
            }
            db.inventory_movements.insert_one(movement_data)

            flash(trans('inventory_added', default='Inventory item added!'), 'success')
            return redirect(url_for('inventory.index'))
        except Exception as e:
            flash(trans('db_error', default=f'Error adding item: {str(e)}'), 'error')
            return render_template('inventory/add.html', form=form, can_interact=can_interact)
    return render_template('inventory/add.html', form=form, can_interact=can_interact)
@inventory_bp.route('/edit/<item_id>', methods=['GET', 'POST'])
@login_required
def edit(item_id):
    db = utils.get_mongo_db()
    user_id = str(current_user.id)
    item = db.records.find_one({'_id': ObjectId(item_id), 'user_id': user_id, 'type': 'inventory'})
    if not item:
        flash('Inventory item not found.', 'error')
        return redirect(url_for('inventory.index'))

    class EditInventoryForm(InventoryForm):
        pass
    form = EditInventoryForm(data=item)

    old_quantity = item.get('quantity_in_stock', 0)

    if form.validate_on_submit():
        update_data = {
            'name': form.name.data,
            'cost': form.cost.data,
            'expected_margin': form.expected_margin.data,
            'quantity_in_stock': form.quantity_in_stock.data,
            'reorder_level': form.reorder_level.data,
            'restock_date': form.restock_date.data,
            'status': form.status.data,
            'vendor_id': form.vendor_id.data,
            'category': form.category.data,
            'unit': form.unit.data
        }
        manual_override = (form.manual_price_override.data == 'True')
        if manual_override and form.selling_price.data is not None:
            update_data['selling_price'] = form.selling_price.data
            update_data['manual_price_override'] = True
        else:
            update_data['selling_price'] = float(form.cost.data) + float(form.expected_margin.data)
            update_data['manual_price_override'] = False

        db.records.update_one({'_id': ObjectId(item_id)}, {'$set': update_data})

        # Movement tracking if quantity changed
        new_quantity = form.quantity_in_stock.data
        if new_quantity != old_quantity:
            movement_data = {
                'inventory_item_id': str(item_id),
                'change_type': 'adjust',
                'quantity': new_quantity - old_quantity,
                'date': datetime.now(timezone.utc),
                'notes': 'Stock quantity adjusted via edit'
            }
            db.inventory_movements.insert_one(movement_data)

        flash('Inventory item updated!', 'success')
        return redirect(url_for('inventory.index'))

    return render_template('inventory/edit.html', form=form, item=item, INVENTORY_CATEGORIES=INVENTORY_CATEGORIES, INVENTORY_UNITS=INVENTORY_UNITS)


@inventory_bp.route('/<item_id>/history')
@login_required
def history(item_id):
    db = utils.get_mongo_db()
    user_id = str(current_user.id)
    movements = list(db.inventory_movements.find({'inventory_item_id': str(item_id)}).sort('date', -1))
    return render_template('inventory/history.html', movements=movements)