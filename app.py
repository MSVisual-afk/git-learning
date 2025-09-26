import socket
print("HELLO word")

hostname = socket.gethostname()
print(f"HOSTNAME: {hostname}")

ipaddr= socket.gethostbyname(hostname)
print(f"IP ADDRESS:{ipaddr}")

for i in range(10):
    print(f"count:{i}")

num_a=int(input("DAME EL PRIMER NUMERO: "))
num_b=int(input("DAME EL SEGUNDO NUMERO: "))
print(f"La suma es: {num_a + num_b}")

print(f"La resta es: {num_a - num_b}")

print(f"La multiplicacion es: {num_a * num_b}")