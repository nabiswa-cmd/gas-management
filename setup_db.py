import sqlite3
import os

DATABASE = os.path.join(os.path.dirname(__file__), 'gas.db')

conn = sqlite3.connect(DATABASE)
conn.execute("PRAGMA foreign_keys = ON")
cur = conn.cursor()

# gas_table (no GENERATED ALWAYS - SQLite doesn't support it; compute total in Python/SQL)
cur.execute("""
    CREATE TABLE IF NOT EXISTS gas_table (
        gas_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        gas_name        TEXT NOT NULL,
        empty_cylinders INTEGER DEFAULT 0,
        filled_cylinders INTEGER DEFAULT 0
    )
""")

# prepaid_sales
cur.execute("""
    CREATE TABLE IF NOT EXISTS prepaid_sales (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        gas_id           INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        customer_name    TEXT NOT NULL,
        customer_phone   TEXT,
        customer_address TEXT,
        empty_given      INTEGER DEFAULT 0,
        customer_picture TEXT,
        created_at       TEXT DEFAULT (datetime('now'))
    )
""")

# sales_table (no GENERATED ALWAYS for total)
cur.execute("""
    CREATE TABLE IF NOT EXISTS sales_table (
        sale_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        gas_id                   INTEGER REFERENCES gas_table(gas_id),
        sale_date                TEXT DEFAULT (datetime('now')),
        amount_paid_cash         REAL DEFAULT 0,
        amount_paid_till         REAL DEFAULT 0,
        time_sold                TEXT DEFAULT (datetime('now')),
        source_kipsongo_pioneer  INTEGER DEFAULT 0,
        source_mama_pam          INTEGER DEFAULT 0,
        source_external          INTEGER DEFAULT 0,
        complete_sale            INTEGER DEFAULT 0,
        empty_not_given          INTEGER DEFAULT 0,
        exchange_cylinder        INTEGER DEFAULT 0,
        from_debt                INTEGER DEFAULT 0,
        cleared                  INTEGER DEFAULT 0
    )
""")

# gas_debts
cur.execute("""
    CREATE TABLE IF NOT EXISTS gas_debts (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        gas_id               INTEGER REFERENCES gas_table(gas_id),
        amount_paid          REAL DEFAULT 0.00,
        amount_to_be_paid    REAL,
        date_to_be_paid      TEXT,
        authorized_by        TEXT CHECK (authorized_by IN ('Mama Dan','Baba Dan')),
        empty_cylinder_given INTEGER DEFAULT 0,
        customer_name        TEXT,
        customer_phone       TEXT,
        customer_address     TEXT,
        time                 TEXT DEFAULT (datetime('now')),
        customer_picture     TEXT,
        cleared              INTEGER DEFAULT 0
    )
""")

# gas_debt_payments
cur.execute("""
    CREATE TABLE IF NOT EXISTS gas_debt_payments (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        debt_id      INTEGER REFERENCES gas_debts(id) ON DELETE CASCADE,
        amount       REAL,
        payment_date TEXT DEFAULT (datetime('now'))
    )
""")

# stock_out
cur.execute("""
    CREATE TABLE IF NOT EXISTS stock_out (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        gas_id           INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        cylinder_state   TEXT CHECK (cylinder_state IN ('empty','filled')),
        destination_type TEXT CHECK (destination_type IN ('station','delivery','customer')),
        destination_value TEXT NOT NULL,
        time_out         TEXT DEFAULT (datetime('now'))
    )
""")

# stock_change
cur.execute("""
    CREATE TABLE IF NOT EXISTS stock_change (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        gas_id          INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        action          TEXT NOT NULL,
        quantity_change INTEGER NOT NULL,
        notes           TEXT,
        changed_at      TEXT DEFAULT (datetime('now'))
    )
""")

# users
cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role     TEXT DEFAULT 'user'
    )
""")

# Insert default admin
cur.execute("""
    INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin','admin123','admin')
""")

# Source-specific tables
cur.execute("""
    CREATE TABLE IF NOT EXISTS kipsongo_gas_in_ukweli (
        gas_id        INTEGER PRIMARY KEY REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        number_of_gas INTEGER DEFAULT 0
    )
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS mama_pam_gas_in_ukweli (
        gas_id        INTEGER PRIMARY KEY REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        number_of_gas INTEGER DEFAULT 0
    )
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS external_gas_in_ukweli (
        gas_id        INTEGER PRIMARY KEY REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        number_of_gas INTEGER DEFAULT 0
    )
""")

# buying_company
cur.execute("""
    CREATE TABLE IF NOT EXISTS buying_company (
        company_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT UNIQUE NOT NULL
    )
""")

# Seed suppliers
for name in ['KAFUSH AND JAY', 'DAN SUPPLY', 'NEW SUPPLIER']:
    cur.execute("INSERT OR IGNORE INTO buying_company (company_name) VALUES (?)", (name,))

# company_gas_price
cur.execute("""
    CREATE TABLE IF NOT EXISTS company_gas_price (
        company_id   INTEGER NOT NULL REFERENCES buying_company(company_id) ON DELETE CASCADE,
        gas_id       INTEGER NOT NULL REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        refill_price REAL DEFAULT 0,
        full_price   REAL DEFAULT 0,
        last_updated TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (company_id, gas_id)
    )
""")

# refill_table (no GENERATED ALWAYS - compute total_cost in queries)
cur.execute("""
    CREATE TABLE IF NOT EXISTS refill_table (
        refill_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id  INTEGER REFERENCES buying_company(company_id) ON DELETE CASCADE,
        gas_id      INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        quantity    INTEGER NOT NULL CHECK (quantity > 0),
        unit_price  REAL NOT NULL CHECK (unit_price >= 0),
        refill_time TEXT DEFAULT (datetime('now'))
    )
""")

# stock_in
cur.execute("""
    CREATE TABLE IF NOT EXISTS stock_in (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        gas_id         INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        cylinder_state TEXT CHECK (cylinder_state IN ('empty','filled')),
        source_type    TEXT CHECK (source_type IN ('supplier','Work Station','customer')),
        source_value   TEXT NOT NULL,
        time_in        TEXT DEFAULT (datetime('now'))
    )
""")

# profit_table
cur.execute("""
    CREATE TABLE IF NOT EXISTS profit_table (
        profit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id       INTEGER REFERENCES sales_table(sale_id) ON DELETE SET NULL,
        gas_id        INTEGER REFERENCES gas_table(gas_id) ON DELETE CASCADE,
        company_id    INTEGER REFERENCES buying_company(company_id) ON DELETE SET NULL,
        qty           INTEGER NOT NULL DEFAULT 1,
        revenue       REAL NOT NULL,
        cost          REAL NOT NULL,
        time_recorded TEXT DEFAULT (datetime('now')),
        created_at    TEXT DEFAULT (datetime('now'))
    )
""")

conn.commit()
conn.close()
print("✅ SQLite database created successfully.")
print(f"   Database file: {DATABASE}")
