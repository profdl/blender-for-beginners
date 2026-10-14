"""Headless checks for the phase 1 cleanup of Lumber Studio (run with plain python3 + bpy module)."""
import sys, os
repo = sys.argv[1]
sys.path.insert(0, repo)
import bpy
import lumber_studio as ls

ok = True
def check(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok = ok and bool(cond)

ls.register()
check(True, "register() ran")

for idname in ("button", "button_undo"):
    op = getattr(bpy.ops.lumberstudio, idname)
    props = {p.identifier for p in op.get_rna_type().properties}
    check({"kind", "target"} <= props, f"lumberstudio.{idname} has kind/target")
check('UNDO' in ls.LUMBERSTUDIO_OT_button_undo.bl_options, "undo wrapper records undo")
check('UNDO' not in ls.LUMBERSTUDIO_OT_button.bl_options, "tool wrapper adds no undo step")

class P: pass
p = P(); p.target = "builtin.select_box"
check(ls.LUMBERSTUDIO_OT_button.description(None, p) == "Select  (V)", "tooltip 'Select  (V)'")
p.target = "lumberstudio.add_image"
check(ls.LUMBERSTUDIO_OT_button.description(None, p) == "Image", "tooltip without key")

# every general/edit toolbar target has a hint
for prof in ("general", "edit_mesh", "edit_curve", "lumber"):
    for item in ls.PROFILES[prof]["items"]:
        if item:
            check(item[1] in ls.BUTTON_HINTS, f"{prof}: hint for {item[1]}")
check(not any(i and i[1] == "builtin.annotate" for i in ls.PROFILES["general"]["items"]), "annotate removed")
check("C" not in ls.SHORTCUTS, "C key removed")
check(ls._op_exists("view3d.view_selected") and not ls._op_exists("lumber.nope"), "_op_exists works")

# load the shipped workspaces from the template
with bpy.data.libraries.load(ls.TEMPLATE) as (src, dst):
    dst.workspaces = [n for n in src.workspaces]
names = [w.name for w in bpy.data.workspaces]
print("workspaces now:", names)
studio = bpy.data.workspaces.get("Studio")
check(studio is not None and studio.get("studio_profile") == "general", "Studio has profile general")
check(ls.STUDIO_WORKSPACES == ("Lumber", "Studio"), "studioEdit is no longer added to files")
check(not hasattr(ls, "_retire_legacy_workspaces"), "no scripted workspace deletion (it crashes Blender)")

ls._apply_owner_filter()
check(studio.use_filter_by_owner, "Studio add-on filter on")
check("lumber_studio" in {o.name for o in studio.owner_ids}, "Lumber Studio allowed in Studio")
lumber = bpy.data.workspaces.get("Lumber")
check(lumber is not None and lumber.use_filter_by_owner, "Lumber keeps its shipped filter")

ls._enable_orbit_ball()
for scr in studio.screens:
    for a in scr.areas:
        if a.type == 'VIEW_3D':
            sp = a.spaces.active
            check(not sp.show_region_ui and not sp.show_region_tool_header, "Studio sidebar + tool header hidden")

ls.unregister()
check(not studio.use_filter_by_owner, "unregister clears the filter")
check(True, "unregister() ran")
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
