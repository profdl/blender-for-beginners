"""Switch between stock Blender (General) and the Studio app template and check nothing leaks.

Runs Blender's Python module against throwaway config, scripts and extension
folders with the template and extension "installed" there:

    pip install bpy==5.2.1
    python3 -I tests/test_app_template.py .
"""
import os
import shutil
import sys
import tempfile

REPO = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
root = tempfile.mkdtemp(prefix="studio_test_")
for k, sub in (("BLENDER_USER_CONFIG", "config"), ("BLENDER_USER_SCRIPTS", "scripts"),
               ("BLENDER_USER_EXTENSIONS", "extensions")):
    os.environ[k] = os.path.join(root, sub)
tmpl_dst = os.path.join(root, "scripts", "startup", "bl_app_templates_user", "studio")
shutil.copytree(os.path.join(REPO, "app_template", "studio"), tmpl_dst,
                ignore=shutil.ignore_patterns("__pycache__"))
ext_dst = os.path.join(root, "extensions", "user_default", "lumber_studio")
shutil.copytree(os.path.join(REPO, "lumber_studio"), ext_dst, ignore=shutil.ignore_patterns("__pycache__"))

import bpy  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok = ok and bool(cond)


def state():
    P = bpy.context.preferences
    wm = bpy.context.window_manager
    return {
        "template": P.app_template,
        "active": tuple(round(c, 3) for c in P.themes[0].view_3d.object_active),
        "lumber": any(a.module.endswith("lumber_studio") for a in P.addons),
        "ui_scale": P.view.ui_scale,
        "nav": P.view.show_navigate_ui,
        "workspace": wm.windows[0].workspace.name if wm.windows else None,
        "mm": bpy.context.scene.unit_settings.length_unit,
    }


ORANGE = (1.0, 0.627, 0.157)            # Blender Dark's active object
BLUE = (0.051, 0.6, 1.0)                # Studio's #0D99FF

bpy.ops.wm.read_factory_settings(use_empty=False)
P = bpy.context.preferences
P.view.ui_scale = 1.0
P.view.show_navigate_ui = True
check(bpy.utils.app_template_paths() and any(
    "studio" in os.listdir(p) for p in bpy.utils.app_template_paths()), "template is discoverable")
s = state()
print("General:", s)
check(s["template"] == "" and s["active"] == ORANGE and not s["lumber"], "starts as stock Blender")

bpy.ops.wm.read_homefile(app_template="studio")
s = state()
print("Studio: ", s)
check(s["template"] == "studio", "File > New > Studio switches template")
check(s["active"] == BLUE, "Studio theme loaded")
check(s["lumber"], "Lumber Studio turned on in Studio")
check(s["ui_scale"] == 1.25 and s["nav"] is False, "Studio scale 1.25, nav buttons hidden")
# Opening on the Studio tab happens from a timer once Blender's window is up.
# Background Blender can't switch tabs at all, so this one is checked in the app.
print("SKIP new Studio file opens on the Studio tab (needs a real window)")
check(s["mm"] == 'MILLIMETERS', "new Studio file is in millimetres")
studio_ws = bpy.data.workspaces.get("Studio")
check(studio_ws is not None and studio_ws.use_filter_by_owner, "add-on filter on in Studio")
check("studioEdit" not in bpy.data.workspaces, "no studioEdit tab")

bpy.ops.wm.read_homefile(app_template="")
s = state()
print("General:", s)
check(s["template"] == "", "File > New > General switches back")
check(s["active"] == ORANGE, "stock theme back")
check(not s["lumber"], "Lumber Studio off again")
check(s["ui_scale"] == 1.0 and s["nav"] is True, "your scale and nav buttons restored")
check(s["mm"] != 'MILLIMETERS', "stock new file is not in millimetres")

print("ALL PASS" if ok else "SOME FAILED")
shutil.rmtree(root, ignore_errors=True)
sys.exit(0 if ok else 1)
