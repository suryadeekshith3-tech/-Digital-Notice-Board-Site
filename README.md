Digital Notice Board (Flask + MongoDB)

1. Setup
   - Python 3.10+
   - MongoDB running locally or use Atlas

2. Install
   $ python -m venv venv
   $ source venv/bin/activate   # Windows: venv\Scripts\activate
   $ pip install -r requirements.txt

3. Configure
   - Copy .env.example -> .env and set MONGO_URI and SECRET_KEY

4. Run
   $ python app.py
   - Open http://localhost:5000

Optional: visit /init-sample to create a sample user admin@example.com / password

# GECK Digital Notice Board

A feature-rich digital notice board system built with Flask and MongoDB, featuring real-time updates, user roles, multimedia support, and multi-channel notifications.

## 📋 Overview

The GECK Digital Notice Board replaces traditional physical notice boards with a modern, accessible digital solution. It allows faculty and administrators to post notices with multimedia attachments, while students can view, search, and receive notifications across multiple channels.

## ✨ Features

### Core Features
- **User Authentication System** - Secure login/registration with role-based access
- **Role-Based Access Control** - Different permissions for Students, Faculty, and Admins
- **Notice Management** - Create, edit, delete notices with rich text content
- **Department-wise Organization** - Notices categorized by CSE, ECE, MECH, CIVIL
- **Multimedia Support** - Upload images, audio, and video with notices
- **Pinned Notices** - Highlight important announcements
- **Announcement Banner** - Special display type for critical updates

### Advanced Features
- **Real-time Updates** - Live notifications via Socket.IO
- **Multi-channel Notifications**
  - 📧 Email alerts for new notices
  - 📱 SMS notifications (Twilio integration)
  - 💬 WhatsApp messages (Twilio integration)
- **Profile Management** - Customizable user profiles with avatars
- **Photo Gallery** - Upload and manage images
- **Event Calendar** - Schedule and display events
- **Notice Search** - Search functionality across all notices
- **PDF Export** - Download notices as PDF documents
- **Bookmark System** - Save important notices
- **Notification Preferences** - Users control their notification channels
- **Chatbot Assistant** - FAQ bot for common queries

## 🚀 Tech Stack

- **Backend**: Python Flask 2.2.5
- **Database**: MongoDB (PyMongo 3.12.3)
- **Real-time**: Flask-SocketIO
- **Authentication**: Werkzeug security (password hashing)
- **Email**: Flask-Mail with SMTP
- **SMS/WhatsApp**: Twilio API
- **PDF Generation**: FPDF
- **Frontend**: HTML5, CSS3, JavaScript (with responsive design)
- **Templating**: Jinja2

## 📦 Installation

### Prerequisites
- Python 3.8 or higher
- MongoDB (local installation or MongoDB Atlas)
- Twilio account (for SMS/WhatsApp)
- Gmail account (for email notifications)

### Step-by-Step Setup

1. **Clone the Repository**
```bash
git clone https://github.com/yourusername/digital-notice-board.git
cd digital-notice-board

digital-notice-board/
├── app.py                      # Main application file
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables
├── check.py                    # Database checker utility
├── email_errors.log            # Email error logging
├── static/
│   ├── uploads/                # Uploaded media files
│   ├── gallery/                 # Gallery images
│   └── avatars/                 # User profile pictures
├── templates/                  # HTML templates
│   ├── index.html              # Homepage
│   ├── auth.html               # Authentication page
│   ├── dashboard.html          # User dashboard
│   ├── profile.html            # User profile
│   ├── create_notice.html      # Create notice form
│   ├── edit_notice.html        # Edit notice form
│   ├── admin_manage.html       # Admin management
│   ├── all_notices.html        # All notices view
│   ├── departments/            # Department pages
│   │   ├── cse.html
│   │   ├── ece.html
│   │   ├── mech.html
│   │   └── civil.html
│   ├── gallery.html            # Photo gallery
│   ├── events.html             # Calendar events
│   ├── about.html              # About page
│   └── contact.html            # Contact page
└── README.md                   # This file


This README provides comprehensive documentation tailored to your actual codebase, including all the features and technologies present in your `app.py` file.
