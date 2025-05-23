import psycopg2

DATABASE_URL = "postgresql://ukwelitradersbase_user:KQTv3VjbP9E7lCo4wAmERxGrg7arHHlp@dpg-d0b0e82dbo4c73c9st5g-a.oregon-postgres.render.com/ukwelitradersbase"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # --- Create gas_table ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS gas_table (
        gas_id SERIAL PRIMARY KEY,
        gas_name TEXT NOT NULL,
        empty_cylinders INTEGER DEFAULT 0,
        filled_cylinders INTEGER DEFAULT 0
    );
    """)

    # --- Create sales_table ---
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

    # --- Create users table ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    );
    """)

    # --- Insert default user ---
    cur.execute("""
    INSERT INTO users (username, password)
    VALUES (%s, %s)
    ON CONFLICT (username) DO NOTHING;
    """, ('admin', 'admin123'))

     # --- Create source-specific gas tables ---
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

    conn.commit()
    print("✅ Tables created successfully.")

except Exception as e:
    print("❌ Error creating tables:", e)

finally:
    if 'conn' in locals():
        conn.close()