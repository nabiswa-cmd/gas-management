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


from collections import defaultdict

@app.route("/sales", methods=["GET"])
def sales():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Fetch all recent sales (latest 50)
                cur.execute("""
                    SELECT s.sale_id, g.gas_name, s.amount_paid_cash, s.amount_paid_till, 
                           s.time_sold::date AS sale_date, s.time_sold::time
                    FROM sales_table s
                    JOIN gas_table g ON s.gas_id = g.gas_id
                    ORDER BY s.time_sold DESC LIMIT 50;
                """)
                rows = cur.fetchall()

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

                # Build final grouped structure
                grouped_sales = []
                for raw_date, sales_list in grouped_sales_dict.items():
                    grouped_sales.append({
                        "date": raw_date,  # raw date for sorting
                        "date_str": raw_date.strftime("%A, %d %B %Y"),  # formatted string for display
                        "sales": sales_list,
                        "total_gas": len(sales_list)
                    })

                # Sort by newest date (descending)
                grouped_sales.sort(key=lambda x: x["date"], reverse=True)

                # Load gas list
                cur.execute("SELECT gas_id, gas_name, empty_cylinders, filled_cylinders FROM gas_table ORDER BY gas_id ASC;")
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
                    flash("No filled gas available and no source selected. Cannot proceed.", "error")
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