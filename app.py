import os
from datetime import datetime
from functools import wraps

from bson import ObjectId
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO
from flask_mail import Mail, Message  # <-- NEW
from fpdf import FPDF
from flask import make_response
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading

import requests
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
# Initialize Twilio client
twilio_client = None
whatsapp_client = None

if os.getenv('TWILIO_ACCOUNT_SID') and os.getenv('TWILIO_AUTH_TOKEN'):
    twilio_client = Client(
        os.getenv('TWILIO_ACCOUNT_SID'),
        os.getenv('TWILIO_AUTH_TOKEN')
    )
    whatsapp_client = twilio_client  # Same client for WhatsApp

class NotificationManager:
    def __init__(self):
        self.twilio_client = twilio_client
        self.twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
        self.whatsapp_from = f"whatsapp:{os.getenv('WHATSAPP_FROM_NUMBER', '+14155238886')}"
    
    def send_sms(self, to_number, message):
        """Send SMS notification"""
        if not self.twilio_client:
            print("Twilio not configured")
            return False
        
        try:
            # Format phone number (ensure it has country code)
            if not to_number.startswith('+'):
                to_number = f'+91{to_number}'  # Assuming India, adjust as needed
            
            response = self.twilio_client.messages.create(
                body=message,
                from_=self.twilio_phone,
                to=to_number
            )
            print(f"SMS sent to {to_number}: {response.sid}")
            return True
        except TwilioRestException as e:
            print(f"Twilio SMS error: {e}")
            return False
    
    def send_whatsapp(self, to_number, message):
        """Send WhatsApp notification"""
        if not self.twilio_client:
            print("Twilio not configured")
            return False
        
        try:
            # Format WhatsApp number
            if not to_number.startswith('+'):
                to_number = f'+91{to_number}'
            
            response = self.twilio_client.messages.create(
                body=message,
                from_=self.whatsapp_from,
                to=f"whatsapp:{to_number}"
            )
            print(f"WhatsApp sent to {to_number}: {response.sid}")
            return True
        except TwilioRestException as e:
            print(f"Twilio WhatsApp error: {e}")
            return False
    
    def send_notice_notification(self, notice, user, urgency='normal'):
        """Send appropriate notifications based on user preferences"""
        results = {'sms': False, 'whatsapp': False}
        
        # Check if user has phone number
        if not user.get('phone_number'):
            return results
        
        # Get user preferences
        prefs = user.get('notification_prefs', {})
        
        # Create message
        message = self._create_notice_message(notice, urgency)
        
        # Send SMS if enabled and (urgent or user wants SMS)
        if prefs.get('sms') and (urgency == 'urgent' or prefs.get('all_sms')):
            results['sms'] = self.send_sms(user['phone_number'], message)
        
        # Send WhatsApp if enabled
        if prefs.get('whatsapp'):
            results['whatsapp'] = self.send_whatsapp(user['phone_number'], message)
        
        return results
    
    def send_bulk_notification(self, notice, urgency='normal'):
        """Send notifications to all eligible users"""
        # Find users with phone numbers and appropriate preferences
        query = {
            "phone_number": {"$exists": True, "$ne": None, "$ne": ""}
        }
        
        if urgency == 'urgent':
            # For urgent notices, send to all with SMS enabled
            query["notification_prefs.sms"] = True
        else:
            # For normal notices, only send to those who want all SMS
            query["notification_prefs.all_sms"] = True
        
        users = users_col.find(query)
        
        results = {
            'total': 0,
            'sms_sent': 0,
            'whatsapp_sent': 0,
            'failed': []
        }
        
        for user in users:
            try:
                res = self.send_notice_notification(notice, user, urgency)
                results['total'] += 1
                if res['sms']:
                    results['sms_sent'] += 1
                if res['whatsapp']:
                    results['whatsapp_sent'] += 1
            except Exception as e:
                results['failed'].append({
                    'user': user.get('username'),
                    'error': str(e)
                })
        
        return results
    
    def _create_notice_message(self, notice, urgency='normal'):
        """Create formatted message for SMS/WhatsApp"""
        urgency_tag = "🔴 URGENT: " if urgency == 'urgent' else "📢 "
        dept = notice.get('department', 'GENERAL').upper()
        
        message = f"""{urgency_tag}{notice['title']}
Department: {dept}
Posted by: {notice.get('author_name', 'System')}

{notice['content'][:100]}{'...' if len(notice['content']) > 100 else ''}

View full notice: {url_for('index', _external=True)}"""
        
        return message

# Initialize notification manager
notifier = NotificationManager()
# ---- App Config ----
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/digital_noticeboard")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

app = Flask(__name__)
app.secret_key = SECRET_KEY
socketio = SocketIO(app)

# ---- Email config (Flask‑Mail) ----
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "True") == "True"
app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "False") == "True"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = (
    os.getenv("MAIL_DEFAULT_SENDER") or app.config["MAIL_USERNAME"]
)

app.config["MAIL_SUPPRESS_SEND"] = False
app.config["MAIL_DEBUG"] = True
app.config["TESTING"] = False
mail = Mail(app)  # mail instance
print("DEBUG DEFAULT SENDER:", app.config["MAIL_DEFAULT_SENDER"])

client = MongoClient(MONGO_URI)
db = client.get_default_database()

# Collections
users_col = db.users
notices_col = db.notices
events_col = db.events

# Upload config
UPLOAD_FOLDER = os.path.join("static", "uploads")
GALLERY_FOLDER = os.path.join(app.static_folder, "gallery")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

AVATAR_FOLDER = os.path.join('static', 'avatars')
os.makedirs(AVATAR_FOLDER, exist_ok=True)
app.config['AVATAR_FOLDER'] = AVATAR_FOLDER

ALLOWED_EXTENSIONS = {
    "mp3", "wav", "ogg", "mp4", "avi", "mov", "webm", "mkv",
    "jpg", "jpeg", "png", "gif"
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GALLERY_FOLDER, exist_ok=True)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---- Helpers ----
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    
    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user:
        return None
    
    # Convert ObjectId to string for template use
    user['id'] = str(user['_id'])
    
    # Ensure all profile fields exist with defaults
    if 'full_name' not in user or not user['full_name']:
        user['full_name'] = user.get('username', 'User')
    
    if 'profile_picture' not in user:
        user['profile_picture'] = None
    
    if 'phone_number' not in user:
        user['phone_number'] = None
    
    if 'bio' not in user:
        user['bio'] = ''
    
    if 'department' not in user:
        user['department'] = None
    
    if 'year' not in user:
        user['year'] = None
    
    # Ensure notification preferences exist
    if 'notification_prefs' not in user or not user['notification_prefs']:
        user['notification_prefs'] = {
            'email': True,
            'sms': False,
            'all_sms': False,
            'whatsapp': False,
            'browser': True
        }
    else:
        # Make sure all_sms field exists
        if 'all_sms' not in user['notification_prefs']:
            user['notification_prefs']['all_sms'] = False
    
    if 'bookmarked_notices' not in user:
        user['bookmarked_notices'] = []
    
    if 'total_notices' not in user:
        user['total_notices'] = notices_col.count_documents({"author_id": ObjectId(user['_id'])})
    
    return user

# ---- Email helper ----
# Find this function in your app.py (around line 100-120)
def send_new_notice_email(title, content, department, author_name):
    """Send email notifications about new notices (synchronous for debugging)"""
    recipients = [u["email"] for u in users_col.find({}, {"email": 1}) if u.get("email")]
    
    if not recipients:
        print("No recipients found for email notification")
        return

    dept_label = department.upper() if department else "GENERAL"
    
    # Generate URL within app context
    with app.app_context():
        index_url = url_for('index', _external=True)
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    subject = f"📢 New Notice: {title} [{dept_label}]"
    
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #f9f9f9; border-radius: 8px; padding: 20px;">
          <h2 style="color: #16bba5;">📋 New Notice Posted</h2>
          <div style="background: white; padding: 15px; border-radius: 5px;">
            <p><strong>Department:</strong> {dept_label}</p>
            <p><strong>Title:</strong> {title}</p>
            <p><strong>Content:</strong></p>
            <p style="background: #f0f0f0; padding: 10px; border-radius: 3px;">{content}</p>
            <p><strong>Posted by:</strong> {author_name}</p>
            <p><strong>Date:</strong> {date_str}</p>
          </div>
          <p style="margin-top: 20px;">
            <a href="{index_url}" style="color: #16bba5;">View on Notice Board</a>
          </p>
        </div>
      </body>
    </html>
    """
    
    text_body = f"""
    New Notice Posted
    
    Department: {dept_label}
    Title: {title}
    Content: {content}
    Posted by: {author_name}
    Date: {date_str}
    
    View at: {index_url}
    """
    
    print(f"Attempting to send {len(recipients)} emails...")
    
    try:
        # Send without threading to see exact error
        with mail.connect() as conn:
            for i, recipient in enumerate(recipients):
                try:
                    msg = Message(
                        subject=subject,
                        recipients=[recipient],
                        html=html_body,
                        body=text_body,
                        sender=app.config["MAIL_DEFAULT_SENDER"]
                    )
                    conn.send(msg)
                    print(f"✓ Email {i+1}/{len(recipients)} sent to {recipient}")
                except Exception as e:
                    print(f"✗ Failed to send to {recipient}: {e}")
                    
        print("✓ All email attempts completed")
        
    except Exception as e:
        print(f"✗ Connection error: {e}")
        # Log full error details
        import traceback
        with open('email_errors.log', 'a') as f:
            f.write(f"\n--- {datetime.now()} ---\n")
            f.write(f"Error: {e}\n")
            f.write(traceback.format_exc())
def roles_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return redirect(url_for("auth"))
            
            # Check if user role exists and is allowed
            if user.get("role") not in roles:
                flash("Unauthorized: This action requires higher privileges.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper
# ---- Routes ----
@app.route("/")
def index():
    all_notices = list(notices_col.find().sort("created_at", -1))

    for n in all_notices:
        n["id"] = str(n["_id"])
        n["created_str"] = (
            n.get("created_at").strftime("%Y-%m-%d %H:%M")
            if n.get("created_at") else ""
        )

    announcements = [
        n for n in all_notices
        if n.get("display_type") == "announcement"
    ][:6]

    card_notices = [
        n for n in all_notices
        if n.get("display_type") != "announcement"
    ]

    return render_template(
        "index.html",
        announcements=announcements,
        notices=card_notices,
        current_user=get_current_user()
    )


@app.route("/about")
def about():
    return render_template("about.html", current_user=get_current_user())


@app.route("/contact")
def contact():
    return render_template("contact.html", current_user=get_current_user())


@app.route("/departments")
def departments():
    return render_template("departments.html", current_user=get_current_user())


@app.route("/departments/<dept>")
def department_page(dept):
    allowed_departments = ["cse", "ece", "mech", "civil"]
    if dept not in allowed_departments:
        return render_template("404.html"), 404

    notices = list(notices_col.find({"department": dept}).sort("created_at", -1))
    for n in notices:
        n["id"] = str(n["_id"])
        n["created_str"] = (
            n.get("created_at").strftime("%Y-%m-%d %H:%M")
            if n.get("created_at") else ""
        )

    return render_template(
        f"departments/{dept}.html",
        notices=notices,
        department=dept,
        current_user=get_current_user()
    )


@app.route("/auth")
def auth():
    return render_template("auth.html", current_user=get_current_user())


# Register
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "student").strip().lower()
        department = request.form.get("department", "").strip()
        year = request.form.get("year", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        # Validation
        if not all([username, full_name, email, password, department, year]):
            flash("All required fields must be filled.", "danger")
            return redirect(url_for("auth"))

        if password != password2:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth"))

        if users_col.find_one({"email": email}):
            flash("An account with that email already exists.", "danger")
            return redirect(url_for("auth"))

        # Validate role
        valid_roles = ['student', 'faculty', 'admin']
        if role not in valid_roles:
            role = 'student'

        hashed = generate_password_hash(password)
        
        # Create user with all profile fields
        user = {
            "username": username,
            "full_name": full_name,
            "email": email,
            "password": hashed,
            "role": role,
            "department": department,
            "year": year,
            "phone_number": phone_number if phone_number else None,
            "profile_picture": None,
            "bio": "",
            "notification_prefs": {
                "email": True,
                "sms": bool(phone_number),  # Enable SMS if phone provided
                "whatsapp": False,
                "browser": True
            },
            "profile_visibility": "public",
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow(),
            "bookmarked_notices": [],
            "total_notices": 0
        }
        
        result = users_col.insert_one(user)
        session["user_id"] = str(result.inserted_id)
        
        flash(f"Welcome {full_name}! Your account has been created.", "success")
        return redirect(url_for("profile"))

    return render_template("auth.html", current_user=get_current_user())

@app.route("/admin/manage")
@login_required
def admin_manage():
    # Get the current user first
    user = get_current_user()
    
    # Only allow users with the 'admin' role
    if user.get('role', 'student') != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('index'))
    
    # Fetch all notices and users
    all_notices = list(db.notices.find().sort("created_at", -1))
    all_users = list(db.users.find().sort("username", 1))
    
    # Ensure IDs are strings for template processing
    for n in all_notices: 
        n["id"] = str(n["_id"])
    
    for u in all_users: 
        u["id"] = str(u["_id"])
        
    return render_template("admin_manage.html", 
                           notices=all_notices, 
                           users=all_users,
                           current_user=user)  # Pass the user to the template

@app.route("/admin/toggle-pin/<id>", methods=["POST"])
@login_required
def toggle_pin(id):
    if getattr(current_user, 'role', 'student') != 'admin':
        return "Unauthorized", 403
        
    notice = db.notices.find_one({"_id": ObjectId(id)})
    if notice:
        # Flip the current pinned status
        new_status = not notice.get("pinned", False)
        db.notices.update_one({"_id": ObjectId(id)}, {"$set": {"pinned": new_status}})
        flash("Notice priority updated successfully.", "success")
        
    return redirect(url_for("admin_manage"))


    # Add this to app.py temporarily to update existing users
@app.route('/migrate-users')
@login_required
@roles_required('admin')
def migrate_users():
    """Add missing fields to all existing users"""
    
    # Update notification preferences with new fields
    users_col.update_many(
        {},
        {
            "$set": {
                "notification_prefs.all_sms": False
            }
        }
    )
    
    # ... rest of migration code ...
    
    return "Migration complete"

# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = users_col.find_one({"email": email})
        
        if not user or not check_password_hash(user["password"], password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

        # Set session
        session["user_id"] = str(user["_id"])
        session.permanent = True  # Optional: makes session last longer
        
        flash("Logged in successfully.", "success")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("dashboard"))
    
    return render_template("login.html", current_user=get_current_user())

# Logout
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("index"))


@app.route('/profile')
@login_required
def profile():
    """View user profile"""
    user = get_current_user()
    
    # Ensure user exists (login_required should guarantee this)
    if not user:
        flash("Please log in to view your profile.", "warning")
        return redirect(url_for('login'))
    
    # Get user's notices count (already handled in get_current_user, but just in case)
    if 'total_notices' not in user:
        user['total_notices'] = notices_col.count_documents({"author_id": ObjectId(user['_id'])})
    
    return render_template('profile.html', user=user)

@app.route('/profile/<user_id>')
def view_profile(user_id):
    """View another user's profile"""
    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
        if not user:
            flash("User not found", "danger")
            return redirect(url_for('index'))
        
        # Check privacy settings
        if user.get('profile_visibility') == 'private':
            if not session.get('user_id') or session['user_id'] != user_id:
                flash("This profile is private", "warning")
                return redirect(url_for('index'))
        
        user['id'] = str(user['_id'])
        user['total_notices'] = notices_col.count_documents({"author_id": ObjectId(user_id)})
        
        return render_template('profile.html', user=user)
    except:
        flash("Invalid user ID", "danger")
        return redirect(url_for('index'))

@app.route('/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    """Upload profile picture"""
    if 'avatar' not in request.files:
        flash('No file selected', 'warning')
        return redirect(url_for('profile'))
    
    file = request.files['avatar']
    if file.filename == '':
        flash('No file selected', 'warning')
        return redirect(url_for('profile'))
    
    if file and allowed_file(file.filename):
        # Secure filename and save
        filename = secure_filename(f"avatar_{session['user_id']}_{file.filename}")
        filepath = os.path.join(app.config['AVATAR_FOLDER'], filename)
        file.save(filepath)
        
        # Update user record
        avatar_url = url_for('static', filename=f'avatars/{filename}')
        users_col.update_one(
            {"_id": ObjectId(session['user_id'])},
            {"$set": {"profile_picture": avatar_url}}
        )
        
        flash('Profile picture updated!', 'success')
    else:
        flash('Invalid file type. Please upload an image.', 'danger')
    
    return redirect(url_for('profile'))

@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    """Update user profile information"""
    user = get_current_user()
    
    # Get form data
    full_name = request.form.get('full_name', '').strip()
    phone_number = request.form.get('phone_number', '').strip()
    department = request.form.get('department', '').strip()
    year = request.form.get('year', '').strip()
    bio = request.form.get('bio', '').strip()
    
    # Get notification preferences
    email_pref = 'email_pref' in request.form
    sms_pref = 'sms_pref' in request.form
    all_sms_pref = 'all_sms_pref' in request.form
    whatsapp_pref = 'whatsapp_pref' in request.form
    browser_pref = 'browser_pref' in request.form
    
    # Update user
    update_data = {
        "full_name": full_name,
        "phone_number": phone_number if phone_number else None,
        "department": department,
        "year": year,
        "bio": bio,
        "notification_prefs": {
            "email": email_pref,
            "sms": sms_pref,  # Urgent only
            "all_sms": all_sms_pref,  # All notices
            "whatsapp": whatsapp_pref,
            "browser": browser_pref
        },
        "last_active": datetime.utcnow()
    }
    
    users_col.update_one(
        {"_id": user['_id']},
        {"$set": update_data}
    )
    
    flash('Profile updated successfully!', 'success')
    return redirect(url_for('profile'))

# Add a template filter for time since
@app.template_filter('time_since')
def time_since(date):
    if not date:
        return 'Never'
    
    if isinstance(date, str):
        return date
    
    now = datetime.utcnow()
    diff = now - date
    
    if diff.days > 365:
        return f"{diff.days // 365}y ago"
    if diff.days > 30:
        return f"{diff.days // 30}mo ago"
    if diff.days > 0:
        return f"{diff.days}d ago"
    if diff.seconds > 3600:
        return f"{diff.seconds // 3600}h ago"
    if diff.seconds > 60:
        return f"{diff.seconds // 60}m ago"
    return 'Just now'


# Dashboard
@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    user = get_current_user()
    selected_department = request.args.get("selected_department")

    # gallery upload
    if request.method == "POST":
        if "gallery_file" not in request.files:
            flash("No file selected", "warning")
        else:
            file = request.files["gallery_file"]
            if file.filename == "":
                flash("No file selected", "warning")
            elif file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                gallery_path = os.path.join(GALLERY_FOLDER, filename)
                file.save(gallery_path)
                flash(f"{filename} added to gallery!", "success")
            else:
                flash("Only images (JPG, PNG, GIF) allowed", "warning")

    # notices by this user
    query = {"author_id": ObjectId(user["_id"])}
    if selected_department and selected_department != "all":
        query["department"] = selected_department

    notices = list(notices_col.find(query).sort("created_at", -1))
    for n in notices:
        n["id"] = str(n["_id"])
        n["created_str"] = (
            n.get("created_at").strftime("%Y-%m-%d %H:%M") if n.get("created_at") else ""
        )

    # recent events for sidebar
    recent_events = list(events_col.find().sort("start", 1).limit(5))
    for e in recent_events:
        e["id"] = str(e["_id"])

    return render_template(
        "dashboard.html",
        current_user=user,
        notices=notices,
        selected_department=selected_department,
        recent_events=recent_events,
    )

@app.route('/download_notice/<id>')
def download_notice(id):
    # Fetch the notice from MongoDB
    notice = db.notices.find_one({"_id": ObjectId(id)})
    
    if not notice:
        return "Notice not found", 404

    # Create PDF logic
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="GECK DIGITAL NOTICE BOARD", ln=True, align='C')
    
    pdf.ln(10) # Line break
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt=notice['title'], ln=True, align='L')
    
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Department: {notice['department'].upper()}", ln=True, align='L')
    pdf.cell(200, 10, txt=f"Date: {notice['created_at'].strftime('%Y-%m-%d')}", ln=True, align='L')
    
    pdf.ln(5)
    pdf.multi_cell(0, 10, txt=notice['content'])
    
    # Return PDF as a download
    response = make_response(pdf.output(dest='S'))
    response.headers.set('Content-Type', 'application/pdf')
    response.headers.set('Content-Disposition', 'attachment', filename=f"Notice_{id}.pdf")
    return response




@app.route("/create_notice", methods=["GET", "POST"])
@roles_required("admin", "faculty")
def create_notice():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        pinned = bool(request.form.get("pinned"))
        department = request.form.get("department")
        display_type = request.form.get("display_type", "card")
        urgency = request.form.get('urgency', 'normal')  # Add this line

        if not title or not content:
            flash("Title and content are required.", "danger")
            return redirect(url_for("create_notice"))

        media_url = None
        media_type = None

        if "media" in request.files:
            file = request.files["media"]
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(save_path)

                media_url = url_for("static", filename=f"uploads/{filename}")
                ext = filename.rsplit(".", 1)[1].lower()

                if ext in ["mp3", "wav", "ogg"]:
                    media_type = "audio"
                elif ext in ["mp4", "avi", "mov", "webm", "mkv"]:
                    media_type = "video"
                else:
                    media_type = "image"

        user = get_current_user()
        notice = {
            "title": title,
            "content": content,
            "department": department,
            "pinned": pinned,
            "author_id": ObjectId(user["_id"]),
            "author_name": user["username"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "media_url": media_url,
            "media_type": media_type,
            "display_type": display_type,
            "urgency": urgency  # Add urgency field
        }

        notices_col.insert_one(notice)

        # Send notifications
        socketio.emit(
            "new_notice",
            {
                "title": title,
                "department": department,
                "created_str": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            },
            namespace="/"
        )
        
        # Email notifications
        send_new_notice_email(title, content, department, user["username"])
        
        # SMS/WhatsApp notifications for urgent notices
        if urgency == 'urgent':
            results = notifier.send_bulk_notification(notice, urgency='urgent')
            if results['sms_sent'] > 0 or results['whatsapp_sent'] > 0:
                flash(f"📱 Sent {results['sms_sent']} SMS and {results['whatsapp_sent']} WhatsApp notifications", "info")
        
        flash("Notice created.", "success")
        return redirect(url_for("dashboard"))

    department = request.args.get("department", "")
    return render_template(
        "create_notice.html",
        current_user=get_current_user(),
        department=department
    )

@app.route('/test-sms')
@login_required
@roles_required('admin')
def test_sms():
    """Test SMS functionality"""
    user = get_current_user()
    
    if not user.get('phone_number'):
        flash("You don't have a phone number saved. Add one in your profile first.", "warning")
        return redirect(url_for('profile'))
    
    test_notice = {
        'title': 'Test Notification',
        'content': 'This is a test message to verify SMS functionality.',
        'department': 'system',
        'author_name': 'System'
    }
    
    # Send test SMS
    result = notifier.send_sms(user['phone_number'], "🔧 Test message from GECK Notice Board. If you receive this, SMS is working!")
    
    if result:
        flash("✅ Test SMS sent successfully! Check your phone.", "success")
    else:
        flash("❌ Failed to send SMS. Check Twilio configuration.", "danger")
    
    return redirect(url_for('profile'))

@app.route('/whatsapp-setup')
@login_required
def whatsapp_setup():
    """Show WhatsApp sandbox setup instructions"""
    whatsapp_number = os.getenv('WHATSAPP_FROM_NUMBER', '+14155238886')
    join_code = "join your-sandbox-code"  # Get this from Twilio console
    
    return render_template('whatsapp_setup.html', 
                         whatsapp_number=whatsapp_number,
                         join_code=join_code)

# Edit Notice
@app.route("/notice/<id>/edit", methods=["GET", "POST"])
@login_required
def edit_notice(id):
    try:
        nid = ObjectId(id)
    except Exception:
        flash("Invalid notice ID.", "danger")
        return redirect(url_for("dashboard"))

    notice = notices_col.find_one({"_id": nid})
    if not notice:
        flash("Notice not found.", "danger")
        return redirect(url_for("dashboard"))

    user = get_current_user()
    if str(notice["author_id"]) != str(user["_id"]):
        flash("You are not authorized to edit this notice.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        pinned = bool(request.form.get("pinned"))

        if not title or not content:
            flash("Title and content are required.", "danger")
            return redirect(url_for("edit_notice", id=id))

        media_url = notice.get("media_url")
        media_type = notice.get("media_type")

        if "media" in request.files:
            file = request.files["media"]
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(save_path)

                media_url = url_for("static", filename=f"uploads/{filename}")
                ext = filename.rsplit(".", 1)[1].lower()

                if ext in ["mp3", "wav", "ogg"]:
                    media_type = "audio"
                elif ext in ["mp4", "avi", "mov", "webm", "mkv"]:
                    media_type = "video"
                else:
                    media_type = "image"

        notices_col.update_one(
            {"_id": nid},
            {"$set": {
                "title": title,
                "content": content,
                "pinned": pinned,
                "updated_at": datetime.utcnow(),
                "media_url": media_url,
                "media_type": media_type
            }}
        )

        socketio.emit(
            "update_notice",
            {
                "title": title,
                "department": notice.get("department"),
            },
            namespace="/"
        )

        flash("Notice updated.", "success")
        return redirect(url_for("dashboard"))

    notice["id"] = str(notice["_id"])
    return render_template("edit_notice.html", notice=notice, current_user=user)


# Delete Notice
@app.route("/notice/<id>/delete", methods=["POST"])
@login_required
def delete_notice(id):
    try:
        nid = ObjectId(id)
    except Exception:
        flash("Invalid ID.", "danger")
        return redirect(url_for("dashboard"))

    notice = notices_col.find_one({"_id": nid})
    user = get_current_user()

    if not notice or str(notice["author_id"]) != str(user["_id"]):
        flash("Not authorized or not found.", "danger")
        return redirect(url_for("dashboard"))

    notices_col.delete_one({"_id": nid})
    flash("Notice deleted.", "info")
    return redirect(url_for("dashboard"))


@app.route("/all-notices")
def all_notices():
    all_n = list(notices_col.find().sort("created_at", -1))
    for n in all_n:
        n["id"] = str(n["_id"])
        n["created_str"] = (
            n.get("created_at").strftime("%Y-%m-%d %H:%M")
            if n.get("created_at") else ""
        )
    return render_template(
        "all_notices.html",
        notices=all_n,
        current_user=get_current_user()
    )


# Notices API
@app.route("/api/notices")
def api_notices():
    notices = list(notices_col.find().sort([("pinned", -1), ("created_at", -1)]))
    for n in notices:
        n["id"] = str(n["_id"])
        n["created_at"] = n.get("created_at").isoformat() if n.get("created_at") else None
        n["_id"] = str(n["_id"])
        n["author_id"] = str(n.get("author_id")) if n.get("author_id") else None
    return jsonify(notices)


# Sample data initializer
@app.route("/init-sample")
def init_sample():
    if users_col.find_one({"email": "admin@example.com"}):
        flash("Sample user already exists.", "info")
        return redirect(url_for("index"))

    pw = generate_password_hash("password")
    res = users_col.insert_one({
        "username": "admin",
        "email": "admin@example.com",
        "password": pw,
        "role": "admin",
        "created_at": datetime.utcnow()
    })

    notices_col.insert_many([
        {
            "title": "Welcome to the Notice Board",
            "content": "This is a sample notice. Edit or remove it after logging in.",
            "pinned": True,
            "author_id": res.inserted_id,
            "author_name": "admin",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
        {
            "title": "Meeting Tomorrow",
            "content": "Don't forget the team meeting at 10am in Room 3.",
            "pinned": False,
            "author_id": res.inserted_id,
            "author_name": "admin",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    ])

    flash("Sample user and notices created. Login with admin@example.com / password", "success")
    return redirect(url_for("index"))


@app.route("/gallery")
def gallery():
    files = []
    if os.path.isdir(GALLERY_FOLDER):
        files = [
            f"gallery/{name}" for name in os.listdir(GALLERY_FOLDER)
            if name.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))
        ]
    files.sort()
    return render_template("gallery.html", images=files, current_user=get_current_user())


# Chat bot endpoint
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip().lower()

    if not message:
        return jsonify({"reply": "Please type a question about notices, departments, exams or gallery."})

    if any(word in message for word in ["hi", "hello", "hey", "hai"]):
        return jsonify({"reply": "Hello! How can I help you with notices, exams, or departments today?"})

    if "thank" in message:
        return jsonify({"reply": "You’re welcome! If you need anything else about notices or timetable, just ask."})

    if "all notice" in message or "all notices" in message:
        return jsonify({"reply": "To view all notices, open the 'All Notices' page from the Departments section. There you can scroll through every department notice in one place."})

    if "cse" in message and "notice" in message:
        return jsonify({"reply": "To view CSE notices, open the CSE department card and check the notices listed there."})

    if "login" in message or "log in" in message or "sign in" in message:
        return jsonify({"reply": "To log in, use your email and password on the Login page. If you don’t have an account yet, use Sign up first."})

    if (("create" in message and "notice" in message) or
        ("edit" in message and "notice" in message)):
        return jsonify({"reply": "Anyone can create a notice and only the person who created it can edit it."})

    if "gallery" in message or "photo" in message or "image" in message:
        return jsonify({"reply": "To view the photo gallery, click on the 'Photo Gallery' link in the navbar."})

    if "department" in message or "branch" in message:
        return jsonify({"reply": "Available departments include CSE, ECE, Mechanical, and Civil. Each has its own notice section."})

    if "search" in message or "find" in message or "notice" in message:
        keyword = message.replace("search", "").replace("find", "").replace("notice", "").strip()
        if not keyword:
            keyword = message

        results = notices_col.find(
            {
                "$or": [
                    {"title": {"$regex": keyword, "$options": "i"}},
                    {"content": {"$regex": keyword, "$options": "i"}},
                ]
            }
        ).sort("created_at", -1).limit(3)

        titles = [n.get("title", "Untitled") for n in results]

        if titles:
            reply_lines = ["Here are some notices related to your search:"]
            for t in titles:
                reply_lines.append(f"- {t}")
            reply_lines.append("You can see full details on the website by opening the related department or All Notices page.")
            return jsonify({"reply": "\n".join(reply_lines)})

    return jsonify({"reply": "Sorry, I am a simple FAQ bot. Please ask about notices, departments, exams, login, gallery, or ask me to search for a notice by keyword."})


# Events pages & API
@app.route("/events")
def events():
    return render_template("events.html", current_user=get_current_user())


@app.route("/api/events")
def api_events():
    events = []
    for e in events_col.find().sort("start", 1):
        events.append({
            "id": str(e["_id"]),
            "title": e.get("title", "Event"),
            "start": e.get("start").date().isoformat() if e.get("start") else None,
            "end": e.get("end").date().isoformat() if e.get("end") else None,
            "allDay": True,
        })
    return jsonify(events)


@app.route("/events/add", methods=["POST"])
@login_required
def add_event():
    title = request.form.get("title", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()

    if not title or not start_date:
        flash("Event title and start date are required.", "danger")
        return redirect(url_for("dashboard"))

    try:
        start = datetime.fromisoformat(start_date)
    except Exception:
        flash("Invalid start date.", "danger")
        return redirect(url_for("dashboard"))

    end = None
    if end_date:
        try:
            end = datetime.fromisoformat(end_date)
        except Exception:
            flash("Invalid end date.", "danger")
            return redirect(url_for("dashboard"))

    events_col.insert_one({
        "title": title,
        "start": start,
        "end": end,
        "created_at": datetime.utcnow(),
        "created_by": get_current_user().get("username"),
    })

    flash("Event added to calendar.", "success")
    return redirect(url_for("dashboard"))


@app.route("/events/<id>/delete", methods=["POST"])
@login_required
def delete_event(id):
    try:
        eid = ObjectId(id)
    except Exception:
        flash("Invalid event ID.", "danger")
        return redirect(url_for("dashboard"))

    events_col.delete_one({"_id": eid})
    flash("Event deleted from calendar.", "info")
    return redirect(url_for("dashboard"))
@app.route('/debug-session')
@login_required
def debug_session():
    """Debug route to check session and user"""
    user = get_current_user()
    session_data = dict(session)
    
    debug_info = {
        'session_id': session.get('user_id'),
        'session_data': session_data,
        'user_exists': user is not None,
        'user_id': str(user['_id']) if user else None,
        'user_keys': list(user.keys()) if user else [],
        'full_name': user.get('full_name') if user else None,
        'username': user.get('username') if user else None
    }
    
    return jsonify(debug_info)

if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
