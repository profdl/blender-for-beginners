# blender-for-beginners

Simplified, beginner-friendly Blender workspaces for students, built as the
**Lumber Studio** extension (`lumber_studio/`). Plan: Studio Workspace UX Plan.

## Install for testing
Zip the `lumber_studio` folder and install it from Blender's
Preferences > Get Extensions > Install from Disk, or copy it into
`~/Library/Application Support/Blender/5.2/extensions/user_default/`.

## Headless tests
```
pip install bpy==5.2.1
python3 -I tests/test_phase1.py .
```
