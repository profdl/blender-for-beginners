# blender-for-beginners

Simplified, beginner-friendly Blender for students designing 3D prints.

- `app_template/studio/` — the **Studio** application template: its own theme,
  add-ons, startup file and settings, separate from your normal Blender.
- `lumber_studio/` — the **Lumber Studio** extension: Studio's toolbar, panels,
  keys and print tools.

## Switching between Studio and normal Blender

| To | Do |
| --- | --- |
| Go into Studio | File › New › **Studio** (or pick Studio on the splash screen) |
| Go back to normal Blender | Studio's ☰ menu › **Exit to Full Blender**, or File › New › **General** |

Switching starts a new file, so save first. Studio keeps its theme, add-ons and
keymaps in its own preferences file; normal Blender keeps yours. Studio's
interface scale (1.25) and hidden zoom/pan buttons are set on entry and your own
values are put back when you leave (change them in `app_template/studio/__init__.py`).

To open Blender straight into Studio (for a lab machine or a dock shortcut):

```
/Applications/Blender.app/Contents/MacOS/Blender --app-template studio
```

## Install

1. Build the install files: `python3 tools/package.py` (writes `dist/`).
2. In Blender, Preferences › Get Extensions › ⌄ › **Install from Disk…** and pick
   `dist/lumber_studio-<version>.zip`. Leave it turned off in normal Blender;
   Studio turns it on for itself.
3. Blender menu (the Blender logo, top left) › **Install Application Template…** and pick
   `dist/studio_app_template.zip`.
4. File › New › Studio.

## Rebuilding the template files

`startup.blend` and `userpref.blend` are generated. After changing the theme
(`app_template/studio_theme.xml`) or the starting file, run:

```
pip install bpy==5.2.1
python3 -I tools/build_app_template.py .
```

## Tests

```
python3 -I tests/test_phase1.py .
python3 -I tests/test_app_template.py .
```

`test_app_template.py` installs the template and extension into throwaway
folders and switches General → Studio → General, checking that theme, add-ons,
interface scale, navigation buttons and units all go back.
