from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
import psycopg2.extras  
from datetime import datetime
from collections import defaultdict
from decimal import Decimal
from psycopg2.extras import RealDictCursor
import os
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATABASE_URL = "postgresql://james:SPpKLyvgRTImuzDFaUy4thGKojpKfuBY@dpg-d120e495pdvs73c758og-a.oregon-postgres.render.com/ukwelidb"
def get_connection():
    return psycopg2.connect(DATABASE_URL)

# --- AUTHENTICATION AND DASHBOARD ---

@app.route("/")
def home():
    return render_template('login.html')

@app.route("/login", methods=["POST"])
def login():
    username = request.form['username']
    password = request.form['password']
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
                user = cur.fetchone()
        if user:
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return "Invalid credentials. <a href='/'>Try again</a>"
    except Exception as e:
        return f"Database error: {e}"

@app.route("/dashboard")
def dashboard():
    if 'username' in session:
        return render_template('dashboard.html', username=session['username'])
    else:
        return redirect(url_for('home'))
from flask import request, redirect, url_for, render_template
from datetime import datetime
@app.route('/prepaid-form')
def Prepaidform():
    gas_id = request.args.get("gas_id", type=int)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gas_id, gas_name FROM gas_table")
            gases = cur.fetchall()

    return render_template("Prepaidform.html", gases=gases, selected_gas_id=gas_id)
@app.route("/prepaid-list")
def prepaid_list():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ps.id, ps.customer_name, ps.empty_given, ps.customer_picture, 
                           g.gas_name
                    FROM prepaid_sales ps
                    JOIN gas_table g ON ps.gas_id = g.gas_id
                    ORDER BY ps.created_at DESC;
                """)
                rows = cur.fetchall()

                pending_prepaid = []
                for row in rows:
                    pending_prepaid.append({
                        "id": row[0],
                        "customer_name": row[1],
                        "empty_given": row[2],
                        "customer_picture": row[3],
                        "gas_name": row[4] or "Unknown"
                    })

        return render_template("Prepaidlist.html", pending_prepaid=pending_prepaid)
        

    except Exception as e:
        return f"Error loading prepaid list: {e}"
        

@app.route('/record-sale-and-open-prepay', methods=['POST'])
def record_sale_and_open_prepay():
    gas_id = request.args.get("gas_id", type=int)
    amount_paid_cash = float(request.form.get("amount_paid_cash", 0))
    amount_paid_till = float(request.form.get("amount_paid_till", 0))

    selected_source = request.form.get("source", "customer")
    source_kipsongo_pioneer = selected_source == "kipsongo_pioneer"
    source_mama_pam = selected_source == "mama_pam"
    source_external = selected_source == "external"

    sale_type = request.form.get("sale_type")
    complete_sale = sale_type == "complete_sale"
    empty_not_given = sale_type == "empty_not_given"
    exchange_cylinder = sale_type == "exchange_cylinder"

    time_sold = datetime.now()

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sales_table (
                        gas_id, amount_paid_cash, amount_paid_till,
                        source_kipsongo_pioneer, source_mama_pam, source_external,
                        complete_sale, empty_not_given, exchange_cylinder, time_sold
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    gas_id, amount_paid_cash, amount_paid_till,
                    source_kipsongo_pioneer, source_mama_pam, source_external,
                    complete_sale, empty_not_given, exchange_cylinder, time_sold
                ))
                conn.commit()

        return redirect(url_for('Prepaidform', gas_id=gas_id))

    except Exception as e:
        return f"Error: {e}", 500


@app.route('/submit-prepaid-sale', methods=['POST'])
def submit_prepaid_sale():
    customer_name = request.form.get('customer_name')
    customer_phone = request.form.get('customer_phone')
    customer_address = request.form.get('customer_address')
    gas_id = request.form.get('gas_id')
    empty_given = 'empty_given' in request.form
    picture_file = request.files.get('customer_picture')

    picture_path = ''
    if picture_file:
        filename = secure_filename(picture_file.filename)
        picture_path = os.path.join('static/uploads', filename)
        picture_file.save(picture_path)

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO prepaid_sales (
                        gas_id, customer_name, customer_phone, customer_address,
                        empty_given, customer_picture
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (gas_id, customer_name, customer_phone, customer_address, empty_given, picture_path))

                if empty_given:
                    cur.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders + 1 WHERE gas_id = %s", (gas_id,))

            conn.commit()
        flash('Prepaid sale recorded successfully', 'success')
    except Exception as e:
        flash(f"Error saving prepaid record: {e}", 'error')

    return redirect(url_for('sales'))


@app.route("/collect-prepaid/<int:prepaid_id>", methods=["POST"])
def collect_prepaid(prepaid_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1. Get prepaid record
                cur.execute("SELECT gas_id, empty_given FROM prepaid_sales WHERE id = %s", (prepaid_id,))
                record = cur.fetchone()

                if not record:
                    flash("❌ Prepaid record not found", "error")
                    return redirect(url_for('prepaid_list'))

                gas_id, empty_given = record

                # 2. Check gas availability
                cur.execute("SELECT filled_cylinders FROM gas_table WHERE gas_id = %s", (gas_id,))
                gas_status = cur.fetchone()

                if not gas_status or gas_status[0] <= 0:
                    flash("❌ No filled gas cylinders available for collection!", "error")
                    return redirect(url_for('prepaid_list'))

                # 3. Reduce filled by 1
                cur.execute("""
                    UPDATE gas_table SET filled_cylinders = filled_cylinders - 1
                    WHERE gas_id = %s
                """, (gas_id,))
                cur.execute("""
                    INSERT INTO stock_change (gas_id, action, quantity_change, notes)
                    VALUES (%s, 'decrease_filled', -1, 'Collected prepaid sale')
                """, (gas_id,))

                # 4. Handle empty_given logic
                checkbox_checked = request.form.get("empty_checkbox") == "on"

                if not empty_given:  # If empty wasn't given initially
                    if checkbox_checked:
                        # Now empty has been given
                        cur.execute("""
                            UPDATE gas_table SET empty_cylinders = empty_cylinders + 1
                            WHERE gas_id = %s
                        """, (gas_id,))
                        cur.execute("""
                            INSERT INTO stock_change (gas_id, action, quantity_change, notes)
                            VALUES (%s, 'increase_empty', 1, 'Empty received at collection')
                        """, (gas_id,))
                    else:
                        # No empty given still → record stock_out
                        cur.execute("""
                        INSERT INTO stock_out (gas_id, cylinder_state, destination_type, destination_value)
                        VALUES (%s, 'filled', 'customer', %s)
                    """, (gas_id, ['customer_name']))
                        cur.execute("""
                            INSERT INTO stock_change (gas_id, action, quantity_change, notes)
                            VALUES (%s, 'stock_out', -1, 'Prepaid collection without empty')
                        """, (gas_id,))

                # 5. Delete from prepaid_sales
                cur.execute("DELETE FROM prepaid_sales WHERE id = %s", (prepaid_id,))

                conn.commit()
                flash("✅ Collection completed successfully.", "success")
                return redirect(url_for('prepaid_list'))

    except Exception as e:
        flash(f"❌ Error during collection: {e}", "error")
        return redirect(url_for('prepaid_list'))
@app.route('/logs')
def view_logs():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT sc.id, g.gas_name, sc.action, sc.quantity_change, sc.notes, sc.changed_at
                    FROM stock_change sc
                    JOIN gas_table g ON sc.gas_id = g.gas_id
                    ORDER BY sc.changed_at DESC
                """)
                logs = cur.fetchall()
        return render_template("logs.html", logs=logs)
    except Exception as e:
        return f"Error fetching logs: {e}"

@app.route('/undo-payment/<int:debt_id>', methods=['POST'])
def undo_payment(debt_id):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get the most recent payment for this debt
                cur.execute("""
                    SELECT id, amount FROM gas_debt_payments
                    WHERE debt_id = %s
                    ORDER BY payment_date DESC, id DESC
                    LIMIT 1
                """, (debt_id,))
                last_payment = cur.fetchone()

                if not last_payment:
                    flash("No payment found to undo.", "warning")
                    return redirect(url_for('add_gas_debt'))

                payment_id = last_payment["id"]
                payment_amount = last_payment["amount"]

                # Delete the payment
                cur.execute("DELETE FROM gas_debt_payments WHERE id = %s", (payment_id,))

                # Update the main debt record (subtract the payment amount)
                cur.execute("""
                    UPDATE gas_debts
                    SET amount_paid = amount_paid - %s
                    WHERE id = %s
                """, (payment_amount, debt_id))

            conn.commit()
            flash("Last payment undone successfully.", "success")

    except Exception as e:
        flash(f"Error undoing payment: {e}", "danger")

    return redirect(url_for('add_gas_debt'))



@app.route('/add-payment/<int:debt_id>', methods=['POST'])
def add_payment(debt_id):
    try:
        amount = float(request.form['payment_amount'])

        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 1. Insert payment
                cur.execute("""
                    INSERT INTO gas_debt_payments (debt_id, amount, payment_date)
                    VALUES (%s, %s, NOW())
                """, (debt_id, amount))

                # 2. Update amount_paid
                cur.execute("""
                    UPDATE gas_debts
                    SET amount_paid = amount_paid + %s
                    WHERE id = %s
                """, (amount, debt_id))

                # 3. Fetch updated debt info
                cur.execute("""
                    SELECT gas_id, amount_paid, amount_to_be_paid, cleared
                    FROM gas_debts
                    WHERE id = %s
                """, (debt_id,))
                debt = cur.fetchone()

                if not debt:
                    raise Exception("Debt record not found.")

                balance = float(debt['amount_to_be_paid']) - float(debt['amount_paid'])

                # 4. If fully paid and not yet cleared, record as a sale
                if balance <= 0 and not debt['cleared']:
                    cur.execute("""
                        INSERT INTO sales_table (
                            gas_id,
                            sale_date,
                            amount_paid_cash,
                            amount_paid_till,
                            complete_sale,
                            source_kipsongo_pioneer,
                            source_mama_pam,
                            source_external,
                            empty_not_given,
                            exchange_cylinder,
                            from_debt
                        ) VALUES (%s, NOW(), %s, 0, TRUE, FALSE, FALSE, FALSE, FALSE, FALSE, TRUE)
                    """, (
                        debt['gas_id'],
                        float(debt['amount_to_be_paid'])
                    ))

                    # 5. Mark the debt as cleared
                    cur.execute("""
                        UPDATE gas_debts SET cleared = TRUE WHERE id = %s
                    """, (debt_id,))

            conn.commit()

        flash("Payment added successfully!", "success")
        return redirect(url_for('add_gas_debt'))

    except Exception as e:
        print("Error in add_payment:", e)
        flash(f"Error processing payment: {e}", "error")
        return redirect(url_for('add_gas_debt'))




@app.post("/delete-gas-debt/<int:debt_id>")
def delete_gas_debt(debt_id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("SELECT amount_paid, amount_to_be_paid FROM gas_debts WHERE id = %s", (debt_id,))
        debt = cur.fetchone()

        if debt is None:
            flash("Debt record not found.")
        else:
            amount_paid = debt["amount_paid"] or 0
            amount_to_be_paid = debt["amount_to_be_paid"] or 0
            balance = amount_to_be_paid - amount_paid

            if balance > 0:
                flash("Cannot delete. Customer still has a balance.")
            else:
                cur.execute("DELETE FROM gas_debts WHERE id = %s", (debt_id,))
                conn.commit()
                flash("Debt record deleted successfully.")


    except Exception as e:
        conn.rollback()
        flash(f"Error occurred: {e}")
    finally:
        cur.close()
        conn.close()
    return render_template("dashboard.html")
    # <-- Change here to your actual list view function name

@app.route('/gas-debt', methods=['GET'])
def search_gas_debt():
    search_term = request.args.get('search', '').strip()

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
    cur = conn.cursor()

    if search_term:
        query = """
        SELECT d.*, g.gas_name
        FROM gas_debts d
        JOIN gas_table g ON d.gas_id = g.gas_id
        WHERE LOWER(g.gas_name) LIKE %s OR LOWER(d.customer_name) LIKE %s
        ORDER BY d.id DESC
        """
        cur.execute(query, (f'%{search_term.lower()}%', f'%{search_term.lower()}%'))
    else:
        cur.execute("""
        SELECT d.*, g.gas_name
        FROM gas_debts d
        JOIN gas_table g ON d.gas_id = g.gas_id
        ORDER BY d.id DESC
        """)

    debts = cur.fetchall()

    # Get payment history for each debt
    debt_list = []
    for debt in debts:
        cur.execute("SELECT amount, payment_date FROM gas_debt_payments WHERE debt_id = %s ORDER BY payment_date", (debt['id'],))
        payments = cur.fetchall()
        debt_dict = dict(debt)
        debt_dict['payments'] = payments
        debt_dict['amount_paid'] = sum([float(p['amount']) for p in payments])
        debt_dict['balance'] = float(debt['amount_to_be_paid']) - debt_dict['amount_paid']
        debt_list.append(debt_dict)

    cur.close()
    conn.close()

    return render_template("search_gas_debt.html", debt_list=debt_list)
@app.route('/add-gas-debt', methods=['GET', 'POST'])
def add_gas_debt():
    from collections import defaultdict
    from decimal import Decimal

    gas_id = request.args.get('gas_id')

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()

    if request.method == 'GET':
        if not gas_id:
            flash("Gas ID is required.", "danger")
            cur.close()
            conn.close()
            return redirect(url_for('sales'))

        cur.execute("SELECT gas_name, filled_cylinders FROM gas_table WHERE gas_id = %s", (gas_id,))
        gas = cur.fetchone()

        if not gas:
            flash("Gas not found.", "warning")
            cur.close()
            conn.close()
            return redirect(url_for('sales'))

        if gas['filled_cylinders'] <= 0:
            flash("No filled gas cylinder available for this type.", "danger")
            cur.close()
            conn.close()
            return redirect(url_for('sales'))

    
        
    
    if request.method == 'POST':
            gas_id = request.form['gas_id']
            amount_paid = float(request.form.get('amount_paid', 0))

            amount_to_be_paid = float(request.form['amount_to_be_paid'])
            date_to_be_paid = request.form['date_to_be_paid']
            authorized_by = request.form['authorized_by']
            empty_given = 'empty_cylinder_given' in request.form
            customer_name = request.form['customer_name']
            customer_phone = request.form['customer_phone']
            customer_address = request.form['customer_address']
            customer_picture = request.files.get('customer_picture')
            image_data = customer_picture.read() if customer_picture else None

            cur.execute("""
            INSERT INTO gas_debts (
                gas_id, amount_paid, amount_to_be_paid, date_to_be_paid,
                authorized_by, empty_cylinder_given, customer_name,
                customer_phone, customer_address, customer_picture
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            gas_id, amount_paid, amount_to_be_paid, date_to_be_paid,
            authorized_by, empty_given, customer_name,
            customer_phone, customer_address, image_data
        ))


            # Update gas stock
            if empty_given:
                cur.execute("""
                    UPDATE gas_table
                    SET filled_cylinders = filled_cylinders - 1,
                        empty_cylinders = empty_cylinders + 1
                    WHERE gas_id = %s
                """, (gas_id,))
            else:
                cur.execute("""
                    UPDATE gas_table
                    SET filled_cylinders = filled_cylinders - 1
                    WHERE gas_id = %s
                """, (gas_id,))
                # Record gas going out in stock_out table
                cur.execute("""
                    INSERT INTO stock_out (
                    gas_id, cylinder_state, destination_type, destination_value
                    ) VALUES (%s, %s, %s, %s)
                   """, (
        gas_id, 'filled', 'customer', customer_name
    ))

            conn.commit()
            flash("Gas debt added successfully.", "success")
            return redirect(url_for('add_gas_debt', gas_id=gas_id))  # Redirect to GET after POST

        
            

    # Continue with GET rendering logic
   
     # GET logic
    search = request.args.get("search")
    query = """
        SELECT d.*, g.gas_name
        FROM gas_debts d
        JOIN gas_table g ON d.gas_id = g.gas_id
    """
    params = ()
    if search:
        query += " WHERE d.customer_name ILIKE %s OR g.gas_name ILIKE %s"
        params = (f"%{search}%", f"%{search}%")
    query += " ORDER BY d.time DESC"

    cur.execute(query, params)
    debt_list = cur.fetchall()

    # Fetch payments
    cur.execute("""
        SELECT debt_id, amount, payment_date
        FROM gas_debt_payments
        WHERE debt_id IN %s
        ORDER BY payment_date DESC
    """, (tuple(d['id'] for d in debt_list) if debt_list else (0,),))
    all_payments = cur.fetchall()

    # Group payments by debt_id
    from collections import defaultdict
    payments_by_debt = defaultdict(list)
    for p in all_payments:
        payments_by_debt[p['debt_id']].append(p)

    # Fetch related payments
    debt_ids = tuple(d['id'] for d in debt_list) or (0,)
    cur.execute("""
        SELECT debt_id, amount, payment_date
        FROM gas_debt_payments
        WHERE debt_id IN %s
        ORDER BY payment_date DESC
    """, (debt_ids,))
    all_payments = cur.fetchall()

    payments_by_debt = defaultdict(list)
    for p in all_payments:
        payments_by_debt[p['debt_id']].append(p)

    # Compute balance per debt
    for debt in debt_list:
        debt_payments = payments_by_debt.get(debt['id'], [])
        total_paid = sum(float(p['amount']) for p in debt_payments)
        balance = Decimal(str(debt['amount_to_be_paid'] or 0)) - Decimal(str(total_paid))

        debt['payments'] = debt_payments
        debt['amount_paid'] = total_paid
        debt['balance'] = balance

    gas_name = ''
    if gas_id:
        cur.execute("SELECT gas_name FROM gas_table WHERE gas_id = %s", (gas_id,))
        row = cur.fetchone()
        gas_name = row['gas_name'] if row else ''

    cur.close()
    conn.close()

    return render_template('add_gas_debt.html', gas_id=gas_id, gas_name=gas_name, debt_list=debt_list)


@app.route('/add-gas', methods=['GET', 'POST'])
def add_gas():
    conn = get_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        gas_name = request.form['gas_name'].strip()
        empty_cylinders = request.form['empty_cylinders']
        filled_cylinders = request.form['filled_cylinders']

        if not gas_name or empty_cylinders is None or filled_cylinders is None:
            flash("Please fill all fields.")
            return redirect(url_for('add_gas'))

        try:
            empty_cylinders = int(empty_cylinders)
            filled_cylinders = int(filled_cylinders)
        except ValueError:
            flash("Quantity fields must be numbers.")
            return redirect(url_for('add_gas'))

        # Insert into gas table (adjust table and column names)
        cur.execute("""
            INSERT INTO gas_table (gas_name, empty_cylinders, filled_cylinders)
            VALUES (%s, %s, %s)
        """, (gas_name, empty_cylinders, filled_cylinders))
        conn.commit()

        flash(f"Gas '{gas_name}' added successfully.")
        return redirect(url_for('add_gas'))

    # On GET, show all gases
    cur.execute("SELECT gas_id, gas_name, empty_cylinders, filled_cylinders FROM gas_table ORDER BY gas_id")
    gases = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('gas_form.html', gases=gases)

# --- SALES PAGE AND SUBMISSION ---
from collections import defaultdict
from flask import render_template

@app.route("/sales", methods=["GET"])
def sales():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Fetch all recent sales (latest 50) including source fields
                cur.execute("""
                    SELECT 
                        s.sale_id, 
                        g.gas_name, 
                        s.amount_paid_cash, 
                        s.amount_paid_till, 
                        s.time_sold::date AS sale_date, 
                        s.time_sold::time,
                        s.from_debt,
                        s.source_mama_pam,
                        s.source_external,
                        s.source_kipsongo_pioneer
                    FROM sales_table s
                    JOIN gas_table g ON s.gas_id = g.gas_id
                    ORDER BY s.time_sold DESC 
                    LIMIT 50;
                """)
                rows = cur.fetchall()

                grouped_sales_dict = defaultdict(list)
                for sale in rows:
                    (sale_id, gas_name, cash, till, sale_date, time_only,
                     from_debt, source_mama_pam, source_external, source_kipsongo_pioneer) = sale

                    grouped_sales_dict[sale_date].append({
                        "id": sale_id,
                        "gas": gas_name,
                        "cash": float(cash),
                        "till": float(till),
                        "time": time_only.strftime("%I:%M %p"),
                        "from_debt": from_debt,
                        "source_mama_pam": source_mama_pam,
                        "source_external": source_external,
                        "source_kipsongo_pioneer": source_kipsongo_pioneer
                    })

                # Final structure for rendering
                grouped_sales = []
                for raw_date, sales_list in grouped_sales_dict.items():
                    grouped_sales.append({
                        "date": raw_date,
                        "date_str": raw_date.strftime("%A, %d %B %Y"),
                        "sales": sales_list,
                        "total_gas": len(sales_list)
                    })

                grouped_sales.sort(key=lambda x: x["date"], reverse=True)

                # Fetch gas dropdown list
                cur.execute("""
                    SELECT gas_id, gas_name, empty_cylinders, filled_cylinders
                    FROM gas_table 
                    ORDER BY gas_id ASC;
                """)
                gases = cur.fetchall()

        return render_template("sales.html", gases=gases, grouped_sales=grouped_sales)

    except Exception as e:
        return f"Error loading sales form: {e}"

@app.route("/edit-sale/<int:sale_id>", methods=["GET", "POST"])
def edit_sale(sale_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if request.method == "POST":
                    cash = float(request.form["amount_paid_cash"])
                    till = float(request.form["amount_paid_till"])
                    # Only update payment amounts, not gas_id
                    cur.execute("""
                        UPDATE sales_table
                        SET amount_paid_cash = %s, amount_paid_till = %s
                        WHERE sale_id = %s;
                    """, (cash, till, sale_id))
                    conn.commit()
                    return redirect(url_for('sales'))

                # For GET: load the existing sale
                cur.execute("SELECT gas_id, amount_paid_cash, amount_paid_till FROM sales_table WHERE sale_id = %s;", (sale_id,))
                row = cur.fetchone()
                if not row:
                    return "Sale not found."

                sale = {
                    "gas_id": row[0],
                    "amount_paid_cash": row[1],
                    "amount_paid_till": row[2]
                }

                # Load all gas types to show the gas name (readonly)
                cur.execute("SELECT gas_id, gas_name FROM gas_table ORDER BY gas_name ASC")
                gases = cur.fetchall()

        return render_template("edit_sale.html", sale=sale, gases=gases)
    except Exception as e:
        return f"An error occurred: {str(e)}"

    except Exception as e:
        return f"Error editing sale: {e}"

@app.route('/submit-sale', methods=['POST'])
def submit_sale():
    try:
        gas_id = int(request.form["gas_id"])
        amount_paid_cash = float(request.form.get("amount_paid_cash", 0))
        amount_paid_till = float(request.form.get("amount_paid_till", 0))
        
        selected_source = request.form.get("source", "customer")
        source_kipsongo_pioneer = selected_source == "kipsongo_pioneer"
        source_mama_pam = selected_source == "mama_pam"
        source_external = selected_source == "external"

        sale_type = request.form.get("sale_type")

        complete_sale = sale_type == "complete_sale"
        empty_not_given = sale_type == "empty_not_given"
        exchange_cylinder = sale_type == "exchange_cylinder"

        time_sold = datetime.now()

        source_selected = selected_source in ["kipsongo_pioneer", "mama_pam", "external"]

        with get_connection() as conn:
            with conn.cursor() as cur:
                # Get current stock
                cur.execute("SELECT filled_cylinders, empty_cylinders FROM gas_table WHERE gas_id = %s", (gas_id,))
                row = cur.fetchone()

                if not row:
                    flash("Gas record not found.", "error")
                    return redirect("/sales")

                filled, empty = row

                # If no source is selected and filled cylinders are zero, prevent sale
                if filled == 0 and not source_selected:
                    flash("No filled  gas available in ukweli store confirm in other station.", "error")
                    return redirect("/sales")

                # Insert into sales_table
                cur.execute("""
                    INSERT INTO sales_table (
                        gas_id, amount_paid_cash, amount_paid_till,
                        source_kipsongo_pioneer, source_mama_pam, source_external,
                        complete_sale, empty_not_given, exchange_cylinder, time_sold
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    gas_id, amount_paid_cash, amount_paid_till,
                    source_kipsongo_pioneer, source_mama_pam, source_external,
                    complete_sale, empty_not_given, exchange_cylinder, time_sold
                ))

                # Always increase empty cylinders by 1
                cur.execute("""
                    UPDATE gas_table
                    SET empty_cylinders = empty_cylinders + 1
                    WHERE gas_id = %s
                """, (gas_id,))

                # If no source is selected, also decrease filled cylinders by 1
                if not source_selected:
                    cur.execute("""
                        UPDATE gas_table
                        SET filled_cylinders = filled_cylinders - 1
                        WHERE gas_id = %s
                    """, (gas_id,))

                # Update the specific source table
                if source_kipsongo_pioneer:
                    cur.execute("""
                        INSERT INTO kipsongo_gas_in_ukweli (gas_id, number_of_gas)
                        VALUES (%s, 1)
                        ON CONFLICT (gas_id) DO UPDATE
                        SET number_of_gas = kipsongo_gas_in_ukweli.number_of_gas + 1
                    """, (gas_id,))

                elif source_mama_pam:
                    cur.execute("""
                        INSERT INTO mama_pam_gas_in_ukweli (gas_id, number_of_gas)
                        VALUES (%s, 1)
                        ON CONFLICT (gas_id) DO UPDATE
                        SET number_of_gas = mama_pam_gas_in_ukweli.number_of_gas + 1
                    """, (gas_id,))

                elif source_external:
                    cur.execute("""
                        INSERT INTO external_gas_in_ukweli (gas_id, number_of_gas)
                        VALUES (%s, 1)
                        ON CONFLICT (gas_id) DO UPDATE
                        SET number_of_gas = external_gas_in_ukweli.number_of_gas + 1
                    """, (gas_id,))

                conn.commit()
                flash("Sale recorded successfully.", "success")

    except Exception as e:
        flash(f"Error processing sale: {str(e)}", "error")
    selected_gas_id = request.form.get("gas_id")  # This might be None on GET
    
    return redirect("/sales")
@app.route('/stock-out', methods=['GET', 'POST'])
def stock_out():
    conn = get_connection()
    cur = conn.cursor()

    # Get gases for dropdown
    cur.execute("SELECT gas_id, gas_name ,empty_cylinders, filled_cylinders FROM gas_table ORDER BY gas_name")
    gases = cur.fetchall()

    # Get users for delivery dropdown
    cur.execute("SELECT user_id, username FROM users ORDER BY username")
    users = cur.fetchall()

    message = None

    if request.method == 'POST':
        gas_id = request.form['gas_id']
        cylinder_state = request.form['cylinder_state']
        destination_type = request.form['destination_type']

        # Pick correct destination value
        if destination_type == "station":
            destination_value = request.form.get("destination_value_station")
        elif destination_type == "delivery":
            destination_value = request.form.get("destination_value_delivery")
        elif destination_type == "customer":
            destination_value = request.form.get("destination_value_customer")
        else:
            destination_value = None

        empty_not_given = request.form.get('empty_not_given')

        # Check availability in gas_table
        cur.execute("SELECT empty_cylinders, filled_cylinders FROM gas_table WHERE gas_id = %s", (gas_id,))
        stock = cur.fetchone()

        if not stock:
            message = "Gas not found."
        else:
            empty, filled = stock
            available = filled if cylinder_state == 'filled' else empty

            if available < 1:
                message = f"No {cylinder_state} cylinders available to send out."
            else:
                # Subtract from gas_table
                if cylinder_state == 'filled':
                    cur.execute("UPDATE gas_table SET filled_cylinders = filled_cylinders - 1 WHERE gas_id = %s", (gas_id,))
                else:
                    cur.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders - 1 WHERE gas_id = %s", (gas_id,))

                # Insert into stock_out table
                cur.execute("""
                    INSERT INTO stock_out (
                        gas_id, 
                        cylinder_state, 
                        destination_type, 
                        destination_value, 
                        time_out
                    ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (gas_id, cylinder_state, destination_type, destination_value))

                conn.commit()
                message = "Stock out entry saved successfully."

    # Fetch stock_out records with gas name and unified destination detail
    cur.execute("""
        SELECT
          so.id,
          g.gas_name,
          so.cylinder_state,
          so.destination_type,
          so.destination_value,
          so.time_out
        FROM stock_out so
        JOIN gas_table g ON so.gas_id = g.gas_id
        ORDER BY so.time_out DESC
    """)
    stock_out_records = cur.fetchall()

    stock_out_list = []
    for row in stock_out_records:
        destination_type = row[3]
        destination_value = row[4]
        goes_to = customer_name = delivery_username = None

        if destination_type == 'station':
            goes_to = destination_value
        elif destination_type == 'customer':
            customer_name = destination_value
        elif destination_type == 'delivery':
            cur.execute("SELECT username FROM users WHERE user_id = %s", (destination_value,))
            result = cur.fetchone()
            delivery_username = result[0] if result else 'Unknown'

        stock_out_list.append({
            'id': row[0],
            'gas_name': row[1],
            'cylinder_state': row[2],
            'goes_to': goes_to,
            'customer_name': customer_name,
            'delivery_username': delivery_username,
            'time': row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else ''
        })

    cur.close()
    conn.close()

    return render_template('stock_out.html',
                           gases=gases,
                           users=users,
                           stock_out_records=stock_out_list,
                           message=message)

@app.route('/add-stock-out', methods=['POST'])
def add_stock_out():
    gas_id = request.form.get('gas_id')
    cylinder_state = request.form.get('cylinder_state')
    destination_type = request.form.get('destination_type')
    empty_not_given = request.form.get('empty_not_given')  # This will be None if unchecked

    # Validate required inputs
    if not gas_id or not cylinder_state or not destination_type:
        flash("All fields are required.", "error")
        return redirect(url_for('stock_out'))

    # Get correct destination_value from form
    destination_value = None
    if destination_type == 'station':
        destination_value = request.form.get('destination_value_station')
    elif destination_type == 'delivery':
        destination_value = request.form.get('destination_value_delivery')
    elif destination_type == 'customer':
        destination_value = request.form.get('destination_value_customer')

    if not destination_value:
        flash("Destination value is required.", "error")
        return redirect(url_for('stock_out'))

    conn = get_connection()
    cur = conn.cursor()

    # Check gas availability
    cur.execute("SELECT empty_cylinders, filled_cylinders FROM gas_table WHERE gas_id = %s", (gas_id,))
    stock = cur.fetchone()
    if not stock:
        flash("Gas record not found.", "error")
        cur.close()
        conn.close()
        return redirect(url_for('stock_out'))

    empty_stock, filled_stock = stock

    if cylinder_state == 'empty' and empty_stock <= 0:
        flash("No empty cylinders available for this gas.", "error")
        cur.close()
        conn.close()
        return redirect(url_for('stock_out'))

    if cylinder_state == 'filled' and filled_stock <= 0:
        flash("No filled cylinders available for this gas.", "error")
        cur.close()
        conn.close()
        return redirect(url_for('stock_out'))

    # Insert into stock_out table
    cur.execute("""
        INSERT INTO stock_out (gas_id, cylinder_state, destination_type, destination_value)
        VALUES (%s, %s, %s, %s)
    """, (gas_id, cylinder_state, destination_type, destination_value))

    # Update stock in gas_table
    if empty_not_given and destination_type == 'customer':
        # Special condition: customer didn't return the empty cylinder
        if cylinder_state == 'empty':
            cur.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders - 1 WHERE gas_id = %s", (gas_id,))
        elif cylinder_state == 'filled':
            cur.execute("UPDATE gas_table SET filled_cylinders = filled_cylinders - 1 WHERE gas_id = %s", (gas_id,))
    else:
        # Default case
        if cylinder_state == 'empty':
            cur.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders - 1 WHERE gas_id = %s", (gas_id,))
        elif cylinder_state == 'filled':
            cur.execute("UPDATE gas_table SET filled_cylinders = filled_cylinders - 1 WHERE gas_id = %s", (gas_id,))

    conn.commit()
    cur.close()
    conn.close()

    flash("Stock out recorded successfully.", "success")
    return redirect(url_for('stock_out'))
@app.route('/return-stock/<int:stock_id>', methods=['POST'])
def return_stock(stock_id):
    returned_state = request.form.get('returned_cylinder_state')
    if returned_state not in ['empty', 'filled']:
        flash('Invalid returned cylinder state.', 'error')
        return redirect(url_for('stock_out'))

    conn = get_connection()
    cur = conn.cursor()

    # ✅ Get stock out record by stock_id
    cur.execute("""
        SELECT id, gas_id, cylinder_state, destination_type, destination_value, time_out
        FROM stock_out
        WHERE id = %s
    """, (stock_id,))
    
    record = cur.fetchone()
    if not record:
        flash('Record not found.', 'error')
        cur.close()
        conn.close()
        return redirect(url_for('stock_out'))

    # ✅ Unpack stock_out record
    _, gas_id, original_state, destination_type, destination_value, _ = record
    display_name = destination_value  # Default note value

    # ✅ If destination is delivery, fetch delivery username
    if destination_type == 'delivery':
        cur.execute("SELECT username FROM users WHERE user_id = %s", (destination_value,))
    result = cur.fetchone()
    if result:
        display_name = result[0]  # Use name instead of ID
    else:
        display_name = f"Unknown delivery (ID: {destination_value})"


    # ✅ If it's a delivery return (from filled → empty), redirect to payment
    if destination_type == 'delivery' and original_state == 'filled' and returned_state == 'empty':
        session['delivery_return_info'] = {
            'gas_id': gas_id,
            'stock_id': stock_id,
            'delivery_id': destination_value  # Still needed for later use
        }
        cur.close()
        conn.close()
        return redirect(url_for('record_delivery_sale'))

    # ✅ Log return in stock_change
    cur.execute("""
        INSERT INTO stock_change (gas_id, action, quantity_change, notes)
        VALUES (%s, %s, %s, %s)
    """, (
        gas_id,
        f"return_{returned_state}",
        1,
        f"Returned from {destination_type}: {display_name}"
    ))

    # ✅ Delete stock_out record
    cur.execute("DELETE FROM stock_out WHERE id = %s", (stock_id,))

    # ✅ Update cylinder count
    if returned_state == 'empty':
        cur.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders + 1 WHERE gas_id = %s", (gas_id,))
    else:
        cur.execute("UPDATE gas_table SET filled_cylinders = filled_cylinders + 1 WHERE gas_id = %s", (gas_id,))

    conn.commit()
    cur.close()
    conn.close()

    flash("Gas returned successfully!", "success")
    return redirect(url_for('stock_out'))

@app.route("/delete-sale/<int:sale_id>")
def delete_sale(sale_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Fetch the sale record
                cur.execute("""
                    SELECT gas_id, source_kipsongo_pioneer, source_mama_pam, source_external
                    FROM sales_table WHERE sale_id = %s
                """, (sale_id,))
                sale = cur.fetchone()

                if not sale:
                    return "Sale not found.", 404

                gas_id, is_kipsongo, is_mama_pam, is_external = sale

                # Undo the gas count updates
                if is_kipsongo:
                    # Subtract 1 from kipsongo_sales
                    cur.execute("UPDATE kipsongo_gas_in_ukweli SET number_of_gas = number_of_gas - 1 WHERE gas_id = %s", (gas_id,))
                    cur.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders - 1 WHERE gas_id = %s", (gas_id,))
                elif is_mama_pam:
                    cur.execute("UPDATE mama_pam_gas_in_ukweli SET number_of_gas = number_of_gas - 1 WHERE gas_id = %s", (gas_id,))
                    cur.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders - 1 WHERE gas_id = %s", (gas_id,))
                elif is_external:
                    cur.execute("UPDATE external_gas_in_ukweli SET number_of_gas = number_of_gas - 1 WHERE gas_id = %s", (gas_id,))
                    cur.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders - 1 WHERE gas_id = %s", (gas_id,))
                else:
                    # No source selected: reverse both empty and filled
                    cur.execute("""
                        UPDATE gas_table 
                        SET empty_cylinders = empty_cylinders - 1,
                            filled_cylinders = filled_cylinders + 1
                        WHERE gas_id = %s
                    """, (gas_id,))

                # Delete the sale record
                cur.execute("DELETE FROM sales_table WHERE sale_id = %s", (sale_id,))
                conn.commit()

        flash("Sale deleted .", "success")
        return redirect(url_for('sales'))

    except Exception as e:
        return f"Error deleting sale: {e}"

@app.route('/record-delivery-sale', methods=['GET', 'POST'])
def record_delivery_sale():
    info = session.get('delivery_return_info')
    if not info:
        flash("No delivery return info found in session.", "error")
        return redirect(url_for('stock_out'))

    if request.method == 'POST':
        amount_cash = request.form.get('amount_paid_cash')
        amount_till = request.form.get('amount_paid_till')

        try:
            amount_cash = float(amount_cash) if amount_cash else 0
            amount_till = float(amount_till) if amount_till else 0
        except ValueError:
            flash("Enter valid numeric values for payment.", "error")
            return redirect(url_for('record_delivery_sale'))

        gas_id = info['gas_id']
        stock_id = info['stock_id']
        delivery_id = info['delivery_id']

        conn = get_connection()
        cur = conn.cursor()

        # ✅ Insert into sales_table
        cur.execute("""
            INSERT INTO sales_table (
                gas_id, amount_paid_cash, amount_paid_till,
                source_external, complete_sale
            ) VALUES (%s, %s, %s, TRUE, TRUE)
        """, (gas_id, amount_cash, amount_till))

        # ✅ Record in stock_change (return from delivery)
        cur.execute("""
            INSERT INTO stock_change (gas_id, action, quantity_change, notes)
            VALUES (%s, %s, %s, %s)
        """, (gas_id, "return_empty", 1, f"Returned from delivery ID: {delivery_id}"))

        # ✅ Delete from stock_out
        cur.execute("DELETE FROM stock_out WHERE id = %s", (stock_id,))

        # ✅ Increase empty_cylinders
        cur.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders + 1 WHERE gas_id = %s", (gas_id,))

        conn.commit()
        cur.close()
        conn.close()

        session.pop('delivery_return_info', None)  # ✅ Clear session after done
        flash("Delivery return and sale recorded successfully.", "success")
        return redirect(url_for('stock_out'))

    # If GET request, show form
    return render_template("record_delivery_sale.html")



# --- GAS SOURCE HANDLER ---
def handle_gas_source(source_name, session_key, table_name, template_name):
    conn = get_connection()
    cur = conn.cursor()

    # Fetch source-specific gas data to navigate through
    cur.execute(f"""
        SELECT t.gas_id, g.gas_name, t.number_of_gas
        FROM {table_name} t
        JOIN gas_table g ON t.gas_id = g.gas_id
        ORDER BY t.gas_id
    """)
    source_gas = cur.fetchall()

    # Debugging Output
    print(f"[DEBUG] Source Gas Data: {source_gas}")

    # Check if source_gas is empty
    if not source_gas:
        print("[DEBUG] No gases found in source table.")
        current_gas = (None, "No Gas Available", 0)
    else:
        # Set index if not already set in session
        if session_key not in session:
            session[session_key] = 0

        current_index = session[session_key]
        current_gas = source_gas[current_index]

    if request.method == 'POST':
        action = request.form.get('action')
        nav = request.form.get('nav')
        quantity = request.form.get('quantity')

        # Ensure quantity is a positive integer
        try:
            quantity = int(quantity) if quantity else 1
        except ValueError:
            quantity = 1 

        print(f"[DEBUG] Action received: {action}, Nav: {nav}, Quantity: {quantity}")

        # Navigation logic based on source table records
        if nav == 'next':
            session[session_key] = (current_index + 1) % len(source_gas) if source_gas else 0
        elif nav == 'prev':
            session[session_key] = (current_index - 1) % len(source_gas) if source_gas else 0

        # Add +1 logic - Only increase quantity by 1 for the selected gas
        elif action == 'add_1':
            gas_id = current_gas[0] if current_gas[0] else None

            if gas_id:
                try:
                    cur.execute(f"""
                        UPDATE {table_name}
                        SET number_of_gas = number_of_gas + 1
                        WHERE gas_id = %s
                    """, (gas_id,))
                    conn.commit()  # Commit the update
                    flash(f"1 unit added to {source_name} successfully.")
                except Exception as e:
                    flash(f"Error adding gas to {source_name}: {e}")
                    print(f"[DEBUG] Error adding gas: {e}")

        # Add logic - Insert or update the source table
        elif action == 'add':
            gas_id = request.form.get('gas_id')

            if gas_id:
                try:
                    cur.execute(f"""
                        INSERT INTO {table_name} (gas_id, number_of_gas)
                        VALUES (%s, %s)
                        ON CONFLICT (gas_id) DO UPDATE
                        SET number_of_gas = {table_name}.number_of_gas + %s
                    """, (gas_id, quantity, quantity))
                    conn.commit()  # Commit the insert/update
                    flash(f"{quantity} units added to {source_name} successfully.")
                except Exception as e:
                    flash(f"Error adding gas to {source_name}: {e}")
                    print(f"[DEBUG] Error adding gas: {e}")

        # Fetch the updated source-specific gas data (after commit)
        cur.execute(f"""
            SELECT t.gas_id, g.gas_name, t.number_of_gas
            FROM {table_name} t
            JOIN gas_table g ON t.gas_id = g.gas_id
            ORDER BY t.gas_id
        """)
        source_gas = cur.fetchall()

        # Debugging Output for updated data
        print(f"[DEBUG] Updated Source Gas Data: {source_gas}")

    cur.close()
    conn.close()

    # Render the template with updated data
    return render_template(template_name, 
                           source_gas=source_gas, 
                           current_gas=current_gas)

# --- ROUTES ---
@app.route('/external-u', methods=['GET', 'POST'])
def external_u():
    return handle_gas_source(
        source_name="External Gas",
        session_key="external_index",
        table_name="external_gas_in_ukweli",
        template_name="external-u.html"
    )

@app.route('/mpam-gas-u', methods=['GET', 'POST'])
def mpam_gas_u():
    return handle_gas_source(
        source_name="Mama Pam Gas",
        session_key="mpam_index",
        table_name="mama_pam_gas_in_ukweli",
        template_name="mpam-gas-u.html"
    )

@app.route('/kipsongo-gas-u', methods=['GET', 'POST'])
def kipsongo_gas_u():
    conn = get_connection()
    cur = conn.cursor()

    # Fetch gases for dropdown
    cur.execute("SELECT gas_id, gas_name FROM gas_table;")
    gases = cur.fetchall()

    # Fetch source-specific gas data to navigate through
    cur.execute("""
        SELECT g.gas_id, g.gas_name, k.number_of_gas 
        FROM kipsongo_gas_in_ukweli k
        LEFT JOIN gas_table g ON k.gas_id = g.gas_id
        ORDER BY g.gas_id
    """)
    source_gas = cur.fetchall()

    # Debugging Output
    print(f"[DEBUG] Gases fetched: {gases}")
    print(f"[DEBUG] Source Gas Data: {source_gas}")

    # Check if source_gas is empty
    if not source_gas:
        print("[DEBUG] No gases found in source table.")
        current_gas = (None, "No Gas Available", 0)
    else:
        # Set index if not already set in session
        if "kipsongo_index" not in session:
            session["kipsongo_index"] = 0

        current_index = session["kipsongo_index"]
        current_gas = source_gas[current_index]

    cur.close()
    conn.close()

    # Render the template with required data
    return render_template("kipsongo-gas-u.html", 
                           gases=gases, 
                           source_gas=source_gas, 
                           current_gas=current_gas)


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect('/')

@app.route('/delete-kipsongo-gas/<int:id>', methods=['POST'])
def delete_kipsongo_gas(id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM kipsongo_gas_in_ukweli WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('add_kipsongo_gas'))

# --- EXTRA PAGES ---

@app.route("/refill")
def refill():
    return render_template('refill.html')
@app.route("/gas-form")
def gasform():
    conn = get_connection()          # Call the function to get connection
    cur = conn.cursor()              # Use cur or cursor consistently
    cur.execute("SELECT gas_id, gas_name, empty_cylinders, filled_cylinders FROM gas_table ORDER BY gas_id")
    gases = cur.fetchall()
    cur.close()
    conn.close()

    # Assuming you want to render a template 'gas_form.html' with gases data
    return render_template('gas_form.html', gases=gases)

@app.route("/debug-gases")
def debug_gases():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM gas_table;")
                gases = cur.fetchall()
        return f"Gas table: {gases}"
    except Exception as e:
        return f"Error fetching gas table: {e}"

# --- MAIN APP ---

if __name__ == '__main__':
    app.run(debug=True)