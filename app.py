from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from datetime import datetime
from collections import defaultdict
from datetime import datetime


app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATABASE_URL = "postgresql://ukwelitradersbase_user:KQTv3VjbP9E7lCo4wAmERxGrg7arHHlp@dpg-d0b0e82dbo4c73c9st5g-a.oregon-postgres.render.com/ukwelitradersbase"

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

# --- SALES PAGE AND SUBMISSION ---


@app.route("/sales", methods=["GET"])
def sales():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Fetch all recent sales (limit to latest 50 by time)
                cur.execute("""
                    SELECT s.sale_id, g.gas_name, s.amount_paid_cash, s.amount_paid_till, s.time_sold::timestamp::date as sale_date, s.time_sold::time
                    FROM sales_table s
                    JOIN gas_table g ON s.gas_id = g.gas_id
                    ORDER BY s.time_sold DESC LIMIT 50;
                """)
                rows = cur.fetchall()

                # Organize sales grouped by date
                grouped_sales_dict = defaultdict(list)
                for sale in rows:
                    sale_id, gas_name, cash, till, sale_date, time_only = sale
                    grouped_sales_dict[sale_date].append({
                        "id": sale_id,
                        "gas": gas_name,
                        "cash": float(cash),
                        "till": float(till),
                        "time": time_only.strftime("%I:%M %p")
                    })

                # Build final grouped structure for template
                grouped_sales = []
                for date, sales_list in grouped_sales_dict.items():
                    grouped_sales.append({
                        "date": date.strftime("%A, %d %B %Y"),
                        "sales": sales_list,
                        "total_gas": len(sales_list)
                    })

                # Sort by newest date first
                grouped_sales.sort(key=lambda x: x["date"], reverse=True)

                # Load gas list for the dropdown
                cur.execute("SELECT gas_id, gas_name, empty_cylinders, filled_cylinders FROM gas_table;")
                gases = cur.fetchall()

        return render_template("sales.html", gases=gases, grouped_sales=grouped_sales)

    except Exception as e:
        return f"Error loading sales form: {e}"
@app.route('/submit-sale', methods=['POST'])
def submit_sale():
    try:
        gas_id = int(request.form["gas_id"])
        amount_paid_cash = float(request.form.get("amount_paid_cash", 0))
        amount_paid_till = float(request.form.get("amount_paid_till", 0))
        source_kipsongo_pioneer = 'source_kipsongo_pioneer' in request.form
        source_mama_pam = 'source_mama_pam' in request.form
        source_external = 'source_external' in request.form
        complete_power = 'complete_power' in request.form
        empty_not_given = 'empty_not_given' in request.form
        exchange_cylinder = 'exchange_cylinder' in request.form
        time_sold = datetime.now()

        source_selected = source_kipsongo_pioneer or source_mama_pam or source_external

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
                    flash("No filled gas available and no source selected. Cannot proceed.", "error")
                    return redirect("/sales")

                # Insert into sales_table
                cur.execute("""
                    INSERT INTO sales_table (
                        gas_id, amount_paid_cash, amount_paid_till,
                        source_kipsongo_pioneer, source_mama_pam, source_external,
                        complete_power, empty_not_given, exchange_cylinder, time_sold
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    gas_id, amount_paid_cash, amount_paid_till,
                    source_kipsongo_pioneer, source_mama_pam, source_external,
                    complete_power, empty_not_given, exchange_cylinder, time_sold
                ))

                # Always increase empty cylinders by 1
                cur.execute("""
                    UPDATE gas_table
                    SET empty_cylinders = empty_cylinders + 1
                    WHERE gas_id = %s
                """, (gas_id,))

                # If no source is selected, also increase filled cylinders
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

                if source_mama_pam:
                    cur.execute("""
                        INSERT INTO mama_pam_gas_in_ukweli (gas_id, number_of_gas)
                        VALUES (%s, 1)
                        ON CONFLICT (gas_id) DO UPDATE
                        SET number_of_gas = mama_pam_gas_in_ukweli.number_of_gas + 1
                    """, (gas_id,))

                if source_external:
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

    return redirect("/sales")



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
    return redirect(url_for('login'))

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
    
    return render_template('gas_form.html')

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