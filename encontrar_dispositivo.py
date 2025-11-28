#!/usr/bin/env python3
from netmiko import ConnectHandler, NetMikoAuthenticationException, NetMikoTimeoutException
import re
import getpass
import time
import ipaddress
from typing import Optional, Dict, List, Tuple

COMMON_USERNAMES = ["cisco", "admin", "cisco123"]
COMMON_PASSWORDS = ["cisco", "cisco123", "cisco99", "admin"]

CMD_ARP = "show ip arp"
CMD_MAC = "show mac address-table"
CMD_MAC_ALT = "show mac-address-table"
CMD_CDP_INT_FMT = "show cdp neighbors {} detail"
CMD_VER = "show version"

def try_connect(host: str, user_given: str, pass_given: str, timeout: int = 7):
    combos = [(user_given, pass_given)]
    combos += [(user_given, p) for p in COMMON_PASSWORDS if p != pass_given]
    combos += [(u, pass_given) for u in COMMON_USERNAMES if u != user_given]
    for u in COMMON_USERNAMES:
        for p in COMMON_PASSWORDS:
            if (u,p) not in combos:
                combos.append((u,p))

    for user, pwd in combos:
        device = {
            "device_type": "cisco_ios",
            "host": host,
            "username": user,
            "password": pwd,
            "timeout": timeout,
        }
        try:
            conn = ConnectHandler(**device)
            try: conn.enable()
            except: pass
            return conn, (user,pwd)
        except: continue
    return None, None

def normalize_mac_to_dots(mac_raw: str):
    if not mac_raw:
        return None
    s = mac_raw.strip().lower().replace(".", "").replace(":", "").replace("-", "")
    if len(s) != 12:
        return None
    return f"{s[0:4]}.{s[4:8]}.{s[8:12]}"

def find_mac_in_arp(arp_output: str, ip_target: str):
    for line in arp_output.splitlines():
        if ip_target in line:
            m = re.search(r"([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})", line, re.I)
            if m: return normalize_mac_to_dots(m.group(1))
            m2 = re.search(r"([0-9a-f]{2}(:|-)){5}[0-9a-f]{2}", line, re.I)
            if m2: return normalize_mac_to_dots(m2.group(0))
            m3 = re.search(r"([0-9a-f]{12})", line.replace(" ", ""), re.I)
            if m3: return normalize_mac_to_dots(m3.group(1))
    return None

def find_interface_by_mac(mac_table_output: str, mac_normalized: str):
    for line in mac_table_output.splitlines():
        if mac_normalized and mac_normalized.lower() in line.lower():
            parts = line.split()
            if len(parts) >= 4:
                return parts[-1]
    return None

def parse_cdp_int_detail_for_ip(cdp_output: str):
    if not cdp_output or "Device ID" not in cdp_output:
        return None

    device_id = None
    ips = []
    neighbor_port = None

    for line in cdp_output.splitlines():
        line = line.strip()
        if line.lower().startswith("device id:"):
            device_id = line.split(":",1)[1].strip()
        m_ip = re.search(r"IP address:\s*([\d\.]+)", line)
        if m_ip: ips.append(m_ip.group(1))
        m_port = re.search(r"Port ID .*:\s*(\S+)", line)
        if m_port: neighbor_port = m_port.group(1)

    return {"device_id": device_id, "ips": ips, "neighbor_port": neighbor_port} if device_id else None

def get_hostname_from_show_ver(show_ver: str):
    for line in show_ver.splitlines():
        if " uptime " in line:
            return line.split()[0]
        if line.lower().startswith("hostname"):
            parts = line.split()
            if len(parts) >= 2:
                return parts[-1]
    return None

def rastrear_ip_hasta_host(start_switch: str, user: str, pwd: str, ip_objetivo: str):
    visited_hosts = set()
    current_host = start_switch

    while True:
        conn, creds = try_connect(current_host, user, pwd)
        if conn is None:
            return None

        show_ver = conn.send_command(CMD_VER)
        hostname = get_hostname_from_show_ver(show_ver) or current_host

        arp_out = conn.send_command(CMD_ARP)
        mac_found = find_mac_in_arp(arp_out, ip_objetivo)
        if not mac_found:
            conn.disconnect()
            return None

        mac_table_out = conn.send_command(CMD_MAC)
        if not mac_table_out or "Invalid input" in mac_table_out:
            mac_table_out = conn.send_command(CMD_MAC_ALT)

        intf = find_interface_by_mac(mac_table_out, mac_found)
        if not intf:
            conn.disconnect()
            return None

        cdp_out = conn.send_command(CMD_CDP_INT_FMT.format(intf))
        vecino_info = parse_cdp_int_detail_for_ip(cdp_out)

        conn.disconnect()

        # si no hay vecino -> host final
        if not vecino_info:
            return {
                "ip": ip_objetivo,
                "device": hostname,
                "interface": intf,
                "mac": mac_found
            }

        # si tiene vecino -> saltamos
        neigh_ips = vecino_info.get("ips", [])
        if not neigh_ips:
            return {
                "ip": ip_objetivo,
                "device": hostname,
                "interface": intf,
                "mac": mac_found
            }

        next_host = neigh_ips[0]
        current_host = next_host
        time.sleep(1)

def main():
    start_switch = input("Switch inicial: ").strip()
    user = input("Usuario: ").strip()
    pwd = getpass.getpass("Contraseña: ").strip()
    ip_obj = input("IP objetivo: ").strip()

    data = rastrear_ip_hasta_host(start_switch, user, pwd, ip_obj)
    if not data:
        print("No se encontró.")
        return

    # --- SOLO RESULTADO FINAL ----
    print(f"\nIP: {data['ip']}")
    print(f"Dispositivo: {data['device']}")
    print(f"Interfaz: {data['interface']}")
    print(f"MAC: {data['mac']}\n")

if __name__ == "__main__":
    main()
