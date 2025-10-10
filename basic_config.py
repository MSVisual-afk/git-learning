import serial
import time
import pandas as pd
import ipaddress
import textfsm
from ntc_templates.parse import parse_output  #--- Pa sacar la info de show inventory e interfaces.


# ---------------------------- FUNCIONES

def obtener_modelo_serie(ser):
    """Ejecuta 'show inventory' y obtiene modelo y serie con TextFSM."""
    ser.write(b"\x03\n")  # Ctrl+C para limpiar
    time.sleep(1)
    ser.write(b"show inventory\n")
    time.sleep(3)

    salida = ""
    if ser.in_waiting:
        salida = ser.read(ser.in_waiting).decode(errors="ignore")

    try:
        parsed = parse_output(platform="cisco_ios", command="show inventory", data=salida)
        if parsed:
            modelo = parsed[0].get("pid")
            serie = parsed[0].get("sn")
            return modelo, serie, salida
    except Exception as e:
        print(" Error al parsear con TextFSM:", e)

    return None, None, salida


def obtener_interfaces(ser):
    """Ejecuta 'show ip interface brief' y lo parsea con TextFSM."""
    ser.write(b"\x03\n")
    time.sleep(1)
    ser.write(b"show ip interface brief\n")
    time.sleep(3)

    salida = ""
    if ser.in_waiting:
        salida = ser.read(ser.in_waiting).decode(errors="ignore")

    try:
        parsed = parse_output(platform="cisco_ios", command="show ip interface brief", data=salida)
        return parsed  # Lista de diccionarios
    except Exception as e:
        print(" Error al parsear interfaces:", e)

    return []


def interfaces_a_columnas(df, idx, interfaces):
    """
    Agrega dinámicamente cada interfaz como columnas en la fila correspondiente.
    Ejemplo: Fa0/0_IP, Fa0/0_STATUS, Fa0/0_PROTO
    """
    for i in interfaces:
        nombre = i.get("interface")
        if not nombre or not nombre.startswith(("FastEthernet", "GigabitEthernet")):
            continue  # ignoramos seriales y otras

        df.at[idx, f"{nombre}_IP"] = i.get("ip_address", "")
        df.at[idx, f"{nombre}_STATUS"] = i.get("status", "")
        df.at[idx, f"{nombre}_PROTO"] = i.get("proto", "")


def configurar_dispositivo(ser, fila):
    """Configura el dispositivo a partir de la fila del Excel."""
    ser.write(b"\x03\n")
    time.sleep(1)
    ser.write(b"enable\n")
    time.sleep(1)

    comandos = [
        "configure terminal",
        f"hostname {fila['nombre']}",
        f"username {fila['usuario']} password {fila['contrasena']}",
        f"ip domain-name {fila['dominio']}",
        "crypto key generate rsa modulus 1024",
    ]
    for cmd in comandos:
        ser.write(f"{cmd}\n".encode())
        time.sleep(1)

    ser.write(b"1024\n")
    time.sleep(2)

    extra_cmds = [
        "ip ssh version 2",
        "line console 0",
        "login local",
        "line vty 0 4",
        "login local",
        "transport input ssh",
        "transport output ssh",
        "end",
        "write memory",
    ]
    for cmd in extra_cmds:
        ser.write(f"{cmd}\n".encode())
        time.sleep(1)

    print(f" Configuración aplicada a {fila['nombre']}")


def configurar_ip_interfaz(ser, df, idx):
    """Permite elegir interfaz e ingresar IP y máscara, validando errores."""
    print("\n=== Configuración de IP en interfaz ===")

    interfaces = obtener_interfaces(ser)
    if not interfaces:
        print(" No se pudieron obtener interfaces.")
        return

    print("\nInterfaces disponibles:")
    for num, i in enumerate(interfaces, start=1):
        print(f"{num}. {i['interface']}  (IP: {i['ip_address']})")

    try:
        seleccion = int(input("\n Ingresa el número de la interfaz a configurar: ")) - 1
        if seleccion < 0 or seleccion >= len(interfaces):
            print(" Opción inválida.")
            return
        interfaz = interfaces[seleccion]['interface']
    except ValueError:
        print(" Entrada no válida.")
        return

    ip = input(f" Ingresa la IP para {interfaz}: ")
    mascara = input(" Ingresa la máscara de subred (ej. 255.255.255.0): ")

    try:
        ipaddress.IPv4Address(ip)
        ipaddress.IPv4Network(f"{ip}/{mascara}", strict=False)
    except ValueError:
        print(" IP o máscara inválidas. Intenta de nuevo.")
        return

    print(f"\n Configurando {interfaz} con IP {ip} {mascara}...")

    comandos = [
        "configure terminal",
        f"interface {interfaz}",
        f"ip address {ip} {mascara}",
        "no shutdown",
        "end",
        "write memory",
    ]

    for cmd in comandos:
        ser.write(f"{cmd}\n".encode())
        time.sleep(1)

    print(f" Interfaz {interfaz} configurada correctamente con {ip}/{mascara}.")

    # --- Actualiza Excel con los nuevos datos desde el router
    interfaces_actualizadas = obtener_interfaces(ser)
    interfaces_a_columnas(df, idx, interfaces_actualizadas)

def cargar_y_configurar():
    """Lee Excel, configura dispositivos coincidentes y exporta interfaces."""
    ruta_excel = r"C:\Users\moniy\OneDrive\Documentos\UNI\TRABAJOS\Programación de Redes\GIT LEARNING\dispositivos_salazar.xlsx"
    df = pd.read_excel(ruta_excel)

    columnas = {"modelo", "serie", "puerto", "baudios", "nombre", "usuario", "contrasena", "dominio"}
    if not columnas.issubset(df.columns):
        raise ValueError(f"El Excel debe tener las columnas: {columnas}")

    for puerto, baudios in df[["puerto", "baudios"]].drop_duplicates().values:
        try:
            print(f"\n --- Conectando al puerto {puerto}...")
            ser = serial.Serial(puerto, int(baudios), timeout=3)
            time.sleep(2)

            modelo_real, serie_real, salida = obtener_modelo_serie(ser)
            print(f" -- Modelo detectado: {modelo_real}, -- Serie: {serie_real}")

            coincidencias = df[(df["modelo"] == modelo_real) & (df["serie"] == serie_real)]

            if not coincidencias.empty:
                for idx, fila in coincidencias.iterrows():
                    print(" Coincidencia encontrada, configurando...")
                    configurar_dispositivo(ser, fila)

                    # --- Obtener interfaces para las columnas
                    interfaces = obtener_interfaces(ser)
                    if interfaces:
                        interfaces_a_columnas(df, idx, interfaces)
                    else:
                        df.at[idx, "Interfaces"] = "No detectadas"

                    configurar_ip_interfaz(ser, df, idx)


            else:
                print(" No hay coincidencia en el Excel, se omite configuración.")
                print("Salida completa de 'show inventory':\n", salida)

            ser.close()

        except Exception as e:
            print(f" Error en {puerto}: {e}")

    # Guardar resultados en Excel actualizado
    df.to_excel(ruta_excel, index=False)
    print(f"\n --- Archivo Excel actualizado en: {ruta_excel}")


# ========= MAIN =========
if __name__ == "__main__":
    cargar_y_configurar()