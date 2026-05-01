"""
EZ4ME — Bot de Discord v2
==================================================
Nuevo flujo de autenticacion:
  1. Usuario ingresa su KEY en el .exe
  2. Usuario ingresa su nombre de Discord
  3. Servidor verifica duplicados → blacklist automatica

Comandos (solo en tu canal de admin):
  !addkey <nombre>     — Crea una key nueva
  !list                — Lista todas las keys
  !reset <KEY>         — Resetea HWID + Discord de una key
  !delete <KEY>        — Elimina una key
  !info <KEY>          — Info detallada de una key
  !blacklist           — Ver la blacklist
  !banear <discord>    — Agregar a la blacklist manualmente
  !desbanear <discord> — Quitar de la blacklist
"""

import discord
import aiohttp
import asyncio
import json
import secrets
import os
from datetime import datetime
from aiohttp import web
from discord.ext import commands

# ============================================================
#  CONFIGURA ESTO
# ============================================================
BOT_TOKEN      = os.environ["BOT_TOKEN"]
ADMIN_GUILD_ID = int(os.environ["ADMIN_GUILD_ID"])
ADMIN_CHANNEL  = int(os.environ["ADMIN_CHANNEL_ID"])
HTTP_PORT      = 8080
KEYS_FILE      = "keys.json"
BL_FILE        = "blacklist.json"

# ============================================================
#  Base de datos en JSON
# ============================================================
def load_keys() -> dict:
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_keys(keys: dict):
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=2)

def load_blacklist() -> dict:
    if os.path.exists(BL_FILE):
        with open(BL_FILE, "r") as f:
            return json.load(f)
    return {}

def save_blacklist(bl: dict):
    with open(BL_FILE, "w") as f:
        json.dump(bl, f, indent=2)

def generate_key() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    segments = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
    return "-".join(segments)

# ============================================================
#  Bot de Discord
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def is_admin_channel():
    async def predicate(ctx):
        return ctx.guild and ctx.guild.id == ADMIN_GUILD_ID and ctx.channel.id == ADMIN_CHANNEL
    return commands.check(predicate)

# ---- !addkey <nombre> ----
@bot.command(name="addkey")
@is_admin_channel()
async def addkey(ctx, *, note: str = "sin nombre"):
    keys = load_keys()
    key  = generate_key()
    keys[key] = {
        "hwid":            None,
        "discord_name":    None,
        "awaiting_discord": False,
        "note":            note,
        "created_at":      datetime.utcnow().isoformat(),
        "bound_at":        None,
        "discord_set_at":  None,
        "last_used":       None,
        "use_count":       0
    }
    save_keys(keys)

    embed = discord.Embed(title="✅ Key Creada", color=0x00ff88)
    embed.add_field(name="🔑 Key",    value=f"```{key}```",  inline=False)
    embed.add_field(name="👤 Para",   value=note,            inline=True)
    embed.add_field(name="📊 Estado", value="Sin atar",      inline=True)
    embed.set_footer(text=f"Creada: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    await ctx.send(embed=embed)

# ---- !list ----
@bot.command(name="list")
@is_admin_channel()
async def list_keys(ctx):
    keys = load_keys()
    if not keys:
        await ctx.send("📭 No hay keys.")
        return

    embed = discord.Embed(title=f"🔑 Keys — Total: {len(keys)}", color=0x00aaff)
    for key, data in list(keys.items())[:20]:
        hwid    = data.get("hwid")
        discord_name = data.get("discord_name") or "—"
        note    = data.get("note", "—")
        uses    = data.get("use_count", 0)
        awaiting = data.get("awaiting_discord", False)

        if hwid and discord_name != "—":
            status = f"🟢 Activa · {discord_name}"
        elif hwid and awaiting:
            status = "🟠 Esperando Discord..."
        elif hwid:
            status = f"🟡 HWID atado, sin Discord"
        else:
            status = "⚪ Sin atar"

        embed.add_field(
            name=f"`{key}`",
            value=f"**{note}** | {status} | Usos: {uses}",
            inline=False
        )
    if len(keys) > 20:
        embed.set_footer(text=f"Mostrando 20 de {len(keys)}. Usa !info <KEY> para detalles.")
    await ctx.send(embed=embed)

# ---- !reset <KEY> ----
@bot.command(name="reset")
@is_admin_channel()
async def reset_key(ctx, key: str):
    keys = load_keys()
    key  = key.upper().strip()
    if key not in keys:
        await ctx.send(f"❌ Key `{key}` no encontrada.")
        return

    old_hwid    = keys[key].get("hwid", "ninguno")
    old_discord = keys[key].get("discord_name", "ninguno")
    keys[key]["hwid"]            = None
    keys[key]["bound_at"]        = None
    keys[key]["discord_name"]    = None
    keys[key]["discord_set_at"]  = None
    keys[key]["awaiting_discord"] = False
    save_keys(keys)

    embed = discord.Embed(title="🔄 Key Reseteada Completamente", color=0xffaa00)
    embed.add_field(name="Key",          value=f"`{key}`",        inline=False)
    embed.add_field(name="HWID anterior",value=old_hwid or "—",   inline=True)
    embed.add_field(name="Discord anterior", value=old_discord or "—", inline=True)
    embed.add_field(name="Estado",       value="La proxima vez que la use, pedira HWID y Discord nuevos.", inline=False)
    await ctx.send(embed=embed)

# ---- !delete <KEY> ----
@bot.command(name="delete")
@is_admin_channel()
async def delete_key(ctx, key: str):
    keys = load_keys()
    key  = key.upper().strip()
    if key not in keys:
        await ctx.send(f"❌ Key `{key}` no encontrada.")
        return

    data = keys[key]
    note    = data.get("note", "—")
    discord = data.get("discord_name") or "—"
    del keys[key]
    save_keys(keys)

    embed = discord.Embed(title="🗑️ Key Eliminada", color=0xff4444)
    embed.add_field(name="🔑 Key",     value=f"`{key}`", inline=True)
    embed.add_field(name="👤 Era de",  value=note,       inline=True)
    embed.add_field(name="💬 Discord", value=discord,    inline=True)
    await ctx.send(embed=embed)

# ---- !info <KEY> ----
@bot.command(name="info")
@is_admin_channel()
async def info_key(ctx, key: str):
    keys = load_keys()
    key  = key.upper().strip()
    if key not in keys:
        await ctx.send(f"❌ Key `{key}` no encontrada.")
        return

    data = keys[key]
    hwid = data.get("hwid")
    discord_name = data.get("discord_name") or "—"

    embed = discord.Embed(title=f"🔍 Info: `{key}`", color=0xaa88ff)
    embed.add_field(name="👤 Nota",      value=data.get("note", "—"),      inline=True)
    embed.add_field(name="💬 Discord",   value=discord_name,               inline=True)
    embed.add_field(name="📊 Estado",    value="🟢 Activa" if (hwid and discord_name != "—") else ("🟠 Sin Discord" if hwid else "⚪ Sin atar"), inline=True)
    embed.add_field(name="🖥️ HWID",     value=hwid or "ninguno",          inline=False)
    embed.add_field(name="📅 Creada",   value=data.get("created_at", "—"), inline=True)
    embed.add_field(name="🔗 Atada el", value=data.get("bound_at", "—"),   inline=True)
    embed.add_field(name="💬 Discord el",value=data.get("discord_set_at","—"), inline=True)
    embed.add_field(name="⏰ Ultimo uso",value=data.get("last_used", "—"), inline=True)
    embed.add_field(name="🔢 Usos",     value=str(data.get("use_count", 0)), inline=True)
    await ctx.send(embed=embed)

# ---- !blacklist ----
@bot.command(name="blacklist")
@is_admin_channel()
async def show_blacklist(ctx):
    bl = load_blacklist()
    if not bl:
        await ctx.send("✅ La blacklist está vacía.")
        return

    embed = discord.Embed(
        title=f"🚫 Blacklist EZ4STRAP — {len(bl)} usuarios",
        color=0xff2222
    )
    for name, info in list(bl.items())[:25]:
        reason   = info.get("reason", "—")
        banned_at = info.get("banned_at", "—")[:10]
        embed.add_field(
            name=f"❌ {name}",
            value=f"**Razón:** {reason}\n**Fecha:** {banned_at}",
            inline=False
        )
    if len(bl) > 25:
        embed.set_footer(text=f"Mostrando 25 de {len(bl)}")
    await ctx.send(embed=embed)

# ---- !banear <discord_name> [razon] ----
@bot.command(name="banear")
@is_admin_channel()
async def ban_user(ctx, discord_name: str, *, reason: str = "ban manual por administrador"):
    bl = load_blacklist()
    name_lower = discord_name.lower()

    if name_lower in bl:
        await ctx.send(f"⚠️ `{discord_name}` ya está en la blacklist.")
        return

    bl[name_lower] = {
        "original_name": discord_name,
        "reason":       reason,
        "banned_at":    datetime.utcnow().isoformat(),
        "banned_by":    str(ctx.author)
    }
    save_blacklist(bl)

    embed = discord.Embed(title="🚫 Usuario Baneado", color=0xff2222)
    embed.add_field(name="💬 Discord", value=discord_name, inline=True)
    embed.add_field(name="📝 Razón",   value=reason,       inline=True)
    embed.add_field(name="👮 Por",     value=str(ctx.author), inline=True)
    await ctx.send(embed=embed)

# ---- !desbanear <discord_name> ----
@bot.command(name="desbanear")
@is_admin_channel()
async def unban_user(ctx, discord_name: str):
    bl = load_blacklist()
    name_lower = discord_name.lower()

    if name_lower not in bl:
        await ctx.send(f"❌ `{discord_name}` no está en la blacklist.")
        return

    del bl[name_lower]
    save_blacklist(bl)

    embed = discord.Embed(title="✅ Usuario Desbaneado", color=0x00ff88)
    embed.add_field(name="💬 Discord", value=discord_name, inline=True)
    embed.set_footer(text=f"Removido por {ctx.author}")
    await ctx.send(embed=embed)

# ---- !ayuda ----
@bot.command(name="ayuda")
@is_admin_channel()
async def ayuda(ctx):
    embed = discord.Embed(title="⚙️ EZ4ME v2 — Comandos de Admin", color=0x00ccff)
    embed.add_field(name="!addkey <nombre>",    value="Crea una key nueva",            inline=False)
    embed.add_field(name="!list",               value="Lista todas las keys",           inline=False)
    embed.add_field(name="!info <KEY>",         value="Info detallada de una key",      inline=False)
    embed.add_field(name="!reset <KEY>",        value="Resetea HWID + Discord de la key", inline=False)
    embed.add_field(name="!delete <KEY>",       value="Elimina una key permanentemente", inline=False)
    embed.add_field(name="!blacklist",          value="Ver la blacklist completa",      inline=False)
    embed.add_field(name="!banear <discord> [razon]", value="Banear manualmente",      inline=False)
    embed.add_field(name="!desbanear <discord>",value="Quitar de la blacklist",        inline=False)
    await ctx.send(embed=embed)

# ============================================================
#  Servidor HTTP — /auth  y  /auth/discord
# ============================================================
async def handle_auth(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "invalid"}, status=400)

    key  = str(data.get("key",  "")).strip().upper()
    hwid = str(data.get("hwid", "")).strip().upper()

    if not key or not hwid:
        return web.json_response({"status": "invalid"})

    keys = load_keys()
    now  = datetime.utcnow().isoformat()

    if key not in keys:
        print(f"[AUTH] INVALID  key={key}")
        return web.json_response({"status": "invalid"})

    entry = keys[key]

    # Primera vez — atar HWID y pedir Discord
    if entry["hwid"] is None:
        keys[key]["hwid"]             = hwid
        keys[key]["bound_at"]         = now
        keys[key]["last_used"]        = now
        keys[key]["use_count"]       += 1
        keys[key]["awaiting_discord"] = True
        save_keys(keys)

        channel = bot.get_channel(ADMIN_CHANNEL)
        if channel:
            embed = discord.Embed(title="🔗 Key Atada — Esperando Discord", color=0xffaa00)
            embed.add_field(name="Key",  value=f"`{key}`",            inline=True)
            embed.add_field(name="Para", value=entry.get("note","—"), inline=True)
            embed.add_field(name="HWID", value=hwid,                  inline=False)
            asyncio.create_task(channel.send(embed=embed))

        print(f"[AUTH] BOUND    key={key} hwid={hwid} — esperando Discord")
        return web.json_response({
            "status": "need_discord",
            "msg": "Key atada. Ahora ingresa tu nombre de Discord."
        })

    # HWID incorrecto
    if entry["hwid"] != hwid:
        print(f"[AUTH] DENIED   key={key} tried={hwid}")
        return web.json_response({"status": "denied", "msg": "Esta key pertenece a otro PC"})

    # Ya tiene Discord configurado → OK
    if entry.get("discord_name") and not entry.get("awaiting_discord"):
        keys[key]["last_used"]  = now
        keys[key]["use_count"] += 1
        save_keys(keys)
        return web.json_response({"status": "ok", "discord": entry["discord_name"]})

    # HWID correcto pero falta Discord
    return web.json_response({
        "status": "need_discord",
        "msg": "Ingresa tu nombre de Discord para continuar."
    })

async def handle_auth_discord(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "invalid"}, status=400)

    key          = str(data.get("key",          "")).strip().upper()
    hwid         = str(data.get("hwid",         "")).strip().upper()
    discord_name = str(data.get("discord_name", "")).strip()

    if not key or not hwid or not discord_name:
        return web.json_response({"status": "invalid"})

    keys = load_keys()
    bl   = load_blacklist()
    now  = datetime.utcnow().isoformat()

    if key not in keys:
        return web.json_response({"status": "invalid"})

    entry = keys[key]

    if entry["hwid"] != hwid:
        return web.json_response({"status": "denied"})

    # Verificar blacklist
    if discord_name.lower() in bl:
        print(f"[AUTH] BLACKLISTED  discord={discord_name} key={key}")
        return web.json_response({
            "status": "blacklisted",
            "msg": "Tu nombre de Discord está en la blacklist de EZ4STRAP."
        })

    # Verificar nombre duplicado en otras keys
    duplicate_key = None
    for k, v in keys.items():
        if k != key and v.get("discord_name", "").lower() == discord_name.lower():
            duplicate_key = k
            break

    if duplicate_key:
        # Auto-blacklist
        bl[discord_name.lower()] = {
            "original_name": discord_name,
            "reason":        "nombre duplicado detectado automaticamente",
            "banned_at":     now,
            "banned_by":     "sistema"
        }
        save_blacklist(bl)

        # Notificar en Discord
        channel = bot.get_channel(ADMIN_CHANNEL)
        if channel:
            embed = discord.Embed(title="🚨 NOMBRE DUPLICADO DETECTADO → AUTO-BLACKLIST", color=0xff0000)
            embed.add_field(name="💬 Discord",   value=discord_name,    inline=True)
            embed.add_field(name="🔑 Key 1",     value=f"`{duplicate_key}`", inline=True)
            embed.add_field(name="🔑 Key 2",     value=f"`{key}`",      inline=True)
            embed.add_field(name="⚠️ Accion",    value="Agregado automaticamente a la blacklist de EZ4STRAP", inline=False)
            asyncio.create_task(channel.send(embed=embed))

        print(f"[AUTH] DUPLICATE  discord={discord_name} → BLACKLISTED")
        return web.json_response({
            "status": "duplicate",
            "msg": "Nombre duplicado. Agregado a la blacklist de EZ4STRAP."
        })

    # Guardar nombre de Discord
    keys[key]["discord_name"]    = discord_name
    keys[key]["discord_set_at"]  = now
    keys[key]["awaiting_discord"] = False
    keys[key]["last_used"]       = now
    keys[key]["use_count"]      += 1
    save_keys(keys)

    # Notificar en Discord
    channel = bot.get_channel(ADMIN_CHANNEL)
    if channel:
        embed = discord.Embed(title="✅ Key Activada Completamente", color=0x00ff88)
        embed.add_field(name="🔑 Key",     value=f"`{key}`",            inline=True)
        embed.add_field(name="👤 Para",    value=entry.get("note","—"), inline=True)
        embed.add_field(name="💬 Discord", value=discord_name,          inline=True)
        asyncio.create_task(channel.send(embed=embed))

    print(f"[AUTH] DISCORD SET  key={key} discord={discord_name}")
    return web.json_response({"status": "ok", "discord": discord_name})

async def start_http_server():
    app_http = web.Application()
    app_http.router.add_post("/auth",         handle_auth)
    app_http.router.add_post("/auth/discord", handle_auth_discord)
    runner = web.AppRunner(app_http)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    print(f"[HTTP] Escuchando en 0.0.0.0:{HTTP_PORT}")

@bot.event
async def on_ready():
    print(f"[BOT] Conectado como {bot.user} (ID: {bot.user.id})")

    # Publicar anuncio de blacklist en el canal de admin
    channel = bot.get_channel(ADMIN_CHANNEL)
    if channel:
        embed = discord.Embed(
            title="⚠️ AVISO — Sistema de Autenticacion EZ4STRAP",
            description=(
                "Para usar **EZ4ME**, necesitas:\n"
                "1️⃣ Ingresar tu **KEY** de acceso\n"
                "2️⃣ Ingresar tu **nombre de Discord** real\n\n"
                "🚫 **NOMBRES DUPLICADOS O FALSOS** resultarán en un "
                "**BAN PERMANENTE en la blacklist de EZ4STRAP**.\n\n"
                "Cada key es personal e intransferible. "
                "Compartir o revender keys también puede resultar en ban."
            ),
            color=0xff4400
        )
        embed.set_footer(text="EZ4STRAP Security System · Respeta las reglas")
        await channel.send(embed=embed)

async def main():
    await start_http_server()
    await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())