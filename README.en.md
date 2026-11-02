# Hamzzi Capture (Windows)

[한국어](README.md) | **English**

A simple screen-capture tool for Windows. The UI is available in Korean and English: it follows your Windows display language on first launch, and you can switch anytime from the ⓘ (About) window (your choice is remembered).

<img width="802" height="510" alt="Hamzzicapture02_ENG" src="https://github.com/user-attachments/assets/046e98d5-e210-4a14-87b1-dc2ea859939e" />


## Run
1. Install Python 3.9+ (python.org, check "Add to PATH")
2. `pip install -r requirements.txt`
3. `python app.py`

## Build an exe
Double-click `build.bat` → `dist\HamzziCapture.exe` (with the hamster icon).

## Usage
| Feature | Hotkey |
|---|---|
| Region capture (one overlay per monitor, drag within a monitor) | Ctrl+Shift+A |
| Current monitor (where the mouse is) | Ctrl+Shift+M |
| All monitors as one image | Ctrl+Shift+F |
| Active window | Ctrl+Shift+W |

After a capture, the main window shows only a preview. Press **Edit** to open the editor; you can also Copy / Save straight from the main window. While a Hamzzi Capture window is active, Ctrl+Shift+W captures the app itself.

The 5 most recent captures are kept as thumbnails below the preview. Click one to reopen it, click × to delete it, or use **Clear all** (with confirmation) to delete them all. They live in memory only and disappear when you quit.

Editor: pen / highlighter / line / arrow / rectangle / ellipse / text / mosaic, Ctrl+Z undo, Ctrl+C copy, Ctrl+S save.

The mosaic uses blocks of at least 12px and randomly shifts each block's brightness, making it hard to recover text by rendering candidate strings in a known font and comparing. For information that must stay hidden (passwords, etc.), painting over it completely with a thick pen or leaving it out of the capture is still the safest option.

Running the program twice would clash on hotkeys, so a second launch shows a notice and exits.

## Language & font
- On first launch the UI is Korean if your Windows display language is Korean, otherwise English.
- Use the **Language** buttons (한국어 | English) in the ⓘ About window to switch at any time; the change applies immediately. Your choice is saved to `%APPDATA%\HamzziCapture\settings.json` and kept on the next launch. Delete that file to go back to auto-detection.
- Both languages use the same Windows default font, **Malgun Gothic**, so the text looks consistent even when Korean and English are mixed. No extra fonts need to be installed.

## Security & privacy
- No network access at all. Captured content never leaves your PC.
- Does not launch other programs or touch the registry / startup items.
- Captures are saved only where you choose via "Save" (PNG/JPG). The only other file written is the settings file (`%APPDATA%\HamzziCapture\settings.json`, holding just the language) when you change the language.
- Global hotkeys use Windows hotkey registration and react only to Ctrl+Shift+A/M/F/W; keystrokes are not logged.
- Recent captures stay in memory until you quit. After capturing sensitive screens, press **Clear all** or close the app.
- Copied images stay on the clipboard (and possibly in Windows clipboard history, Win+V).
- An unsigned exe may trigger SmartScreen warnings or antivirus false positives. Building from source with `build.bat` is the safest route.
- Found an issue? Please open a GitHub Issue.

## Changelog
**v1.2.0**
- Added a **Clear all** button for recent captures (asks for confirmation)
- Stronger mosaic: blocks of at least 12px with random per-block brightness, so text is hard to recover by guessing
- The selected language is remembered across launches

**v1.1.0**
- Added Korean / English UI switching (auto-detects the Windows display language; change it in the ⓘ About window)
- Unified the font to Malgun Gothic for both languages
- Replaced the hamster images with the new camera-holding Hamzzi (app icon, favicon, About window image)
- Added the English README

**v1.0.1**
- Added an × delete button to recent-capture thumbnails

## Credits
- Made by: Studying Hamzzi
- Made with Claude (Anthropic). The hamster images are AI-generated.

## License
Source code is released under the [MIT License](LICENSE).
