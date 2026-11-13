# Hamzzi Capture (Windows)

[한국어](README.md) | **English**

A screen-capture tool for Windows. Korean and English are supported.

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

- After a capture, the main window shows a preview. Press **Edit** to open the editor; **Copy** and **Save** work right from the main window.
- The 5 most recent captures stay as thumbnails below the preview, and you can click one to reopen it. **×** on a thumbnail deletes that one, and **Clear all** deletes them all (after confirmation). They disappear when you quit, and from the 6th capture on the oldest ones are dropped.
- Main-window shortcuts: **Ctrl+C** copy, **Ctrl+S** save, **Ctrl+V** load an image from the clipboard (including a copied image file) as a new capture. They also work with a Korean input mode on.
- **⚙ Settings** in the header: set the save folder and choose whether to copy to the clipboard and/or save a PNG to that folder right after each capture. The Save button's file dialog also starts in that folder.
- Editor: pen / highlighter / line / arrow / rectangle / ellipse / text / mosaic / **crop**. Ctrl+Z undo, Ctrl+C copy, Ctrl+S save. Crop applies as soon as you drag over the area to keep, and Undo reverts it.
- The mosaic uses blocks of at least 12px and varies each block's brightness a little at random, which makes the original text hard to recover. Still, for anything that must stay hidden, such as a password, it is safest to **paint over it completely with a thick pen or leave it out of the capture**.
- Running two copies makes the hotkeys collide, so if one is already running, a second launch only shows a notice and exits.

## Language & font
- If your display language is Korean, the UI is shown in Korean; otherwise it starts in English.
- You can change the language with the Language button in the About window.
- The font is Malgun Gothic.

## Security & privacy
**Data handling**
- No network connection. Captured content never leaves your PC.
- Does not run other programs or touch the registry or startup items.
- Images are saved to the location you choose with "Save" (PNG/JPG). **If auto-save is on**, they are saved to the save folder you set.
- The only file besides images is the settings file (`%APPDATA%\HamzziCapture\settings.json`), which holds the language, save folder, and whether auto copy/save is on.
- Global hotkeys use Windows' hotkey registration and receive only Ctrl+Shift+A/M/F/W. Other keystrokes are not read.

**Things to keep in mind**
- The 5 most recent captures stay in memory until you quit. After capturing a screen with passwords or personal information, press **Clear all** or close the program.
- A copied image stays on the clipboard until you copy something else, and may also remain in Windows clipboard history (Win+V).

**If you downloaded the exe**
- It is not code-signed, so Windows SmartScreen may warn and some antivirus programs may flag it. The safest route is to get the source and build it yourself with `build.bat`.
- If you find a vulnerability or other problem, please open an issue in the GitHub repository.

## Changelog
**v1.3.1**
- Fixed phone photos pasted with Ctrl+V appearing sideways (the photo's rotation info is now applied)
- Fixed transparent areas turning black when copying or saving as JPG (they are now filled with white)
- Internal code cleanup (screens and features unchanged)

**v1.3.0**
- Added **Settings** (⚙ in the header): save folder, auto copy / auto save right after capture
- Added **Crop** to the editor
- Main window now supports Ctrl+C (copy), Ctrl+S (save) and Ctrl+V (load clipboard image)
- Fixed the editor's Ctrl+Z/C/S not working while a Korean input mode was on

**v1.2.1**
- Internal cleanup: the single source file is now split by role (app, editor, region, widgets, drawing, winapi, settings). Screens and features are unchanged.
- Saving the settings file now merges with existing values instead of overwriting them

**v1.2.0**
- Added a **Clear all** button for recent captures (asks for confirmation)
- Stronger mosaic: blocks of at least 12px with random per-block brightness, so the text is harder to guess back
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
