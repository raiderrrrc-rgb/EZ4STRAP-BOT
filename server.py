"""
EZ4ME — Servidor de Autenticacion v2
======================================
Nuevas funcionalidades:
  - Autenticacion en 2 pasos: KEY primero, luego nombre de Discord
  - Deteccion de nombres duplicados o falsos → Blacklist automatica
  - Gestion de blacklist (agregar/ver/quitar)
  - Delete de keys mejorado

Endpoints:
    POST /auth            — Paso 1: valida key + hwid
    POST /auth/discord    — Paso 2: registra nombre de Discord en la key
    POST /admin/add       — Crea una key nueva
    POST /admin/reset     — Resetea el HWID de una key
    GET  /admin/list      — Lista todas las keys
    POST /admin/delete    — Elimina una key
    POST /admin/blacklist/add    — Agrega a blacklist manualmente
    POST /admin/blacklist/remove — Quita de la blacklist
    GET  /admin/blacklist/list   — Lista la blacklist
"""

import sqlite3
import secrets
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# ============================================================
#  CONFIGURA ESTO
# ============================================================
DB_PATH      = "ez4me_keys.db"
ADMIN_SECRET = "CAMBIA_ESTO_POR_UNA_CONTRASENA_LARGA"   # <-- CAMBIA ESTO
HOST         = "0.0.0.0"
PORT         = 8080

# ============================================================
#  Base de datos
# ============================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        # Tabla principal de keys
        db.execute("""
            CREATE TABLE IF NOT EXISTS keys (
                key             TEXT PRIMARY KEY,
                hwid_bound      TEXT DEFAULT NULL,
                discord_name    TEXT DEFAULT NULL,
                note            TEXT DEFAULT '',
                created_at      TEXT NOT NULL,
                bound_at        TEXT DEFAULT NULL,
                discord_set_at  TEXT DEFAULT NULL,
                last_used       TEXT DEFAULT NULL,
                use_count       INTEGER DEFAULT 0,
                awaiting_discord INTEGER DEFAULT 0
            )
        """)
        # Tabla de blacklist
        db.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_name TEXT NOT NULL UNIQUE,
                reason      TEXT DEFAULT 'nombre duplicado o falso',
                banned_at   TEXT NOT NULL
            )
        """)
        db.commit()
    print(f"[DB] Base de datos lista: {DB_PATH}")

def generate_key() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    segments = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
    return "-".join(segments)

def require_admin(data: dict) -> bool:
    return data.get("secret") == ADMIN_SECRET

# ============================================================
#  POST /auth
#  Paso 1: Valida key + HWID
#  Body: { "key": "XXXX-XXXX-XXXX-XXXX", "hwid": "ABCDEF..." }
#
#  Respuestas:
#    {"status": "ok"}               — key valida, HWID correcto
#    {"status": "bound"}            — primer uso, key atada al HWID
#    {"status": "need_discord"}     — key OK pero falta nombre de Discord
#    {"status": "denied"}           — key pertenece a otro PC
#    {"status": "invalid"}          — key no existe
#    {"status": "blacklisted"}      — usuario en la blacklist
# ============================================================
@app.route("/auth", methods=["POST"])
def auth():
    data = request.get_json(force=True, silent=True) or {}
    key  = str(data.get("key",  "")).strip().upper()
    hwid = str(data.get("hwid", "")).strip().upper()

    if not key or not hwid:
        return jsonify({"status": "invalid", "msg": "Faltan campos"}), 400

    now = datetime.utcnow().isoformat()

    with get_db() as db:
        row = db.execute("SELECT * FROM keys WHERE key = ?", (key,)).fetchone()

        if not row:
            print(f"[AUTH] INVALID   key={key} hwid={hwid}")
            return jsonify({"status": "invalid"})

        # Primera vez — atar al HWID y pedir Discord
        if row["hwid_bound"] is None:
            db.execute("""
                UPDATE keys
                SET hwid_bound = ?, bound_at = ?, last_used = ?,
                    use_count = use_count + 1, awaiting_discord = 1
                WHERE key = ?
            """, (hwid, now, now, key))
            db.commit()
            print(f"[AUTH] BOUND     key={key} hwid={hwid} — esperando Discord")
            return jsonify({
                "status": "need_discord",
                "msg": "Key atada. Ahora ingresa tu nombre de Discord."
            })

        # HWID diferente — denegado
        if row["hwid_bound"] != hwid:
            print(f"[AUTH] DENIED    key={key} tried={hwid} real={row['hwid_bound']}")
            return jsonify({"status": "denied", "msg": "Esta key pertenece a otro PC"})

        # HWID correcto pero falta Discord
        if not row["discord_name"] or row["awaiting_discord"]:
            db.execute("""
                UPDATE keys SET last_used = ?, use_count = use_count + 1
                WHERE key = ?
            """, (now, key))
            db.commit()
            return jsonify({
                "status": "need_discord",
                "msg": "Ingresa tu nombre de Discord para continuar."
            })

        # Todo OK
        db.execute("""
            UPDATE keys SET last_used = ?, use_count = use_count + 1
            WHERE key = ?
        """, (now, key))
        db.commit()
        print(f"[AUTH] OK        key={key} discord={row['discord_name']} uses={row['use_count']+1}")
        return jsonify({"status": "ok", "discord": row["discord_name"]})

# ============================================================
#  POST /auth/discord
#  Paso 2: Registra el nombre de Discord en la key
#  Body: { "key": "XXXX-XXXX-XXXX-XXXX", "hwid": "...", "discord_name": "usuario#0000" }
#
#  Respuestas:
#    {"status": "ok"}           — nombre registrado correctamente
#    {"status": "blacklisted"}  — nombre en la blacklist
#    {"status": "duplicate"}    — nombre ya usado por otra key (→ blacklist)
#    {"status": "denied"}       — HWID incorrecto
#    {"status": "invalid"}      — key no existe
# ============================================================
@app.route("/auth/discord", methods=["POST"])
def auth_discord():
    data         = request.get_json(force=True, silent=True) or {}
    key          = str(data.get("key",          "")).strip().upper()
    hwid         = str(data.get("hwid",         "")).strip().upper()
    discord_name = str(data.get("discord_name", "")).strip()

    if not key or not hwid or not discord_name:
        return jsonify({"status": "invalid", "msg": "Faltan campos"}), 400

    now = datetime.utcnow().isoformat()

    with get_db() as db:
        row = db.execute("SELECT * FROM keys WHERE key = ?", (key,)).fetchone()

        if not row:
            return jsonify({"status": "invalid"})

        if row["hwid_bound"] != hwid:
            return jsonify({"status": "denied", "msg": "HWID incorrecto"})

        # Verificar si el nombre está en la blacklist
        bl = db.execute(
            "SELECT * FROM blacklist WHERE LOWER(discord_name) = LOWER(?)",
            (discord_name,)
        ).fetchone()
        if bl:
            print(f"[AUTH] BLACKLISTED discord={discord_name} key={key}")
            return jsonify({
                "status": "blacklisted",
                "msg": "Tu nombre de Discord está en la blacklist de EZ4STRAP. Contacta al soporte."
            })

        # Verificar nombre duplicado (otra key con mismo discord_name y HWID diferente)
        duplicate = db.execute(
            "SELECT * FROM keys WHERE LOWER(discord_name) = LOWER(?) AND key != ?",
            (discord_name, key)
        ).fetchone()
        if duplicate:
            # Agregar automáticamente a la blacklist
            try:
                db.execute(
                    "INSERT INTO blacklist (discord_name, reason, banned_at) VALUES (?, ?, ?)",
                    (discord_name, "nombre duplicado detectado en autenticacion", now)
                )
                db.commit()
            except Exception:
                pass  # Ya estaba en la blacklist
            print(f"[AUTH] DUPLICATE discord={discord_name} → BLACKLISTED")
            return jsonify({
                "status": "duplicate",
                "msg": "Nombre duplicado detectado. Has sido agregado a la blacklist de EZ4STRAP."
            })

        # Guardar nombre de Discord
        db.execute("""
            UPDATE keys
            SET discord_name = ?, discord_set_at = ?, awaiting_discord = 0,
                last_used = ?, use_count = use_count + 1
            WHERE key = ?
        """, (discord_name, now, now, key))
        db.commit()

        print(f"[AUTH] DISCORD SET  key={key} discord={discord_name}")
        return jsonify({"status": "ok", "discord": discord_name})

# ============================================================
#  POST /admin/add
#  Body: { "secret": "...", "note": "nombre del usuario" }
# ============================================================
@app.route("/admin/add", methods=["POST"])
def admin_add():
    data = request.get_json(force=True, silent=True) or {}
    if not require_admin(data):
        return jsonify({"error": "No autorizado"}), 403

    note = str(data.get("note", "")).strip()
    key  = generate_key()
    now  = datetime.utcnow().isoformat()

    with get_db() as db:
        db.execute(
            "INSERT INTO keys (key, note, created_at) VALUES (?, ?, ?)",
            (key, note, now)
        )
        db.commit()

    print(f"[ADMIN] KEY CREADA  key={key} note={note}")
    return jsonify({"status": "ok", "key": key, "note": note})

# ============================================================
#  POST /admin/reset
#  Body: { "secret": "...", "key": "XXXX-XXXX-XXXX-XXXX" }
# ============================================================
@app.route("/admin/reset", methods=["POST"])
def admin_reset():
    data = request.get_json(force=True, silent=True) or {}
    if not require_admin(data):
        return jsonify({"error": "No autorizado"}), 403

    key = str(data.get("key", "")).strip().upper()
    if not key:
        return jsonify({"error": "Falta key"}), 400

    with get_db() as db:
        row = db.execute("SELECT * FROM keys WHERE key = ?", (key,)).fetchone()
        if not row:
            return jsonify({"error": "Key no encontrada"}), 404

        db.execute("""
            UPDATE keys
            SET hwid_bound = NULL, bound_at = NULL,
                discord_name = NULL, discord_set_at = NULL, awaiting_discord = 0
            WHERE key = ?
        """, (key,))
        db.commit()

    print(f"[ADMIN] RESET   key={key}")
    return jsonify({"status": "ok", "msg": f"Key {key} reseteada (HWID + Discord)"})

# ============================================================
#  GET /admin/list
#  Headers: X-Secret: ...
# ============================================================
@app.route("/admin/list", methods=["GET"])
def admin_list():
    secret = request.headers.get("X-Secret", "")
    if secret != ADMIN_SECRET:
        return jsonify({"error": "No autorizado"}), 403

    with get_db() as db:
        rows = db.execute("SELECT * FROM keys ORDER BY created_at DESC").fetchall()

    result = []
    for r in rows:
        result.append({
            "key":          r["key"],
            "note":         r["note"],
            "discord_name": r["discord_name"] or "—",
            "hwid_bound":   r["hwid_bound"]   or "NO ATADA",
            "bound_at":     r["bound_at"]      or "—",
            "last_used":    r["last_used"]     or "—",
            "use_count":    r["use_count"],
            "created_at":   r["created_at"],
        })

    return jsonify({"status": "ok", "count": len(result), "keys": result})

# ============================================================
#  POST /admin/delete
#  Body: { "secret": "...", "key": "XXXX-XXXX-XXXX-XXXX" }
# ============================================================
@app.route("/admin/delete", methods=["POST"])
def admin_delete():
    data = request.get_json(force=True, silent=True) or {}
    if not require_admin(data):
        return jsonify({"error": "No autorizado"}), 403

    key = str(data.get("key", "")).strip().upper()
    if not key:
        return jsonify({"error": "Falta key"}), 400

    with get_db() as db:
        row = db.execute("SELECT * FROM keys WHERE key = ?", (key,)).fetchone()
        if not row:
            return jsonify({"error": "Key no encontrada"}), 404

        info = {
            "key":          key,
            "note":         row["note"],
            "discord_name": row["discord_name"] or "—"
        }
        db.execute("DELETE FROM keys WHERE key = ?", (key,))
        db.commit()

    print(f"[ADMIN] KEY ELIMINADA  key={key}")
    return jsonify({"status": "ok", "deleted": info})

# ============================================================
#  POST /admin/blacklist/add
#  Body: { "secret": "...", "discord_name": "...", "reason": "..." }
# ============================================================
@app.route("/admin/blacklist/add", methods=["POST"])
def blacklist_add():
    data = request.get_json(force=True, silent=True) or {}
    if not require_admin(data):
        return jsonify({"error": "No autorizado"}), 403

    name   = str(data.get("discord_name", "")).strip()
    reason = str(data.get("reason", "ban manual por administrador")).strip()
    if not name:
        return jsonify({"error": "Falta discord_name"}), 400

    now = datetime.utcnow().isoformat()
    with get_db() as db:
        try:
            db.execute(
                "INSERT INTO blacklist (discord_name, reason, banned_at) VALUES (?, ?, ?)",
                (name, reason, now)
            )
            db.commit()
        except sqlite3.IntegrityError:
            return jsonify({"status": "already_blacklisted", "msg": f"{name} ya está en la blacklist"})

    print(f"[BLACKLIST] ADDED  discord={name} reason={reason}")
    return jsonify({"status": "ok", "msg": f"{name} agregado a la blacklist"})

# ============================================================
#  POST /admin/blacklist/remove
#  Body: { "secret": "...", "discord_name": "..." }
# ============================================================
@app.route("/admin/blacklist/remove", methods=["POST"])
def blacklist_remove():
    data = request.get_json(force=True, silent=True) or {}
    if not require_admin(data):
        return jsonify({"error": "No autorizado"}), 403

    name = str(data.get("discord_name", "")).strip()
    if not name:
        return jsonify({"error": "Falta discord_name"}), 400

    with get_db() as db:
        db.execute("DELETE FROM blacklist WHERE LOWER(discord_name) = LOWER(?)", (name,))
        db.commit()

    print(f"[BLACKLIST] REMOVED  discord={name}")
    return jsonify({"status": "ok", "msg": f"{name} removido de la blacklist"})

# ============================================================
#  GET /admin/blacklist/list
#  Headers: X-Secret: ...
# ============================================================
@app.route("/admin/blacklist/list", methods=["GET"])
def blacklist_list():
    secret = request.headers.get("X-Secret", "")
    if secret != ADMIN_SECRET:
        return jsonify({"error": "No autorizado"}), 403

    with get_db() as db:
        rows = db.execute("SELECT * FROM blacklist ORDER BY banned_at DESC").fetchall()

    result = [{"discord_name": r["discord_name"], "reason": r["reason"], "banned_at": r["banned_at"]} for r in rows]
    return jsonify({"status": "ok", "count": len(result), "blacklist": result})

# ============================================================
#  Main
# ============================================================
if __name__ == "__main__":
    init_db()
    print(f"[SERVER] EZ4ME Auth Server v2 corriendo en {HOST}:{PORT}")
    print(f"[SERVER] ADMIN_SECRET = {ADMIN_SECRET[:4]}{'*' * max(0, len(ADMIN_SECRET)-4)}")
    app.run(host=HOST, port=PORT, debug=False)