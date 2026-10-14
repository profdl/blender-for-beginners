"""Studio's starting scene, the sun controls and the Preview floor.

    python3 -I tests/test_preview_sun.py .
"""
import math
import os
import sys

REPO = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
sys.path.insert(0, REPO)
import bpy  # noqa: E402
import lumber_studio as ls  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok = ok and bool(cond)


bpy.ops.wm.open_mainfile(filepath=os.path.join(REPO, "app_template", "studio", "startup.blend"))
ls.register()
scene = bpy.context.scene
cube = bpy.data.objects["Cube"]
sun = bpy.data.objects["Preview Sun"]
floor = bpy.data.objects["Preview Floor"]

# Starting scene
check([round(d) for d in cube.dimensions] == [100, 100, 100], "cube is 100 mm")
check(cube.modifiers.get(ls.CORNERS_MOD) is not None, "cube has rounded corners")
check(abs(floor.location.z) < 1e-4, "floor sits right under the cube")
check(ls._is_preview_sun(sun) and not sun.hide_select, "sun is clickable in Layers")

# Sun controls
diff = bpy.data.materials["Preview Floor"].node_tree.nodes["Stage Diffuse"].inputs["Color"]
before = diff.default_value[0]
scene.lumberstudio_sun_height = math.radians(20)
check(abs(math.degrees(sun.rotation_euler.x) - 70) < 1e-3, "Height 20° tilts the sun 70° from overhead")
check(diff.default_value[0] > before, "floor re-matches the backdrop when the sun drops")
scene.lumberstudio_sun_direction = math.radians(200)
check(abs(math.degrees(sun.rotation_euler.z) - 200) < 1e-3, "Direction turns the sun")
scene.lumberstudio_sun_brightness = 4.0
check(sun.data.energy == 4.0, "Brightness sets sun strength")
scene.lumberstudio_sun_color = (1.0, 0.9, 0.8)
check(abs(sun.data.color[2] - 0.8) < 1e-6, "Color sets sun colour")
ls._preview_rig(scene)
check(sun.data.energy == 4.0 and abs(math.degrees(sun.rotation_euler.x) - 70) < 1e-3,
      "turning Preview on again keeps the student's sun")

# Floor follows the lowest object while previewing
cube.location.z += 30
bpy.context.view_layer.update()
ls._on_depsgraph_update(scene, bpy.context.evaluated_depsgraph_get())   # what Blender calls after an edit
check(abs(floor.location.z - 30) < 1e-3, "floor follows the cube up")

ls.unregister()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
