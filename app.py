from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import datetime
from collections import defaultdict
from decimal import Decimal
import os
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATABASE = os.path.join(os.path.dirname(__file__), 'gas.db')

# ─────────────────────────────────────────────
#  DB Connection (SQLite)
# ─────────────────────────────────────────────
def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row   # allows dict-style access: row['col']
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ─────────────────────────────────────────────
#  Admin-only decorator
# ─────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admins only ❌", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapped

# ─────────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"].lower()
    password = request.form["password"]
    try:
        with get_connection() as conn:
            cur = conn.execute(
                "SELECT user_id, username, password, role FROM users WHERE LOWER(username) = ?",
                (username,)
            )
            user = cur.fetchone()
        if user and password == user["password"]:
            session["user_id"]  = user["user_id"]
            session["username"] = user["username"]
            session["role"]     = user["role"] or "user"
            flash("Login successful ✅", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("❌ Incorrect username or password", "error")
    except Exception as e:
        flash(f"Database error: {e}", "error")
    return redirect(url_for("home"))


@app.post("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("home"))
    return render_template("dashboard.html", username=session["username"], role=session.get("role", "user"))


# ─────────────────────────────────────────────
#  Account
# ─────────────────────────────────────────────
@app.route("/account")
def my_account():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("home"))
    with get_connection() as conn:
        row = conn.execute("SELECT username FROM users WHERE username=?", (session["username"],)).fetchone()
    if not row:
        flash("User not found.", "error")
        return redirect(url_for("dashboard"))
    return render_template("account.html", username=row["username"])


@app.post("/update-account")
def update_account():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("home"))
    current_user = session["username"]
    new_user     = request.form.get("new_username", "").strip().lower()
    new_pass     = request.form.get("new_password_1", "")
    confirm_pass = request.form.get("new_password_2", "")
    if new_pass or new_user:
        if new_pass and new_pass != confirm_pass:
            flash("Passwords do not match.", "error")
            return redirect(url_for("my_account"))
        try:
            with get_connection() as conn:
                if new_user and new_user != current_user:
                    conn.execute("UPDATE users SET username=? WHERE username=?", (new_user, current_user))
                    session["username"] = new_user
                    current_user = new_user
                if new_pass:
                    conn.execute("UPDATE users SET password=? WHERE username=?", (new_pass, current_user))
                conn.commit()
                flash("Account updated ✔️", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
    else:
        flash("Nothing to update.", "info")
    return redirect(url_for("my_account"))


# ─────────────────────────────────────────────
#  Manage Pricing
# ─────────────────────────────────────────────
@app.route('/manage-pricing')
@admin_required
def manage_pricing():
    with get_connection() as conn:
        companies = [dict(r) for r in conn.execute(
            "SELECT company_id, company_name FROM buying_company ORDER BY company_name"
        ).fetchall()]
        gases = [dict(r) for r in conn.execute(
            "SELECT gas_id, gas_name FROM gas_table ORDER BY gas_name"
        ).fetchall()]
        prices = [dict(r) for r in conn.execute("""
            SELECT c.company_name, g.gas_name,
                   COALESCE(p.refill_price,0) AS refill_price,
                   COALESCE(p.full_price,0)   AS full_price,
                   p.last_updated
            FROM company_gas_price p
            JOIN buying_company c ON p.company_id = c.company_id
            JOIN gas_table      g ON p.gas_id     = g.gas_id
            ORDER BY c.company_name, g.gas_name
        """).fetchall()]
    return render_template("manage_pricing.html", companies=companies, gases=gases, prices=prices)


@app.route('/add-supplier', methods=['POST'])
def add_supplier():
    name = request.form['company_name'].strip()
    try:
        with get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO buying_company (company_name) VALUES (?)", (name,))
            row = conn.execute("SELECT company_id FROM buying_company WHERE company_name=?", (name,)).fetchone()
            if row:
                conn.execute("""
                    INSERT OR IGNORE INTO company_gas_price (company_id, gas_id)
                    SELECT ?, gas_id FROM gas_table
                """, (row["company_id"],))
            conn.commit()
            flash("Supplier added.", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for('manage_pricing'))


@app.route('/set-price', methods=['POST'])
def set_price():
    comp_id = int(request.form['company_id'])
    gid_raw = request.form['gas_id']
    refill  = float(request.form['refill_price'] or 0)
    full    = float(request.form['full_price'] or 0)
    with get_connection() as conn:
        if gid_raw == "all_below":
            gas_ids = [r[0] for r in conn.execute(
                "SELECT gas_id FROM gas_table WHERE gas_name NOT LIKE '%13%'"
            ).fetchall()]
        elif gid_raw == "all_above":
            gas_ids = [r[0] for r in conn.execute(
                "SELECT gas_id FROM gas_table WHERE gas_name LIKE '%13%'"
            ).fetchall()]
        else:
            gas_ids = [int(gid_raw)]
        for gid in gas_ids:
            conn.execute("""
                INSERT INTO company_gas_price (company_id, gas_id, refill_price, full_price, last_updated)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(company_id, gas_id) DO UPDATE
                SET refill_price=excluded.refill_price,
                    full_price=excluded.full_price,
                    last_updated=excluded.last_updated
            """, (comp_id, gid, refill, full))
        conn.commit()
    flash("Price saved.", "success")
    return redirect(url_for('manage_pricing'))


# ─────────────────────────────────────────────
#  Prepaid
# ─────────────────────────────────────────────
@app.route('/prepaid-form')
def Prepaidform():
    gas_id = request.args.get("gas_id", type=int)
    with get_connection() as conn:
        gases = conn.execute("SELECT gas_id, gas_name FROM gas_table").fetchall()
    return render_template("Prepaidform.html", gases=gases, selected_gas_id=gas_id)


@app.route("/prepaid-list")
def prepaid_list():
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT ps.id, ps.customer_name, ps.empty_given, ps.customer_picture, g.gas_name
                FROM prepaid_sales ps
                JOIN gas_table g ON ps.gas_id = g.gas_id
                ORDER BY ps.created_at DESC
            """).fetchall()
        pending_prepaid = [dict(r) for r in rows]
        return render_template("Prepaidlist.html", pending_prepaid=pending_prepaid)
    except Exception as e:
        return f"Error loading prepaid list: {e}"


@app.route('/record-sale-and-open-prepay', methods=['POST'])
def record_sale_and_open_prepay():
    gas_id = request.args.get("gas_id", type=int)
    cash   = float(request.form.get("amount_paid_cash", 0))
    till   = float(request.form.get("amount_paid_till", 0))
    source = request.form.get("source", "customer")
    src_k  = source == "kipsongo_pioneer"
    src_m  = source == "mama_pam"
    src_e  = source == "external"
    st     = request.form.get("sale_type")
    complete = st == "complete_sale"
    empty_ng = st == "empty_not_given"
    exch_cyl = st == "exchange_cylinder"
    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO sales_table (
                    gas_id, amount_paid_cash, amount_paid_till,
                    source_kipsongo_pioneer, source_mama_pam, source_external,
                    complete_sale, empty_not_given, exchange_cylinder, time_sold
                ) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (gas_id, cash, till, src_k, src_m, src_e, complete, empty_ng, exch_cyl))
            conn.commit()
        return redirect(url_for('Prepaidform', gas_id=gas_id))
    except Exception as e:
        return f"Error: {e}", 500


@app.route('/submit-prepaid-sale', methods=['POST'])
def submit_prepaid_sale():
    customer_name    = request.form.get('customer_name')
    customer_phone   = request.form.get('customer_phone')
    customer_address = request.form.get('customer_address')
    gas_id           = request.form.get('gas_id')
    empty_given      = 'empty_given' in request.form
    picture_file     = request.files.get('customer_picture')
    picture_path = ''
    if picture_file and picture_file.filename:
        filename     = secure_filename(picture_file.filename)
        picture_path = os.path.join('static/uploads', filename)
        picture_file.save(picture_path)
    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO prepaid_sales (gas_id, customer_name, customer_phone,
                    customer_address, empty_given, customer_picture)
                VALUES (?,?,?,?,?,?)
            """, (gas_id, customer_name, customer_phone, customer_address, empty_given, picture_path))
            if empty_given:
                conn.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders + 1 WHERE gas_id=?", (gas_id,))
            conn.commit()
        flash('Prepaid sale recorded successfully', 'success')
    except Exception as e:
        flash(f"Error saving prepaid record: {e}", 'error')
    return redirect(url_for('sales'))


@app.route("/collect-prepaid/<int:prepaid_id>", methods=["POST"])
def collect_prepaid(prepaid_id):
    try:
        with get_connection() as conn:
            record = conn.execute(
                "SELECT gas_id, empty_given, customer_name FROM prepaid_sales WHERE id=?", (prepaid_id,)
            ).fetchone()
            if not record:
                flash("❌ Prepaid record not found", "error")
                return redirect(url_for('prepaid_list'))
            gas_id, empty_given, customer_name = record["gas_id"], record["empty_given"], record["customer_name"]
            gas_status = conn.execute("SELECT filled_cylinders FROM gas_table WHERE gas_id=?", (gas_id,)).fetchone()
            if not gas_status or gas_status["filled_cylinders"] <= 0:
                flash("❌ No filled gas cylinders available!", "error")
                return redirect(url_for('prepaid_list'))
            conn.execute("UPDATE gas_table SET filled_cylinders = filled_cylinders - 1 WHERE gas_id=?", (gas_id,))
            conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                         (gas_id, 'decrease_filled', -1, 'Collected prepaid sale'))
            checkbox_checked = request.form.get("empty_given", "").lower() in ["true", "on", "1"]
            if not empty_given:
                if checkbox_checked:
                    conn.execute("UPDATE gas_table SET empty_cylinders = empty_cylinders + 1 WHERE gas_id=?", (gas_id,))
                    conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                                 (gas_id, 'increase_empty', 1, 'Empty received at collection'))
                else:
                    conn.execute("INSERT INTO stock_out (gas_id, cylinder_state, destination_type, destination_value) VALUES (?,?,?,?)",
                                 (gas_id, 'filled', 'customer', customer_name))
                    conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                                 (gas_id, 'stock_out', -1, f"Prepaid collection without empty by {customer_name}"))
            conn.execute("DELETE FROM prepaid_sales WHERE id=?", (prepaid_id,))
            conn.commit()
            flash("✅ Collection completed successfully.", "success")
    except Exception as e:
        flash(f"❌ Error during collection: {e}", "error")
    return redirect(url_for('prepaid_list'))


# ─────────────────────────────────────────────
#  Logs
# ─────────────────────────────────────────────
@app.route('/logs')
def view_logs():
    try:
        with get_connection() as conn:
            logs = conn.execute("""
                SELECT sc.id, g.gas_name, sc.action, sc.quantity_change, sc.notes, sc.changed_at
                FROM stock_change sc
                JOIN gas_table g ON sc.gas_id = g.gas_id
                ORDER BY sc.changed_at DESC
            """).fetchall()
        return render_template("logs.html", logs=logs)
    except Exception as e:
        return f"Error fetching logs: {e}"


# ─────────────────────────────────────────────
#  Gas Debts & Payments
# ─────────────────────────────────────────────
@app.post('/undo-payment/<int:debt_id>')
def undo_payment(debt_id):
    try:
        with get_connection() as conn:
            last = conn.execute("""
                SELECT id, amount FROM gas_debt_payments
                WHERE debt_id=? ORDER BY payment_date DESC, id DESC LIMIT 1
            """, (debt_id,)).fetchone()
            if not last:
                flash("No payment found to undo.", "warning")
                return redirect(url_for('add_gas_debt'))
            conn.execute("DELETE FROM gas_debt_payments WHERE id=?", (last["id"],))
            conn.execute("UPDATE gas_debts SET amount_paid = amount_paid - ? WHERE id=?",
                         (last["amount"], debt_id))
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
            conn.execute("INSERT INTO gas_debt_payments (debt_id, amount, payment_date) VALUES (?,?,datetime('now'))",
                         (debt_id, amount))
            conn.execute("UPDATE gas_debts SET amount_paid = amount_paid + ? WHERE id=?", (amount, debt_id))
            debt = conn.execute(
                "SELECT gas_id, amount_paid, amount_to_be_paid, cleared FROM gas_debts WHERE id=?", (debt_id,)
            ).fetchone()
            if not debt:
                raise Exception("Debt record not found.")
            balance = float(debt["amount_to_be_paid"]) - float(debt["amount_paid"])
            if balance <= 0 and not debt["cleared"]:
                conn.execute("""
                    INSERT INTO sales_table (gas_id, sale_date, amount_paid_cash, amount_paid_till,
                        complete_sale, source_kipsongo_pioneer, source_mama_pam, source_external,
                        empty_not_given, exchange_cylinder, from_debt)
                    VALUES (?,datetime('now'),?,0,0,0,0,0,0,0,1)
                """, (debt["gas_id"], float(debt["amount_to_be_paid"])))
                conn.execute("UPDATE gas_debts SET cleared=1 WHERE id=?", (debt_id,))
            conn.commit()
        flash("Payment added successfully!", "success")
    except Exception as e:
        flash(f"Error processing payment: {e}", "error")
    return redirect(url_for('add_gas_debt'))


@app.route('/gas-debt', methods=['GET'])
def search_gas_debt():
    search_term = request.args.get('search', '').strip()
    with get_connection() as conn:
        if search_term:
            debts = conn.execute("""
                SELECT d.*, g.gas_name FROM gas_debts d
                JOIN gas_table g ON d.gas_id = g.gas_id
                WHERE LOWER(g.gas_name) LIKE ? OR LOWER(d.customer_name) LIKE ?
                ORDER BY d.id DESC
            """, (f'%{search_term.lower()}%', f'%{search_term.lower()}%')).fetchall()
        else:
            debts = conn.execute("""
                SELECT d.*, g.gas_name FROM gas_debts d
                JOIN gas_table g ON d.gas_id = g.gas_id ORDER BY d.id DESC
            """).fetchall()
        debt_list = []
        for debt in debts:
            payments = conn.execute(
                "SELECT amount, payment_date FROM gas_debt_payments WHERE debt_id=? ORDER BY payment_date",
                (debt["id"],)
            ).fetchall()
            d = dict(debt)
            d['payments']    = [dict(p) for p in payments]
            d['amount_paid'] = sum(float(p["amount"]) for p in payments)
            d['balance']     = float(debt["amount_to_be_paid"]) - d['amount_paid']
            debt_list.append(d)
    return render_template("search_gas_debt.html", debt_list=debt_list)


@app.route('/add-gas-debt', methods=['GET', 'POST'])
def add_gas_debt():
    gas_id = request.args.get('gas_id')
    with get_connection() as conn:
        if request.method == 'GET':
            if not gas_id:
                flash("Gas name must be selected.", "danger")
                return redirect(url_for('sales'))
            gas = conn.execute(
                "SELECT gas_name, filled_cylinders FROM gas_table WHERE gas_id=?", (gas_id,)
            ).fetchone()
            if not gas:
                flash("Gas not found.", "warning")
                return redirect(url_for('sales'))
            if gas["filled_cylinders"] <= 0:
                flash("No filled gas cylinder available for this type.", "danger")
                return redirect(url_for('sales'))

        if request.method == 'POST':
            gas_id           = request.form['gas_id']
            amount_paid      = float(request.form.get('amount_paid', 0))
            amount_to_be_paid= float(request.form['amount_to_be_paid'])
            date_to_be_paid  = request.form['date_to_be_paid']
            authorized_by    = request.form['authorized_by']
            empty_given      = 'empty_cylinder_given' in request.form
            customer_name    = request.form['customer_name']
            customer_phone   = request.form['customer_phone']
            customer_address = request.form['customer_address']
            conn.execute("""
                INSERT INTO gas_debts (gas_id, amount_paid, amount_to_be_paid, date_to_be_paid,
                    authorized_by, empty_cylinder_given, customer_name,
                    customer_phone, customer_address)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (gas_id, amount_paid, amount_to_be_paid, date_to_be_paid,
                  authorized_by, empty_given, customer_name, customer_phone, customer_address))
            if empty_given:
                conn.execute("UPDATE gas_table SET filled_cylinders=filled_cylinders-1, empty_cylinders=empty_cylinders+1 WHERE gas_id=?", (gas_id,))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (gas_id, 'filled decrease while empty increase', 0, f"Gas collection without payment by '{customer_name}'"))
            else:
                conn.execute("UPDATE gas_table SET filled_cylinders=filled_cylinders-1 WHERE gas_id=?", (gas_id,))
                conn.execute("INSERT INTO stock_out (gas_id, cylinder_state, destination_type, destination_value) VALUES (?,?,?,?)",
                             (gas_id, 'filled', 'customer', customer_name))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (gas_id, 'filled decrease', -1, f"Gas collection without payment, no empty returned by '{customer_name}'"))
            conn.commit()
            flash("Gas debt added successfully.", "success")
            return redirect(url_for('add_gas_debt', gas_id=gas_id))

        # GET: list debts
        search = request.args.get("search")
        if search:
            debt_list = conn.execute("""
                SELECT d.*, g.gas_name FROM gas_debts d
                JOIN gas_table g ON d.gas_id = g.gas_id
                WHERE d.customer_name LIKE ? OR g.gas_name LIKE ?
                ORDER BY d.time DESC
            """, (f"%{search}%", f"%{search}%")).fetchall()
        else:
            debt_list = conn.execute("""
                SELECT d.*, g.gas_name FROM gas_debts d
                JOIN gas_table g ON d.gas_id = g.gas_id ORDER BY d.time DESC
            """).fetchall()

        debt_ids = tuple(d["id"] for d in debt_list) or (0,)
        placeholders = ",".join("?" * len(debt_ids))
        all_payments = conn.execute(f"""
            SELECT debt_id, amount, payment_date FROM gas_debt_payments
            WHERE debt_id IN ({placeholders}) ORDER BY payment_date DESC
        """, debt_ids).fetchall()

        payments_by_debt = defaultdict(list)
        for p in all_payments:
            payments_by_debt[p["debt_id"]].append(dict(p))

        final_debts = []
        for debt in debt_list:
            d = dict(debt)
            debt_payments = payments_by_debt.get(d["id"], [])
            total_paid = sum(float(p["amount"]) for p in debt_payments)
            d['payments']    = debt_payments
            d['amount_paid'] = total_paid
            d['balance']     = Decimal(str(d.get('amount_to_be_paid') or 0)) - Decimal(str(total_paid))
            final_debts.append(d)

        gas_name = ''
        if gas_id:
            row = conn.execute("SELECT gas_name FROM gas_table WHERE gas_id=?", (gas_id,)).fetchone()
            gas_name = row["gas_name"] if row else ''

    return render_template('add_gas_debt.html', gas_id=gas_id, gas_name=gas_name, debt_list=final_debts)


@app.post("/delete-gas-debt/<int:debt_id>")
def delete_gas_debt(debt_id):
    with get_connection() as conn:
        debt = conn.execute("SELECT amount_paid, amount_to_be_paid FROM gas_debts WHERE id=?", (debt_id,)).fetchone()
        if not debt:
            flash("Debt record not found.")
        else:
            balance = (debt["amount_to_be_paid"] or 0) - (debt["amount_paid"] or 0)
            if balance > 0:
                flash("Cannot delete. Customer still has a balance.")
            else:
                conn.execute("DELETE FROM gas_debts WHERE id=?", (debt_id,))
                conn.commit()
                flash("Debt record deleted successfully.")
    return render_template("dashboard.html")


# ─────────────────────────────────────────────
#  Empty Cylinders
# ─────────────────────────────────────────────
@app.route("/empty-cylinders")
def empty_cylinders_page():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT gas_id, gas_name, empty_cylinders FROM gas_table
            WHERE empty_cylinders > 0 ORDER BY gas_name
        """).fetchall()
    total_13    = sum(r["empty_cylinders"] for r in rows if "13kg" in r["gas_name"].lower())
    total_other = sum(r["empty_cylinders"] for r in rows if "13kg" not in r["gas_name"].lower())
    return render_template("empty_cylinders.html",
                           brands=rows, total_13=total_13,
                           total_other=total_other, grand_total=total_13 + total_other)


# ─────────────────────────────────────────────
#  Manage Users
# ─────────────────────────────────────────────
@app.route("/manage-users")
def manage_users():
    with get_connection() as conn:
        users = conn.execute("SELECT user_id, username, role FROM users ORDER BY user_id").fetchall()
    return render_template("manage_users.html", users=users)


@app.post("/add-user")
def add_user():
    uname = request.form["username"].strip()
    pwd   = request.form["password"]
    role  = request.form.get("role", "user")
    if not uname or not pwd:
        flash("Username and password required.", "error")
        return redirect(url_for("manage_users"))
    try:
        with get_connection() as conn:
            conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (uname, pwd, role))
            conn.commit()
            flash("User added ✔️", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("manage_users"))


@app.post("/update-user/<int:uid>")
def update_user(uid):
    uname = request.form["username"].strip()
    pwd   = request.form["password"].strip()
    role  = request.form.get("role", "user")
    try:
        with get_connection() as conn:
            if pwd:
                conn.execute("UPDATE users SET username=?, password=?, role=? WHERE user_id=?", (uname, pwd, role, uid))
            else:
                conn.execute("UPDATE users SET username=?, role=? WHERE user_id=?", (uname, role, uid))
            conn.commit()
            flash("User updated ✔️", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("manage_users"))


@app.post("/delete-user/<int:uid>")
def delete_user(uid):
    try:
        with get_connection() as conn:
            conn.execute("DELETE FROM users WHERE user_id=?", (uid,))
            conn.commit()
            flash("User deleted.", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("manage_users"))


# ─────────────────────────────────────────────
#  Stock In
# ─────────────────────────────────────────────
@app.route("/stock-in")
def stock_in_page():
    with get_connection() as conn:
        gases = conn.execute("SELECT gas_id, gas_name FROM gas_table ORDER BY gas_name").fetchall()
        grouped = conn.execute("""
            SELECT g.gas_id, g.gas_name, si.cylinder_state, si.source_type, si.source_value, COUNT(*) AS qty
            FROM stock_in si JOIN gas_table g ON g.gas_id = si.gas_id
            GROUP BY g.gas_id, g.gas_name, si.cylinder_state, si.source_type, si.source_value
            ORDER BY g.gas_name, si.cylinder_state, si.source_type, si.source_value
        """).fetchall()
    return render_template("stock_in.html", gases=gases, grouped=grouped)


@app.route("/add-stock-in", methods=["GET", "POST"])
def add_stock_in():
    if request.method == "POST":
        try:
            gid   = int(request.form["gas_id"])
            state = request.form["cylinder_state"]
            src_t = request.form["source_type"]
            src_v = request.form["source_value"].strip()
            with get_connection() as conn:
                conn.execute("INSERT INTO stock_in (gas_id, cylinder_state, source_type, source_value) VALUES (?,?,?,?)",
                             (gid, state, src_t, src_v))
                col = "filled_cylinders" if state == "filled" else "empty_cylinders"
                conn.execute(f"UPDATE gas_table SET {col} = {col} + 1 WHERE gas_id=?", (gid,))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (gid, 'stock_in', 1, f"Stock-IN ({state}) from {src_t}: {src_v}"))
                conn.commit()
            flash("Stock-in recorded ✔️", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("stock_in_page"))
    return redirect(url_for("stock_in_page"))


@app.post("/return-stock-in")
def return_stock_in():
    try:
        gid       = int(request.form["gas_id"])
        in_state  = request.form["cylinder_state"]
        src_type  = request.form["source_type"]
        src_value = request.form["source_value"]
        qty       = int(request.form["return_qty"])
        out_state = request.form["returned_state"]
        if qty <= 0:
            flash("Quantity must be positive.", "error")
            return redirect(url_for("stock_in_page"))
        with get_connection() as conn:
            available = conn.execute("""
                SELECT COUNT(*) FROM stock_in
                WHERE gas_id=? AND cylinder_state=? AND source_type=? AND source_value=?
            """, (gid, in_state, src_type, src_value)).fetchone()[0]
            if qty > available:
                flash("❌ Not enough cylinders available.", "error")
                return redirect(url_for("stock_in_page"))
            # Delete oldest N rows using rowid
            ids = conn.execute("""
                SELECT rowid FROM stock_in
                WHERE gas_id=? AND cylinder_state=? AND source_type=? AND source_value=?
                ORDER BY time_in LIMIT ?
            """, (gid, in_state, src_type, src_value, qty)).fetchall()
            for row in ids:
                conn.execute("DELETE FROM stock_in WHERE rowid=?", (row[0],))
            col = "filled_cylinders" if out_state == "filled" else "empty_cylinders"
            conn.execute(f"UPDATE gas_table SET {col} = {col} - ? WHERE gas_id=?", (qty, gid))
            conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                         (gid, 'return_out', -qty,
                          f"Returned {qty} {in_state} → sent back as {out_state} to {src_type}: {src_value}"))
            conn.commit()
            flash("Return recorded ✔️", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("stock_in_page"))


# ─────────────────────────────────────────────
#  Sales
# ─────────────────────────────────────────────
@app.route("/sales", methods=["GET"])
def sales():
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT s.sale_id, g.gas_name, s.amount_paid_cash, s.amount_paid_till,
                       DATE(s.time_sold) AS sale_date, TIME(s.time_sold) AS time_only,
                       s.from_debt, s.source_mama_pam, s.source_external, s.source_kipsongo_pioneer
                FROM sales_table s JOIN gas_table g ON s.gas_id = g.gas_id
                ORDER BY s.time_sold DESC LIMIT 50
            """).fetchall()
            grouped_sales_dict = defaultdict(list)
            for sale in rows:
                sale_date = sale["sale_date"]
                time_only = sale["time_only"]
                # Format time
                try:
                    t = datetime.strptime(time_only, "%H:%M:%S")
                    time_str = t.strftime("%I:%M %p")
                except:
                    time_str = time_only or ""
                grouped_sales_dict[sale_date].append({
                    "id": sale["sale_id"], "gas": sale["gas_name"],
                    "cash": float(sale["amount_paid_cash"]),
                    "till": float(sale["amount_paid_till"]),
                    "time": time_str,
                    "from_debt": sale["from_debt"],
                    "source_mama_pam": sale["source_mama_pam"],
                    "source_external": sale["source_external"],
                    "source_kipsongo_pioneer": sale["source_kipsongo_pioneer"],
                })
            grouped_sales = []
            for raw_date, sales_list in grouped_sales_dict.items():
                try:
                    d = datetime.strptime(raw_date, "%Y-%m-%d")
                    date_str = d.strftime("%A, %d %B %Y")
                except:
                    date_str = raw_date
                grouped_sales.append({
                    "date": raw_date, "date_str": date_str,
                    "sales": sales_list, "total_gas": len(sales_list)
                })
            grouped_sales.sort(key=lambda x: x["date"], reverse=True)
            gases = conn.execute("""
                SELECT gas_id, gas_name, empty_cylinders, filled_cylinders
                FROM gas_table ORDER BY gas_id ASC
            """).fetchall()
        return render_template("sales.html", gases=gases, grouped_sales=grouped_sales)
    except Exception as e:
        return f"Error loading sales form: {e}"


@app.route("/edit-sale/<int:sale_id>", methods=["GET", "POST"])
def edit_sale(sale_id):
    try:
        with get_connection() as conn:
            if request.method == "POST":
                cash = float(request.form["amount_paid_cash"])
                till = float(request.form["amount_paid_till"])
                conn.execute("UPDATE sales_table SET amount_paid_cash=?, amount_paid_till=? WHERE sale_id=?",
                             (cash, till, sale_id))
                conn.commit()
                return redirect(url_for('sales'))
            row = conn.execute(
                "SELECT gas_id, amount_paid_cash, amount_paid_till FROM sales_table WHERE sale_id=?", (sale_id,)
            ).fetchone()
            if not row:
                return "Sale not found."
            sale  = dict(row)
            gases = conn.execute("SELECT gas_id, gas_name FROM gas_table ORDER BY gas_name ASC").fetchall()
        return render_template("edit_sale.html", sale=sale, gases=gases)
    except Exception as e:
        return f"An error occurred: {str(e)}"


@app.route('/submit-sale', methods=['POST'])
def submit_sale():
    try:
        gas_id = int(request.form["gas_id"])
        cash   = float(request.form.get("amount_paid_cash", 0) or 0)
        till   = float(request.form.get("amount_paid_till", 0) or 0)
        selected_source = request.form.get("source", "customer")
        src_kipsongo = selected_source == "kipsongo_pioneer"
        src_mama     = selected_source == "mama_pam"
        src_external = selected_source == "external"
        source_selected = selected_source in ["kipsongo_pioneer", "mama_pam", "external"]
        sale_type       = request.form.get("sale_type")
        complete_sale   = sale_type == "complete_sale"
        empty_not_given = sale_type == "empty_not_given"
        exchange_cyl    = sale_type == "exchange_cylinder"
        empty_customer  = request.form.get("empty_customer") if empty_not_given else None
        exch_customer   = request.form.get("exchange_customer") if exchange_cyl else None
        gas_id_received = request.form.get("gas_id_received") if exchange_cyl else None
        exch_note       = request.form.get("exchange_note") or ""
        with get_connection() as conn:
            row = conn.execute("SELECT filled_cylinders FROM gas_table WHERE gas_id=?", (gas_id,)).fetchone()
            if not row:
                flash("Gas record not found.", "error")
                return redirect("/sales")
            if row["filled_cylinders"] == 0 and not source_selected:
                flash("No filled gas available.", "error")
                return redirect("/sales")
            conn.execute("""
                INSERT INTO sales_table (gas_id, amount_paid_cash, amount_paid_till,
                    source_kipsongo_pioneer, source_mama_pam, source_external,
                    complete_sale, empty_not_given, exchange_cylinder, time_sold)
                VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
            """, (gas_id, cash, till, src_kipsongo, src_mama, src_external,
                  complete_sale, empty_not_given, exchange_cyl))
            if not source_selected:
                conn.execute("UPDATE gas_table SET filled_cylinders=filled_cylinders-1 WHERE gas_id=?", (gas_id,))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (gas_id, 'decrease_filled', -1, 'Sale out'))
            if exchange_cyl:
                target = int(gas_id_received) if gas_id_received else gas_id
                note_txt = f"Exchange empty from {exch_customer or 'customer'}: {exch_note}"
                conn.execute("UPDATE gas_table SET empty_cylinders=empty_cylinders+1 WHERE gas_id=?", (target,))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (target, 'increase_empty', 1, note_txt))
            elif not complete_sale and not empty_not_given:
                conn.execute("UPDATE gas_table SET empty_cylinders=empty_cylinders+1 WHERE gas_id=?", (gas_id,))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (gas_id, 'increase_empty', 1, 'Empty received'))
            if empty_not_given:
                dest = empty_customer or "No name"
                conn.execute("INSERT INTO stock_out (gas_id, cylinder_state, destination_type, destination_value) VALUES (?,?,?,?)",
                             (gas_id, 'filled', 'customer', dest))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (gas_id, 'stock_out', -1, f"Filled taken w/out empty by {dest}"))
            if complete_sale:
                conn.execute("INSERT INTO stock_out (gas_id, cylinder_state, destination_type, destination_value) VALUES (?,?,?,?)",
                             (gas_id, 'filled', 'customer', 'complete sale'))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (gas_id, 'stock_out', -1, 'Complete sale'))
            if src_kipsongo:
                conn.execute("INSERT INTO stock_in (gas_id, cylinder_state, source_type, source_value) VALUES (?,?,?,?)",
                             (gas_id, 'filled', 'Work Station', 'Pioneer Kipsongo'))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (gas_id, 'stock_in', 1, 'empty from kipsongo'))
            elif src_mama:
                conn.execute("INSERT INTO stock_in (gas_id, cylinder_state, source_type, source_value) VALUES (?,?,?,?)",
                             (gas_id, 'filled', 'Work Station', 'Mama Pam'))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (gas_id, 'stock_in', 1, 'empty from mama pam'))
            elif src_external:
                ext_value = request.form.get("external_details", "").strip() or "external-unknown"
                conn.execute("INSERT INTO stock_in (gas_id, cylinder_state, source_type, source_value) VALUES (?,?,?,?)",
                             (gas_id, 'filled', 'Work Station', ext_value))
                conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                             (gas_id, 'stock_in', 1, f"empty from external place: {ext_value}"))
            conn.commit()
            flash("Sale recorded successfully.", "success")
    except Exception as e:
        flash(f"Error processing sale: {e}", "error")
    return redirect("/sales")


@app.route("/delete-sale/<int:sale_id>")
def delete_sale(sale_id):
    try:
        with get_connection() as conn:
            sale = conn.execute("""
                SELECT gas_id, source_kipsongo_pioneer, source_mama_pam, source_external
                FROM sales_table WHERE sale_id=?
            """, (sale_id,)).fetchone()
            if not sale:
                return "Sale not found.", 404
            gas_id = sale["gas_id"]
            if sale["source_kipsongo_pioneer"]:
                conn.execute("UPDATE kipsongo_gas_in_ukweli SET number_of_gas=number_of_gas-1 WHERE gas_id=?", (gas_id,))
                conn.execute("UPDATE gas_table SET empty_cylinders=empty_cylinders-1 WHERE gas_id=?", (gas_id,))
            elif sale["source_mama_pam"]:
                conn.execute("UPDATE mama_pam_gas_in_ukweli SET number_of_gas=number_of_gas-1 WHERE gas_id=?", (gas_id,))
                conn.execute("UPDATE gas_table SET empty_cylinders=empty_cylinders-1 WHERE gas_id=?", (gas_id,))
            elif sale["source_external"]:
                conn.execute("UPDATE external_gas_in_ukweli SET number_of_gas=number_of_gas-1 WHERE gas_id=?", (gas_id,))
                conn.execute("UPDATE gas_table SET empty_cylinders=empty_cylinders-1 WHERE gas_id=?", (gas_id,))
            else:
                conn.execute("""
                    UPDATE gas_table SET empty_cylinders=empty_cylinders-1, filled_cylinders=filled_cylinders+1
                    WHERE gas_id=?
                """, (gas_id,))
            conn.execute("DELETE FROM sales_table WHERE sale_id=?", (sale_id,))
            conn.commit()
        flash("Sale deleted.", "success")
        return redirect(url_for('sales'))
    except Exception as e:
        return f"Error deleting sale: {e}"


# ─────────────────────────────────────────────
#  Profit & Finance
# ─────────────────────────────────────────────
@app.route("/profit-list")
def profit_list():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT p.profit_id, g.gas_name, p.qty, p.revenue, p.cost,
                   (p.revenue - p.cost) AS profit,
                   DATE(p.created_at) AS day, TIME(p.created_at) AS clock
            FROM profit_table p JOIN gas_table g ON g.gas_id = p.gas_id
            ORDER BY day DESC, p.created_at DESC
        """).fetchall()
    day_map = {}
    for r in rows:
        try:
            t = datetime.strptime(r["clock"], "%H:%M:%S")
            clock_str = t.strftime("%H:%M")
        except:
            clock_str = r["clock"] or "00:00"
        rec = {
            "id": r["profit_id"], "gas": r["gas_name"],
            "qty": r["qty"] or 0, "rev": float(r["revenue"] or 0),
            "cost": float(r["cost"] or 0), "prf": float(r["profit"] or 0),
            "clock": clock_str
        }
        day_map.setdefault(r["day"], []).append(rec)
    grouped = []
    for d, lst in day_map.items():
        grouped.append({
            "day": d, "records": lst,
            "tot_qty":  sum(r["qty"]  for r in lst),
            "tot_rev":  sum(r["rev"]  for r in lst),
            "tot_cost": sum(r["cost"] for r in lst),
            "tot_prf":  sum(r["prf"]  for r in lst),
        })
    grouped.sort(key=lambda x: x["day"], reverse=True)
    return render_template("profit_list.html", grouped=grouped)


@app.route('/profit')
def view_profit():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DATE(created_at) AS day,
                   SUM(revenue) AS total_revenue, SUM(cost) AS total_cost,
                   SUM(revenue - cost) AS total_profit
            FROM profit_table GROUP BY day ORDER BY day DESC
        """).fetchall()
    daily = [{"day": r["day"], "revenue": float(r["total_revenue"] or 0),
               "cost": float(r["total_cost"] or 0), "profit": float(r["total_profit"] or 0)}
             for r in rows]
    return render_template("profit.html", daily=daily)


@app.route("/finance")
@admin_required
def finance_page():
    try:
        with get_connection() as conn:
            row = conn.execute("SELECT COALESCE(SUM(revenue - cost), 0) FROM profit_table").fetchone()
            total_profit = float(row[0])
        return render_template("finance.html", total_profit=total_profit)
    except Exception as e:
        flash(f"Finance page error: {e}", "error")
        return redirect(url_for("dashboard"))


# ─────────────────────────────────────────────
#  Refill
# ─────────────────────────────────────────────
@app.route('/refill')
def refill_page():
    from collections import namedtuple
    with get_connection() as conn:
        companies = [dict(r) for r in conn.execute(
            "SELECT company_id, company_name FROM buying_company ORDER BY company_name"
        ).fetchall()]
        gases = [dict(r) for r in conn.execute(
            "SELECT gas_id, gas_name, empty_cylinders AS empty, filled_cylinders AS filled FROM gas_table ORDER BY gas_name"
        ).fetchall()]
        raw = conn.execute("""
            SELECT DATE(r.refill_time) AS d, TIME(r.refill_time) AS t,
                   bc.company_name, g.gas_name, r.quantity, r.unit_price,
                   (r.quantity * r.unit_price) AS total_cost
            FROM refill_table r
            JOIN buying_company bc ON bc.company_id = r.company_id
            JOIN gas_table g ON g.gas_id = r.gas_id
            ORDER BY r.refill_time DESC LIMIT 150
        """).fetchall()
    HistoryRec = namedtuple("HistoryRec", "gas qty price total time")
    day_map = defaultdict(lambda: defaultdict(list))
    for r in raw:
        day_map[r["d"]][r["company_name"]].append(
            HistoryRec(r["gas_name"], r["quantity"], float(r["unit_price"]),
                       float(r["total_cost"]), r["t"])
        )
    history = []
    for d in sorted(day_map.keys(), reverse=True):
        companies_group = []
        for comp in sorted(day_map[d].keys()):
            recs = day_map[d][comp]
            companies_group.append({
                "company": comp, "records": recs,
                "total_qty": sum(r.qty for r in recs),
                "total_cost": sum(r.total for r in recs),
            })
        history.append({"date": d, "companies": companies_group})
    return render_template("refill.html", companies=companies, gases=gases, history=history)


@app.route('/add-refill', methods=['POST'])
def add_refill():
    try:
        comp_id = int(request.form['company_id'])
        gid     = int(request.form['gas_id'])
        qty     = int(request.form['refill_qty'])
        if qty <= 0:
            flash("Quantity must be positive.", "error")
            return redirect(url_for('refill_page'))
        with get_connection() as conn:
            row = conn.execute(
                "SELECT refill_price FROM company_gas_price WHERE company_id=? AND gas_id=?", (comp_id, gid)
            ).fetchone()
            if not row or not row["refill_price"]:
                flash("No price set for this supplier and gas brand.", "error")
                return redirect(url_for('refill_page'))
            unit_price = float(row["refill_price"])
            stock = conn.execute("SELECT empty_cylinders FROM gas_table WHERE gas_id=?", (gid,)).fetchone()
            if not stock or stock["empty_cylinders"] < qty:
                flash("❌ Not enough empty cylinders available.", "error")
                return redirect(url_for('refill_page'))
            conn.execute("""
                UPDATE gas_table
                SET filled_cylinders=filled_cylinders+?, empty_cylinders=empty_cylinders-?
                WHERE gas_id=?
            """, (qty, qty, gid))
            conn.execute("INSERT INTO refill_table (company_id, gas_id, quantity, unit_price) VALUES (?,?,?,?)",
                         (comp_id, gid, qty, unit_price))
            conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                         (gid, 'refill', qty, f"Refill from supplier {comp_id} at {unit_price:.2f} KSh"))
            conn.commit()
            flash("Refill saved.", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for('refill_page'))


@app.route('/refill-old')
def refill():
    with get_connection() as conn:
        gases = [dict(r) for r in conn.execute(
            "SELECT gas_id, gas_name, empty_cylinders, filled_cylinders FROM gas_table ORDER BY gas_name"
        ).fetchall()]
        companies = conn.execute("SELECT company_id, company_name FROM buying_company ORDER BY company_name").fetchall()
    return render_template("refill.html", gases=gases, companies=companies)


@app.route('/get-price')
def get_price():
    comp = request.args.get('company_id', type=int)
    gid  = request.args.get('gas_id', type=int)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT refill_price FROM company_gas_price WHERE company_id=? AND gas_id=?", (comp, gid)
        ).fetchone()
    return {"price": float(row["refill_price"]) if row else 0}


# ─────────────────────────────────────────────
#  Gas Form (Add/Edit/Delete gas brands)
# ─────────────────────────────────────────────
@app.route("/gas-form")
def gas_form():
    with get_connection() as conn:
        gases = conn.execute("""
            SELECT gas_id, gas_name, empty_cylinders, filled_cylinders,
                   (empty_cylinders + filled_cylinders) AS total
            FROM gas_table ORDER BY gas_id
        """).fetchall()
    return render_template("gas_form.html", gases=gases)


@app.post("/add-gas")
def add_gas():
    name   = request.form["gas_name"].strip()
    empty  = int(request.form["empty_cylinders"] or 0)
    filled = int(request.form["filled_cylinders"] or 0)
    with get_connection() as conn:
        conn.execute("INSERT INTO gas_table (gas_name, empty_cylinders, filled_cylinders) VALUES (?,?,?)",
                     (name, empty, filled))
        conn.commit()
    flash("Gas added ✅", "success")
    return redirect(url_for("gas_form"))


@app.post("/update-gas/<int:gid>")
def update_gas(gid):
    name   = request.form["gas_name"].strip()
    empty  = int(request.form["empty_cylinders"] or 0)
    filled = int(request.form["filled_cylinders"] or 0)
    with get_connection() as conn:
        conn.execute("UPDATE gas_table SET gas_name=?, empty_cylinders=?, filled_cylinders=? WHERE gas_id=?",
                     (name, empty, filled, gid))
        conn.commit()
    flash("Gas updated ✅", "success")
    return redirect(url_for("gas_form"))


@app.post("/delete-gas/<int:gid>")
def delete_gas(gid):
    with get_connection() as conn:
        conn.execute("DELETE FROM gas_table WHERE gas_id=?", (gid,))
        conn.commit()
    flash("Gas deleted 🗑️", "success")
    return redirect(url_for("gas_form"))


# ─────────────────────────────────────────────
#  Gas Summary
# ─────────────────────────────────────────────
@app.route('/gas-summary')
def gas_summary():
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT
                  CASE WHEN gas_name LIKE '%13%' THEN '13kg' ELSE 'non-13kg' END AS gas_type,
                  SUM(empty_cylinders) AS total_empty,
                  SUM(filled_cylinders) AS total_filled,
                  SUM(empty_cylinders + filled_cylinders) AS total_cylinders
                FROM gas_table GROUP BY gas_type
            """).fetchall()
        summary = [{"type": r["gas_type"], "empty": r["total_empty"],
                    "filled": r["total_filled"], "total": r["total_cylinders"]} for r in rows]
        return render_template("gas_summary.html", summary=summary)
    except Exception as e:
        flash(f"Error loading gas summary: {e}", "error")
        return redirect(url_for("dashboard"))


# ─────────────────────────────────────────────
#  Stock Out
# ─────────────────────────────────────────────
@app.route('/stock-out', methods=['GET', 'POST'])
def stock_out():
    with get_connection() as conn:
        gases = conn.execute(
            "SELECT gas_id, gas_name, empty_cylinders, filled_cylinders FROM gas_table ORDER BY gas_name"
        ).fetchall()
        users = conn.execute("SELECT user_id, username FROM users ORDER BY username").fetchall()
        message = None

        if request.method == 'POST':
            gas_id           = request.form['gas_id']
            cylinder_state   = request.form['cylinder_state']
            destination_type = request.form['destination_type']
            if destination_type == "station":
                destination_value = request.form.get("destination_value_station")
            elif destination_type == "delivery":
                destination_value = request.form.get("destination_value_delivery")
            elif destination_type == "customer":
                destination_value = request.form.get("destination_value_customer")
            else:
                destination_value = None

            stock = conn.execute(
                "SELECT empty_cylinders, filled_cylinders FROM gas_table WHERE gas_id=?", (gas_id,)
            ).fetchone()
            if not stock:
                message = "Gas not found."
            else:
                available = stock["filled_cylinders"] if cylinder_state == 'filled' else stock["empty_cylinders"]
                if available < 1:
                    message = f"No {cylinder_state} cylinders available."
                else:
                    if cylinder_state == 'filled':
                        conn.execute("UPDATE gas_table SET filled_cylinders=filled_cylinders-1 WHERE gas_id=?", (gas_id,))
                    else:
                        conn.execute("UPDATE gas_table SET empty_cylinders=empty_cylinders-1 WHERE gas_id=?", (gas_id,))
                    conn.execute("""
                        INSERT INTO stock_out (gas_id, cylinder_state, destination_type, destination_value, time_out)
                        VALUES (?,?,?,?,datetime('now'))
                    """, (gas_id, cylinder_state, destination_type, destination_value))
                    conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                                 (gas_id, f"stock_out_{cylinder_state}", -1,
                                  f"Stock out to {destination_type}: {destination_value}"))
                    conn.commit()
                    message = "Stock out entry saved successfully."

        records = conn.execute("""
            SELECT so.id, g.gas_name, so.cylinder_state, so.destination_type,
                   so.destination_value, so.time_out
            FROM stock_out so JOIN gas_table g ON so.gas_id = g.gas_id
            ORDER BY so.time_out DESC
        """).fetchall()

        stock_out_list = []
        for row in records:
            dt = row["destination_type"]
            dv = row["destination_value"]
            goes_to = customer_name = delivery_username = None
            if dt == 'station':
                goes_to = dv
            elif dt == 'customer':
                customer_name = dv
            elif dt == 'delivery':
                u = conn.execute("SELECT username FROM users WHERE user_id=?", (dv,)).fetchone()
                delivery_username = u["username"] if u else 'Unknown'
            stock_out_list.append({
                'id': row["id"], 'gas_name': row["gas_name"],
                'cylinder_state': row["cylinder_state"],
                'goes_to': goes_to, 'customer_name': customer_name,
                'delivery_username': delivery_username,
                'time': row["time_out"] or ''
            })

    return render_template('stock_out.html', gases=gases, users=users,
                           stock_out_records=stock_out_list, message=message)


@app.route('/add-stock-out', methods=['POST'])
def add_stock_out():
    gas_id           = request.form.get('gas_id')
    cylinder_state   = request.form.get('cylinder_state')
    destination_type = request.form.get('destination_type')
    if not gas_id or not cylinder_state or not destination_type:
        flash("All fields are required.", "error")
        return redirect(url_for('stock_out'))
    if destination_type == 'station':
        destination_value = request.form.get('destination_value_station')
    elif destination_type == 'delivery':
        destination_value = request.form.get('destination_value_delivery')
    elif destination_type == 'customer':
        destination_value = request.form.get('destination_value_customer')
    else:
        destination_value = None
    if not destination_value:
        flash("Destination value is required.", "error")
        return redirect(url_for('stock_out'))
    with get_connection() as conn:
        stock = conn.execute(
            "SELECT empty_cylinders, filled_cylinders FROM gas_table WHERE gas_id=?", (gas_id,)
        ).fetchone()
        if not stock:
            flash("Gas record not found.", "error")
            return redirect(url_for('stock_out'))
        if cylinder_state == 'empty' and stock["empty_cylinders"] <= 0:
            flash("No empty cylinders available.", "error")
            return redirect(url_for('stock_out'))
        if cylinder_state == 'filled' and stock["filled_cylinders"] <= 0:
            flash("No filled cylinders available.", "error")
            return redirect(url_for('stock_out'))
        conn.execute("INSERT INTO stock_out (gas_id, cylinder_state, destination_type, destination_value) VALUES (?,?,?,?)",
                     (gas_id, cylinder_state, destination_type, destination_value))
        col = "empty_cylinders" if cylinder_state == 'empty' else "filled_cylinders"
        conn.execute(f"UPDATE gas_table SET {col} = {col} - 1 WHERE gas_id=?", (gas_id,))
        conn.commit()
    flash("Stock out recorded successfully.", "success")
    return redirect(url_for('stock_out'))


@app.route('/return-stock/<int:stock_id>', methods=['POST'])
def return_stock(stock_id):
    returned_state = request.form.get('returned_cylinder_state')
    if returned_state not in ['empty', 'filled']:
        flash('Invalid returned cylinder state.', 'error')
        return redirect(url_for('stock_out'))
    with get_connection() as conn:
        record = conn.execute("""
            SELECT id, gas_id, cylinder_state, destination_type, destination_value, time_out
            FROM stock_out WHERE id=?
        """, (stock_id,)).fetchone()
        if not record:
            flash('Record not found.', 'error')
            return redirect(url_for('stock_out'))
        gas_id = record["gas_id"]
        destination_type  = record["destination_type"]
        destination_value = record["destination_value"]
        display_name = destination_value
        if destination_type == 'delivery':
            u = conn.execute("SELECT username FROM users WHERE user_id=?", (destination_value,)).fetchone()
            display_name = u["username"] if u else f"Unknown delivery (ID: {destination_value})"
        if destination_type == 'delivery' and record["cylinder_state"] == 'filled' and returned_state == 'empty':
            session['delivery_return_info'] = {
                'gas_id': gas_id, 'stock_id': stock_id, 'delivery_id': destination_value
            }
            return redirect(url_for('record_delivery_sale'))
        conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                     (gas_id, f"return_{returned_state}", 1,
                      f"Returned from {destination_type}: {display_name}"))
        conn.execute("DELETE FROM stock_out WHERE id=?", (stock_id,))
        col = "empty_cylinders" if returned_state == 'empty' else "filled_cylinders"
        conn.execute(f"UPDATE gas_table SET {col} = {col} + 1 WHERE gas_id=?", (gas_id,))
        conn.commit()
    flash("Gas returned successfully!", "success")
    return redirect(url_for('stock_out'))


@app.route('/record-delivery-sale', methods=['GET', 'POST'])
def record_delivery_sale():
    info = session.get('delivery_return_info')
    if not info:
        flash("No delivery return info found in session.", "error")
        return redirect(url_for('stock_out'))
    if request.method == 'POST':
        try:
            amount_cash = float(request.form.get('amount_paid_cash') or 0)
            amount_till = float(request.form.get('amount_paid_till') or 0)
        except ValueError:
            flash("Enter valid numeric values.", "error")
            return redirect(url_for('record_delivery_sale'))
        gas_id   = info['gas_id']
        stock_id = info['stock_id']
        delivery_id = info['delivery_id']
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO sales_table (gas_id, amount_paid_cash, amount_paid_till,
                    source_external, complete_sale)
                VALUES (?,?,?,1,1)
            """, (gas_id, amount_cash, amount_till))
            conn.execute("INSERT INTO stock_change (gas_id, action, quantity_change, notes) VALUES (?,?,?,?)",
                         (gas_id, "return_empty", 1, f"Returned from delivery ID: {delivery_id}"))
            conn.execute("DELETE FROM stock_out WHERE id=?", (stock_id,))
            conn.execute("UPDATE gas_table SET empty_cylinders=empty_cylinders+1 WHERE gas_id=?", (gas_id,))
            conn.commit()
        session.pop('delivery_return_info', None)
        flash("Delivery return and sale recorded successfully.", "success")
        return redirect(url_for('stock_out'))
    return render_template("record_delivery_sale.html")


# ─────────────────────────────────────────────
#  Source-specific pages
# ─────────────────────────────────────────────
@app.route('/kipsongo-gas')
def kipsongo_gas():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT g.gas_name, k.number_of_gas
            FROM kipsongo_gas_in_ukweli k JOIN gas_table g ON k.gas_id = g.gas_id
        """).fetchall()
    return render_template("kipsongo-gas.html", data=rows)


@app.route('/kipsongo-gas-u')
def kipsongo_gas_u():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT g.gas_name, k.number_of_gas
            FROM kipsongo_gas_in_ukweli k JOIN gas_table g ON k.gas_id = g.gas_id
        """).fetchall()
    return render_template("kipsongo-gas-u.html", data=rows)


@app.route('/mpam-gas-u')
def mpam_gas_u():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT g.gas_name, m.number_of_gas
            FROM mama_pam_gas_in_ukweli m JOIN gas_table g ON m.gas_id = g.gas_id
        """).fetchall()
    return render_template("mpam-gas-u.html", data=rows)


@app.route('/external-u')
def external_u():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT g.gas_name, e.number_of_gas
            FROM external_gas_in_ukweli e JOIN gas_table g ON e.gas_id = g.gas_id
        """).fetchall()
    return render_template("external-u.html", data=rows)


if __name__ == '__main__':
    app.run(debug=True)
