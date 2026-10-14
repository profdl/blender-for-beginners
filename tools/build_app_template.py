"""Build the Studio application template's startup.blend and userpref.blend.

Run from the repo root with Blender's Python module (pip install bpy==5.2.1):

    python3 -I tools/build_app_template.py .

or with Blender itself:

    blender --background --factory-startup --python tools/build_app_template.py -- .

Writes:
    app_template/studio/userpref.blend   Studio's own preferences: theme (app_template/studio_theme.xml)
    app_template/studio/startup.blend    Studio's starting file: Studio + Lumber tabs, millimetres, 20 mm cube
"""

import os
import sys
import tempfile

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
REPO = os.path.abspath(args[0] if args else ".")
TEMPLATE_DIR = os.path.join(REPO, "app_template", "studio")
THEME_XML = os.path.join(REPO, "app_template", "studio_theme.xml")

# Keep the build away from anyone's real Blender configuration.
_config = tempfile.mkdtemp(prefix="studio_build_config_")
os.environ["BLENDER_USER_CONFIG"] = _config

import bpy  # noqa: E402  (after the environment is set)

sys.path.insert(0, REPO)
import lumber_studio as ls  # noqa: E402


def build_userpref():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import _rna_xml
    from bl_ui.space_userpref import USERPREF_MT_interface_theme_presets as presets
    _rna_xml.xml_file_run(bpy.context, THEME_XML, presets.preset_xml_map)
    prefs = bpy.context.preferences
    prefs.themes[0].filepath = ""
    # The extensions themselves are turned on by the template's __init__.py,
    # which finds them wherever they are installed.
    bpy.ops.wm.save_userpref()
    src = os.path.join(_config, "userpref.blend")
    dst = os.path.join(TEMPLATE_DIR, "userpref.blend")
    with open(src, "rb") as f, open(dst, "wb") as g:
        g.write(f.read())
    print("wrote", dst)


def build_startup():
    import mathutils
    bpy.ops.wm.read_factory_settings(use_empty=False)
    ls.register()
    try:
        with bpy.data.libraries.load(ls.TEMPLATE) as (src, dst):
            dst.workspaces = [n for n in ls.STUDIO_WORKSPACES if n in src.workspaces]
        studio = bpy.data.workspaces["Studio"]
        # Set up the studio views while they're off-screen (toggling regions on the
        # visible screen isn't safe without a real window).
        ls._enable_orbit_ball()
        win = bpy.context.window_manager.windows[0]
        win.workspace = studio
        # Blender's own tabs stay in the file (removing workspaces from a script
        # isn't safe), but Studio's menu only lists Studio and Lumber.

        scene = bpy.context.scene
        us = scene.unit_settings
        us.system, us.scale_length, us.length_unit = 'METRIC', 0.001, 'MILLIMETERS'
        # Layers start with just the cube: light and camera belong to a later Present workspace
        for name in ("Light", "Camera"):
            ob = bpy.data.objects.get(name)
            if ob is not None:
                bpy.data.objects.remove(ob)
        cube = bpy.data.objects.get("Cube")
        if cube is not None:
            s = ls._mm(scene, scene.lumberstudio_new_size)
            cube.data.transform(mathutils.Matrix.Scale(s / 2.0, 4))   # factory cube is 2 units wide
            cube.location = (0.0, 0.0, s / 2)
            if not cube.data.materials:
                cube.data.materials.append(ls._default_material())
        ls._apply_owner_filter()
        ls._frame_plate(scene)
        dst = os.path.join(TEMPLATE_DIR, "startup.blend")
        # No thumbnail: drawing one needs a screen, which a background build doesn't have
        bpy.context.preferences.filepaths.file_preview_type = 'NONE'
        bpy.ops.wm.save_as_mainfile(filepath=dst, compress=True, copy=True)
        print("wrote", dst)
    finally:
        ls.unregister()


if __name__ == "__main__":
    # Each step in its own Blender session: reloading factory settings twice in
    # one Python-module session is not reliable.
    step = os.environ.get("STUDIO_BUILD_STEP")
    if step == "userpref":
        build_userpref()
    elif step == "startup":
        build_startup()
    elif bpy.app.background and "--" in sys.argv:
        build_userpref()            # running inside a Blender binary: one session is fine
        build_startup()
    else:
        import subprocess
        for s in ("userpref", "startup"):
            env = dict(os.environ, STUDIO_BUILD_STEP=s)
            subprocess.run([sys.executable, "-I", os.path.abspath(__file__), REPO], env=env, check=True)
