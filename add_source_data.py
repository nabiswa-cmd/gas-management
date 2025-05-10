import psycopg2

DATABASE_URL = "postgresql://ukwelitradersbase_user:KQTv3VjbP9E7lCo4wAmERxGrg7arHHlp@dpg-d0b0e82dbo4c73c9st5g-a.oregon-postgres.render.com/ukwelitradersbase"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Example data to add
    # Ensure these gas IDs already exist in the gas_table
    data_to_insert = [
        # Format: (gas_id, number_of_gas)
        (1, 5),
        (2, 3),
        (3, 7)
    ]

    # --- Add data to Kipsongo ---
    print("Adding data to kipsongo_gas_in_ukweli...")
    for gas_id, quantity in data_to_insert:
        cur.execute("""
            INSERT INTO kipsongo_gas_in_ukweli (gas_id, number_of_gas)
            VALUES (%s, %s)
            ON CONFLICT (gas_id) DO UPDATE
            SET number_of_gas = kipsongo_gas_in_ukweli.number_of_gas + EXCLUDED.number_of_gas;
        """, (gas_id, quantity))
    print("Data added to kipsongo_gas_in_ukweli successfully.")

    # --- Add data to Mama Pam ---
    print("Adding data to mama_pam_gas_in_ukweli...")
    for gas_id, quantity in data_to_insert:
        cur.execute("""
            INSERT INTO mama_pam_gas_in_ukweli (gas_id, number_of_gas)
            VALUES (%s, %s)
            ON CONFLICT (gas_id) DO UPDATE
            SET number_of_gas = mama_pam_gas_in_ukweli.number_of_gas + EXCLUDED.number_of_gas;
        """, (gas_id, quantity))
    print("Data added to mama_pam_gas_in_ukweli successfully.")

    # --- Add data to External ---
    print("Adding data to external_gas_in_ukweli...")
    for gas_id, quantity in data_to_insert:
        cur.execute("""
            INSERT INTO external_gas_in_ukweli (gas_id, number_of_gas)
            VALUES (%s, %s)
            ON CONFLICT (gas_id) DO UPDATE
            SET number_of_gas = external_gas_in_ukweli.number_of_gas + EXCLUDED.number_of_gas;
        """, (gas_id, quantity))
    print("Data added to external_gas_in_ukweli successfully.")

    conn.commit()

except Exception as e:
    print(f"❌ Error adding data to source tables: {e}")

finally:
    if 'conn' in locals():
        conn.close()
