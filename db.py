# db.py
import psycopg2
from sqlalchemy import select

DATABASE_URL = "postgresql://ukwelitradersbase_user:KQTv3VjbP9E7lCo4wAmERxGrg7arHHlp@dpg-d0b0e82dbo4c73c9st5g-a.oregon-postgres.render.com/ukwelitradersbase"

def get_connection():
    return psycopg2.connect(DATABASE_URL)
select * FROM gas_table;

