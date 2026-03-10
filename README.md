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
