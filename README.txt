IIT Cal – Offline JEE Study Dashboard
====================================

WHAT THIS APP IS
----------------
IIT Cal is a fully offline Windows desktop application made for
long-term, disciplined JEE preparation.

It helps you:
- Track daily study sessions (start / stop)
- Measure total study time
- Write daily mistakes and reflections
- View monthly productivity in a calendar view

No internet.
No login.
No cloud.
All data stays on this computer.

--------------------------------------------------

HOW TO USE (BASIC)
------------------
1. Open the folder: Desktop → IIT Cal
2. Run the file: app.py
3. Use Start / Stop to track study sessions
4. Fill daily details and save
5. Complete the end-of-day popup honestly

--------------------------------------------------

IMPORTANT FOLDERS (DO NOT RENAME)
---------------------------------
data/     → All your study data (VERY IMPORTANT)
images/   → Background images (optional)
sounds/   → Alert sounds (optional)
logs/     → Error and safety logs

--------------------------------------------------

FILES YOU MAY EDIT SAFELY
-------------------------
config.json  → App settings
links.txt    → Website shortcut buttons
quotes.txt   → Motivational quotes

DO NOT edit CSV files while the app is running.

--------------------------------------------------

DATA SAFETY
-----------
- Your data is saved automatically.
- Backups are created if anything goes wrong.
- If Excel opens a CSV file, close Excel before saving in the app.

--------------------------------------------------

IF SOMETHING BREAKS
-------------------
1. Close the app.
2. Open logs/error_log.txt
3. Read the last message.
4. Do NOT delete data files.

--------------------------------------------------

DEVELOPER NOTES
---------------
- Change image interval: edit config.json → image_interval_seconds.
- Add new buttons: edit links.txt (DisplayName|URL per line).
- Change quotes: edit quotes.txt (one per line).
- Rebuild EXE (example):
  pyinstaller --noconsole --onefile app.py

--------------------------------------------------

NOTE
----
This app is designed for discipline, not entertainment.
Use it daily. Use it honestly.
