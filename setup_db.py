import psycopg2

DATABASE_URL = "postgresql://james:SPpKLyvgRTImuzDFaUy4thGKojpKfuBY@dpg-d120e495pdvs73c758og-a.oregon-postgres.render.com/ukwelidb"
try:
    # ✅ Connect securely using SSL
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()

    # Create gas_table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gas_table (
            gas_id SERIAL PRIMARY KEY,
            gas_name TEXT NOT NULL,
            empty_cylinders INTEGER DEFAULT 0,
            filled_cylinders INTEGER DEFAULT 0,
            total_cylinders NUMERIC(10,2) GENERATED ALWAYS AS (empty_cylinders + filled_cylinders) STORED
        );
    """)

    # Create stock_out
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_out (
            id SERIAL PRIMARY KEY,
            gas_id INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
            cylinder_state TEXT CHECK (cylinder_state IN ('empty', 'filled')),
            destination_type TEXT CHECK (destination_type IN ('station', 'delivery', 'customer')),
            destination_value TEXT NOT NULL,
            time_out TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create sales_table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales_table (
            sale_id SERIAL PRIMARY KEY,
            gas_id INTEGER REFERENCES gas_table(gas_id),
            sale_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            amount_paid_cash NUMERIC(10,2) DEFAULT 0,
            amount_paid_till NUMERIC(10,2) DEFAULT 0,
            total NUMERIC(10,2) GENERATED ALWAYS AS (amount_paid_cash + amount_paid_till) STORED,
            time_sold TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            source_kipsongo_pioneer BOOLEAN DEFAULT FALSE,
            source_mama_pam BOOLEAN DEFAULT FALSE,
            source_external BOOLEAN DEFAULT FALSE,
            complete_sale BOOLEAN DEFAULT FALSE,
            empty_not_given BOOLEAN DEFAULT FALSE,
            exchange_cylinder BOOLEAN DEFAULT FALSE
        );
    """)

    # Create gas_debts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gas_debts (
            id SERIAL PRIMARY KEY,
            gas_id INTEGER REFERENCES gas_table(gas_id),
            amount_paid NUMERIC(10,2),
            amount_to_be_paid NUMERIC(10,2),
            date_to_be_paid DATE,
            authorized_by TEXT CHECK (authorized_by IN ('mama done', 'baba done')),
            empty_cylinder_given BOOLEAN DEFAULT FALSE,
            customer_name TEXT,
            customer_phone TEXT,
            customer_address TEXT,
            time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            customer_picture TEXT
        );
    """)

    # Create gas_debt_payments
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gas_debt_payments (
            id SERIAL PRIMARY KEY,
            debt_id INTEGER REFERENCES gas_debts(id) ON DELETE CASCADE,
            amount NUMERIC(10,2),
            payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    """)

    # Insert default admin user
    cur.execute("""
        INSERT INTO users (username, password)
        VALUES (%s, %s)
        ON CONFLICT (username) DO NOTHING;
    """, ('admin', 'admin123'))

    # Create gas source tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS kipsongo_gas_in_ukweli (
            gas_id INTEGER PRIMARY KEY REFERENCES gas_table(gas_id) ON DELETE CASCADE,
            number_of_gas INTEGER NOT NULL DEFAULT 0
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mama_pam_gas_in_ukweli (
            gas_id INTEGER PRIMARY KEY REFERENCES gas_table(gas_id) ON DELETE CASCADE,
            number_of_gas INTEGER NOT NULL DEFAULT 0
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS external_gas_in_ukweli (
            gas_id INTEGER PRIMARY KEY REFERENCES gas_table(gas_id) ON DELETE CASCADE,
            number_of_gas INTEGER NOT NULL DEFAULT 0
        );
    """)

    # ✅ FIXED: Correct syntax for stock_change table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_change (
            id SERIAL PRIMARY KEY,
            gas_id INTEGER REFERENCES gas_table(gas_id),
            cylinder_state VARCHAR(10) CHECK (cylinder_state IN ('empty', 'filled')),
            returned_to VARCHAR(50),
            time_returned TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    conn.commit()
    print("✅ Tables created successfully.")

except Exception as e:
    print("❌ Error creating tables:", e)

finally:
    if 'conn' in locals():
        conn.close()
