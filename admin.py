"""
EZ4ME — Admin CLI
==================
Herramienta de linea de comandos para gestionar keys.

Uso:
    python admin.py add  "nombre del usuario"
    python admin.py list
    python admin.py reset  XXXX-XXXX-XXXX-XXXX
    python admin.py delete XXXX-XXXX-XXXX-XXXX
"""

import sys
import json
import urllib.request
import urllib.error

# ============================================================
#  CONFIGURA ESTO (igual que en server.py)
# ============================================================
SERVER_URL    = "http://localhost:8080"   # Cambia por tu IP/dominio
ADMIN_SECRET  = "CAMBIA_ESTO_POR_UNA_CONTRASENA_LARGA"

# ============================================================
#  Helpers
# ============================================================
def post(endpoint: str, payload: dict) -> dict:
    payload["secret"] = ADMIN_SECRET
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        SERVER_URL + endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except Exception as ex:
        return {"error": str(ex)}

def get_list() -> dict:
    req = urllib.request.Request(
        SERVER_URL + "/admin/list",
        headers={"X-Secret": ADMIN_SECRET},
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as ex:
        return {"error": str(ex)}

# ============================================================
#  Colores ANSI
# ============================================================
G  = "\x1b[32m"
R  = "\x1b[31m"
Y  = "\x1b[33m"
C  = "\x1b[36m"
GR = "\x1b[90m"
W  = "\x1b[97m"
B  = "\x1b[1m"
RS = "\x1b[0m"

def banner():
    print(f"{C}{B}")
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║         EZ4ME  —  Admin CLI                     ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print(f"{RS}")

# ============================================================
#  Comandos
# ============================================================
def cmd_add(note: str):
    res = post("/admin/add", {"note": note})
    if "key" in res:
        print(f"\n  {G}{B}Key creada:{RS}")
        print(f"  {W}{B}{res['key']}{RS}")
        print(f"  {GR}Para: {note}{RS}\n")
    else:
        print(f"  {R}Error: {res}{RS}")

def cmd_list():
    res = get_list()
    if "keys" not in res:
        print(f"  {R}Error: {res}{RS}")
        return

    keys = res["keys"]
    print(f"\n  {C}Total: {len(keys)} keys{RS}\n")
    print(f"  {'KEY':<22} {'ESTADO':<12} {'NOTA':<20} {'HWID ATADO':<18} {'USOS'}")
    print(f"  {GR}{'-'*90}{RS}")

    for k in keys:
        hwid = k["hwid_bound"]
        if hwid == "NO ATADA":
            estado = f"{Y}SIN ATAR{RS}"
            hwid_str = f"{GR}—{RS}"
        else:
            estado = f"{G}ATADA{RS}"
            hwid_str = f"{C}{hwid[:16]}{RS}"

        nota = k["note"][:18] if k["note"] else "—"
        print(f"  {W}{k['key']}{RS}  {estado:<20} {nota:<20} {hwid_str:<26} {k['use_count']}")
    print()

def cmd_reset(key: str):
    res = post("/admin/reset", {"key": key.upper()})
    if res.get("status") == "ok":
        print(f"\n  {G}HWID reseteado para {key}{RS}")
        print(f"  {GR}La proxima vez que la use, se atara al nuevo PC.{RS}\n")
    else:
        print(f"  {R}Error: {res}{RS}")

def cmd_delete(key: str):
    confirm = input(f"  {Y}Seguro que quieres eliminar {key}? (s/n): {RS}").strip().lower()
    if confirm != "s":
        print(f"  {GR}Cancelado.{RS}")
        return
    res = post("/admin/delete", {"key": key.upper()})
    if res.get("status") == "ok":
        print(f"\n  {R}Key {key} eliminada.{RS}\n")
    else:
        print(f"  {R}Error: {res}{RS}")

# ============================================================
#  Main
# ============================================================
def usage():
    print(f"""
  {C}Uso:{RS}
    python admin.py add    {GR}"nombre del usuario"{RS}
    python admin.py list
    python admin.py reset  {GR}XXXX-XXXX-XXXX-XXXX{RS}
    python admin.py delete {GR}XXXX-XXXX-XXXX-XXXX{RS}
""")

if __name__ == "__main__":
    banner()

    if len(sys.argv) < 2:
        usage()
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "add":
        note = sys.argv[2] if len(sys.argv) > 2 else "sin nombre"
        cmd_add(note)
    elif cmd == "list":
        cmd_list()
    elif cmd == "reset":
        if len(sys.argv) < 3:
            print(f"  {R}Falta la key.{RS}")
        else:
            cmd_reset(sys.argv[2])
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print(f"  {R}Falta la key.{RS}")
        else:
            cmd_delete(sys.argv[2])
    else:
        print(f"  {R}Comando desconocido: {cmd}{RS}")
        usage()
