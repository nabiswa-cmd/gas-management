import psycopg2
import os

DATABASE_URL = os.environ["DATABASE_URL"]
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
    cur.execute("""CREATE TABLE IF NOT EXISTS prepaid_sales (
    id SERIAL PRIMARY KEY,
    gas_id INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
    customer_name TEXT NOT NULL,
    customer_phone TEXT,
    customer_address TEXT,
    empty_given BOOLEAN DEFAULT FALSE,
    customer_picture TEXT, -- path or image URL
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
    amount_paid NUMERIC(10,2) DEFAULT 0.00,  -- Set default value to 0
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
    cur.execute("""
            CREATE TABLE IF NOT EXISTS stock_out (
        id                SERIAL PRIMARY KEY,
        gas_id            INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        cylinder_state    TEXT
            CHECK (cylinder_state  IN ('empty','filled')),
        destination_type  TEXT
            CHECK (destination_type IN ('station','delivery','customer')),
        destination_value TEXT NOT NULL,
        time_out          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Optional helper indexes for faster look‑ups by gas or destination
    create_indexes_sql = """
    CREATE INDEX IF NOT EXISTS idx_stock_out_gas_id     ON stock_out (gas_id);
    CREATE INDEX IF NOT EXISTS idx_stock_out_dest_type  ON stock_out (destination_type);
    """
        
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
  # ✅ Create stock_change table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_change (
            id SERIAL PRIMARY KEY,
            gas_id INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            quantity_change INTEGER NOT NULL,
            notes TEXT,
            changed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # 1. buying_company master list
    cur.execute("""
        CREATE TABLE IF NOT EXISTS buying_company (
            company_id   SERIAL PRIMARY KEY,
            company_name TEXT UNIQUE NOT NULL
        );
    """)

    SEED_COMPANIES = ['KAFUSH AND JAY', 'DAN SUPPLY', 'NEW SUPPLIER']
    for name in SEED_COMPANIES:
        cur.execute("""
            INSERT INTO buying_company (company_name)
            VALUES (%s)
            ON CONFLICT (company_name) DO NOTHING;
        """, (name,))

    # 2. company_gas_price (one row per company × brand)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_gas_price (
            company_id   INTEGER NOT NULL
                         REFERENCES buying_company(company_id) ON DELETE CASCADE,
            gas_id       INTEGER NOT NULL
                         REFERENCES gas_table(gas_id)         ON DELETE CASCADE,
            refill_price NUMERIC(10,2) DEFAULT 0,
            full_price   NUMERIC(10,2) DEFAULT 0,
            last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (company_id, gas_id)
        );
    """)

    # 3. Auto‑populate matrix with zero prices for every combo
    cur.execute("""
        INSERT INTO company_gas_price (company_id, gas_id)
        SELECT c.company_id, g.gas_id
        FROM   buying_company c
        CROSS  JOIN gas_table g
        ON CONFLICT DO NOTHING;
    """)
    cur.execute("""
CREATE TABLE IF NOT EXISTS refill_table (
    refill_id     SERIAL PRIMARY KEY,
    company_id    INTEGER NOT NULL REFERENCES buying_company(company_id) ON DELETE CASCADE,
    gas_id        INTEGER NOT NULL REFERENCES gas_table(gas_id) ON DELETE CASCADE,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(10,2) NOT NULL CHECK (unit_price >= 0),
    total_cost    NUMERIC(12,2) GENERATED ALWAYS AS (quantity * unit_price) STORED,
    refill_time   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
)
""")
    cur.execute("""
CREATE TABLE IF NOT EXISTS stock_in (
    id              SERIAL PRIMARY KEY,
    gas_id          INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
    cylinder_state  TEXT   CHECK (cylinder_state IN ('empty','filled')),
    source_type     TEXT   CHECK (source_type IN ('supplier','Work Station','customer')),
    source_value    TEXT   NOT NULL,
    time_in         TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
""")


except Exception as e:
    print("❌ Error creating tables:", e)

finally:
    if 'conn' in locals():
        conn.close()


