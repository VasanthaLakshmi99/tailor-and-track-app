# Tailor&Track

A free job-search helper that runs on your own laptop. It:

- **finds jobs** that fit your master resume: company career sites (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, Bullhorn and others), remote-job feeds, and the **J button** on LinkedIn, Dice, ZipRecruiter or any job page
- **blocks duplicates**, so you never apply to the same job twice
- shows a **match %** for every job against your resume
- **tailors your resume** for each job automatically (PDF, in your master resume's layout)
- **checks visa sponsorship**: UK jobs against the Home Office register of licensed sponsors, and what every JD says
- **checks the ATS score** of every resume against the JD (hard skills, job title, soft skills, experience, education, format)
- **tracks applications** and makes **Excel reports** for any dates you pick
- **fills application forms** (name, email, phone, LinkedIn, work authorization, resume upload…) with the J button. You check and submit.

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
3. **Find jobs:** pick **Date posted** (30 min … past month, or Custom) and the **🎓 Experience** range, then click **Collect now**.
   Under the Collection card pick **📍 Locations** (several countries, Remote, or type cities), **🎯 Which jobs**
   (only target roles / + related roles / any job your skills match) and **➕ Top up with older jobs to** (0 = only jobs
   from your Date posted time; e.g. 30 = add the newest older ones, up to 7 days, until there are 30).
   In **Jobs waiting**, set the filters and click **✅ Keep only these**: the other waiting jobs are deleted and
   are not collected again.
   While the app is open it also collects new jobs **every 3 hours** by itself (change it in ⚙️ Collection settings).
   Jobs come from the countries in the resume / profile locations (US, India, UK, Canada, Germany, UAE and more).
4. **Tailor resumes:** click **⚡ Auto-tailor**. Only tick JD skills you have really used. **📊 ATS check** on each card shows the score and what to fix.
5. **Profiles → ✍️ Application form answers:** save them once. On an application page click **J → ✍️ Fill application form**.
6. **Apply & track:** open each job, apply, and tick **Applied ✓**. Download the Excel report at the bottom (pick **Custom dates…** for any period).
   **🧹 Duplicate jobs** at the bottom removes jobs saved twice.

### Visa sponsorship
In **Profiles**, fill **Needs visa sponsorship for** (e.g. `United Kingdom`). Then:
- every job shows ✅ licensed sponsor / JD offers sponsorship, ❌ JD says no, ⚠️ not on the UK register, ❔ not mentioned
- the J button shows the same line
- automatic collection skips jobs whose JD says "no sponsorship" (and, with **Collect only from visa sponsors**, UK companies that are not licensed sponsors)
The UK register (about 120,000 employers) is downloaded free from GOV.UK once a week.

### Keep the laptop fast
- **Profiles → 📁 Where tailored resumes are saved:** use a Google Drive / OneDrive folder with "Stream files" / "Files On-Demand".
- **Profiles → 🧹 Free up space:** deletes tailored PDFs of jobs you did not apply to (applied ones are kept).

### Optional free keys (more jobs, all official and free)
In **Find jobs → ⚙️ Collection settings** you can add:

| Key | Country | Get it |
|---|---|---|
| Jooble | many countries | https://jooble.org/api/about |
| JSearch (RapidAPI, free Basic plan) | all countries (Google Jobs) | https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch |
| Reed | United Kingdom | https://www.reed.co.uk/developers/jobseeker |
| USAJOBS | US government | https://developer.usajobs.gov/apirequest/ |
| France Travail (client ID + secret) | France | https://francetravail.io/data/api/offres-emploi |
| Findwork | software jobs, US / EU / remote | https://findwork.dev/developers/ |

No key needed: Arbeitsagentur (Germany), Arbetsförmedlingen (Sweden), 300 company career sites, remote-job feeds.
Naukri, LinkedIn and Indeed have no free public API: use the J button on their pages.

Never put keys in the code or on GitHub. Type them into the app.

## Updating

Download the new version, replace the `.py` files, the `extension` folder and the `fonts` folder, and restart the app.
Your data (`tailortrack.db`) and your resumes are not touched.

## Privacy

- Everything is stored in `tailortrack.db` and your resumes folder, both on your computer.
- These are listed in `.gitignore`, so they are **never** uploaded to GitHub.

## License

MIT, see `LICENSE`. The bundled Carlito font uses the SIL Open Font License (`fonts/OFL.txt`).