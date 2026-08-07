from database import get_db
from werkzeug.security import generate_password_hash


db = get_db()


username = "Williams"
password = "Williams12"


hashed = generate_password_hash(password)


db.execute("""
INSERT INTO admins
(username, password)

VALUES(?,?)

""",
(username, hashed))


db.commit()

db.close()


print("Admin created")
