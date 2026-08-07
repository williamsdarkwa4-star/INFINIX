from werkzeug.security import generate_password_hash
import sqlite3


DATABASE = "zenith.db"


def get_db():

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    return conn



def create_admin():

    conn = get_db()
    cursor = conn.cursor()

    username = "Williams"
    password = "Williams12"

    hashed_password = generate_password_hash(password)


    existing = cursor.execute(
        """
        SELECT * FROM admins
        WHERE username=?
        """,
        (username,)
    ).fetchone()


    if not existing:

        cursor.execute(
            """
            INSERT INTO admins
            (
            username,
            password
            )

            VALUES(?,?)

            """,
            (
            username,
            hashed_password
            )
        )


        conn.commit()

        print("Admin created")
        print("Username: Williams")
        print("Password: Williams12")


    else:

        print("Admin already exists")


    conn.close()



if __name__ == "__main__":

    create_tables()

    create_plans()

    create_admin()

    print("Database setup completed!")
