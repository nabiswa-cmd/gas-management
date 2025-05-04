from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a strong, random key in production

DATABASE_URL = "postgresql://ukwelitradersbase_user:KQTv3VjbP9E7lCo4wAmERxGrg7arHHlp@dpg-d0b0e82dbo4c73c9st5g-a.oregon-postgres.render.com/ukwelitradersbase"

def get_connection():
    return psycopg2.connect(DATABASE_URL)


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


@app.route("/sales", methods=["GET"])
def sales():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT s.sale_id,g.gas_name,s.amount_paid_cash,s.amount_paid_till,s.time_sold
                    FROM sales_table s
                    JOIN gas_table g ON s.gas_id = g.gas_id
                    ORDER BY s.time_sold DESC
                    LIMIT 50;
                """)
                sales = cur.fetchall()

                cur.execute("SELECT gas_id, gas_name, empty_cylinders, filled_cylinders FROM gas_table;")
                gases = cur.fetchall()

        return render_template("sales.html",gases=gases,sales=sales)
    except Exception as e:
        return f"Error loading sales form: {e}"


@app.route("/submit-sale", methods=["POST"])
def submit_sale():
    try:
        gas_id = request.form["gas_id"]
        amount_paid_cash = float(request.form.get("amount_paid_cash", 0))
        amount_paid_till = float(request.form.get("amount_paid_till", 0))

        source_kipsongo_pioneer = 'source_kipsongo_pioneer' in request.form
        source_mama_pam = 'source_mama_pam' in request.form
        source_external = 'source_external' in request.form
        complete_power = 'complete_power' in request.form
        empty_not_given = 'empty_not_given' in request.form
        exchange_cylinder = 'exchange_cylinder' in request.form

        time_sold = datetime.now()

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sales_table (
                        gas_id,amount_paid_cash,amount_paid_till,
                        source_kipsongo_pioneer,source_mama_pam,source_external,
                        complete_power,empty_not_given,exchange_cylinder,time_sold
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    gas_id,amount_paid_cash,amount_paid_till,
                    source_kipsongo_pioneer,source_mama_pam,source_external,
                    complete_power,empty_not_given,exchange_cylinder,time_sold
                ))
                conn.commit()

        return redirect("/sales")
    except Exception as e:
        return f"Error during sale submission: {e}"


@app.route("/gas-form", methods=["GET", "POST"])
def gas_form():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if request.method == "POST":
                    gas_name = request.form["gas_name"]
                    empty = int(request.form["empty_cylinders"])
                    filled = int(request.form["filled_cylinders"])

                    cur.execute("""
                        INSERT INTO gas_table (gas_name, empty_cylinders, filled_cylinders)
                        VALUES (%s, %s, %s);
                    """, (gas_name, empty, filled))
                    conn.commit()

                cur.execute("SELECT gas_id, gas_name, empty_cylinders, filled_cylinders FROM gas_table")
                gases = cur.fetchall()

        return render_template("gas_form.html", gases=gases)
    except Exception as e:
        return f"Error with gas form: {e}"


@app.route("/refill")
def refill():
    return render_template('refill.html')  # Ensure refill.html exists


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


if __name__ == '__main__':
    app.run(debug=True)
