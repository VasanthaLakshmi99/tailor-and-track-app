# Tailor&Track

A free job-search helper that runs on your own laptop. It:

- **finds jobs** that fit your master resume: company career sites (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, Bullhorn and others), remote-job feeds, and the **J button** on LinkedIn, Dice, ZipRecruiter or any job page
- **blocks duplicates**, so you never apply to the same job twice
- shows a **match %** for every job against your resume
- **tailors your resume** for each job automatically (PDF, in your master resume's layout)
- **tracks applications** and makes monthly or yearly **Excel reports**

Your data (resumes, applications) stays **on your own computer**. Nothing is uploaded anywhere.

---

## 1. Install (one time, about 10 minutes)

1. Install **Python 3.11 or newer** from https://www.python.org/downloads/.
   On Windows, tick **"Add python.exe to PATH"** on the first screen of the installer.
2. Download this project:
   - **Easy way:** on the GitHub page click the green **Code** button, then **Download ZIP**, and unzip it (for example to `C:\Users\<you>\tailor-and-track`).
   - **With Git:** `git clone <this repo link>`
3. Open a terminal (Command Prompt, or the terminal in VS Code) **inside the project folder** and run:
   ```
   python -m pip install -r requirements.txt
   ```

## 2. Start the app

In the project folder run:
```
python -m streamlit run app.py
```
The app opens in your browser at http://localhost:8501. Keep the terminal open while you use it.
To stop it, press **Ctrl+C** in the terminal.

## 3. Install the J button (Chrome or Edge, one time)

1. Open `chrome://extensions` (or `edge://extensions`).
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and choose the **`extension`** folder inside this project.
4. Click the puzzle icon 🧩 in the toolbar and **pin** the J button.

On any job page, click **J** to see the match % and the duplicate check, then **Save**.
The app must be running for the J button to work.

## 4. First steps in the app

1. **Profiles:** set your name, then upload your **master resume** (PDF or DOCX). Target roles and locations are read from the resume automatically, and you can change them.
2. **Profiles → 📁 Where tailored resumes are saved:** choose a folder. A Google Drive or OneDrive folder saves laptop space.
3. **Find jobs:** pick **Date posted** and click **Collect now**. Also save jobs with the **J button**.
4. **Tailor resumes:** click **⚡ Auto-tailor**. Only tick JD skills you have really used.
5. **Apply & track:** open each job, apply, and tick **Applied ✓**. Download the Excel report at the bottom.

### Optional free keys (more US jobs)
In **Find jobs → ⚙️ Collection settings** you can add:
- **Jooble** API key (free): https://jooble.org/api/about
- **JSearch** on RapidAPI (free Basic plan, 200 searches/month): https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch

Never put keys in the code or on GitHub. Type them into the app.

## Updating

Download the new version, replace the `.py` files, the `extension` folder and the `fonts` folder, and restart the app.
Your data (`tailortrack.db`) and your resumes are not touched.

## Privacy

- Everything is stored in `tailortrack.db` and your resumes folder, both on your computer.
- These are listed in `.gitignore`, so they are **never** uploaded to GitHub.

## License

MIT, see `LICENSE`. The bundled Carlito font uses the SIL Open Font License (`fonts/OFL.txt`).