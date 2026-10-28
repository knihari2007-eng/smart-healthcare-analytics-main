import getpass

from werkzeug.security import generate_password_hash

from db import get_db_connection


def create_admin():
    username = input("Enter administrator username: ").strip()
    password = getpass.getpass("Enter administrator password: ")
    confirm_password = getpass.getpass("Confirm password: ")

    if not username or len(username) > 50:
        print("Username must contain 1 to 50 characters.")
        return

    if len(password) < 12:
        print("Use a password with at least 12 characters.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        password_hash = generate_password_hash(password)

        cursor.execute(
            """
            INSERT INTO users (username, password_hash)
            VALUES (%s, %s)
            """,
            (username, password_hash)
        )

        connection.commit()
        print("Administrator account created successfully.")

    except Exception as error:
        if connection is not None and connection.is_connected():
            connection.rollback()

        print("Could not create administrator account.")
        print("Check whether the username already exists and verify the database connection.")

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

if __name__ == "__main__":
    create_admin()