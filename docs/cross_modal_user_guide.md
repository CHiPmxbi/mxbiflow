## MXBI — Installation & Setup (one-time)

This guide covers **macOS** and **Windows (PowerShell)**. Follow the steps in order.

---

### What you need

* The **mxbi** project ZIP (you will unzip it on your computer).
* Internet connection (only for installing Python and packages).
* **macOS:** Python **3.13 or newer**
* **Windows:** Python **3.11** (required for **PyAudio** on Windows; do not use 3.13 there)

---

## 1) Unzip the mxbi repo ZIP

### macOS (Finder)

1. Open **Finder** → go to **Downloads** (or wherever you saved the ZIP).
2. Double-click the ZIP to unzip it.
3. Move the unzipped folder to a stable location, for example:

   * `~/Documents/mxbi`

> Note: If the ZIP was created on a Mac, you may see a `__MACOSX` folder after unzipping. You can ignore it.

### Windows (PowerShell) — recommended location and unzip

**Important**
* Avoid long paths and synced folders like OneDrive.
* Use a short, stable folder such as `C:\mxbi`.

#### Step 1 — Create the destination folder
You will unzip the project into `C:\mxbi`.

```powershell
New-Item -ItemType Directory -Force C:\mxbi | Out-Null
````

#### Step 2 — Unzip (choose ONE method)

**Option A — Unzip via File Explorer**

1. Right-click the ZIP → **Extract All…**
2. Set the destination to: `C:\mxbi`
3. Extract.

**Option B — Unzip via PowerShell (reliable)**

1. Open **Windows Terminal** → **PowerShell**
2. Run (update the ZIP name if needed):

```powershell
Expand-Archive -Path "$HOME\Downloads\mxbi.zip" -DestinationPath "C:\mxbi" -Force
```

#### Step 3 — Find the repo root (this is the folder you will `cd` into later)

The **repo root** is the folder that contains:
`config\`, `src\`, and `pyproject.toml`.

Start here:

```powershell
cd C:\mxbi
dir
```

Now do the “go in and check” loop:

1. If you see a single folder (commonly named `mxbi`), go into it:

   ```powershell
   cd .\mxbi
   dir
   ```
2. If you still don’t see `config`, `src`, and `pyproject.toml`, you are one level too high. Go into the next folder you see and run `dir` again.

**You are done when `dir` shows `config`, `src`, and `pyproject.toml`.**

#### If you ended up with an extra nested `mxbi\mxbi\` folder (common with ZIPs)

Example problem:
`C:\mxbi\mxbi\mxbi\` contains `pyproject.toml` (too deep).

If you are currently at `C:\mxbi\mxbi` and you see another `mxbi` folder inside it, run:

```powershell
Move-Item -Force .\mxbi\* .\
Remove-Item -Recurse -Force .\mxbi
dir
```

After this, `dir` should show `config`, `src`, and `pyproject.toml` directly in `C:\mxbi\mxbi`.

---

## 2) Open a terminal

### macOS

1. Open **Finder**
2. Go to **Applications → Utilities**
3. Open **Terminal**

### Windows (PowerShell)

1. Press the **Windows key**
2. Type **Windows Terminal**
3. Open **Windows Terminal**
4. Make sure the tab says **PowerShell** (not Command Prompt)

---

## 3) Install Python

### macOS — install Python 3.13+

1. Download Python from the official Python site (macOS installer for **Python 3.13**).
2. Run the installer and complete it.
3. Verify:

   ```bash
   python3 --version
   ```

   You should see `Python 3.13.x` (or newer).

If `python3` is not found, try:

```bash
python --version
```

### Windows — install Python 3.11 (required)

1. Download Python **3.11.x** from the official Python site (Windows installer).
2. Run the installer.
3. **Critical:** check **“Add python.exe to PATH”**.
4. Finish installation.
5. Verify in PowerShell:

   ```powershell
   python --version
   ```

   You should see `Python 3.11.x`.

If `python` still isn’t found, close and re-open Windows Terminal, then try again.

If **`python --version` is NOT 3.11**
Some PCs have multiple Python versions installed. In PowerShell, you can use the Windows Python launcher to target 3.11 explicitly:

```powershell
py -3.11 --version
```

---

## 4) Go to the mxbi project folder (repo root)

You need to navigate into the folder that contains `config/`, `src/`, and `pyproject.toml`.

### macOS example

If your project is in `~/Documents/mxbi`:

```bash
cd ~/Documents/mxbi
```

### Windows example

If your project is in `C:\mxbi\mxbi`:

```powershell
cd C:\mxbi\mxbi
```

### Confirm you are in the right place

**macOS**

```bash
ls
```

**Windows**

```powershell
dir
```

You should see items including:

* `config`
* `src`
* `pyproject.toml`

If you don’t see those, you are not in the repo root yet.

---

Yes. You can make that “remove `pymotego`” portion a single coherent mini-procedure (goal → do → verify → what if it didn’t work), instead of “optional” plus scattered code blocks.

Below is a **drop-in replacement** for the entire “remove `pymotego`” subsection (keep your section header `## 5) ...` and replace the contents under it with this). It preserves the manual editor route but makes the command route first-class and idiot-proof.

---

## 5) Remove `pymotego` from `pyproject.toml` (required)

MXBI currently includes a dependency line that must be removed before installing packages.

### Step 1 — Confirm you are in the repo root
You must run this in the folder that contains `pyproject.toml`.

**macOS**
```bash
ls
````

**Windows (PowerShell)**

```powershell
dir
```

You should see `pyproject.toml` in the output.

### Step 2 — Remove the `pymotego` line (choose ONE method)

#### Method A — Remove it using a command (recommended)

**macOS (Terminal)**

```bash
# Removes any line that contains the text "pymotego"
perl -i -ne 'print unless /pymotego/' pyproject.toml
```

**Windows (PowerShell)**

```powershell
# Removes any line that contains the text "pymotego"
(Get-Content .\pyproject.toml) | Where-Object { $_ -notmatch 'pymotego' } | Set-Content .\pyproject.toml
```

#### Method B — Remove it manually in an editor

1. Open `pyproject.toml` (VS Code recommended).
2. Find and delete the line that looks like:

   ```toml
   "pymotego>=0.1.3",
   ```
3. Save the file.

### Step 3 — Verify it is removed

**macOS**

```bash
grep -n "pymotego" pyproject.toml || echo "OK: pymotego removed"
```

**Windows (PowerShell)**

```powershell
if (Select-String -Path .\pyproject.toml -Pattern "pymotego" -Quiet) { "Still present (not removed)" } else { "OK: pymotego removed" }
```

> If you already ran the dependency installation step before removing `pymotego`, remove it now, then re-run the install step in section 7.

---

## 6) Create and activate the Python environment

This keeps the project packages isolated.

### macOS

1. Create:

   ```bash
   python3 -m venv .venv
   ```
2. Activate:

   ```bash
   source .venv/bin/activate
   ```

### Windows (PowerShell)

1. Create:

   ```powershell
   py -3.11 -m venv .venv
   ```
    
    Alternatively try
    ```powershell
   python -m venv .venv
   ```
    
2. Activate:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

If Windows blocks activation with a policy error, run this once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then activate again:

```powershell
.\.venv\Scripts\Activate.ps1
```

You should see `(.venv)` at the start of your prompt.

Verify the Python version. It should be 3.13 for Mac and 3.11 for Windows:
```powershell
   python --version
   ```

---

## 7) Install MXBI and its required packages

Make sure:

* You are in the repo root (same folder as `pyproject.toml`)
* Your environment is activated (`(.venv)` visible)

1. Upgrade installer tools:

   ```bash
   python -m pip install --upgrade pip
   ```
2. Install MXBI and dependencies:

   ```bash
   python -m pip install -e .
   ```

This reads dependencies from `pyproject.toml`.

---

## 8) Fix the PyAudio dependency (required for audio playback)

### macOS (recommended method)

PyAudio needs PortAudio. Install PortAudio, then PyAudio: ([PyPI][1])

1. Install Homebrew (if you don’t have it), then:

   ```bash
   brew install portaudio
   ```
2. Install PyAudio:

   ```bash
   python -m pip install pyaudio
   ```

### Windows (PowerShell) — Python 3.11 required

On Windows, PyAudio often fails to build from source. The most reliable approach is installing a prebuilt binary via `pipwin`: ([Stack Overflow][2])

1. Install pipwin:

   ```powershell
   python -m pip install pipwin
   ```
2. Install PyAudio:

   ```powershell
   pipwin install pyaudio
   ```

**If `pipwin install pyaudio` fails**, try this fallback (prebuilt wheels helper): ([PyPI][3])

```powershell
python -m pip install pyaudio-wheels
python -m pip install pyaudio
```

---

## 9) Create the `data` folder for bundle input and run output (recommended)

From the repo root:

### macOS

```bash
mkdir -p data/bundles
```

### Windows (PowerShell)

```powershell
New-Item -ItemType Directory -Force .\data\bundles | Out-Null
```

You will place your **dataset bundle folder** inside `data/bundles/`.

---

# MXBI — Usage (day-to-day)

## A) Launch the MXBI apps

From the repo root (same folder as `pyproject.toml`) with the environment activated:

### 1) Open the Launch Panel (session configuration)

```bash
python -m src.mxbi.ui.launch_panel
```

Use this to:

* choose **Session** settings (general hardware + animals + detector)
* load a cross-modal bundle directory (Cross-modal tab)
* choose audio/visual settings
* press **Start** to save configuration

### 2) Run the mock theater (test run of the box software)

```bash
python -m src.mxbi.theater
```

Use this to run a test/mock session (development / dry-run), depending on your configuration.

---

## B) Create a cross-modal dataset bundle (web app)

Use the bundle creation web app:

* `https://marmoset-dataset-preparation.vercel.app/`

### Important note about bundle folder names

Sometimes the **downloaded** bundle folder name differs from the name you used when **uploading** in the web app. That is fine.

What matters for MXBI is:

* you **unzip** the bundle
* you select the **bundle folder itself** in the Launch Panel (not the ZIP, not the parent directory)

Recommended placement after download:

* Put the unzipped bundle folder under:

  * `mxbi/data/bundles/<your_bundle_folder>`

### Move the bundle into place

#### macOS example

If the bundle is in Downloads:

```bash
mv ~/Downloads/<bundle_folder> ./data/bundles/
```

#### Windows (PowerShell) example

```powershell
Move-Item "$HOME\Downloads\<bundle_folder>" ".\data\bundles\"
```

---

## C) Cross-modal Launch Panel — How to create a session (Cross-modal tab)

### What you need before you open the Launch Panel

#### 1) Have a prepared cross-modal dataset bundle folder

You need a dataset bundle directory that already contains the trials and media. You will select this folder in the Cross-modal tab.

You don’t edit files inside the bundle from the Launch Panel. The bundle is treated as read-only input.

#### 2) Make sure all subject names from the bundle are “known” to MXBI

When you load a bundle, MXBI checks whether every subject in that bundle is in the allowed animal name list. If it isn’t, the Launch Panel will show an error and won’t let you start.

**File to edit (if you get that error):**

* `mxbi/config/options_session.json`

**What to change:**

* Add missing subject IDs under:

```json
{
  "animal": {
    "name": [
      "...",
      "your_subject_id_here"
    ]
  }
}
```

**Important:**

* The subject ID must match exactly (same spelling and capitalization) what the bundle reports as a subject.

#### 3) If you use RFID identity detection: register tags to animal names

If the box uses RFID to identify animals, the system needs a mapping from tag → animal name.

**File to edit:**

* `mxbi/config/animal_db.json`

**What to add:**

* Add the RFID tag ID as the key, and the animal’s name as the value:

```json
{
  "abcd": { "name": "your_subject_id_here" }
}
```

**Important:**

* The `"name"` must match the subject ID used in the bundle.

If you are running a mock setup without RFID, this may not block starting, but it’s still recommended for consistent naming.

---

### Using the Launch Panel (Cross-modal tab)

The Launch Panel has two tabs: **Session** and **Cross-modal**. For cross-modal experiments, you mainly use **Cross-modal**, then press **Start**.

#### Step 1 — Go to the “Cross-modal” tab

#### Step 2 — Select the dataset bundle directory

Under **Dataset bundle**, click **Browse…** and select the dataset bundle folder.

After selection:

* The list of subjects should appear in the **Subjects** box.
* The **Errors** box should be empty.

If you see errors:

* Fix what it says (most commonly: missing subject names in `options_session.json`)
* Then select the bundle again.

#### Step 3 — Choose which subjects will run

In **Subjects**, you can select one or more subjects.

By default, all subjects are selected.

Only the selected subjects will be included when you press **Start**.

#### Step 4 — Adjust Visual settings

**Image size**
This controls how large the two face images appear on the screen.

* Smaller values → smaller images
* Larger values → larger images

Use this to ensure the faces are clearly visible and not cropped or too small.

#### Step 5 — Adjust Audio settings

**Master volume**
Overall output volume level of the system.

**Digital volume**
A second loudness control that affects the digital output stage.

**Gain**
Software loudness applied directly to the sound file before playback.

* `1.00` = unchanged
* above `1.00` = louder, but can distort if pushed too high
* below `1.00` = quieter

Recommended practice:

* First set Master/Digital to safe, comfortable levels.
* Then use Gain for fine adjustment if the stimuli themselves vary.

#### Step 6 — Set WAV sample rate policy

**Policy = resample**
MXBI will adapt mismatched WAV sample rates automatically so playback works.

**Policy = error**
MXBI will refuse to run a trial if an audio file has the wrong sample rate.

---

### Starting the session

#### Step 7 — Press “Start”

When you press **Start**:

1. Your Cross-modal settings are saved.
2. Your session settings are saved.
3. The Launch Panel closes.

From that point on, the session uses:

* the selected bundle directory
* the selected subject list
* the visual/audio settings you chose

---

## D) Session Launch Panel — What each option means (Session tab)

The **Session** tab defines the “hardware + identity + animal setup” for the run. This is where you choose **mock vs real box** behavior.

### General section

#### Experimenter

* Who is running the session (used for labeling/logging).
* **Dropdown values come from:** `mxbi/config/options_session.json` → `experimenter`
* To add a new experimenter, add it to that list, for example:

  ```json
  {
    "experimenter": ["jgr", "jcm", "mjk", "cko", "kud", "yang", "NEWNAME"]
  }
  ```

#### XBI

* Which physical box configuration you are using.
* **`debug` = mock/testing box identity**
* **`mxbi1` … `mxbi9` = real box identities**

**Rule of thumb**

* **Dry run / laptop testing:** use `debug`
* **Real box run:** use the correct `mxbiX` for that physical setup

#### Reward

* Type of reward delivery (e.g., what liquid/reward profile is being used).
* Pick the one your rig is actually configured for.

#### Pump

* **`mock`**: no real hardware pump (safe for testing)
* **`rasberry_pi_gpio`**: real pump controlled via Raspberry Pi GPIO (real box mode)

#### Platform

* Choose the platform the session is running on.
* In real box operation this is typically the Raspberry Pi.

#### Screen

* Screen profile (resolution/target display). Often `default`.

#### Comments

* Free text notes stored with the session config (useful to record anything special about the run).

---

### Detector section

#### Detector

* **`mock`**: no real detector hardware (safe for testing)
* **`dorset_lid665v42`**: real detector (use only when connected)

#### Port

* The serial port device for the detector.
* This is machine-dependent.

  * macOS examples often look like: `/dev/cu.*`
  * Linux/Raspberry Pi examples often look like: `/dev/ttyUSB*` or `/dev/ttyACM*`

#### Baudrate

* Communication speed. Choose one from the dropdown (commonly `115200`).

#### Interval

* Timing interval (if required by detector mode). If you do not know you need it, leave it at the default/None.

---

### Animals section

You assign animals to “slots” (Animal 0–3 shown; you can add/remove animals).

For each animal:

#### Name

* Must match an allowed name from:

  * `mxbi/config/options_session.json` → `animal.name`
* For real sessions, ensure the subject IDs used in the bundle are in this list.

#### Level

* Training level (used by task logic).

#### Task

* For this workflow, use:

  * `cross_modal`

---

### Quick presets (recommended)

#### Preset 1 — Mock / dry-run (safe on a laptop)

* XBI: `debug`
* Pump: `mock`
* Detector: `mock`
* Animals: use test animals like `mock_001`, `mock_002` (or your real subject names if you want to test naming)
* Then configure Cross-modal tab and press **Start**
* Run:

  ```bash
  python -m src.mxbi.theater
  ```

#### Preset 2 — Real box run (hardware connected)

* XBI: `mxbi1` … `mxbi9` (the correct rig)
* Pump: `rasberry_pi_gpio`
* Detector: `dorset_lid665v42` (and set correct Port/Baudrate)
* Animals: real subject IDs (must be present in `options_session.json`)
* Cross-modal tab: select the correct bundle folder and settings
* Press **Start**, then run theater as required for that setup

---

## E) What gets saved where (configuration files)

These are the key files you will touch most often:

### `mxbi/config/options_session.json`

* Controls the dropdown option lists (experimenter IDs, XBI IDs, animal names, baudrates).
* If the Launch Panel refuses your bundle due to unknown subjects, add them under:

  * `animal.name`

### `mxbi/config/animal_db.json`

* RFID tag → animal name mapping (only needed for RFID setups).

### `config_session.json` (saved by Launch Panel when you press **Start**)

* The saved state for the **Session** tab.
* Includes experimenter, XBI, reward, pump, detector, animals, etc.

### `config_cross_modal.json` (saved by Launch Panel when you press **Start**)

* The saved state for the **Cross-modal** tab.
* Includes visual/audio/timing settings and WAV policy.

> Practical rule: **Use the Launch Panel UI**, then press **Start**. Do not hand-edit `config_session.json` / `config_cross_modal.json` unless you know exactly what you are doing.

---

## F) After the run: where results are written, and how to copy them to Desktop

After running `python -m src.mxbi.theater`, MXBI writes outputs under the repo’s `data/` directory (typically in a date-stamped subfolder).

### Find the newest output folder

#### macOS

```bash
ls -lt data
```

#### Windows (PowerShell)

```powershell
Get-ChildItem .\data | Sort-Object LastWriteTime -Descending | Select-Object -First 10
```

### Copy the newest run folder to your Desktop

#### macOS (example)

Replace `<run_folder>` with the folder name you saw under `data/`:

```bash
cp -R ./data/<run_folder> ~/Desktop/
```

#### Windows (PowerShell example)

```powershell
Copy-Item -Recurse ".\data\<run_folder>" "$HOME\Desktop\"
```

---

# Optional: Sync data to the DPZ Samba server (Yang’s documentation integrated)

This repository includes a one-way sync tool (wrapper around `rsync`) for synchronizing the local `data/` directory to a remote Samba server.

> This is primarily intended for **Linux/Raspberry Pi** environments (it creates a `systemd` service). If you are on Windows or macOS, do not run the `systemd` setup steps.

## 1) Run Samba setup (Linux/Raspberry Pi)

From the repo root:

1. Go to the sync tool directory:

   ```bash
   cd src/mxbi/tools/sync_data
   ```
2. Run setup:

   ```bash
   python main.py setup
   ```

During setup you will be prompted for:

* Samba address
* Domain
* Username
* Password
* Other connection details

The setup:

* creates a `systemd` service for automatic mounting
* stores credentials encrypted using `systemd-creds`
* mounts the Samba share under:

  * `samba_mount` (inside the sync tool root)

## 2) Trigger a sync

In Python, call:

```python
from mxbi.tools.sync_data.sync_data import sync_data
sync_data()
```

This synchronizes the local **project root `data/` directory** to the Samba server.

---

# Troubleshooting

### “Bundle subjects are not present…”

Meaning: the bundle contains subject IDs that MXBI doesn’t recognize as allowed names.

Fix:

* Add those subject IDs to `mxbi/config/options_session.json` under `animal.name`.

### Bundle loads but errors show up in “Errors”

Meaning: the bundle folder structure or contents are invalid or incomplete.

Fix:

* Use the error text as a checklist (missing folders, missing trials, missing media, mismatched subject folders, etc.)
* Correct the bundle and reload it.

### Audio plays but is too quiet / too loud / distorted

Fix order:

1. Adjust **Master volume**
2. Adjust **Digital volume**
3. Use **Gain** last (high gain can introduce distortion)

### PyAudio install fails

* **Windows:** confirm you installed **Python 3.11** (not 3.12/3.13), then use `pipwin install pyaudio`. ([Stack Overflow][2])
* **macOS:** ensure PortAudio is installed (`brew install portaudio`) then install PyAudio. ([PyPI][1])

---

# Recurring commands (copy/paste)

From the repo root, with `(.venv)` active:

### Open Launch Panel

```bash
python -m src.mxbi.ui.launch_panel
```

### Run mock theater

```bash
python -m src.mxbi.theater
```

### Update/install dependencies (after repo changes)

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

### Deactivate environment

```bash
deactivate
```

[1]: https://pypi.org/project/PyAudio/?utm_source=chatgpt.com "PyAudio"
[2]: https://stackoverflow.com/questions/55936179/trying-to-install-pyaudio-using-pip?utm_source=chatgpt.com "Trying to install pyaudio using pip"
[3]: https://pypi.org/project/pyaudio-wheels/?utm_source=chatgpt.com "pyaudio-wheels"
