from getpass import getpass
from app.db.client import get_database
from app.repositories.user import UserRepository
from app.core.security import hash_password, verify_password

db = get_database()
repo = UserRepository(db)

emails = [
    "s.nair@carbonops.ongc",
    "m.sinha@carbonops.ongc",
    "l.menon@carbonops.ongc",
]

users = [repo.get_raw_by_email(email) for email in emails]

# Check all accounts before making any changes
if any(user is None for user in users):
    print("One or more users were not found. No changes made.")

elif any(user.get("status") != "Active" for user in users):
    print("One or more accounts are inactive. No changes made.")

else:
    password = getpass("Enter the common demo password: ")
    confirm = getpass("Confirm the common demo password: ")

    if password != confirm:
        print("Passwords do not match. No changes made.")

    elif len(password) < 8:
        print("Password must contain at least 8 characters.")

    else:
        password_hash = hash_password(password)

        for email in emails:
            repo.col.update_one(
                {"email": email},
                {"$set": {"passwordHash": password_hash}}
            )

        print("\nPassword verification:")

        for email in emails:
            user = repo.get_raw_by_email(email)
            valid = verify_password(password, user["passwordHash"])
            print(email, ":", valid)

db.client.close()