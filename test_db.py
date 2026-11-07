
from db import get_db_connection

try:
    connection = get_db_connection()

    print("================================")
    print("DATABASE CONNECTED SUCCESSFULLY!")
    print("================================")

    cursor = connection.cursor()

    cursor.execute("SELECT version();")

    result = cursor.fetchone()

    print("PostgreSQL Version:")
    print(result[0])

    cursor.close()
    connection.close()

except Exception as error:
    print("DATABASE CONNECTION FAILED!")
    print(error)
