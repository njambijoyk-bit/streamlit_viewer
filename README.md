# TISL Backup Viewer

A small desktop app for reading the TISL platform's encrypted backup files
(`.wnkjba`). Open a backup, enter its passphrase, browse the data table by
table, and export anything to CSV.

Everything happens **locally on your machine**. The app never uploads a file
anywhere and never writes to a database — it only *reads* the backup.

---

## What it does

- Opens a `.wnkjba` backup produced by the TISL platform.
- Decrypts it with the **backup passphrase** (the one set on the server when
  the backup was made). A wrong passphrase fails cleanly — the file stays
  unreadable.
- Shows the backup's business name, when it was made, and which modules and
  tables it contains.
- Lets you browse each table, filter rows, and download any table (or the whole
  backup) as CSV.

## Requirements

- **Python 3.9 or newer** installed on the machine.
  - Windows: install from <https://www.python.org/downloads/> and tick
    *"Add Python to PATH"*.

Everything else installs itself on first run.

## Running it

### Windows
Double-click **`run.bat`**. The first run sets things up (a minute or two),
then the viewer opens in your web browser. Every run after that is instant.

### macOS / Linux
```bash
./run.sh
```
(the first run sets things up, then opens the viewer in your browser.)

### Manual / advanced
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at <http://localhost:8501>. To stop it, close the browser tab and
press `Ctrl+C` in the terminal window.

## How to use

1. Start the app (above).
2. Click **Choose a backup file** and pick your `.wnkjba` file.
3. Enter the **backup passphrase** and click **Open backup**.
4. Use the sidebar to pick a module and a table. Filter or download as needed.

## About the file format

A `.wnkjba` file is an authenticated encrypted container:

- 8-byte magic `WNKJBAK1`, then a small JSON header (encryption parameters).
- The payload is a ZIP of `manifest.json` + `data/<module>/<table>.jsonl`,
  encrypted with **XChaCha20-Poly1305** (libsodium secretstream).
- The key is derived from your passphrase with **Argon2id**. The passphrase is
  never stored in the file, so the only way to open it is to know it.

## Security notes

- Keep the passphrase safe — if it's lost, the backup cannot be recovered.
- CSV exports are **plain text**. Delete them when you're done, or keep them
  somewhere safe.
- This viewer is read-only. To restore a backup into a live site, use the
  platform's own restore screen (super-admin only).
