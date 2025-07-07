import psycopg2, textwrap

DATABASE_URL = "postgresql://postgres:[James3182.]@db.bjhhadfkerhrejmuhogb.supabase.co:5432/postgres"

sql = textwrap.dedent("""
/* ─────────────────────────────────────────────
   Profit trigger (v4)  – ignores 5‑day refills that
   are already “fully consumed” by sales
   ───────────────────────────────────────────── */
CREATE OR REPLACE FUNCTION f_insert_profit()
RETURNS trigger AS $$
DECLARE
    unit_cost      NUMERIC(10,2);
    v_gas_name     TEXT;

    total_refill   INTEGER;
    total_sold     INTEGER;
BEGIN
    /* 1) brand name  */
    SELECT gas_name INTO v_gas_name
      FROM gas_table
     WHERE gas_id = NEW.gas_id;

    /* ---------- PATH A – COMPLETE SALE ---------------------- */
    IF NEW.complete_sale IS TRUE THEN

        /* cheapest full‑price (except “POWER GAS” fallback rule) */
        SELECT MIN(cgp.full_price)
          INTO unit_cost
          FROM company_gas_price cgp
          JOIN buying_company   bc ON bc.company_id = cgp.company_id
         WHERE cgp.gas_id     = NEW.gas_id
           AND cgp.full_price > 0
           AND (
               v_gas_name IN ('Power','Power 13kg')
               OR bc.company_name <> 'POWER GAS'
           );

        /* fallback to KAFUSH AND JAY (not for Power brands) */
        IF unit_cost IS NULL
           AND v_gas_name NOT IN ('Power','Power 13kg') THEN
            SELECT cg.full_price INTO unit_cost
              FROM company_gas_price cg
              JOIN buying_company bc ON bc.company_id = cg.company_id
             WHERE bc.company_name = 'KAFUSH AND JAY'
               AND cg.gas_id       = NEW.gas_id
             LIMIT 1;
        END IF;

    /* ---------- PATH B – NORMAL REFILL SALE ----------------- */
    ELSE
        /* 2a. Totals in last 5 days */
        SELECT COALESCE(SUM(quantity),0)
          INTO total_refill
          FROM refill_table
         WHERE gas_id      = NEW.gas_id
           AND refill_time >= (CURRENT_TIMESTAMP - INTERVAL '5 days');

        SELECT COUNT(*)          /* each normal sale = 1 cylinder */
          INTO total_sold
          FROM sales_table
         WHERE gas_id       = NEW.gas_id
           AND complete_sale = FALSE
           AND time_sold    >= (CURRENT_TIMESTAMP - INTERVAL '5 days');

        /* 2b. Only use refill prices if there are still “un‑used” cylinders */
        IF total_sold < total_refill THEN
            SELECT MIN(r.unit_price)
              INTO unit_cost
              FROM refill_table   r
              JOIN buying_company bc ON bc.company_id = r.company_id
             WHERE r.gas_id      = NEW.gas_id
               AND r.refill_time >= (CURRENT_TIMESTAMP - INTERVAL '5 days')
               AND (
                     v_gas_name IN ('Power','Power 13kg')
                     OR bc.company_name <> 'POWER GAS'
                   );
        END IF;

        /* 2c. Fallback to KAFUSH AND JAY refill price (not for Power) */
        IF unit_cost IS NULL
           AND v_gas_name NOT IN ('Power','Power 13kg') THEN
            SELECT cg.refill_price
              INTO unit_cost
              FROM company_gas_price cg
              JOIN buying_company bc ON bc.company_id = cg.company_id
             WHERE bc.company_name = 'KAFUSH AND JAY'
               AND cg.gas_id       = NEW.gas_id
             LIMIT 1;
        END IF;
    END IF;

    /* 3) ultimate safety */
    IF unit_cost IS NULL THEN
        unit_cost := 0;
    END IF;

    /* 4) insert profit row (qty = 1) */
    INSERT INTO profit_table (
        sale_id, gas_id, company_id,
        qty, revenue, cost
    )
    VALUES (
        NEW.sale_id,
        NEW.gas_id,
        NULL,
        1,
        NEW.amount_paid_cash + NEW.amount_paid_till,
        unit_cost
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

/* ── (re)attach trigger ───────────────────────── */
DROP TRIGGER IF EXISTS trg_sales_profit ON sales_table;

CREATE TRIGGER trg_sales_profit
AFTER INSERT ON sales_table
FOR EACH ROW
EXECUTE FUNCTION f_insert_profit();
""")

with psycopg2.connect(DATABASE_URL, sslmode="require") as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
print("✅ Profit trigger (v4) installed.")
