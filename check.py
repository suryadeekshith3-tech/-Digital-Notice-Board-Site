from pymongo import MongoClient

# Replace with your actual MongoDB URI if different
MONGO_URI = "mongodb://localhost:27017/digital_noticeboard"
client = MongoClient(MONGO_URI)
db = client.digital_noticeboard
notices_col = db.notices

# Query for notices with department "cse"
cse_notices = list(notices_col.find({"department": "cse"}))

print(f"Found {len(cse_notices)} notices for CSE:")
for n in cse_notices:
    print(f"- Title: {n.get('title')}, Created at: {n.get('created_at')}")
