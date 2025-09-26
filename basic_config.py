import serial
import time
import pandas as pd
import re

# - - - - - - - - - - - FUNCIONES 

def obtener_modelo_serie(ser):
    """Ejecuta 'show inventory' y extrae modelo (PID) y serie (SN)."""
    ser.write(b"show inventory\n")
    time.sleep(2)

    salida = ""
    if ser.in_waiting:
        salida = ser.read(ser.in_waiting).decode(errors="ignore")

    regex_modelo = re.search(r"PID:\s*([\w\-/]+)", salida)
    regex_serie = re.search(r"SN:\s*([\w\d]+)", salida)

    modelo = regex_modelo.group(1) if regex_modelo else None
    serie = regex_serie.group(1) if regex_serie else None

    return modelo, serie, salida


def configurar_dispositivo(ser, nombre, usuario, contrasena, dominio):
    """Comandos de configuración al dispositivo."""
    comandos = [
        "configure terminal",
        f"hostname {nombre}",
        f"username {usuario} password {contrasena}",
        f"ip domain-name {dominio}",
        "crypto key generate rsa",
    ]

    for cmd in comandos:
        ser.write(f"{cmd}\n".encode())
        time.sleep(1)

    # Tamaño de clave
    ser.write(b"1024\n")
    time.sleep(2)

    # Config extra
    extra_cmds = [
        "ip ssh version 2",
        "line console 0",
        "login local",
        "line vty 0 4",
        "login local",
        "transport input ssh",
        "transport output ssh",
        "end",
        "write memory"
    ]

    for cmd in extra_cmds:
        ser.write(f"{cmd}\n".encode())
        time.sleep(1)

    print(f" Configuración aplicada a {nombre}")


def cargar_y_configurar():
    """Lee el Excel y configura el dispositivo si hay coincidencia."""
    df = pd.read_excel(r"C:\Users\moniy\OneDrive\Documentos\UNI\TRABAJOS\Programación de Redes\GIT LEARNING\dispositivos_salazar.xlsx")
    

    # Validar columnas
    columnas = {"modelo", "serie", "puerto", "baudios", "nombre", "usuario", "contrasena", "dominio"}
    if not columnas.issubset(df.columns):
        raise ValueError(f"El Excel debe tener las columnas: {columnas}")

    # Tomar datos de conexión del Excel (puerto y baudios)
    for _, fila in df.iterrows():
        puerto = fila["puerto"]
        baudios = int(fila["baudios"])

        try:
            print(f"\n Conectando al puerto {puerto}...")
            ser = serial.Serial(puerto, baudios, timeout=2)
            time.sleep(2)

            # Obtener modelo y serie reales del dispositivo
            modelo_real, serie_real, salida = obtener_modelo_serie(ser)
            print(f"Modelo detectado: {modelo_real}, Serie: {serie_real}")

            # Comparar con Excel
            if modelo_real == fila["modelo"] and serie_real == fila["serie"]:
                print("Coincidencia encontrada en Excel, configurando...")
                configurar_dispositivo(
                    ser,
                    fila["nombre"],
                    fila["usuario"],
                    fila["contrasena"],
                    fila["dominio"]
                )
            else:
                print(" No coincide con el Excel, se omite configuración.")
                print("Salida completa de 'show inventory':\n", salida)

            ser.close()

        except Exception as e:
            print(f" Error en {puerto}: {e}")


# - - - - - - - - - - - MAIN 
if __name__ == "__main__":

    cargar_y_configurar()