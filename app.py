import streamlit as st
import pandas as pd
import os
import io
import base64
import speech_recognition as sr
from google import genai
from google.genai import types
from gtts import gTTS
from audio_recorder_streamlit import audio_recorder
import sqlite3
import uuid
import random
from datetime import datetime
import smtplib
from email.mime.text import MIMEText

# ==========================================
# 1. PAGE SETUP
# ==========================================
st.set_page_config(page_title="Suyog + Job Finder", page_icon="🤝", layout="centered")

# ==========================================
# 2. DATABASE SETUP (SQLITE)
# ==========================================
conn = sqlite3.connect('suyog_users.db', check_same_thread=False)
c = conn.cursor()

def create_tables():
    c.execute('CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS chat_threads(thread_id TEXT PRIMARY KEY, username TEXT, thread_name TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS thread_messages(thread_id TEXT, role TEXT, content TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS user_profiles(username TEXT PRIMARY KEY, qualification TEXT, disability TEXT, sub_category TEXT)')
    conn.commit()

create_tables()

def get_or_create_user(contact_info):
    c.execute('SELECT * FROM users WHERE username = ?', (contact_info,))
    user = c.fetchone()
    if not user:
        c.execute('INSERT INTO users(username, password) VALUES (?,?)', (contact_info, 'OTP_AUTH'))
        conn.commit()
        return contact_info, True
    return contact_info, False

def get_profile(username):
    c.execute('SELECT qualification, disability, sub_category FROM user_profiles WHERE username=?', (username,))
    row = c.fetchone()
    if row:
        return row[0], row[1], row[2]
    return "Prefer Not to Say", "Prefer not to say", "General / Prefer not to specify"

def save_profile(username, qual, disab, sub):
    c.execute('REPLACE INTO user_profiles (username, qualification, disability, sub_category) VALUES (?, ?, ?, ?)', (username, qual, disab, sub))
    conn.commit()

def create_new_thread(username):
    thread_id = str(uuid.uuid4())
    thread_name = f"Chat {datetime.now().strftime('%b %d, %H:%M')}"
    c.execute('INSERT INTO chat_threads(thread_id, username, thread_name) VALUES (?,?,?)', (thread_id, username, thread_name))
    conn.commit()
    return thread_id

def get_user_threads(username):
    c.execute('SELECT thread_id, thread_name FROM chat_threads WHERE username=? ORDER BY created_at DESC', (username,))
    return c.fetchall()

def save_message_to_thread(thread_id, role, content):
    c.execute('INSERT INTO thread_messages(thread_id, role, content) VALUES (?,?,?)', (thread_id, role, content))
    conn.commit()

def get_thread_history(thread_id):
    c.execute('SELECT role, content FROM thread_messages WHERE thread_id=? ORDER BY rowid ASC', (thread_id,))
    return [{"role": row[0], "content": row[1]} for row in c.fetchall()]

def delete_thread(thread_id):
    c.execute('DELETE FROM chat_threads WHERE thread_id=?', (thread_id,))
    c.execute('DELETE FROM thread_messages WHERE thread_id=?', (thread_id,))
    conn.commit()

def delete_user_account(username):
    user_threads = get_user_threads(username)
    for tid, _ in user_threads:
        delete_thread(tid)
    c.execute('DELETE FROM users WHERE username=?', (username,))
    c.execute('DELETE FROM user_profiles WHERE username=?', (username,))
    conn.commit()

# ==========================================
# 3. EMAIL OTP FUNCTION
# ==========================================
def send_otp_email(receiver_email, otp):
    try:
        sender_email = st.secrets["email_address"]
        sender_password = st.secrets["email_password"]
    except KeyError:
        return False, "Email credentials not configured in secrets.toml"

    msg = MIMEText(f"Hello,\n\nYour Suyog + Job Finder verification code is: {otp}\n\nDo not share this code with anyone.")
    msg['Subject'] = 'Your OTP Verification Code'
    msg['From'] = f"Suyog Job Finder <{sender_email}>"
    msg['To'] = receiver_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        return True, "Email sent successfully!"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

# ==========================================
# 4. WELCOME PAGE & OTP AUTHENTICATION UI
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.is_new_user = False
    st.session_state.active_thread = None
    st.session_state.otp_sent = False
    st.session_state.current_otp = None
    st.session_state.contact_info = ""
    st.session_state.lock_profile = False
    st.session_state.target_identified = False

if not st.session_state.logged_in:
    col1, col2 = st.columns([1, 4])
    with col1:
        try:
            st.image("logo.png", width=100)
        except:
            st.markdown("<h1>🤝</h1>", unsafe_allow_html=True)
            
    with col2:
        st.title("Suyog + Job Finder")
        st.subheader("Your AI-Powered, Accessible Career Assistant")

    st.markdown("""
    Welcome to a new way to find your perfect job. Suyog uses advanced AI to understand your unique needs, 
    qualifications, and accessibility requirements to match you with verified roles.
    
    * 🎙️ **Bilingual:** Speak and listen in both English and Tamil.
    * 🤝 **Accessible:** No complex menus, just a simple conversation.
    * 🔒 **Secure:** Passwordless, email-based login.
    """)
    st.divider()
    
    st.write("#### Login or Create an Account")
    
    if not st.session_state.otp_sent:
        contact_input = st.text_input("Enter your Email Address to continue:", placeholder="e.g., name@example.com")
        if st.button("Send Verification Code", type="primary"):
            contact_info = contact_input.strip()
            if "@" in contact_info and "." in contact_info:
                generated_otp = str(random.randint(100000, 999999))
                with st.spinner("Sending secure code to your email..."):
                    success, message = send_otp_email(contact_info, generated_otp)

                if success:
                    st.session_state.current_otp = generated_otp
                    st.session_state.contact_info = contact_info
                    st.session_state.otp_sent = True
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.error("Please enter a valid email address.")
    else:
        st.info(f"A 6-digit secure code has been sent to **{st.session_state.contact_info}**.")
        entered_otp = st.text_input("Enter the code here:")
        
        col3, col4 = st.columns(2)
        with col3:
            if st.button("Verify & Login", type="primary"):
                if entered_otp == st.session_state.current_otp:
                    username, is_new = get_or_create_user(st.session_state.contact_info)
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.is_new_user = is_new
                    st.success("Welcome in! Loading your dashboard...")
                    st.rerun()
                else:
                    st.error("Incorrect code. Please check your email and try again.")
        with col4:
            if st.button("Use a different Email"):
                st.session_state.otp_sent = False
                st.session_state.current_otp = None
                st.rerun()
                
    st.stop()

# ==========================================
# MAIN APP (ONLY RUNS IF LOGGED IN)
# ==========================================
st.title(f"🤝 Suyog + Job Finder")

# ==========================================
# 5. SIDEBAR UI: CHAT TABS & USER PROFILE
# ==========================================
st.sidebar.subheader("💬 Your Chats")

if st.sidebar.button("➕ New Chat", use_container_width=True):
    new_id = create_new_thread(st.session_state.username)
    st.session_state.active_thread = new_id
    st.session_state.messages = []
    st.rerun()

user_threads = get_user_threads(st.session_state.username)
if not user_threads:
    new_id = create_new_thread(st.session_state.username)
    st.session_state.active_thread = new_id
    user_threads = get_user_threads(st.session_state.username)

if st.session_state.active_thread is None:
    st.session_state.active_thread = user_threads[0][0]

st.sidebar.markdown("<br>", unsafe_allow_html=True) 

for tid, name in user_threads:
    is_active = (tid == st.session_state.active_thread)
    button_label = f"📍 {name}" if is_active else f"💬 {name}"
    button_type = "primary" if is_active else "secondary"
    
    if st.sidebar.button(button_label, key=f"btn_{tid}", use_container_width=True, type=button_type):
        if not is_active: 
            st.session_state.active_thread = tid
            st.session_state.messages = []
            st.rerun()

st.sidebar.markdown("<br>", unsafe_allow_html=True)

if st.sidebar.button("🗑️ Delete Current Chat", use_container_width=True):
    delete_thread(st.session_state.active_thread)
    st.session_state.active_thread = None
    st.session_state.messages = []
    st.rerun()

if "messages" in st.session_state and len(st.session_state.messages) > 1:
    chat_export = f"Suyog Job Finder - Chat History\nUser: {st.session_state.username}\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    chat_export += "="*50 + "\n\n"
    for msg in st.session_state.messages:
        if msg["role"] != "system":
            role_name = "You" if msg["role"] == "user" else "Assistant"
            chat_export += f"{role_name}:\n{msg['content']}\n\n"
            chat_export += "-"*50 + "\n\n"
            
    st.sidebar.download_button(
        label="📥 Download Current Chat",
        data=chat_export,
        file_name=f"Suyog_Chat_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
        mime="text/plain",
        use_container_width=True
    )

st.sidebar.divider()

st.sidebar.subheader("⚙️ Settings / அமைப்புகள்")

if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.is_new_user = False
    st.session_state.messages = []
    st.session_state.active_thread = None
    st.session_state.otp_sent = False
    st.session_state.lock_profile = False
    st.session_state.target_identified = False
    st.rerun()

with st.sidebar.expander("⚠️ Delete Account"):
    st.warning("This will permanently delete your account and all your chat history. This action cannot be undone.")
    if st.button("Delete My Account", type="primary", use_container_width=True):
        delete_user_account(st.session_state.username)
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.is_new_user = False
        st.session_state.messages = []
        st.session_state.active_thread = None
        st.session_state.otp_sent = False
        st.session_state.lock_profile = False
        st.session_state.target_identified = False
        st.rerun()

# GEMINI API INITIALIZATION
try:
    api_key = st.secrets["gemini_api_key"]
except KeyError:
    pass 

if 'api_key' not in locals() or not api_key:
    st.error("🚨 API Key not found! Please configure your Streamlit Secrets with 'gemini_api_key'.")
    st.stop()

try:
    client = genai.Client(api_key=api_key)
except Exception as e:
    st.error(f"Failed to initialize Google Gemini client: {e}")
    st.stop()

def reload_profile():
    st.session_state.messages = []

language = st.sidebar.radio("Language / மொழி:", ["English", "Tamil (தமிழ்)"], on_change=reload_profile)

db_qual, db_disab, db_sub = get_profile(st.session_state.username)

qual_options = ["Prefer Not to Say", "High School / 10th / 12th", "Diploma / Certification", "Bachelor's Degree", "Master's Degree", "PhD / Doctorate", "No Formal Education / Other"]
disab_options = ["Prefer not to say", "Visual (Blindness, Low Vision)", "Hearing (Deaf, Hard of Hearing)", "Locomotor (Mobility, Cerebral Palsy, etc.)", "Cognitive & Intellectual", "Multiple Disabilities"]

qual_idx = qual_options.index(db_qual) if db_qual in qual_options else 0
disab_idx = disab_options.index(db_disab) if db_disab in disab_options else 0

is_locked = st.session_state.get("lock_profile", False)

qualification_level = st.sidebar.selectbox("Qualification:", qual_options, index=qual_idx, disabled=is_locked, on_change=reload_profile)
primary_category = st.sidebar.selectbox("Primary Disability:", disab_options, index=disab_idx, disabled=is_locked, on_change=reload_profile)

sub_category = None
if primary_category == "Cognitive & Intellectual":
    sub_options = ["General / Prefer not to specify", "Intellectual Disability (ID)", "Autism Spectrum Disorder (ASD)", "Specific Learning Disability (SLD)", "Mental Illness (MI)"]
    sub_idx = sub_options.index(db_sub) if db_sub in sub_options else 0
    sub_category = st.sidebar.selectbox("Sub-category:", sub_options, index=sub_idx, disabled=is_locked, on_change=reload_profile)

if not is_locked:
    save_profile(st.session_state.username, qualification_level, primary_category, sub_category)

# ==========================================
# 6. LOAD DATASET & DYNAMIC SYSTEM RULES
# ==========================================
@st.cache_data
def load_data():
    if os.path.exists('jobs.csv'):
        return pd.read_csv('jobs.csv')
    return pd.DataFrame()

df = load_data()
AVAILABLE_DEPARTMENTS = df['Department'].dropna().unique().tolist() if 'Department' in df.columns else []
AVAILABLE_JOBS = df['Job Title'].dropna().unique().tolist() if 'Job Title' in df.columns else []

user_profile_string = f"Qualification: {qualification_level} | Disability Category: {primary_category}"
if sub_category and sub_category != "General / Prefer not to specify":
    user_profile_string += f" (Specifically: {sub_category})"

missing_info = (qualification_level == "Prefer Not to Say" or primary_category == "Prefer not to say")

if language == "Tamil (தமிழ்)":
    tts_lang_code = 'ta'
    stt_lang_code = 'ta-IN'
    lang_instruction = "CRITICAL: You MUST communicate entirely in the Tamil language (தமிழ்). Translate all your thoughts into simple Tamil."
    
    if missing_info:
        welcome_msg = "உங்களுக்கு சரியான வேலையைத் தேட, தயவுசெய்து உங்கள் தகுதி மற்றும் குறைபாட்டைத் தேர்ந்தெடுக்கவும்!"
        enforcement_rule = '8. CRITICAL: You MUST ignore the user\'s input and reply EXACTLY with: "உங்களுக்கு சரியான வேலையைத் தேட, தயவுசெய்து உங்கள் தகுதி மற்றும் குறைபாட்டைத் தேர்ந்தெடுக்கவும்!" until they update their profile.'
    elif not st.session_state.is_new_user and not st.session_state.target_identified:
        welcome_msg = "மீண்டும் வருக! நீங்கள் உங்களுக்காக வேலை தேடுகிறீர்களா அல்லது வேறு யாருக்காகவாவது தேடுகிறீர்களா?"
        enforcement_rule = ""
    else:
        welcome_msg = "வணக்கம்! இன்று வேலை தேடுவதில் நான் உங்களுக்கு எப்படி உதவ முடியும்?"
        enforcement_rule = ""
else:
    tts_lang_code = 'en'
    stt_lang_code = 'en-US'
    lang_instruction = "CRITICAL: You must communicate entirely in English."
    
    if missing_info:
        welcome_msg = "Kindly select the qualification and disability in order to match you with the perfect job!"
        enforcement_rule = '8. CRITICAL: You MUST ignore the user\'s input and reply EXACTLY with: "Kindly select the qualification and disability in order to match you with the perfect job!" until they update their profile.'
    elif not st.session_state.is_new_user and not st.session_state.target_identified:
        welcome_msg = "Welcome back! Are you continuing the job search for yourself, or are you looking for someone else?"
        enforcement_rule = ""
    else:
        welcome_msg = "Hello! How can I help you with your job search today?"
        enforcement_rule = ""

system_prompt = f"""
You are an empathetic, highly accessible job-matching assistant for differently-abled individuals.
The user you are speaking to is already registered and logged in. Their profile is: {user_profile_string}

{lang_instruction}

CRITICAL RULES:
1. ACCESSIBILITY FIRST: Keep your language extremely simple, clear, and easy to understand. Keep your responses short (maximum 2-3 sentences).
2. ONE QUESTION AT A TIME: NEVER ask multiple questions in a single message.
3. ONLY suggest jobs that realistically match their stated Qualification level.
4. NO COMPANY NAMES: When suggesting a job, you are STRICTLY FORBIDDEN from mentioning the farm name, company name, or employer name.
5. STRICT DATABASE ONLY: Do not invent jobs.
6. Available Departments from database: {', '.join(AVAILABLE_DEPARTMENTS)}
7. Available Exact Job Titles you can suggest: {', '.join(AVAILABLE_JOBS)}
{enforcement_rule}
"""

# ==========================================
# 7. LOAD ACTIVE CHAT THREAD INTO MEMORY
# ==========================================
if "messages" not in st.session_state or len(st.session_state.messages) == 0:
    db_history = get_thread_history(st.session_state.active_thread)
    
    if db_history:
        st.session_state.messages = [{"role": "system", "content": system_prompt}] + db_history
    else:
        st.session_state.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": welcome_msg}
        ]
        save_message_to_thread(st.session_state.active_thread, "assistant", welcome_msg)

# ==========================================
# 8. AUDIO PLAYBACK & CHAT UI
# ==========================================
def autoplay_audio(text, lang_code):
    try:
        tts = gTTS(text=text, lang=lang_code)
        tts.save("response.mp3")
        with open("response.mp3", "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            st.markdown(f'<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>', unsafe_allow_html=True)
    except Exception:
        pass 

for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

# ==========================================
# 9. INPUT (TEXT & VOICE)
# ==========================================
user_input = None

col1, col2 = st.columns([1, 4])
with col1:
    st.write("🎙️ Speak:" if language == "English" else "🎙️ பேசுங்கள்:")
    audio_bytes = audio_recorder(text="", recording_color="#FF0000", neutral_color="#000000", icon_size="2x")

text_input = st.chat_input("Type your message here..." if language == "English" else "உங்கள் செய்தியை இங்கே தட்டச்சு செய்யவும்...")

if audio_bytes:
    with st.spinner("Listening..." if language == "English" else "கேட்கிறது..."):
        try:
            r = sr.Recognizer()
            audio_file = sr.AudioFile(io.BytesIO(audio_bytes))
            with audio_file as source:
                audio_data = r.record(source)
            user_input = r.recognize_google(audio_data, language=stt_lang_code)
        except sr.UnknownValueError:
            st.error("Sorry, I didn't catch that." if language == "English" else "மன்னிக்கவும், எனக்கு புரியவில்லை.")
        except Exception as e:
            st.error(f"Voice error: {e}")

if text_input:
    user_input = text_input

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    save_message_to_thread(st.session_state.active_thread, "user", user_input)
    
    if not st.session_state.is_new_user and not st.session_state.target_identified:
        text_lower = user_input.lower()
        if any(w in text_lower for w in ["myself", "me", "my", "own", "naan", "enaku", "enakku"]):
            st.session_state.lock_profile = True
            st.session_state.target_identified = True
        elif any(w in text_lower for w in ["someone", "else", "other", "friend", "brother", "sister", "veru", "matra"]):
            st.session_state.lock_profile = False
            st.session_state.target_identified = True
    
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        try:
            st.session_state.messages[0] = {"role": "system", "content": system_prompt}
            
            gemini_contents = []
            for msg in st.session_state.messages:
                if msg["role"] == "user":
                    gemini_contents.append(types.Content(role="user", parts=[types.Part.from_text(text=msg["content"])]))
                elif msg["role"] == "assistant":
                    gemini_contents.append(types.Content(role="model", parts=[types.Part.from_text(text=msg["content"])]))
            
            response = client.models.generate_content_stream(
                model="gemini-2.5-flash",
                contents=gemini_contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                )
            )
            
            def stream_generator():
                for chunk in response:
                    if chunk.text:
                        yield chunk.text

            reply = st.write_stream(stream_generator())
            
            autoplay_audio(reply, tts_lang_code)
            
            st.session_state.messages.append({"role": "assistant", "content": reply})
            save_message_to_thread(st.session_state.active_thread, "assistant", reply)
            
            if st.session_state.lock_profile:
                st.rerun()
                
        except Exception as e:
            st.error(f"Gemini API Error: {e}")
