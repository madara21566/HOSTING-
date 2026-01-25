import telebot
from telebot import types
import os
import shutil
import zipfile
import subprocess
import threading
import time
import datetime
import uuid
import signal
import psutil
from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId

# ================= CONFIGURATION =================
API_TOKEN = 'YOUR_BOT_TOKEN_HERE'       # <--- Apna Bot Token Dalein
OWNER_ID = 123456789                    # <--- Apni Telegram User ID Dalein
MONGO_URL = "YOUR_MONGODB_URL_HERE"     # <--- MongoDB Connection String Dalein

WEB_PORT = 5000  # File Manager Port
BASE_DIR = os.getcwd()
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

if not os.path.exists(PROJECTS_DIR): os.makedirs(PROJECTS_DIR)
if not os.path.exists(TEMPLATES_DIR): os.makedirs(TEMPLATES_DIR)

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# Temporary Memory
user_data = {} 
auth_tokens = {}

# ================= MONGODB CONNECTION =================
try:
    client = MongoClient(MONGO_URL)
    db = client['hosting_bot_db']
    users_col = db['users']
    projects_col = db['projects']
    print("✅ Connected to MongoDB Database!")
except Exception as e:
    print(f"❌ Database Error: {e}")
    exit()

# ================= SYSTEM FUNCTIONS =================

def is_premium(user_id):
    user = users_col.find_one({"user_id": user_id})
    return user.get("is_premium", False) if user else False

def add_user_if_not_exists(user_id):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({
            "user_id": user_id,
            "is_premium": False,
            "join_date": datetime.datetime.now()
        })

# --- AUTO RESTART SYSTEM ---
def restore_running_projects():
    print("🔄 Restoring active sessions from Database...")
    running_projs = projects_col.find({"status": "Running"})
    count = 0
    for p in running_projs:
        if os.path.exists(p['path']):
            cmd = ["python3", p['run_command']] if p['type'] == "python" else ["node", p['run_command']]
            try:
                log_file = open(os.path.join(p['path'], "logs.txt"), "w")
                proc = subprocess.Popen(cmd, cwd=p['path'], stdout=log_file, stderr=log_file)
                projects_col.update_one({"_id": p["_id"]}, {"$set": {"pid": proc.pid, "last_run": datetime.datetime.now()}})
                count += 1
            except:
                projects_col.update_one({"_id": p["_id"]}, {"$set": {"status": "Stopped", "pid": 0}})
    print(f"✅ Restored {count} projects.")

# ================= WEB FILE MANAGER =================
@app.route('/manager/<token>')
def file_manager(token):
    if token not in auth_tokens or time.time() > auth_tokens[token]['expire']:
        return "❌ Link Expired! Generate a new one from the bot."
    data = auth_tokens[token]
    return render_template('file_manager.html', token=token, project_name=data['project_name'])

@app.route('/api/files/<token>', methods=['GET'])
def list_files(token):
    if token not in auth_tokens: return jsonify({'error': 'Unauthorized'}), 401
    data = auth_tokens[token]
    project_path = os.path.join(PROJECTS_DIR, str(data['user_id']), data['project_name'])
    files = []
    if os.path.exists(project_path):
        for root, dirs, filenames in os.walk(project_path):
            for f in filenames:
                full_path = os.path.join(root, f)
                files.append({'name': f, 'path': os.path.relpath(full_path, project_path)})
    return jsonify({'files': files})

@app.route('/api/read/<token>', methods=['POST'])
def read_file(token):
    if token not in auth_tokens: return jsonify({'error': 'Unauthorized'}), 401
    data = auth_tokens[token]
    full_path = os.path.join(PROJECTS_DIR, str(data['user_id']), data['project_name'], request.json.get('path'))
    try:
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f: return jsonify({'content': f.read()})
    except: return jsonify({'error': 'Read Error'}), 400

@app.route('/api/save/<token>', methods=['POST'])
def save_file(token):
    if token not in auth_tokens: return jsonify({'error': 'Unauthorized'}), 401
    data = auth_tokens[token]
    full_path = os.path.join(PROJECTS_DIR, str(data['user_id']), data['project_name'], request.json.get('path'))
    try:
        with open(full_path, 'w', encoding='utf-8') as f: f.write(request.json.get('content'))
        return jsonify({'success': True})
    except: return jsonify({'success': False})

def run_server(): app.run(host='0.0.0.0', port=WEB_PORT, use_reloader=False)
threading.Thread(target=run_server, daemon=True).start()

# ================= BACKGROUND MONITOR =================
def monitor_loop():
    while True:
        try:
            # 1. Crash Check
            for p in projects_col.find({"status": "Running"}):
                if p['pid'] > 0 and not psutil.pid_exists(p['pid']):
                    projects_col.update_one({"_id": p["_id"]}, {"$set": {"status": "Crashed", "pid": 0}})
            
            # 2. Free Tier 12H Limit
            for p in projects_col.find({"status": "Running"}):
                if not is_premium(p['user_id']) and p.get('last_run'):
                    elapsed = (datetime.datetime.now() - p['last_run']).total_seconds()
                    if elapsed > 43200: # 12 Hours
                        if p['pid'] > 0: 
                            try: os.kill(p['pid'], signal.SIGTERM) 
                            except: pass
                        projects_col.update_one({"_id": p["_id"]}, {"$set": {"status": "Stopped", "pid": 0}})
                        try: bot.send_message(p['user_id'], f"⚠️ **Free Limit:** Project {p['name']} stopped after 12 hours.")
                        except: pass
        except Exception as e: print(f"Monitor Error: {e}")
        time.sleep(60)

threading.Thread(target=monitor_loop, daemon=True).start()

# ================= TELEGRAM BOT =================

@bot.message_handler(commands=['start'])
def start_msg(message):
    add_user_if_not_exists(message.from_user.id)
    text = (
        "👋 **Welcome to the Project Hoster!**\n\n"
        "I'm your personal bot for securely deploying and managing your Python & JS scripts.\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "⚡ **Key Features:**\n"
        "🚀 **Deploy Instantly** — Upload .zip/.py/.js\n"
        "📂 **Web File Manager** — Edit code online\n"
        "🤖 **Auto Restart** — Data safe on Cloud DB\n"
        "💾 **Free Tier:** 2 Projects (12h Runtime)\n"
        "💎 **Premium:** 10 Projects (24/7 Runtime)\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👇 **Get Started Now:**"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🆕 NEW PROJECT", callback_data="new_project"),
               types.InlineKeyboardButton("📂 MY PROJECTS", callback_data="my_projects"))
    markup.add(types.InlineKeyboardButton("❓ HELP", callback_data="help"),
               types.InlineKeyboardButton("💎 PREMIUM BUY", callback_data="buy_premium"))
    if message.from_user.id == OWNER_ID:
        markup.add(types.InlineKeyboardButton("👑 ADMIN PANEL", callback_data="admin_panel"))
    bot.reply_to(message, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def main_menu(call): start_msg(call.message)

# --- NEW PROJECT ---
@bot.callback_query_handler(func=lambda call: call.data == "new_project")
def new_project(call):
    uid = call.from_user.id
    count = projects_col.count_documents({"user_id": uid})
    limit = 10 if is_premium(uid) else 2
    
    if count >= limit:
        bot.answer_callback_query(call.id, "❌ Project Limit Reached! Buy Premium.", show_alert=True)
        return

    user_data[uid] = {'step': 'NAME'}
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
    bot.edit_message_text("📝 **Enter Project Name:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: user_data.get(m.from_user.id, {}).get('step') == 'NAME')
def set_name(message):
    name = message.text.strip().replace(" ", "_")
    user_data[message.from_user.id].update({'name': name, 'step': 'TYPE'})
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🐍 Python", callback_data="set_python"),
               types.InlineKeyboardButton("☕ Node.js", callback_data="set_node"))
    bot.reply_to(message, f"🛠 Project: **{name}**\nSelect Language:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_"))
def set_type(call):
    ptype = call.data.split("_")[1]
    user_data[call.from_user.id].update({'type': ptype, 'step': 'FILE'})
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ DONE", callback_data="upload_done"))
    bot.edit_message_text(f"📤 **Upload .{'py' if ptype=='python' else 'js'} or .zip file.**\nClick DONE when finished.", 
                          call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def upload_file(message):
    uid = message.from_user.id
    if user_data.get(uid, {}).get('step') != 'FILE': return
    
    data = user_data[uid]
    path = os.path.join(PROJECTS_DIR, str(uid), data['name'])
    if not os.path.exists(path): os.makedirs(path)
    
    file_info = bot.get_file(message.document.file_id)
    downloaded = bot.download_file(file_info.file_path)
    save_path = os.path.join(path, message.document.file_name)
    
    with open(save_path, 'wb') as f: f.write(downloaded)
    
    if message.document.file_name.endswith('.zip'):
        with zipfile.ZipFile(save_path, 'r') as z: z.extractall(path)
        os.remove(save_path)
        bot.reply_to(message, "✅ Zip Extracted!")
    else:
        bot.reply_to(message, "📄 File Saved!")

@bot.callback_query_handler(func=lambda call: call.data == "upload_done")
def finish_project(call):
    uid = call.from_user.id
    data = user_data.get(uid)
    if not data: return
    
    path = os.path.join(PROJECTS_DIR, str(uid), data['name'])
    cmd = "main.py" if data['type'] == "python" else "index.js"
    
    projects_col.insert_one({
        "user_id": uid, "name": data['name'], "type": data['type'],
        "path": path, "run_command": cmd, "pid": 0, "status": "Stopped", "last_run": None
    })
    user_data[uid] = {}
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📂 MY PROJECTS", callback_data="my_projects"))
    bot.edit_message_text("✅ **Project Created Successfully!**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

# --- MY PROJECTS ---
@bot.callback_query_handler(func=lambda call: call.data == "my_projects")
def my_projects(call):
    projects = list(projects_col.find({"user_id": call.from_user.id}))
    markup = types.InlineKeyboardMarkup(row_width=2)
    for p in projects: markup.add(types.InlineKeyboardButton(f"📁 {p['name']}", callback_data=f"proj_{p['_id']}"))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
    
    msg = "📂 **Select a Project:**" if projects else "📂 No active projects."
    bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("proj_"))
def project_panel(call):
    oid = call.data.split("_")[1]
    p = projects_col.find_one({"_id": ObjectId(oid)})
    if not p: return

    status = "🔴 Stopped"
    if p['pid'] > 0:
        status = "🟢 Running" if psutil.pid_exists(p['pid']) else "🟠 Crashed"

    text = (f"**Project Status**\n\n🔹 Name: {p['name']}\n🔹 Status: {status}\n🔹 PID: {p['pid']}\n🔹 Cmd: `{p['run_command']}`")
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(types.InlineKeyboardButton("▶️ Start", callback_data=f"a_start_{oid}"),
               types.InlineKeyboardButton("⏹️ Stop", callback_data=f"a_stop_{oid}"),
               types.InlineKeyboardButton("🔄 Restart", callback_data=f"a_restart_{oid}"))
    markup.add(types.InlineKeyboardButton("📝 Logs", callback_data=f"a_logs_{oid}"),
               types.InlineKeyboardButton("📦 Install", callback_data=f"a_req_{oid}"),
               types.InlineKeyboardButton("⚙️ Command", callback_data=f"a_cmd_{oid}"))
    markup.add(types.InlineKeyboardButton("📂 File Manager", callback_data=f"a_file_{oid}"))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="my_projects"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("a_"))
def actions(call):
    act, oid = call.data.split("_")[1], call.data.split("_")[2]
    p = projects_col.find_one({"_id": ObjectId(oid)})
    
    if act == "start":
        if p['pid'] > 0 and psutil.pid_exists(p['pid']):
            bot.answer_callback_query(call.id, "Already Running!")
        else:
            cmd = ["python3", p['run_command']] if p['type'] == "python" else ["node", p['run_command']]
            try:
                log = open(os.path.join(p['path'], "logs.txt"), "w")
                proc = subprocess.Popen(cmd, cwd=p['path'], stdout=log, stderr=log)
                projects_col.update_one({"_id": ObjectId(oid)}, {"$set": {"pid": proc.pid, "status": "Running", "last_run": datetime.datetime.now()}})
                bot.answer_callback_query(call.id, "✅ Started!")
            except Exception as e: bot.answer_callback_query(call.id, f"Error: {e}")

    elif act == "stop":
        if p['pid'] > 0:
            try: os.kill(p['pid'], signal.SIGTERM)
            except: pass
            projects_col.update_one({"_id": ObjectId(oid)}, {"$set": {"pid": 0, "status": "Stopped"}})
            bot.answer_callback_query(call.id, "🛑 Stopped!")
        else: bot.answer_callback_query(call.id, "Not Running")
    
    elif act == "logs":
        try:
            with open(os.path.join(p['path'], "logs.txt"), "rb") as f: bot.send_document(call.message.chat.id, f)
        except: bot.answer_callback_query(call.id, "No logs found.")
        return

    elif act == "req":
        if os.path.exists(os.path.join(p['path'], "requirements.txt")):
            bot.send_message(call.message.chat.id, "📦 Installing Requirements...")
            subprocess.run(["pip", "install", "-r", "requirements.txt"], cwd=p['path'])
            bot.send_message(call.message.chat.id, "✅ Done.")
        else: bot.answer_callback_query(call.id, "requirements.txt not found!")
        return

    elif act == "file":
        token = str(uuid.uuid4())
        auth_tokens[token] = {'user_id': p['user_id'], 'project_name': p['name'], 'expire': time.time() + 600}
        link = f"http://localhost:{WEB_PORT}/manager/{token}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔗 Open Manager", url=link),
                   types.InlineKeyboardButton("🔙 Back", callback_data=f"proj_{oid}"))
        bot.edit_message_text(f"📂 **Web File Manager**\nLink valid for 10 mins.\n[Click Here]({link})", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        return

    project_panel(call)

# --- ADMIN PANEL ---
@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_dash(call):
    if call.from_user.id != OWNER_ID: return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("👥 Users", callback_data="adm_users"),
               types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_cast"))
    markup.add(types.InlineKeyboardButton("💎 Premium", callback_data="adm_prem"),
               types.InlineKeyboardButton("📥 Download", callback_data="adm_dl"))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
    bot.edit_message_text("👑 **Admin Panel**", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_users")
def adm_users(call):
    users = list(users_col.find())
    msg = f"👥 **Total Users:** {len(users)}\n\n" + "\n".join([f"`{u['user_id']}` {'💎' if u['is_premium'] else '🆓'}" for u in users[:20]])
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_panel"))
    bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_prem")
def adm_prem(call):
    msg = bot.send_message(call.message.chat.id, "💎 Send User ID to toggle Premium:")
    bot.register_next_step_handler(msg, toggle_prem)

def toggle_prem(m):
    try:
        uid = int(m.text)
        curr = is_premium(uid)
        users_col.update_one({"user_id": uid}, {"$set": {"is_premium": not curr}})
        bot.reply_to(m, f"✅ User {uid} is now {'💎 Premium' if not curr else '🆓 Free'}")
    except: bot.reply_to(m, "❌ Invalid ID")

@bot.callback_query_handler(func=lambda call: call.data == "adm_dl")
def adm_dl(call):
    msg = bot.send_message(call.message.chat.id, "📥 Send User ID to download scripts:")
    bot.register_next_step_handler(msg, dl_script)

def dl_script(m):
    try:
        path = os.path.join(PROJECTS_DIR, m.text)
        if os.path.exists(path):
            shutil.make_archive(f"user_{m.text}", 'zip', path)
            with open(f"user_{m.text}.zip", "rb") as f: bot.send_document(m.chat.id, f)
            os.remove(f"user_{m.text}.zip")
        else: bot.reply_to(m, "❌ Not found")
    except: bot.reply_to(m, "❌ Error")

# --- EXTRAS ---
@bot.callback_query_handler(func=lambda call: call.data == "help")
def help_menu(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
    bot.edit_message_text("**❓ Guide:**\n1. New Project -> Upload.\n2. My Projects -> Start.\n3. File Manager -> Edit.", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "buy_premium")
def buy_prem(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👤 Contact Owner", url="https://t.me/MADARAXHEREE"),
               types.InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
    bot.edit_message_text("💎 **Premium Plan**\n\n- 10 Projects\n- 24/7 Uptime\n- Priority Support", call.message.chat.id, call.message.message_id, reply_markup=markup)

# Startup
restore_running_projects()
print("🤖 Bot is Online...")
bot.polling(none_stop=True)
