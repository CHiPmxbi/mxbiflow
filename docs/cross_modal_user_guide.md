## Before you start: one-time setup so you can launch the MXBI app

### What you need

* The **mxbi** project folder downloaded on your computer.
* Internet connection (only for installing Python and required packages).
* **Python 3.13** (this project requires Python 3.13 or newer).

---

# A) Open a terminal

## On macOS

1. Open **Finder**
2. Go to **Applications → Utilities**
3. Open **Terminal**

## On Windows

1. Press the **Windows key**
2. Type **Windows Terminal**
3. Open **Windows Terminal**
   (If you don’t have it, open **Command Prompt** instead.)

---

# B) Install Python 3.13 (only if you don’t already have it)

## macOS

1. Go to the official Python website and download **Python 3.13** for macOS.
2. Run the installer package and complete it.

After installing, in Terminal, run:

```bash
python3 --version
```

You should see something like:
`Python 3.13.x`

If `python3` is not found, run:

```bash
python --version
```

## Windows

1. Go to the official Python website and download **Python 3.13** for Windows.
2. Run the installer.
3. **Important:** check the box that says **“Add python.exe to PATH”** during installation.
4. Finish installation.

After installing, in Windows Terminal, run:

```powershell
python --version
```

You should see:
`Python 3.13.x`

---

# C) Go to the mxbi project folder

You need to “navigate” your terminal into the project folder that contains the `config/` and `pyproject.toml`.

## macOS example

If your project is in `Downloads/mxbi`:

```bash
cd ~/Downloads/mxbi
```

## Windows example

If your project is in `Downloads\mxbi`:

```powershell
cd $HOME\Downloads\mxbi
```

### Confirm you are in the right place

Run:

**macOS**

```bash
ls
```

**Windows**

```powershell
dir
```

You should see folders/files including:

* `config`
* `src`
* `pyproject.toml`

If you don’t see those, you’re not in the correct folder yet.

---

# D) Create and activate the Python environment

This keeps the project’s packages isolated.

## macOS

1. Create the environment:

```bash
python3 -m venv .venv
```

2. Activate it:

```bash
source .venv/bin/activate
```

You’ll usually see `(.venv)` appear at the start of your terminal line.

## Windows (PowerShell / Windows Terminal)

1. Create the environment:

```powershell
python -m venv .venv
```

2. Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

If Windows blocks activation with a policy error, open PowerShell as Administrator once and run:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then try activation again.

---

# E) Install the project requirements (one-time, or whenever the project changes)

Make sure you are still in the repo root and your environment is activated (`(.venv)` visible).

1. Upgrade the installer tools:

```bash
python -m pip install --upgrade pip
```

2. Install MXBI and its required packages:

```bash
python -m pip install -e .
```

This reads the project dependencies from `pyproject.toml` automatically.

---

# F) Launch the MXBI apps

From the repo root (same folder as `pyproject.toml`) with the environment activated:

## 1) Open the Launch Panel (session configuration)

```bash
python -m src.mxbi.ui.launch_panel
```

Use this to:

* load a cross-modal bundle directory,
* select subjects,
* set image/audio settings,
* press **Start** to save configuration.

## 2) Run the mock theater (test run of the box software)

```bash
python -m src.mxbi.theater
```

Use this when you want to run the software in a test/mock mode (for development or dry-runs), depending on your system configuration.

---

# Cross-modal Launch Panel — How to create a session

## What you need before you open the Launch Panel

### 1) Have a prepared cross-modal dataset bundle folder

You need a dataset bundle directory that already contains the trials and media. You will select this folder in the Cross-modal tab.

You don’t edit files inside the bundle from the Launch Panel. The bundle is treated as read-only input.

### 2) Make sure all subject names from the bundle are “known” to MXBI

When you load a bundle, MXBI checks whether every subject in that bundle is in the allowed animal name list. If it isn’t, the Launch Panel will show an error and won’t let you start.

**File to edit (if you get that error):**

* `mxbi/config/options_session.json`

**What to change:**

* Add missing subject IDs to:

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

### 3) If you use RFID identity detection: register tags to animal names

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

## Using the Launch Panel

The Launch Panel has two tabs: **Session** and **Cross-modal**. For cross-modal experiments, you mainly use **Cross-modal**, then press **Start**.

### Step 1 — Go to the “Cross-modal” tab

### Step 2 — Select the dataset bundle directory

Under **Dataset bundle**, click **Browse…** and select the dataset bundle folder.

After selection:

* The list of subjects should appear in the **Subjects** box.
* The **Errors** box should be empty.

If you see errors:

* Fix what it says (most commonly: missing subject names in `options_session.json`)
* Then select the bundle again.

### Step 3 — Choose which subjects will run

In **Subjects**, you can select one or more subjects.

By default, all subjects are selected.

Only the selected subjects will be included when you press **Start**.

### Step 4 — Adjust Visual settings

#### Image size

This controls how large the two face images appear on the screen.

* Smaller values → smaller images
* Larger values → larger images

Use this to ensure the faces are clearly visible and not cropped or too small.

### Step 5 — Adjust Audio settings

#### Master volume

Overall output volume level of the system.

Use this as your main “how loud is it in the room” control.

#### Digital volume

A second loudness control that affects the digital output stage.

If audio is too quiet or too loud even after changing Master volume, adjust Digital volume as well. On some hardware this has a strong effect; on others it may be subtle.

#### Gain

Software loudness applied directly to the sound file before playback.

* `1.00` = unchanged
* above `1.00` = louder, but can distort if pushed too high
* below `1.00` = quieter

Use Gain when you need to compensate for stimulus files that were recorded too quietly or too loudly *relative to each other*.

Recommended practice:

* First set Master/Digital to safe, comfortable levels.
* Then use Gain for fine adjustment if the stimuli themselves vary.

### Step 6 — Set WAV sample rate policy

This controls what happens if the audio files in the bundle don’t match the expected audio format.

#### Policy = resample

MXBI will adapt mismatched WAV sample rates automatically so playback works.

Use this when:

* you aren’t 100% sure all audio files were exported with the correct sample rate
* you want the session to run without stopping due to format issues

#### Policy = error

MXBI will refuse to run a trial if an audio file has the wrong sample rate.

Use this when:

* you want strict stimulus QA
* you want to catch and fix bundle preparation issues early

---

## Starting the session

### Step 7 — Press “Start”

When you press **Start**:

1. Your Cross-modal settings are saved.
2. Your session settings are saved.
3. The Launch Panel closes.

From that point on, the session uses:

* the selected bundle directory
* the selected subject list
* the visual/audio settings you chose

---

## Troubleshooting

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