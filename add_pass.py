from cryptography.fernet import Fernet

# pass_one = input("Enter the password:")
# pass_two = input("Enter the password again:")
pass_one = "vuefqwoppjkfqjda"


key = b'qHKP1WZk5yxU4uW3ktNLlzwHLFuSwzRExe4_yj3VolY='
fernet = Fernet(key)
encMessage = fernet.encrypt(pass_one.encode())
print(encMessage)
