# keep_alive.py
from datetime import datetime

print("🚀 Starting keep-alive for Streamlit app...")

# Update timestamp file (this creates real repo activity)
with open("LAST_ACTIVE.txt", "w") as f:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    f.write(f"Streamlit app was kept alive at: {timestamp}\n")
    f.write("This file is automatically updated by GitHub Actions\n")

print(f"✅ Successfully updated LAST_ACTIVE.txt at {timestamp}")
print("Your Streamlit app should now stay active! 🎉")
