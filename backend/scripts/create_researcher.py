from getpass import getpass
from argon2 import PasswordHasher

password = getpass("Researcher password (at least 14 characters): ")
if len(password) < 14:
    raise SystemExit("Choose a password of at least 14 characters.")
print(PasswordHasher().hash(password))
