# USB deployment

Build the portable release from a Windows development machine with Python and PyInstaller installed:

```bat
scripts\build_portable.bat
```

Copy the resulting `dist\AI_System_Diagnostic` folder intact to a USB drive. The recommended layout is `USB:\AI_System_Diagnostic\AI_System_Diagnostic.exe` alongside `data`, `logs`, `reports`, `config`, and `knowledge`. NTFS is preferred when permitted; exFAT is widely compatible. The application creates its SQLite database, portable settings file, logs, and reports beside the executable on first run.

Run `AI_System_Diagnostic.exe` directly. Standard mode supports read-only diagnostics where Windows permits them. Use **Restart as Administrator** only when a selected approved repair explains that elevation is required; elevation is never automatic. Internet access is optional and offline mode remains available.

Collect output from the `reports` folder. Close the app and wait for writes to finish before using Windows **Safely Remove Hardware**. Enterprise policy, antivirus, SmartScreen, UAC, controlled-folder access, read-only media, and USB-execution restrictions can prevent or limit operation. The app shows a clear startup error if its portable folders are not writable.
