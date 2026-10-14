"""Build the Studio application template's startup.blend and userpref.blend.

Run from the repo root with Blender's Python module (pip install bpy==5.2.1):

    python3 -I tools/build_app_template.py .

or with Blender itself:

    blender --background --factory-startup --python tools/build_app_template.py -- .

Writes:
    app_template/studio/userpref.blend   Studio's own preferences: theme (app_template/studio_theme.xml)
    app_template/studio/startup.blend    Studio's starting file: Studio + Lumber tabs, millimetres,
                                         a rounded 100 mm cube in Preview on a white stage
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

# Must match STUDIO_EXTENSIONS + CARRY_OVER_EXTENSIONS in app_template/studio/__init__.py
STUDIO_TEMPLATE_EXTENSIONS = ("lumber_studio", "lumber_supports", "mcp")

# The starting scene, taken from the look approved in Studio (all lengths in mm).
START = {
    "cube_size": 100.0,
    "corner_radius": 0.5,
    "corner_smoothness": 8,
    "cube_color": (0.8, 0.1355, 0.592, 1.0),          # pink
    "cube_roughness": 0.5,
    "stage_color": (0.9755, 0.9755, 1.0),             # near-white backdrop
    # The Studio view: close in, turned so the cube's shadow falls toward the viewer
    "view_location": (-5.717, 3.737, 47.564),
    "view_rotation": (0.76881, 0.47429, -0.22521, -0.36506),   # quaternion w, x, y, z
    "view_distance": 270.5,
}


def build_userpref():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import _rna_xml
    from bl_ui.space_userpref import USERPREF_MT_interface_theme_presets as presets
    _rna_xml.xml_file_run(bpy.context, THEME_XML, presets.preset_xml_map)
    prefs = bpy.context.preferences
    prefs.themes[0].filepath = ""
    # List Studio's extensions (and the Blender connection) as enabled. Every time a
    # Studio file opens, Blender reloads these preferences and turns off anything
    # not listed, which would cut the connection and switch Studio's tools off.
    # Listed extensions that aren't installed are simply skipped.
    have = {a.module for a in prefs.addons}
    for short in STUDIO_TEMPLATE_EXTENSIONS:
        name = "bl_ext.user_default." + short
        if name not in have:
            prefs.addons.new().module = name
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
        cube = bpy.data.objects["Cube"]
        s = ls._mm(scene, START["cube_size"])
        cube.data.transform(mathutils.Matrix.Scale(s / 2.0, 4))   # factory cube is 2 units wide
        cube.location = (0.0, 0.0, s / 2)
        corners = cube.modifiers.new(ls.CORNERS_MOD, 'BEVEL')
        corners.width = ls._mm(scene, START["corner_radius"])
        corners.segments = START["corner_smoothness"]
        corners.limit_method = 'ANGLE'
        mat = bpy.data.materials.new("Cube")
        if hasattr(mat, "use_nodes") and not mat.use_nodes:
            mat.use_nodes = True
        bsdf = ls._principled(mat)
        bsdf.inputs["Base Color"].default_value = START["cube_color"]
        bsdf.inputs["Roughness"].default_value = START["cube_roughness"]
        cube.data.materials.clear()
        cube.data.materials.append(mat)
        for ob in scene.objects:
            ob.select_set(ob == cube)
        bpy.context.view_layer.objects.active = cube

        ls._apply_owner_filter()
        ls._frame_plate(scene)            # every studio view on the plate (the Lumber tab keeps this)

        bpy.context.view_layer.update()   # so the floor fits the cube's new size, not the old one
        # Studio opens in Preview: lit by the sun on a stage that fades into the backdrop
        scene.lumberstudio_stage_color = START["stage_color"]
        scene["lumberstudio_preview_floor"] = 1          # set without running the update (no window here)
        space = next(a.spaces.active for scr in studio.screens for a in scr.areas if a.type == 'VIEW_3D')
        ls._apply_preview(space, True, True)
        r3 = space.region_3d
        r3.view_location = START["view_location"]
        r3.view_rotation = START["view_rotation"]
        r3.view_distance = START["view_distance"]
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
