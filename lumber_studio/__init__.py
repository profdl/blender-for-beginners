"""Lumber Studio: Spline-style minimal UI for chosen Blender workspaces.

A workspace opts in with the custom property ``studio_profile``:
  * "lumber"  - the Lumber build workspace (Lumber tools, left toolbar)
  * "general" - a general Spline-like workspace (Spline's tool set, right toolbar)
Workspaces named "Lumber" get the "lumber" profile automatically.
Other workspaces are untouched, and disabling the extension restores
Blender's stock UI.

Pieces:
  * Floating pill toolbar in the viewport
  * Top bar reduced to a single hamburger menu and the file name
  * Sidebar limited to Item + add-on tabs (Tool/View/Animation hidden)
  * Shift+Right-click no longer moves the (hidden) 3D cursor
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from math import cos, sin, pi
import math
import mathutils

HIDDEN_SIDEBAR_TABS = {"Tool", "View", "Animation"}


def studio_profile(context):
    ws = getattr(context, "workspace", None)
    if ws is None:
        win = getattr(context, "window", None)
        ws = win.workspace if win else None
    if not ws:
        return None
    prof = ws.get("studio_profile")
    if prof in ("general", "edit"):
        mode = getattr(context, "mode", "OBJECT")
        if mode == 'EDIT_MESH':
            return "edit_mesh"
        if mode == 'EDIT_CURVE':
            return "edit_curve"
        return "edit_mesh" if prof == "edit" else "general"
    if prof in PROFILES:
        return prof
    if ws.name == "Lumber" or ws.get("lumber_studio"):
        return "lumber"
    return None


def is_studio(context):
    return studio_profile(context) is not None


GENERAL_FAMILY = {"general", "edit_mesh", "edit_curve"}


def is_general(context):
    """Studio or studioEdit, in any mode."""
    return studio_profile(context) in GENERAL_FAMILY


def is_editing(context):
    return studio_profile(context) in {"edit_mesh", "edit_curve"}


STUDIO_APP_TEMPLATE = "studio"


def in_studio_app():
    """True when Blender is running the Studio application template (File > New > Studio)."""
    return getattr(bpy.context.preferences, "app_template", "") == STUDIO_APP_TEMPLATE


def lumber_available():
    return hasattr(bpy.types, "LUMBER_OT_add_board") or "lumber.add_board" in dir(bpy.ops.lumber)


# ---------------------------------------------------------------------------
# Floating toolbar
# ---------------------------------------------------------------------------

# Each item: (kind, target, icon, extra). kind "tool" switches the active tool
# (extra = tool ids that count as "this button is active"), "op" runs an
# operator, "menu" opens a menu; None inserts a divider.
PROFILES = {
    "lumber": {
        "anchor": "left-center",
        "items": [
            ("tool", "builtin.select_box", "RESTRICT_SELECT_OFF", ()),
            ("tool", "builtin.move", "EMPTY_ARROWS", ()),
            ("tool", "builtin.rotate", "FILE_REFRESH", ()),
            ("tool", "builtin.scale", "FULLSCREEN_ENTER", ()),
            None,
            ("op", "lumber.add_board", "MESH_CUBE", ()),
            ("op", "lumber.add_supports", "MOD_LATTICE", ()),
            ("op", "lumber.fit_to_plate", "PIVOT_BOUNDBOX", ()),
            None,
            ("op", "lumber.export", "EXPORT", ()),
        ],
    },
    # Mirrors Spline's default toolbar: select, frame, 2D shapes, 3D objects,
    # text, pen, image | play. (Annotate/comments are out of scope for prints.)
    "general": {
        "anchor": "left-top",
        "items": [
            ("tool", "builtin.select_box", "RESTRICT_SELECT_OFF",
             ("builtin.select", "builtin.select_box", "builtin.select_circle", "builtin.select_lasso")),
            ("op", "view3d.view_selected", "ZOOM_SELECTED", ()),
            ("panel", "LUMBERSTUDIO_PT_add_shape", "MESH_PLANE", ()),
            ("panel", "LUMBERSTUDIO_PT_add_object", "MESH_CUBE", ()),
            ("add", "TEXT", "FONT_DATA", ()),
            ("op", "lumberstudio.pen", "CURVE_BEZCURVE", ("builtin.draw",)),
            ("op", "lumberstudio.add_image", "IMAGE_DATA", ()),
            None,
            ("op", "lumberstudio.preview_toggle", "PLAY", ()),
        ],
    },
    # Editing inside Studio: same pill, edit tools. kind "selmode" toggles vertex/edge/face.
    "edit_mesh": {
        "anchor": "left-top",
        "items": [
            ("tool", "builtin.select_box", "RESTRICT_SELECT_OFF",
             ("builtin.select", "builtin.select_box", "builtin.select_circle", "builtin.select_lasso")),
            ("selmode", "VERT", "VERTEXSEL", ()),
            ("selmode", "EDGE", "EDGESEL", ()),
            ("selmode", "FACE", "FACESEL", ()),
            None,
            ("tool", "builtin.move", "EMPTY_ARROWS", ()),
            ("tool", "builtin.rotate", "FILE_REFRESH", ()),
            ("tool", "builtin.scale", "FULLSCREEN_ENTER", ()),
            None,
            ("tool", "builtin.extrude_region", "MOD_SOLIDIFY",
             ("builtin.extrude_region", "builtin.extrude_manifold", "builtin.extrude_along_normals",
              "builtin.extrude_individual", "builtin.extrude_to_cursor")),
            ("tool", "builtin.inset_faces", "PIVOT_INDIVIDUAL", ()),
            ("tool", "builtin.bevel", "MOD_BEVEL", ()),
            ("tool", "builtin.loop_cut", "SNAP_EDGE", ("builtin.loop_cut", "builtin.offset_edge_loop_cut")),
            None,
            ("op", "lumberstudio.edit_done", "CHECKMARK", ()),
        ],
    },
    "edit_curve": {
        "anchor": "left-top",
        "items": [
            ("tool", "builtin.select_box", "RESTRICT_SELECT_OFF",
             ("builtin.select", "builtin.select_box", "builtin.select_circle", "builtin.select_lasso")),
            None,
            ("tool", "builtin.move", "EMPTY_ARROWS", ()),
            ("tool", "builtin.rotate", "FILE_REFRESH", ()),
            ("tool", "builtin.scale", "FULLSCREEN_ENTER", ()),
            None,
            ("tool", "builtin.pen", "CURVE_BEZCURVE", ()),
            ("tool", "builtin.draw", "GREASEPENCIL", ()),
            ("tool", "builtin.extrude", "MOD_SOLIDIFY", ("builtin.extrude", "builtin.extrude_cursor")),
            None,
            ("op", "lumberstudio.edit_done", "CHECKMARK", ()),
        ],
    },
}
SELMODE_INDEX = {"VERT": 0, "EDGE": 1, "FACE": 2}

# Tooltip for each toolbar button: (name, key), shown as "Name  Key" like Figma.
# Keys are the ones that work today; update this table when the keymap changes.
BUTTON_HINTS = {
    "builtin.select_box": ("Select", "V"),
    "builtin.move": ("Move", "G"),
    "builtin.rotate": ("Rotate", "R"),
    "builtin.scale": ("Scale", "S"),
    "builtin.extrude_region": ("Extrude", "E"),
    "builtin.inset_faces": ("Inset", "I"),
    "builtin.bevel": ("Bevel", "Ctrl+B"),
    "builtin.loop_cut": ("Loop Cut", "Ctrl+R"),
    "builtin.pen": ("Pen", ""),
    "builtin.draw": ("Draw", ""),
    "builtin.extrude": ("Extrude", "E"),
    "VERT": ("Points", "1"),
    "EDGE": ("Edges", "2"),
    "FACE": ("Faces", "3"),
    "view3d.view_selected": ("Frame Selection", "Numpad ."),
    "LUMBERSTUDIO_PT_add_shape": ("Shapes", "R rectangle · O ellipse"),
    "LUMBERSTUDIO_PT_add_object": ("3D Objects", ""),
    "TEXT": ("Text", "T"),
    "lumberstudio.pen": ("Pen", "P"),
    "lumberstudio.add_image": ("Image", ""),
    "lumberstudio.preview_toggle": ("Preview", ""),
    "lumberstudio.edit_done": ("Done Editing", "Esc"),
    "lumber.add_board": ("Add 2x4", ""),
    "lumber.add_supports": ("Add Supports", ""),
    "lumber.fit_to_plate": ("Fit to Plate", ""),
    "lumber.export": ("Export Print", ""),
}


def _button_tooltip(target):
    name, key = BUTTON_HINTS.get(target, ("", ""))
    if not name:
        return ""
    return f"{name}  ({key})" if key else name


def _op_exists(path):
    mod, _, name = path.partition(".")
    try:
        getattr(getattr(bpy.ops, mod), name).get_rna_type()
        return True
    except Exception:
        return False


class LUMBERSTUDIO_OT_button(bpy.types.Operator):
    """A toolbar button. It exists so each button can show its own name and key"""
    bl_idname = "lumberstudio.button"
    bl_label = "Studio Button"
    bl_options = {'INTERNAL'}

    kind: bpy.props.StringProperty(options={'SKIP_SAVE'})
    target: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return _button_tooltip(props.target) or props.target

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        kind, target = self.kind, self.target
        try:
            if kind == "tool":
                bpy.ops.wm.tool_set_by_id(name=target)
            elif kind == "menu":
                bpy.ops.wm.call_menu(name=target)
            elif kind == "panel":
                bpy.ops.wm.call_panel(name=target, keep_open=False)
            elif kind == "add":
                bpy.ops.lumberstudio.add(kind=target)
            elif kind == "selmode":
                bpy.ops.mesh.select_mode(type=target, use_extend=False, use_expand=False)
            else:
                mod, _, name = target.partition(".")
                op = getattr(getattr(bpy.ops, mod), name)
                if not op.poll():
                    return {'CANCELLED'}
                op('INVOKE_DEFAULT')
        except Exception as e:
            self.report({'WARNING'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


class LUMBERSTUDIO_OT_button_undo(LUMBERSTUDIO_OT_button):
    """A toolbar button that changes the scene, so it records one undo step"""
    bl_idname = "lumberstudio.button_undo"
    bl_label = "Studio Button"
    bl_options = {'INTERNAL', 'UNDO'}

    # Declared again: Blender reads properties from each class's own annotations.
    kind: bpy.props.StringProperty(options={'SKIP_SAVE'})
    target: bpy.props.StringProperty(options={'SKIP_SAVE'})


# Buttons that only switch the active tool or open a palette leave no undo step.
_NO_UNDO_KINDS = {"tool", "menu", "panel"}

PILL = (0.165, 0.165, 0.165, 0.97)
ACTIVE = (0.33, 0.33, 0.33)
IDLE = PILL[:3]
HOVER = (0.27, 0.27, 0.27)
DIVIDER = (0.32, 0.32, 0.32, 1.0)


def _toolbar_layout(context, region, profile):
    """Return (button centers, pill rect, divider y's, radius) in region pixels."""
    items = PROFILES[profile]["items"]
    anchor = PROFILES[profile]["anchor"]
    s = context.preferences.system.ui_scale
    step = 34 * s
    gap = 14 * s
    radius = 13 * s
    pad = 7 * s
    margin = 14 * s
    n_buttons = sum(1 for t in items if t)
    n_div = sum(1 for t in items if t is None)
    inner_h = n_buttons * step + n_div * gap
    width = step + pad
    if anchor.startswith("right"):
        ui_w = 0
        for reg in context.area.regions if context.area else ():
            if reg.type == 'UI' and reg.width > 1 and context.space_data.show_region_ui:
                ui_w = reg.width
        x = region.width - ui_w - margin - width / 2
    else:
        x = margin + width / 2
    if anchor.endswith("top"):
        top = region.height - margin - pad
    else:
        top = region.height / 2 + inner_h / 2
    centers, dividers = [], []
    y = top
    for item in items:
        if item is None:
            dividers.append(y - gap / 2)
            y -= gap
        else:
            centers.append((x, y - step / 2))
            y -= step
    rect = (x - width / 2, top + pad, x + width / 2, top - inner_h - pad)
    return centers, rect, dividers, radius


def _active_tool_id(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        return tool.idname if tool else ""
    except Exception:
        return ""


class LUMBERSTUDIO_GGT_toolbar(bpy.types.GizmoGroup):
    bl_idname = "LUMBERSTUDIO_GGT_toolbar"
    bl_label = "Lumber Studio Toolbar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        return is_studio(context)

    def setup(self, context):
        self.profile = studio_profile(context) or "lumber"
        self.buttons = []
        for item in PROFILES[self.profile]["items"]:
            if item is None:
                continue
            kind, target, icon, extra = item
            gz = self.gizmos.new("GIZMO_GT_button_2d")
            gz.icon = icon
            gz.draw_options = {'BACKDROP'}
            gz.show_drag = False
            gz.alpha = 1.0
            gz.color_highlight = HOVER
            gz.alpha_highlight = 1.0
            if kind == "op" and not _op_exists(target):
                gz.hide = True  # operator missing (e.g. Lumber disabled)
            else:
                # Every button runs through a Studio wrapper so its tooltip reads
                # "Name  (Key)" instead of a generic Blender description.
                wrapper = "lumberstudio.button" if kind in _NO_UNDO_KINDS else "lumberstudio.button_undo"
                try:
                    props = gz.target_set_operator(wrapper)
                    props.kind = kind
                    props.target = target
                except Exception:
                    gz.hide = True
            active_ids = set(extra) | ({target} if kind == "tool" else set())
            self.buttons.append((gz, kind, target, active_ids))

    def draw_prepare(self, context):
        profile = studio_profile(context)
        if profile and profile != self.profile:  # workspace switched profile: rebuild buttons
            self.gizmos.clear()
            self.setup(context)
        centers, _rect, _div, radius = _toolbar_layout(context, context.region, self.profile)
        radius /= context.preferences.system.ui_scale  # the SCALE option applies UI scale again
        active = _active_tool_id(context)
        selmode = tuple(context.tool_settings.mesh_select_mode) if context.mode == 'EDIT_MESH' else (False,) * 3
        for (gz, kind, target, active_ids), (x, y) in zip(self.buttons, centers):
            m = gz.matrix_basis.copy()
            m[0][3] = x
            m[1][3] = y
            gz.matrix_basis = m
            gz.scale_basis = radius
            if kind == "selmode":
                on = selmode[SELMODE_INDEX[target]]
            else:
                on = active in active_ids
            gz.color = ACTIVE if on else IDLE


def _rounded_rect(x0, y0, x1, y1, r, seg=8):
    r = min(r, (x1 - x0) / 2, (y0 - y1) / 2)
    corners = ((x1 - r, y0 - r, 0), (x0 + r, y0 - r, pi / 2),
               (x0 + r, y1 + r, pi), (x1 - r, y1 + r, 3 * pi / 2))
    pts = [((x0 + x1) / 2, (y0 + y1) / 2)]
    for cx, cy, a0 in corners:
        for i in range(seg + 1):
            a = a0 + (pi / 2) * i / seg
            pts.append((cx + r * cos(a), cy + r * sin(a)))
    pts.append(pts[1])
    return pts


_draw_handle = None


def _draw_pill():
    """Runs in the POST_VIEW pass so the pill sits beneath the 2D gizmo buttons."""
    context = bpy.context
    region = context.region
    profile = studio_profile(context)
    if region is None or profile is None:
        return
    from mathutils import Matrix
    w, h = region.width, region.height
    ortho = Matrix(((2 / w, 0, 0, -1), (0, 2 / h, 0, -1), (0, 0, -1, 0), (0, 0, 0, 1)))
    with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
        gpu.matrix.load_identity()
        gpu.matrix.load_projection_matrix(ortho)
        gpu.state.depth_test_set('NONE')
        _draw_pill_shapes(context, region, profile)


def _draw_pill_shapes(context, region, profile):
    centers, rect, dividers, _r = _toolbar_layout(context, region, profile)
    x0, y0, x1, y1 = rect
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": _rounded_rect(x0, y0, x1, y1, (x1 - x0) / 2)})
    shader.uniform_float("color", PILL)
    batch.draw(shader)
    s = context.preferences.system.ui_scale
    lines = []
    for y in dividers:
        lines += [(x0 + 9 * s, y), (x1 - 9 * s, y)]
    if lines:
        gpu.state.line_width_set(max(1.0, s))
        lb = batch_for_shader(shader, 'LINES', {"pos": lines})
        shader.uniform_float("color", DIVIDER)
        lb.draw(shader)
        gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


# ---------------------------------------------------------------------------
# Hamburger menu + top bar
# ---------------------------------------------------------------------------

class LUMBERSTUDIO_OT_set_workspace(bpy.types.Operator):
    bl_idname = "lumberstudio.set_workspace"
    bl_label = "Switch Workspace"
    bl_options = {'INTERNAL'}

    name: bpy.props.StringProperty()

    def execute(self, context):
        ws = bpy.data.workspaces.get(self.name)
        if ws is None:
            self.report({'WARNING'}, f"No workspace named {self.name}")
            return {'CANCELLED'}
        context.window.workspace = ws
        return {'FINISHED'}


class LUMBERSTUDIO_MT_workspaces(bpy.types.Menu):
    bl_idname = "LUMBERSTUDIO_MT_workspaces"
    bl_label = "Workspaces"

    def draw(self, context):
        layout = self.layout
        current = context.window.workspace
        studio_app = in_studio_app()
        for ws in bpy.data.workspaces:
            if ws.name in LEGACY_WORKSPACES and ws != current:
                continue                # the retired studioEdit tab
            if studio_app and not _is_studio_ws(ws):
                continue                # in the Studio template, only Studio's own tabs
            row = layout.row()
            op = row.operator("lumberstudio.set_workspace", text=ws.name,
                              icon='CHECKMARK' if ws == current else 'BLANK1')
            op.name = ws.name


class LUMBERSTUDIO_MT_main(bpy.types.Menu):
    bl_idname = "LUMBERSTUDIO_MT_main"
    bl_label = "Menu"

    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'INVOKE_DEFAULT'

        if in_studio_app():
            # Leave the Studio template: stock Blender with your own theme and settings
            op = layout.operator("wm.read_homefile", text="Exit to Full Blender")
            op.app_template = ""
        else:
            op = layout.operator("lumberstudio.set_workspace", text="Exit to Full Blender")
            op.name = "Layout"
        layout.menu("LUMBERSTUDIO_MT_workspaces")
        layout.separator()

        layout.operator("wm.read_homefile", text="New")
        layout.operator("wm.open_mainfile", text="Open…")
        layout.menu("TOPBAR_MT_file_open_recent")
        layout.operator("wm.save_mainfile", text="Save")
        layout.operator("wm.save_as_mainfile", text="Save As…")
        layout.separator()

        layout.operator("ed.undo")
        layout.operator("ed.redo")
        layout.separator()

        if is_editing(context):
            layout.operator("lumberstudio.edit_done", text="Done Editing", icon='CHECKMARK')
            layout.separator()
        elif studio_profile(context) == "general":
            layout.menu("LUMBERSTUDIO_MT_add_shape", text="Add Shape")
            layout.menu("LUMBERSTUDIO_MT_add_object", text="Add 3D Object")
            layout.operator("lumberstudio.add", text="Add Text").kind = 'TEXT'
            layout.operator("lumberstudio.add_image", text="Add Image…")
            layout.separator()
            layout.operator("lumberstudio.preview_toggle", text="Toggle Preview")
            layout.operator("render.render", text="Render Image")
            layout.separator()
        elif lumber_available():
            layout.operator("lumber.add_board", text="Add 2x4")
            layout.operator("lumber.add_supports", text="Add Supports")
            layout.operator("lumber.fit_to_plate", text="Fit to Plate")
            layout.operator("lumber.setup_print_scene", text="Set Up Print Scene")
            layout.operator("lumber.export", text="Export Print…")
            layout.separator()

        layout.operator("wm.window_fullscreen_toggle", text="Toggle Full Screen")
        layout.operator("screen.userpref_show", text="Preferences…")


# ---------------------------------------------------------------------------
# General (Spline-like) tools
# ---------------------------------------------------------------------------

# name: (label, icon, operator path or "custom.<builder>", kwargs, smooth?, give default material?)
PRIMITIVES = {
    "RECTANGLE": ("Rectangle", 'MESH_PLANE', "mesh.primitive_plane_add", {}, False, True),
    "ROUNDED_RECT": ("Rounded Rect", 'MESH_PLANE', "mesh.primitive_plane_add", {}, False, True),
    "ELLIPSE": ("Ellipse", 'MESH_CIRCLE', "mesh.primitive_circle_add", {"fill_type": 'NGON', "vertices": 64}, False, True),
    "TRIANGLE": ("Triangle", 'MESH_CIRCLE', "mesh.primitive_circle_add", {"fill_type": 'NGON', "vertices": 3}, False, True),
    "POLYGON": ("Polygon", 'MESH_CIRCLE', "mesh.primitive_circle_add", {"fill_type": 'NGON', "vertices": 6}, False, True),
    "STAR": ("Star", 'SOLO_OFF', "custom.star", {}, False, True),
    "PATH": ("Path", 'CURVE_BEZCURVE', "curve.primitive_bezier_curve_add", {}, False, False),
    "RING": ("Ring Path", 'CURVE_BEZCIRCLE', "curve.primitive_bezier_circle_add", {}, False, False),
    "CUBE": ("Cube", 'MESH_CUBE', "mesh.primitive_cube_add", {}, False, True),
    "SPHERE": ("Sphere", 'MESH_UVSPHERE', "mesh.primitive_uv_sphere_add", {"segments": 48, "ring_count": 24}, True, True),
    "CYLINDER": ("Cylinder", 'MESH_CYLINDER', "mesh.primitive_cylinder_add", {"vertices": 64}, True, True),
    "CONE": ("Cone", 'MESH_CONE', "mesh.primitive_cone_add", {"vertices": 64}, True, True),
    "PYRAMID": ("Pyramid", 'MESH_CONE', "mesh.primitive_cone_add", {"vertices": 4}, False, True),
    "TORUS": ("Torus", 'MESH_TORUS', "mesh.primitive_torus_add", {"major_segments": 64, "minor_segments": 24}, True, True),
    "CAPSULE": ("Capsule", 'MESH_CAPSULE', "custom.capsule", {}, True, True),
    "TEXT": ("Text", 'FONT_DATA', "object.text_add", {}, False, True),
    "EMPTY": ("Empty", 'EMPTY_AXIS', "object.empty_add", {}, False, False),
    "LIGHT": ("Light", 'LIGHT_AREA', "object.light_add", {"type": 'AREA'}, False, False),
    "CAMERA": ("Camera", 'CAMERA_DATA', "object.camera_add", {}, False, False),
}
SHAPES_2D = ("RECTANGLE", "ROUNDED_RECT", "ELLIPSE", "TRIANGLE", "POLYGON", "STAR", "PATH", "RING")
OBJECTS_3D = ("CUBE", "SPHERE", "CYLINDER", "CONE", "PYRAMID", "TORUS", "CAPSULE", "TEXT")
OTHER_OBJECTS = ("EMPTY", "LIGHT", "CAMERA")
DEFAULT_MATERIAL = "Studio Default"
CORNERS_MOD = "Studio Corners"
DEPTH_MOD = "Studio Depth"


def _default_material():
    mat = bpy.data.materials.get(DEFAULT_MATERIAL)
    if mat is None:
        mat = bpy.data.materials.new(DEFAULT_MATERIAL)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.78, 0.78, 0.8, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.45
        mat.diffuse_color = (0.78, 0.78, 0.8, 1.0)
    return mat


def _studio_rv3d(context):
    rv3d = getattr(context, "region_data", None)
    if rv3d is None:
        for area in (context.screen.areas if context.screen else ()):
            if area.type == 'VIEW_3D':
                return area.spaces.active.region_3d
    return rv3d


def _studio_view3d(context):
    for area in (context.screen.areas if context.screen else ()):
        if area.type == 'VIEW_3D':
            return area.spaces.active
    return None


def _view_center(context):
    rv3d = _studio_rv3d(context)
    return tuple(rv3d.view_location) if rv3d else (0.0, 0.0, 0.0)


def _view_scale(context):
    """Size new objects relative to the zoom level, so they're always visible."""
    rv3d = _studio_rv3d(context)
    return max(rv3d.view_distance * 0.08, 1e-4) if rv3d else 1.0


# ---------------------------------------------------------------------------
# 3D printing: the printer, plate and units come from Lumber's print settings
# (scene.lumber_print), so Lumber and Studio always agree on the build plate.
# ---------------------------------------------------------------------------

DEFAULT_PLATE_MM = (256.0, 256.0, 260.0)     # Bambu Lab X2D, used if Lumber isn't enabled


def _mm(scene, value):
    """A length in millimetres, in Blender units."""
    us = scene.unit_settings
    scale = us.scale_length if us.system != 'NONE' and us.scale_length > 0 else 1.0
    return value * 0.001 / scale


def _mm_per_bu(scene):
    return 1.0 / _mm(scene, 1.0)


def _is_mm_scene(scene):
    us = scene.unit_settings
    return us.system == 'METRIC' and abs(us.scale_length - 0.001) < 1e-7


def _print_settings(scene):
    return getattr(scene, "lumber_print", None)


def _plate_mm(scene):
    st = _print_settings(scene)
    return tuple(st.dims_mm()) if st else DEFAULT_PLATE_MM


def _print_mode(scene):
    """New objects get real print sizes and land on the plate."""
    return getattr(scene, "lumberstudio_print_sizes", False)


def _world_bounds(context, objs):
    import mathutils
    dg = context.evaluated_depsgraph_get()
    lo = mathutils.Vector((math.inf,) * 3)
    hi = mathutils.Vector((-math.inf,) * 3)
    for ob in objs:
        ev = ob.evaluated_get(dg)
        for c in ev.bound_box:
            w = ob.matrix_world @ mathutils.Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], w[i]); hi[i] = max(hi[i], w[i])
    return (lo, hi) if lo.x != math.inf else None


def _place_on_plate(context, objs, xy=None, drop=True):
    """Move objects as one group: centred on xy (kept inside the plate), resting on it."""
    context.view_layer.update()
    b = _world_bounds(context, objs)
    if b is None:
        return
    lo, hi = b
    scene = context.scene
    px, py, _pz = (_mm(scene, v) / 2 for v in _plate_mm(scene))
    dx = dy = 0.0
    if xy is not None:
        tx, ty = xy
        w, d = (hi.x - lo.x) / 2, (hi.y - lo.y) / 2
        tx = 0.0 if w >= px else max(-px + w, min(px - w, tx))
        ty = 0.0 if d >= py else max(-py + d, min(py - d, ty))
        dx, dy = tx - (lo.x + hi.x) / 2, ty - (lo.y + hi.y) / 2
    dz = -lo.z if drop else 0.0
    for ob in objs:
        if ob.parent in objs:
            continue
        ob.location.x += dx
        ob.location.y += dy
        ob.location.z += dz


def _fits_plate(context, objs):
    b = _world_bounds(context, objs)
    if b is None:
        return True
    k = _mm_per_bu(context.scene)
    size = [(b[1][i] - b[0][i]) * k for i in range(3)]
    return all(s <= p + 1e-3 for s, p in zip(size, _plate_mm(context.scene)))


def _size_mm_get(self):
    ob = bpy.context.object
    if ob is None:
        return (0.0, 0.0, 0.0)
    k = _mm_per_bu(bpy.context.scene)
    return tuple(d * k for d in ob.dimensions)


def _size_mm_set(self, value):
    ob = bpy.context.object
    if ob is None:
        return
    scene = bpy.context.scene
    k = _mm_per_bu(scene)
    cur = list(ob.dimensions)
    new = [max(v, 0.0) / k for v in value]
    if scene.lumberstudio_lock_ratio:
        # keep proportions: scale everything by the axis that was just typed in
        i = max(range(3), key=lambda a: abs(new[a] - cur[a]))
        if cur[i] > 0:
            f = new[i] / cur[i]
            new = [c * f for c in cur]
    new = [n if c > 0 else c for n, c in zip(new, cur)]   # a flat axis stays flat
    ob.dimensions = new


class LUMBERSTUDIO_OT_plate(bpy.types.Operator):
    """Put the selection on the build plate"""
    bl_idname = "lumberstudio.plate"
    bl_label = "Place on Plate"
    bl_options = {'REGISTER', 'UNDO'}

    action: bpy.props.EnumProperty(items=[
        ('DROP', "Drop to Plate", "Lower the selection until it rests on the plate"),
        ('CENTER', "Center on Plate", "Move the selection to the middle of the plate, resting on it"),
    ])

    @classmethod
    def description(cls, context, props):
        return {"DROP": "Lower the selection until it rests on the build plate",
                "CENTER": "Move the selection to the middle of the build plate, resting on it"}[props.action]

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(_selected(context))

    def execute(self, context):
        objs = [o for o in _selected(context) if o.type in {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META', 'EMPTY'}]
        _place_on_plate(context, objs, xy=(0.0, 0.0) if self.action == 'CENTER' else None)
        return {'FINISHED'}


def _frame_plate(scene):
    """Point every studio viewport at the build plate, the way Lumber frames its view."""
    import mathutils
    x, y, z = (_mm(scene, v) for v in _plate_mm(scene))
    top = z * 0.25
    target = mathutils.Vector((0.0, 0.0, top * 0.35))
    view_dir = mathutils.Vector((0.62, -0.78, 0.55)).normalized()
    pts = [mathutils.Vector((sx * x / 2, sy * y / 2, sz)) for sx in (-1, 1) for sy in (-1, 1) for sz in (0.0, top)]
    radius = max((p - target).length for p in pts)
    for ws in bpy.data.workspaces:
        if not _is_studio_ws(ws):
            continue
        for scr in ws.screens:
            for area in scr.areas:
                if area.type != 'VIEW_3D':
                    continue
                sp = area.spaces.active
                sp.clip_start = _mm(scene, 0.1)
                sp.clip_end = _mm(scene, 50000.0)
                r3 = sp.region_3d
                r3.view_perspective = 'PERSP'
                r3.view_location = target
                r3.view_rotation = (-view_dir).to_track_quat('-Z', 'Y')
                r3.view_distance = radius / math.tan(math.radians(20)) * 1.15
                area.tag_redraw()


def _is_default_cube(ob):
    return (ob is not None and ob.name == "Cube" and ob.type == 'MESH' and len(ob.data.vertices) == 8
            and all(abs(d - 2.0) < 1e-4 for d in ob.dimensions) and ob.location.length < 1e-6)


class LUMBERSTUDIO_OT_print_setup(bpy.types.Operator):
    """Switch this scene to millimetres for 3D printing and frame the build plate"""
    bl_idname = "lumberstudio.print_setup"
    bl_label = "Use Millimeters"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import mathutils
        scene = context.scene
        cube = scene.objects.get("Cube")
        cube = cube if _is_default_cube(cube) else None
        if _print_settings(scene) is not None and hasattr(bpy.ops.lumber, "setup_print_scene"):
            # Lumber's setup: mm units, real sizes kept, camera on the plate
            bpy.ops.lumber.setup_print_scene(keep_sizes=True, setup_camera=True,
                                             add_light=False, frame_views=False)
        else:
            us = scene.unit_settings
            us.system, us.scale_length, us.length_unit = 'METRIC', 0.001, 'MILLIMETERS'
        if cube is not None:
            # Blender's 2 m starter cube becomes a printable cube on the plate
            # (measured from the mesh itself: object dimensions lag behind until the next redraw)
            s = _mm(scene, scene.lumberstudio_new_size)
            cube.scale = (1.0, 1.0, 1.0)
            ext = 2 * max(abs(c) for v in cube.data.vertices for c in v.co) or 1.0
            cube.data.transform(mathutils.Matrix.Scale(s / ext, 4))
            cube.location = (0.0, 0.0, s / 2)
        _frame_plate(scene)
        return {'FINISHED'}


def _open_on_studio_tab():
    """A new Studio file starts on the Studio tab, whatever tab the startup file was saved on."""
    if bpy.data.filepath:
        return
    studio = bpy.data.workspaces.get("Studio")
    wm = bpy.context.window_manager
    if studio is None or wm is None:
        return
    for win in wm.windows:
        if not _is_studio_ws(win.workspace):
            win.workspace = studio


def _new_file_setup():
    """New, untitled files start ready to print: millimetres, framed on the plate."""
    wm = bpy.context.window_manager
    if wm is None or not wm.windows:
        return 0.5
    if not in_studio_app():
        return None                             # only Studio's own new files; stock Blender files stay as they are
    _open_on_studio_tab()
    scene = bpy.context.scene
    if bpy.data.filepath or _is_mm_scene(scene) or not getattr(scene, "lumberstudio_print_sizes", False):
        return None
    if any(o.name not in {"Cube", "Light", "Camera"} for o in scene.objects):
        return None                             # not the stock startup scene: leave it alone
    win = wm.windows[0]
    try:
        with bpy.context.temp_override(window=win, screen=win.screen, scene=scene):
            bpy.ops.lumberstudio.print_setup()
    except Exception as e:
        print(f"Lumber Studio: print setup skipped: {e}")
    return None


def _draw_plate_tools(layout, context, objs):
    col = _section(layout, "Print")
    r = col.row(align=True)
    r.operator("lumberstudio.plate", text="Drop to Plate", icon='TRIA_DOWN_BAR').action = 'DROP'
    r.operator("lumberstudio.plate", text="Center", icon='PIVOT_BOUNDBOX').action = 'CENTER'
    if not _fits_plate(context, objs):
        x, y, z = _plate_mm(context.scene)
        col.label(text=f"Larger than the {x:g} x {y:g} x {z:g} mm build area", icon='ERROR')


def _build_star(bm, points=5, inner=0.45):
    verts = []
    for i in range(points * 2):
        a = pi / 2 + i * pi / points
        r = 1.0 if i % 2 == 0 else inner
        verts.append(bm.verts.new((r * cos(a), r * sin(a), 0.0)))
    bm.faces.new(verts)


def _build_capsule(bm):
    import bmesh
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=0.5)
    for v in bm.verts:  # stretch the hemispheres apart into a pill
        if v.co.z > 1e-6:
            v.co.z += 0.5
        elif v.co.z < -1e-6:
            v.co.z -= 0.5


def _add_custom(context, builder, label, location):
    import bmesh
    me = bpy.data.meshes.new(label)
    bm = bmesh.new()
    {"star": _build_star, "capsule": _build_capsule}[builder](bm)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(label, me)
    context.collection.objects.link(obj)
    obj.location = location
    for o in context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return obj


def _is_flat(obj):
    dims = [d for d in obj.dimensions]
    return obj.type == 'MESH' and min(dims) <= max(dims) * 1e-4


def _add_corners(obj, radius=None):
    mod = obj.modifiers.get(CORNERS_MOD) or obj.modifiers.new(CORNERS_MOD, 'BEVEL')
    flat = _is_flat(obj) or obj.modifiers.get(DEPTH_MOD) is not None
    mod.affect = 'VERTICES' if flat else 'EDGES'
    mod.segments = 8
    mod.limit_method = 'ANGLE'
    mod.width = radius if radius is not None else max(obj.dimensions) * 0.12
    mod.harden_normals = False
    # corners round the outline first, then depth extrudes it
    idx = list(obj.modifiers).index(mod)
    if idx != 0:
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=0)
    return mod


def _add_depth(obj):
    mod = obj.modifiers.get(DEPTH_MOD) or obj.modifiers.new(DEPTH_MOD, 'SOLIDIFY')
    mod.thickness = max(obj.dimensions) * 0.25
    mod.offset = 0.0
    mod.use_even_offset = True
    corners = obj.modifiers.get(CORNERS_MOD)
    if corners:
        corners.affect = 'VERTICES'
    return mod


class LUMBERSTUDIO_OT_add(bpy.types.Operator):
    """Add an object at the center of the view, Spline-style"""
    bl_idname = "lumberstudio.add"
    bl_label = "Add"
    bl_options = {'REGISTER', 'UNDO'}

    kind: bpy.props.EnumProperty(items=[(k, v[0], "", v[1], i) for i, (k, v) in enumerate(PRIMITIVES.items())])

    @classmethod
    def description(cls, context, props):
        return f"Add {PRIMITIVES[props.kind][0].lower()} at the center of the view"

    def execute(self, context):
        label, _icon, path, kwargs, smooth, give_mat = PRIMITIVES[self.kind]
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        mod, name = path.split(".")
        if mod == "custom":
            obj = _add_custom(context, name, label, _view_center(context))
        else:
            getattr(getattr(bpy.ops, mod), name)(location=_view_center(context), **kwargs)
            obj = context.active_object
        if obj is None:
            return {'CANCELLED'}
        obj.name = label
        s = _view_scale(context)
        scene = context.scene
        printing = _print_mode(scene) and obj.type in {'MESH', 'CURVE', 'FONT'}
        if printing:
            # a real-world size: the longest side becomes the "New Object Size"
            context.view_layer.update()
            longest = max(obj.dimensions) or 1.0
            s = _mm(scene, scene.lumberstudio_new_size) / longest
        if obj.type in {'MESH', 'CURVE', 'FONT'}:
            obj.scale = (s, s, s)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        elif obj.type == 'EMPTY':
            obj.empty_display_size = s
        elif obj.type == 'CAMERA':
            obj.data.display_size = s
        elif obj.type == 'LIGHT' and obj.data.type == 'AREA':
            obj.data.size = s * 2
        if smooth and hasattr(bpy.ops.object, "shade_auto_smooth"):
            bpy.ops.object.shade_auto_smooth()
        if self.kind == "ROUNDED_RECT":
            _add_corners(obj)
        if give_mat and hasattr(obj.data, "materials") and not obj.data.materials:
            obj.data.materials.append(_default_material())
        if printing:
            if self.kind in SHAPES_2D and obj.type == 'MESH':
                depth = _add_depth(obj)          # flat shapes can't print: give them a base
                depth.thickness = _mm(scene, 2.0)
                depth.offset = 1.0               # grow up from the plate
            elif obj.type == 'FONT':
                obj.data.extrude = _mm(scene, 1.0)
            _place_on_plate(context, [obj], xy=_view_center(context)[:2])
            if obj.type == 'FONT':
                obj.location.z = obj.data.extrude    # text extrudes both ways from its baseline plane
        if studio_profile(context) == "general":
            # Spline drops you back on the select tool, so the new layer shows its handles
            try:
                bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
            except Exception:
                pass
        return {'FINISHED'}


def _draw_add_items(layout, kinds):
    for k in kinds:
        if k is None:
            layout.separator()
            continue
        layout.operator("lumberstudio.add", text=PRIMITIVES[k][0], icon=PRIMITIVES[k][1]).kind = k


def _draw_add_grid(layout, kinds, columns=4):
    """Spline-style palette: big icon tiles with a caption underneath."""
    grid = layout.grid_flow(row_major=True, columns=columns, even_columns=True, even_rows=True, align=False)
    for k in kinds:
        label, icon = PRIMITIVES[k][0], PRIMITIVES[k][1]
        tile = grid.column(align=True)
        big = tile.column(align=True)
        big.scale_y = 2.4
        big.operator("lumberstudio.add", text="", icon=icon).kind = k
        cap = tile.row()
        cap.alignment = 'CENTER'
        cap.label(text=label)


class LUMBERSTUDIO_MT_add_shape(bpy.types.Menu):
    bl_idname = "LUMBERSTUDIO_MT_add_shape"
    bl_label = "Shapes"

    def draw(self, context):
        _draw_add_items(self.layout, SHAPES_2D)


class LUMBERSTUDIO_MT_add_object(bpy.types.Menu):
    bl_idname = "LUMBERSTUDIO_MT_add_object"
    bl_label = "3D Objects"

    def draw(self, context):
        _draw_add_items(self.layout, OBJECTS_3D + (None,) + OTHER_OBJECTS)


class LUMBERSTUDIO_PT_add_shape(bpy.types.Panel):
    """Popover palette opened by the toolbar's shape button"""
    bl_idname = "LUMBERSTUDIO_PT_add_shape"
    bl_label = "Shapes"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 16

    def draw(self, context):
        self.layout.label(text="Shapes")
        _draw_add_grid(self.layout, SHAPES_2D)


class LUMBERSTUDIO_PT_add_object(bpy.types.Panel):
    """Popover palette opened by the toolbar's 3D button"""
    bl_idname = "LUMBERSTUDIO_PT_add_object"
    bl_label = "3D Objects"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 16

    def draw(self, context):
        layout = self.layout
        layout.label(text="3D Objects")
        _draw_add_grid(layout, OBJECTS_3D)
        layout.separator()
        layout.label(text="Scene")
        _draw_add_grid(layout, OTHER_OBJECTS, columns=4)


# ---------------------------------------------------------------------------
# Right panel: changes with the selection, like Spline
#   nothing selected -> Scene   |   one layer -> Design   |   several -> Align + Design
# The panels live in the Properties editor's Tool tab, the one tab that
# exists even when nothing is active.
# ---------------------------------------------------------------------------

def _principled(mat):
    if mat and mat.use_nodes and mat.node_tree:
        for n in mat.node_tree.nodes:
            if n.type == 'BSDF_PRINCIPLED':
                return n
    return None


def _xyz_row(layout, label, owner, prop):
    split = layout.split(factor=0.24)
    split.label(text=label)
    row = split.row(align=True)
    for i in range(3):
        row.prop(owner, prop, index=i, text="")


def _section(layout, title, op=None, op_icon='ADD', **op_props):
    layout.separator()
    row = layout.row()
    row.label(text=title)
    if op:
        o = row.operator(op, text="", icon=op_icon, emboss=False)
        for k, v in op_props.items():
            setattr(o, k, v)
    return layout.column(align=True)


def _selected(context):
    return [o for o in context.view_layer.objects if o.select_get()]


class LUMBERSTUDIO_OT_add_material(bpy.types.Operator):
    """Give the object its own material"""
    bl_idname = "lumberstudio.add_material"
    bl_label = "Add Material"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and hasattr(obj.data, "materials")

    def execute(self, context):
        obj = context.object
        src = obj.active_material or _default_material()
        mat = src.copy()
        mat.name = f"{obj.name} Material"
        if obj.data.materials:
            obj.data.materials[obj.active_material_index] = mat
        else:
            obj.data.materials.append(mat)
        return {'FINISHED'}


class LUMBERSTUDIO_OT_shape_mod(bpy.types.Operator):
    """Add or remove a Spline-style shape setting"""
    bl_idname = "lumberstudio.shape_mod"
    bl_label = "Shape Setting"
    bl_options = {'REGISTER', 'UNDO'}

    kind: bpy.props.EnumProperty(items=[('CORNERS', "Corner Radius", ""), ('DEPTH', "Extrusion", "")])
    remove: bpy.props.BoolProperty(default=False)

    @classmethod
    def description(cls, context, props):
        what = "corner radius" if props.kind == 'CORNERS' else "extrusion depth"
        return f"{'Remove' if props.remove else 'Add'} {what}"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def execute(self, context):
        obj = context.object
        name = CORNERS_MOD if self.kind == 'CORNERS' else DEPTH_MOD
        if self.remove:
            m = obj.modifiers.get(name)
            if m:
                obj.modifiers.remove(m)
        elif self.kind == 'CORNERS':
            _add_corners(obj)
        else:
            _add_depth(obj)
        return {'FINISHED'}


class LUMBERSTUDIO_OT_align(bpy.types.Operator):
    """Align the selected layers to each other"""
    bl_idname = "lumberstudio.align"
    bl_label = "Align"
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")])
    mode: bpy.props.EnumProperty(items=[('OPT_1', "Min", ""), ('OPT_2', "Center", ""), ('OPT_3', "Max", "")])

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(_selected(context)) > 1

    def execute(self, context):
        with context.temp_override(selected_editable_objects=_selected(context)):
            bpy.ops.object.align(align_mode=self.mode, relative_to='OPT_4', align_axis={self.axis})
        return {'FINISHED'}


class LUMBERSTUDIO_OT_select_none(bpy.types.Operator):
    """Deselect everything to see the scene settings"""
    bl_idname = "lumberstudio.select_none"
    bl_label = "Deselect"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for o in _selected(context):
            o.select_set(False)
        return {'FINISHED'}


class _StudioPanel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_options = {'HIDE_HEADER'}


class LUMBERSTUDIO_PT_scene(_StudioPanel, bpy.types.Panel):
    bl_idname = "LUMBERSTUDIO_PT_scene"
    bl_label = "Scene"
    bl_order = -100

    @classmethod
    def poll(cls, context):
        return studio_profile(context) == "general" and not _selected(context)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        v3d = _studio_view3d(context)
        layout.label(text=scene.name, icon='SCENE_DATA')

        st = _print_settings(scene)
        col = _section(layout, "3D Print")
        if st is not None:
            col.prop(st, "printer", text="")
            col.prop(st, "show_build_area", text="Show Build Plate")
            if st.printer == 'X2D':
                col.prop(st, "show_aux_zone", text="Aux-Nozzle Strip")
            elif st.printer == 'CUSTOM':
                r = col.row(align=True)
                r.prop(st, "size_x"); r.prop(st, "size_y"); r.prop(st, "size_z")
        else:
            col.label(text="Enable Lumber Supports for printer plates", icon='INFO')
        col.prop(scene, "lumberstudio_print_sizes", text="Print-Size New Objects")
        sub = col.row()
        sub.enabled = scene.lumberstudio_print_sizes
        sub.prop(scene, "lumberstudio_new_size", text="New Object Size (mm)")
        if not _is_mm_scene(scene):
            col.operator("lumberstudio.print_setup", text="Use Millimeters", icon='FIXED_SIZE')
        else:
            col.operator("lumberstudio.print_setup", text="Frame Build Plate", icon='VIEW_CAMERA')

        if v3d:
            sh, ov = v3d.shading, v3d.overlay
            stage = sh.type == 'MATERIAL' and scene.lumberstudio_preview_floor
            col = _section(layout, "Background")
            split = col.split(factor=0.3)
            split.label(text="Color")
            split.prop(scene if stage else sh, "lumberstudio_stage_color" if stage else "background_color", text="")

            sun = _preview_sun()
            if stage and sun is not None:
                # In Preview the sun does the lighting (the solid-view options below don't apply)
                _draw_sun_controls(layout, scene, sun)
            else:
                col = _section(layout, "Lighting")
                col.row().prop(sh, "light", expand=True)
                col.prop(sh, "show_shadows", text="Shadows")
                col.prop(sh, "show_cavity", text="Soft Edges")
                col.prop(sh, "show_specular_highlight", text="Highlights")

            col = _section(layout, "Canvas")
            previewing = sh.type == 'MATERIAL'
            if previewing:
                col.prop(scene, "lumberstudio_preview_floor", text="Floor")
            else:
                col.prop(ov, "show_floor", text="Grid")
                col.prop(ov, "show_outline_selected", text="Selection Outline")
                col.prop(scene, "lumberstudio_preview_floor", text="Floor in Preview")

        if scene.world and scene.world.name != _STAGE_WORLD:
            col = _section(layout, "Render Background")
            split = col.split(factor=0.3)
            split.label(text="Color")
            split.prop(scene.world, "color", text="")

        col = _section(layout, "Units")
        col.prop(scene.unit_settings, "length_unit", text="")
        layout.separator()
        layout.label(text=f"{len(context.view_layer.objects)} layers", icon='OUTLINER')


class LUMBERSTUDIO_PT_multi(_StudioPanel, bpy.types.Panel):
    bl_idname = "LUMBERSTUDIO_PT_multi"
    bl_label = "Selection"
    bl_order = -95

    @classmethod
    def poll(cls, context):
        return studio_profile(context) == "general" and len(_selected(context)) > 1

    def draw(self, context):
        layout = self.layout
        sel = _selected(context)
        row = layout.row()
        row.label(text=f"{len(sel)} layers selected", icon='RESTRICT_SELECT_OFF')
        row.operator("lumberstudio.select_none", text="", icon='X', emboss=False)

        col = _section(layout, "Align")
        for axis, icons in (("X", ('ALIGN_LEFT', 'ALIGN_CENTER', 'ALIGN_RIGHT')),
                            ("Z", ('ALIGN_BOTTOM', 'ALIGN_MIDDLE', 'ALIGN_TOP'))):
            r = col.row(align=True)
            r.label(text="Horizontal" if axis == "X" else "Vertical")
            for mode, icon in zip(('OPT_1', 'OPT_2', 'OPT_3'), icons):
                op = r.operator("lumberstudio.align", text="", icon=icon)
                op.axis, op.mode = axis, mode
        _draw_plate_tools(layout, context, sel)
        layout.separator()
        layout.operator("lumberstudio.group", text="Group Selection", icon='OUTLINER_OB_EMPTY')


class LUMBERSTUDIO_PT_design(_StudioPanel, bpy.types.Panel):
    bl_idname = "LUMBERSTUDIO_PT_design"
    bl_label = "Design"
    bl_order = -90

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (studio_profile(context) == "general" and obj is not None
                and obj.select_get() and obj.visible_get())

    def draw(self, context):
        layout = self.layout
        obj = context.object

        if _is_preview_sun(obj):
            # The Preview sun only has a direction, not a place: show sun controls, not Position/Rotation
            layout.label(text="Sun", icon='LIGHT_SUN')
            _draw_sun_controls(layout, context.scene, obj, heading=False)
            return

        row = layout.row()
        row.prop(obj, "name", text="", icon='OBJECT_DATA')
        row.prop(obj, "hide_viewport", text="", emboss=False)
        if obj.type in EDITABLE_TYPES:
            layout.operator("lumberstudio.edit_enter", text="Edit", icon='EDITMODE_HLT')

        layout.separator()
        _xyz_row(layout, "Position", obj, "location")
        _xyz_row(layout, "Rotation", obj, "rotation_euler")
        if obj.type not in SIZED_TYPES:
            # Lights, cameras and empties have no real size, so Scale stays for them
            _xyz_row(layout, "Scale", obj, "scale")
        if obj.type in SIZED_TYPES:
            # Size in mm replaces Scale: students think in real measurements
            split = layout.split(factor=0.24)
            split.label(text="Size (mm)")
            row = split.row(align=True)
            for i in range(3):
                row.prop(context.window_manager, "lumberstudio_size_mm", index=i, text="")
            lock = context.scene.lumberstudio_lock_ratio
            row.prop(context.scene, "lumberstudio_lock_ratio", text="",
                     icon='LOCKED' if lock else 'UNLOCKED', emboss=False)
            _draw_plate_tools(layout, context, [obj])

        if obj.type == 'MESH':
            corners = obj.modifiers.get(CORNERS_MOD)
            depth = obj.modifiers.get(DEPTH_MOD)
            flat = _is_flat(obj) or depth is not None
            col = _section(layout, "Shape")
            if corners:
                r = col.row(align=True)
                r.prop(corners, "width", text="Corner Radius")
                r.operator("lumberstudio.shape_mod", text="", icon='X').kind = 'CORNERS'
                col.prop(corners, "segments", text="Smoothness")
            else:
                col.operator("lumberstudio.shape_mod", text="Round Corners", icon='MOD_BEVEL').kind = 'CORNERS'
            if flat:
                if depth:
                    r = col.row(align=True)
                    r.prop(depth, "thickness", text="Extrusion")
                    op = r.operator("lumberstudio.shape_mod", text="", icon='X')
                    op.kind, op.remove = 'DEPTH', True
                else:
                    col.operator("lumberstudio.shape_mod", text="Extrude", icon='MOD_SOLIDIFY').kind = 'DEPTH'

        if obj.type == 'CURVE':
            col = _section(layout, "Path")
            col.prop(obj.data, "bevel_depth", text="Thickness")
            col.prop(obj.data, "extrude", text="Extrusion")
            col.prop(obj.data, "use_fill_caps", text="Fill Ends")

        if obj.type == 'FONT':
            col = _section(layout, "Text")
            col.prop(obj.data, "size")
            col.prop(obj.data, "extrude", text="Extrusion")
            col.prop(obj.data, "bevel_depth", text="Rounding")
            col.row().prop(obj.data, "align_x", expand=True)
            if context.mode != 'EDIT_TEXT':
                col.operator("object.editmode_toggle", text="Edit Text", icon='GREASEPENCIL')

        if obj.type == 'LIGHT':
            col = _section(layout, "Light")
            col.prop(obj.data, "color", text="")
            col.prop(obj.data, "energy", text="Intensity")

        if hasattr(obj.data, "materials"):
            mat = obj.active_material
            needs_own = mat is None or mat.name == DEFAULT_MATERIAL
            col = _section(layout, "Material", "lumberstudio.add_material" if needs_own else None)
            if mat is not None:
                bsdf = _principled(mat)
                if bsdf:
                    split = col.split(factor=0.3)
                    split.label(text="Color")
                    split.prop(bsdf.inputs["Base Color"], "default_value", text="")
                    for label, key in (("Roughness", "Roughness"), ("Metalness", "Metallic"), ("Opacity", "Alpha")):
                        if key in bsdf.inputs:
                            col.prop(bsdf.inputs[key], "default_value", text=label, slider=True)
                else:
                    col.prop(mat, "diffuse_color", text="Color")
                if mat.name == DEFAULT_MATERIAL and mat.users > 1:
                    layout.label(text="Shared default. Press + to make it unique", icon='INFO')

        layout.separator()
        layout.prop(obj, "visible_shadow", text="Cast Shadows")


# ---------------------------------------------------------------------------
# Layers: Spline-style groups (a parent Empty) and a "Layers" outliner header
# ---------------------------------------------------------------------------

class LUMBERSTUDIO_OT_group(bpy.types.Operator):
    """Group the selection under a new Group layer, like Spline"""
    bl_idname = "lumberstudio.group"
    bl_label = "Group Selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and len(context.selected_objects) > 0

    def execute(self, context):
        sel = list(context.selected_objects)
        tops = [o for o in sel if o.parent not in sel]
        center = sum((o.matrix_world.translation for o in tops), sel[0].matrix_world.translation * 0) / len(tops)
        grp = bpy.data.objects.new("Group", None)
        grp["studio_group"] = True
        grp.empty_display_type = 'PLAIN_AXES'
        grp.empty_display_size = 0.0001
        coll = (context.active_object or sel[0]).users_collection[0]
        coll.objects.link(grp)
        grp.location = center
        context.view_layer.update()
        inv = grp.matrix_world.inverted()
        for o in tops:
            mw = o.matrix_world.copy()
            o.parent = grp
            o.matrix_parent_inverse = inv
            o.matrix_world = mw
        for o in sel:
            o.select_set(False)
        grp.select_set(True)
        context.view_layer.objects.active = grp
        return {'FINISHED'}


class LUMBERSTUDIO_OT_ungroup(bpy.types.Operator):
    """Ungroup: lift the group's layers out and remove the group"""
    bl_idname = "lumberstudio.ungroup"
    bl_label = "Ungroup"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and any(o.children for o in context.selected_objects)

    def execute(self, context):
        for grp in [o for o in context.selected_objects if o.children]:
            kids = list(grp.children)
            for k in kids:
                mw = k.matrix_world.copy()
                k.parent = grp.parent
                k.matrix_world = mw
                k.select_set(True)
            if grp.get("studio_group") or (grp.type == 'EMPTY' and grp.name.startswith("Group")):
                bpy.data.objects.remove(grp)
            if kids:
                context.view_layer.objects.active = kids[0]
        return {'FINISHED'}


_orig_outliner_draw = {}


def _outliner_header_draw(self, context):
    if not is_general(context):
        return _orig_outliner_draw["draw"](self, context)
    layout = self.layout
    space = context.space_data
    layout.label(text="Layers")
    layout.separator_spacer()
    row = layout.row(align=True)
    row.prop(space, "filter_text", text="", icon='VIEWZOOM')
    layout.operator("lumberstudio.group", text="", icon='ADD', emboss=False)


def _patch_outliner():
    cls = bpy.types.OUTLINER_HT_header
    _orig_outliner_draw["draw"] = cls.draw
    cls.draw = _outliner_header_draw


def _unpatch_outliner():
    cls = getattr(bpy.types, "OUTLINER_HT_header", None)
    if cls and _orig_outliner_draw:
        cls.draw = _orig_outliner_draw["draw"]
    _orig_outliner_draw.clear()


# ---------------------------------------------------------------------------
# Editing in place: Spline-style editing of a layer's points, edges and faces
# happens inside Studio itself, the way Figma, Spline and Tinkercad do it.
# Studio's toolbar and right panel switch to edit tools while in Edit Mode.
# (The separate studioEdit tab is retired; old files still work if they have it.)
# ---------------------------------------------------------------------------

EDITABLE_TYPES = {'MESH', 'CURVE'}
SIZED_TYPES = {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}
_EDIT_FROM_PREVIEW = "studio_edit_from_preview"


def _leave_preview_for_edit(context):
    """Editing needs the editing overlays: step out of Preview and remember to go back."""
    space = context.space_data if context.space_data and context.space_data.type == 'VIEW_3D' \
        else _studio_view3d(context)
    if space is None or space.shading.type != 'MATERIAL':
        return
    space.id_data[_EDIT_FROM_PREVIEW] = True
    _apply_preview(space, False, context.scene.lumberstudio_preview_floor)


def _return_to_preview_after_edit(context):
    space = context.space_data if context.space_data and context.space_data.type == 'VIEW_3D' \
        else _studio_view3d(context)
    if space is None:
        return
    scr = space.id_data
    if scr.get(_EDIT_FROM_PREVIEW):
        del scr[_EDIT_FROM_PREVIEW]
        _apply_preview(space, True, context.scene.lumberstudio_preview_floor)


class LUMBERSTUDIO_OT_edit_enter(bpy.types.Operator):
    """Edit this layer's points, like double-clicking a shape in Spline"""
    bl_idname = "lumberstudio.edit_enter"
    bl_label = "Edit Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (studio_profile(context) == "general" and context.mode == 'OBJECT'
                and obj is not None and obj.type in EDITABLE_TYPES and obj.select_get())

    def execute(self, context):
        _leave_preview_for_edit(context)
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
        except Exception:
            pass
        return {'FINISHED'}


class LUMBERSTUDIO_OT_edit_done(bpy.types.Operator):
    """Finish editing and go back to the layer"""
    bl_idname = "lumberstudio.edit_done"
    bl_label = "Done"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return is_editing(context)

    def execute(self, context):
        bpy.ops.object.mode_set(mode='OBJECT')
        _return_to_preview_after_edit(context)
        ws = context.workspace
        if ws and ws.get("studio_profile") == "edit":       # legacy studioEdit tab: return to Studio
            studio = bpy.data.workspaces.get("Studio")
            if studio:
                context.window.workspace = studio
        return {'FINISHED'}


def _edit_bmesh(context):
    import bmesh
    obj = context.edit_object
    if obj is None or obj.type != 'MESH':
        return None, None
    return obj, bmesh.from_edit_mesh(obj.data)


def _median_get(self):
    try:
        obj, bm = _edit_bmesh(bpy.context)
        if bm is None:
            return (0.0, 0.0, 0.0)
        sel = [v.co for v in bm.verts if v.select]
        if not sel:
            return (0.0, 0.0, 0.0)
        from mathutils import Vector
        c = sum(sel, Vector()) / len(sel)
        return tuple(obj.matrix_world @ c)
    except Exception:
        return (0.0, 0.0, 0.0)


def _median_set(self, value):
    import bmesh
    from mathutils import Vector
    obj, bm = _edit_bmesh(bpy.context)
    if bm is None:
        return
    sel = [v for v in bm.verts if v.select]
    if not sel:
        return
    cur = obj.matrix_world @ (sum((v.co for v in sel), Vector()) / len(sel))
    delta_world = Vector(value) - cur
    delta_local = obj.matrix_world.to_3x3().inverted() @ delta_world
    for v in sel:
        v.co += delta_local
    bmesh.update_edit_mesh(obj.data)


def _selection_counts(context):
    obj, bm = _edit_bmesh(context)
    if bm is None:
        return 0, 0, 0
    return (sum(1 for v in bm.verts if v.select), sum(1 for e in bm.edges if e.select),
            sum(1 for f in bm.faces if f.select))


class LUMBERSTUDIO_PT_edit(_StudioPanel, bpy.types.Panel):
    bl_idname = "LUMBERSTUDIO_PT_edit"
    bl_label = "Edit"
    bl_order = -100

    @classmethod
    def poll(cls, context):
        return is_editing(context) and context.edit_object is not None

    def draw(self, context):
        layout = self.layout
        obj = context.edit_object
        ts = context.tool_settings

        row = layout.row()
        row.label(text=obj.name, icon='EDITMODE_HLT')
        row.operator("lumberstudio.edit_done", text="Done", icon='CHECKMARK')

        if obj.type == 'MESH':
            nv, ne, nf = _selection_counts(context)
            col = _section(layout, "Selection")
            col.row(align=True).prop(ts, "mesh_select_mode", text="", expand=True)
            col.label(text=f"{nv} points · {ne} edges · {nf} faces")
            if nv:
                split = col.split(factor=0.24)
                split.label(text="Position")
                r = split.row(align=True)
                for i in range(3):
                    r.prop(context.window_manager, "lumberstudio_median", index=i, text="")
            r = col.row(align=True)
            r.operator("mesh.select_all", text="All").action = 'SELECT'
            r.operator("mesh.select_all", text="None").action = 'DESELECT'
            r.operator("mesh.select_linked", text="Linked")

            col = _section(layout, "Shape")
            grid = col.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
            grid.operator("mesh.subdivide", text="Subdivide", icon='MOD_SUBSURF')
            grid.operator("mesh.merge", text="Merge", icon='AUTOMERGE_OFF').type = 'CENTER'
            grid.operator("mesh.edge_face_add", text="Fill", icon='SNAP_FACE')
            grid.operator("mesh.dissolve_mode", text="Dissolve", icon='X')
            grid.operator("mesh.vertices_smooth", text="Smooth", icon='MOD_SMOOTH')
            grid.operator("mesh.delete", text="Delete", icon='TRASH').type = 'VERT'

            col = _section(layout, "Surface")
            r = col.row(align=True)
            r.operator("mesh.faces_shade_smooth", text="Smooth")
            r.operator("mesh.faces_shade_flat", text="Flat")
            col.operator("mesh.normals_make_consistent", text="Fix Normals").inside = False

        elif obj.type == 'CURVE':
            col = _section(layout, "Point")
            r = col.row(align=True)
            r.operator("curve.handle_type_set", text="Smooth").type = 'AUTOMATIC'
            r.operator("curve.handle_type_set", text="Corner").type = 'VECTOR'
            r.operator("curve.handle_type_set", text="Free").type = 'FREE_ALIGN'
            col = _section(layout, "Path")
            col.operator("curve.cyclic_toggle", text="Open / Close Path")
            col.operator("curve.subdivide", text="Add Points")
            col.operator("curve.delete", text="Delete Points").type = 'VERT'
            col.prop(obj.data, "bevel_depth", text="Thickness")

        v3d = _studio_view3d(context)
        if v3d:
            col = _section(layout, "View")
            col.prop(v3d.shading, "show_xray", text="See Through")


# ---------------------------------------------------------------------------
# Spline / Figma-style single-key shortcuts (Object Mode, general studio only)
# ---------------------------------------------------------------------------

SHORTCUTS = {
    'V': ("tool", "builtin.select_box"),
    'R': ("add", "RECTANGLE"),
    'O': ("add", "ELLIPSE"),
    'T': ("add", "TEXT"),
    'P': ("pen", ""),
    'CTRL G': ("op", "group"),
    'CTRL SHIFT G': ("op", "ungroup"),
}


class LUMBERSTUDIO_OT_shortcut(bpy.types.Operator):
    bl_idname = "lumberstudio.shortcut"
    bl_label = "Studio Shortcut"
    bl_options = {'INTERNAL'}

    key: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        # Outside the general studio the key falls through to Blender's default
        return studio_profile(context) == "general" and context.mode == 'OBJECT'

    def execute(self, context):
        kind, arg = SHORTCUTS.get(self.key, ("", ""))
        if kind == "tool":
            bpy.ops.wm.tool_set_by_id(name=arg)
        elif kind == "add":
            bpy.ops.lumberstudio.add(kind=arg)
        elif kind == "pen":
            bpy.ops.lumberstudio.pen()
        elif kind == "op":
            op = getattr(bpy.ops.lumberstudio, arg)
            if op.poll():
                op()
        return {'FINISHED'}


class LUMBERSTUDIO_OT_pen(bpy.types.Operator):
    """Draw a freeform path, like Spline's pen tool"""
    bl_idname = "lumberstudio.pen"
    bl_label = "Pen"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_CURVE'}

    def execute(self, context):
        if context.mode == 'OBJECT':
            bpy.ops.curve.primitive_bezier_curve_add(enter_editmode=True, location=_view_center(context))
            bpy.ops.curve.select_all(action='SELECT')
            bpy.ops.curve.delete(type='VERT')
            context.active_object.name = "Path"
        bpy.ops.wm.tool_set_by_id(name="builtin.draw")
        return {'FINISHED'}


class LUMBERSTUDIO_OT_add_image(bpy.types.Operator):
    """Add an image as a flat plane"""
    bl_idname = "lumberstudio.add_image"
    bl_label = "Add Image"

    def invoke(self, context, event):
        if hasattr(bpy.ops.image, "import_as_mesh_planes"):
            return bpy.ops.image.import_as_mesh_planes('INVOKE_DEFAULT')
        return bpy.ops.object.empty_image_add('INVOKE_DEFAULT')

    def execute(self, context):
        return self.invoke(context, None)


class LUMBERSTUDIO_OT_preview_toggle(bpy.types.Operator):
    """Preview the scene with materials and no editing overlays (press again to return)"""
    bl_idname = "lumberstudio.preview_toggle"
    bl_label = "Preview"

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.type == 'VIEW_3D'

    def execute(self, context):
        space = context.space_data
        previewing = space.shading.type == 'MATERIAL'
        _apply_preview(space, not previewing, context.scene.lumberstudio_preview_floor)
        return {'FINISHED'}


# Preview with floor: overlays stay on so the grid can draw, but every other
# editing overlay is switched off. Their previous values are kept on the
# screen, so they come back when you leave Preview, even after reopening the file.
_PREVIEW_HIDE = ("show_outline_selected", "show_object_origins", "show_object_origins_all",
                 "show_cursor", "show_text", "show_extras", "show_relationship_lines",
                 "show_stats", "show_bones", "show_wireframes", "show_annotation",
                 "show_axis_x", "show_axis_y", "show_axis_z")
_STASH = "studio_preview_stash"


def _restore_overlays(space):
    scr, ov = space.id_data, space.overlay
    saved = scr.get(_STASH)
    if saved:
        for k, v in saved.items():
            if hasattr(ov, k):
                setattr(ov, k, bool(v))
        del scr[_STASH]


# ---------------------------------------------------------------------------
# Preview floor: a real ground plane that catches shadows from a soft sun,
# fading out toward the horizon. Both live in a "Studio Preview" collection
# that only exists in the view while previewing. Tagged so Lumber never treats
# them as obstacles or exports them.
# ---------------------------------------------------------------------------

_FLOOR_COL, _FLOOR_OB, _SUN_OB, _FLOOR_MAT = "Studio Preview", "Preview Floor", "Preview Sun", "Preview Floor"
_STAGE_WORLD = "Preview Stage"
_SUN_STRENGTH, _SUN_TILT = 2.5, math.radians(35)
# Light a white floor gets from the sun, on top of the stage colour itself. The
# floor's shade is set so that, where the sun reaches it, it renders exactly the
# stage colour: the floor vanishes into the backdrop and only its shadows show.
_SUN_ON_FLOOR = _SUN_STRENGTH * math.cos(_SUN_TILT) / math.pi


def _tag_helper(ob):
    ob["studio_helper"] = True
    ob.hide_select = True
    lum = getattr(ob, "lumber", None)
    if lum is not None and hasattr(lum, "owner"):
        lum.owner = "__studio_preview"


def _floor_material():
    mat = bpy.data.materials.get(_FLOOR_MAT)
    if mat is None:
        mat = bpy.data.materials.new(_FLOOR_MAT)
    mat.use_nodes = True
    nt = mat.node_tree
    diff = nt.nodes.get("Stage Diffuse")
    if diff is None:
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
        diff.name = "Stage Diffuse"
        nt.links.new(diff.outputs[0], out.inputs["Surface"])
    return mat


def _stage_world():
    w = bpy.data.worlds.get(_STAGE_WORLD)
    if w is None:
        w = bpy.data.worlds.new(_STAGE_WORLD)
        w.use_fake_user = False
    w.use_nodes = True
    return w


def _set_stage_color(color):
    w = _stage_world()
    bg = next((n for n in w.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bg is not None:
        bg.inputs["Color"].default_value = (*color, 1.0)
        bg.inputs["Strength"].default_value = 1.0
    w.color = color
    diff = _floor_material().node_tree.nodes["Stage Diffuse"]
    sun = _sun_on_floor()
    diff.inputs["Color"].default_value = (*[c / (c + s) if c + s > 0 else 0.0 for c, s in zip(color, sun)], 1.0)


def _sun_on_floor():
    """Light the sun puts on the floor, per colour channel (follows the sun's height, brightness, colour)."""
    sun = _preview_sun()
    if sun is None:
        return (_SUN_ON_FLOOR,) * 3
    e = max(sun.data.energy * math.cos(sun.rotation_euler.x), 0.0) / math.pi
    return tuple(e * c for c in sun.data.color)


def _preview_sun():
    ob = bpy.data.objects.get(_SUN_OB)
    return ob if ob is not None and ob.type == 'LIGHT' else None


def _is_preview_sun(ob):
    return ob is not None and ob.name == _SUN_OB and ob.type == 'LIGHT' and bool(ob.get("studio_helper"))


def _refresh_stage(scene):
    """Keep the floor blending into the backdrop after the sun changes."""
    if bpy.data.materials.get(_FLOOR_MAT) is not None:
        _set_stage_color(tuple(scene.lumberstudio_stage_color))


# Sun controls, in plain terms: how high it is, which way it shines from, colour,
# brightness. They read and write the Preview sun directly.

def _sun_height_get(self):
    sun = _preview_sun()
    return math.pi / 2 - (sun.rotation_euler.x if sun else _SUN_TILT)


def _sun_height_set(self, value):
    sun = _preview_sun()
    if sun:
        sun.rotation_euler.x = math.pi / 2 - value
        _refresh_stage(self)


def _sun_direction_get(self):
    sun = _preview_sun()
    return (sun.rotation_euler.z if sun else 0.0) % (2 * math.pi)


def _sun_direction_set(self, value):
    sun = _preview_sun()
    if sun:
        sun.rotation_euler.z = value


def _sun_brightness_get(self):
    sun = _preview_sun()
    return sun.data.energy if sun else _SUN_STRENGTH


def _sun_brightness_set(self, value):
    sun = _preview_sun()
    if sun:
        sun.data.energy = value
        _refresh_stage(self)


def _sun_color_get(self):
    sun = _preview_sun()
    return tuple(sun.data.color) if sun else (1.0, 1.0, 1.0)


def _sun_color_set(self, value):
    sun = _preview_sun()
    if sun:
        sun.data.color = value
        _refresh_stage(self)


def _draw_sun_controls(layout, scene, sun, heading=True):
    col = _section(layout, "Sun") if heading else layout.column()
    col.prop(scene, "lumberstudio_sun_height", text="Height")
    col.prop(scene, "lumberstudio_sun_direction", text="Direction")
    split = col.split(factor=0.3)
    split.label(text="Color")
    split.prop(scene, "lumberstudio_sun_color", text="")
    col.prop(scene, "lumberstudio_sun_brightness", text="Brightness", slider=True)
    col.prop(sun.data, "angle", text="Shadow Softness")


def _preview_rig(scene):
    col = bpy.data.collections.get(_FLOOR_COL)
    if col is None:
        col = bpy.data.collections.new(_FLOOR_COL)
        col.hide_render = True
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    floor = bpy.data.objects.get(_FLOOR_OB)
    if floor is None:
        me = bpy.data.meshes.new(_FLOOR_OB)
        me.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
        floor = bpy.data.objects.new(_FLOOR_OB, me)
        col.objects.link(floor)
        _tag_helper(floor)
    if not floor.data.materials:
        floor.data.materials.append(_floor_material())
    if hasattr(floor, "visible_shadow"):
        floor.visible_shadow = False         # a huge plane self-shadows; it only needs to receive
    sun = bpy.data.objects.get(_SUN_OB)
    if sun is None:
        sun = bpy.data.objects.new(_SUN_OB, bpy.data.lights.new(_SUN_OB, 'SUN'))
        col.objects.link(sun)
        _tag_helper(sun)
        # Starting values only: after this the sun is the student's to adjust
        sun.data.energy = _SUN_STRENGTH
        sun.data.angle = math.radians(12)    # soft-edged shadow
        sun.rotation_euler = (_SUN_TILT, 0.0, math.radians(30))
    sun.hide_select = False                  # click it in Layers to adjust it
    return col, floor, sun


def _fit_floor(scene, floor):
    """Sit the floor under the lowest point of everything visible."""
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for ob in scene.objects:
        if ob.get("studio_helper") or ob.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'} \
                or not ob.visible_get():
            continue
        for c in ob.bound_box:
            w = ob.matrix_world @ mathutils.Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], w[i]); hi[i] = max(hi[i], w[i])
    if lo[0] == math.inf:
        lo, hi = [0, 0, 0], [1, 1, 1]
    size = max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], 0.1)
    loc = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])
    # Only write real changes: this also runs after every edit while previewing
    if abs(floor.location.z - loc[2]) > 1e-6 or abs(floor.scale.x - size * 200) > 1e-3 * size:
        floor.location = loc
        floor.scale = (size * 200,) * 3      # reaches the horizon


def _show_preview_floor(context, show):
    scene = context.scene
    col = bpy.data.collections.get(_FLOOR_COL)
    if show:
        col, floor, _sun = _preview_rig(scene)
        _fit_floor(scene, floor)
        if scene.world is None or scene.world.name != _STAGE_WORLD:
            scene["studio_prev_world"] = scene.world.name if scene.world else ""
            scene.world = _stage_world()
        _set_stage_color(tuple(scene.lumberstudio_stage_color))
    elif "studio_prev_world" in scene:
        scene.world = bpy.data.worlds.get(scene["studio_prev_world"])
        del scene["studio_prev_world"]
    if col is None:
        return
    lc = _find_layer_collection(context.view_layer.layer_collection, col.name)
    if lc is not None:
        lc.exclude = not show
    col.hide_viewport = not show


def _find_layer_collection(lc, name):
    if lc.name == name:
        return lc
    for ch in lc.children:
        r = _find_layer_collection(ch, name)
        if r:
            return r
    return None


def _apply_preview(space, previewing, floor):
    ctx = bpy.context
    ov, sh = space.overlay, space.shading
    _restore_overlays(space)                 # clean up the earlier grid-in-preview state
    if not previewing:
        ov.show_overlays = True
        sh.type = 'SOLID'
        sh.use_scene_world = sh.use_scene_lights = False
        _show_preview_floor(ctx, False)
        return
    sh.type = 'MATERIAL'
    ov.show_overlays = False
    sh.use_scene_world = sh.use_scene_lights = bool(floor)   # stage backdrop + sun shadow
    _show_preview_floor(ctx, bool(floor))


def _on_preview_floor(scene, context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                sp = area.spaces.active
                if sp.shading.type == 'MATERIAL' and _is_studio_ws(win.workspace):
                    _apply_preview(sp, True, scene.lumberstudio_preview_floor)
                    area.tag_redraw()


_orig_topbar = {}


def _topbar_draw_left(self, context):
    if not is_studio(context):
        return _orig_topbar["draw_left"](self, context)
    layout = self.layout
    layout.menu("LUMBERSTUDIO_MT_main", text="", icon='COLLAPSEMENU')
    layout.separator(factor=1.5)
    name = bpy.path.basename(bpy.data.filepath) or "Untitled"
    if name.endswith(".blend"):
        name = name[:-6]
    if bpy.data.is_dirty:
        name += " •"
    layout.label(text=name)
    if is_general(context):
        layout.separator(factor=1.5)
        row = layout.row(align=True)
        row.operator("ed.undo", text="", icon='LOOP_BACK')
        row.operator("ed.redo", text="", icon='LOOP_FORWARDS')


def _topbar_draw_right(self, context):
    if not is_studio(context):
        return _orig_topbar["draw_right"](self, context)
    if is_general(context):  # Spline keeps Export / Play at the top right
        row = self.layout.row(align=True)
        row.operator("lumberstudio.preview_toggle", text="", icon='PLAY')
        row.separator()
        row.menu("TOPBAR_MT_file_export", text="Export", icon='EXPORT')


def _patch_topbar():
    cls = bpy.types.TOPBAR_HT_upper_bar
    _orig_topbar["draw_left"] = cls.draw_left
    _orig_topbar["draw_right"] = cls.draw_right
    cls.draw_left = _topbar_draw_left
    cls.draw_right = _topbar_draw_right


def _unpatch_topbar():
    cls = getattr(bpy.types, "TOPBAR_HT_upper_bar", None)
    if cls and _orig_topbar:
        cls.draw_left = _orig_topbar["draw_left"]
        cls.draw_right = _orig_topbar["draw_right"]
    _orig_topbar.clear()


# ---------------------------------------------------------------------------
# Sidebar: hide Tool / View / Animation tabs in the studio workspace.
# Blender decides at registration whether a panel has a poll(), so the
# affected panels are re-registered with a wrapped poll and restored later.
# ---------------------------------------------------------------------------

_patched_panels = []  # (cls, had_own_poll, original_poll_descriptor)


def _all_subclasses(base):
    out, stack = [], list(base.__subclasses__())
    while stack:
        c = stack.pop()
        out.append(c)
        stack.extend(c.__subclasses__())
    return out


def _sidebar_panels_to_hide():
    panels = [c for c in _all_subclasses(bpy.types.Panel)
              if getattr(c, "bl_space_type", "") == 'VIEW_3D'
              and getattr(c, "bl_region_type", "") == 'UI'
              and c.is_registered
              and not c.__module__.startswith("bl_ext.user_default.lumber")]
    by_id = {getattr(c, "bl_idname", c.__name__): c for c in panels}
    hidden = {}
    for c in panels:
        if getattr(c, "bl_category", "") in HIDDEN_SIDEBAR_TABS and not getattr(c, "bl_parent_id", ""):
            hidden[getattr(c, "bl_idname", c.__name__)] = c
    changed = True
    while changed:  # pull in children of hidden parents
        changed = False
        for pid, c in by_id.items():
            if pid not in hidden and getattr(c, "bl_parent_id", "") in hidden:
                hidden[pid] = c
                changed = True

    def depth(c):
        d, p = 0, getattr(c, "bl_parent_id", "")
        while p and p in by_id:
            d, p = d + 1, getattr(by_id[p], "bl_parent_id", "")
        return d
    return sorted(hidden.values(), key=depth)  # parents first


def _object_panels_to_hide():
    """Blender's Object-tab panels, replaced by the Design panel in the general studio."""
    panels = [c for c in _all_subclasses(bpy.types.Panel)
              if getattr(c, "bl_space_type", "") == 'PROPERTIES'
              and getattr(c, "bl_context", "") == "object"
              and c.is_registered
              and not c.__module__.startswith("bl_ext.user_default.lumber")]
    by_id = {getattr(c, "bl_idname", c.__name__): c for c in panels}

    def depth(c):
        d, p = 0, getattr(c, "bl_parent_id", "")
        while p and p in by_id:
            d, p = d + 1, getattr(by_id[p], "bl_parent_id", "")
        return d
    return sorted(panels, key=depth)


def _hide_in_any_studio(context):
    return is_studio(context)


def _hide_in_general_studio(context):
    return is_general(context)


def _inherited_poll(c):
    for k in c.__mro__:
        if "poll" in k.__dict__:
            return k.__dict__["poll"]
    return None


def _make_poll(orig, hide_fn):
    def poll(cls, context):
        if hide_fn(context):
            return False
        if orig is None:
            return True
        fn = getattr(orig, "__func__", None)
        return fn(cls, context) if fn else orig(context)
    return classmethod(poll)


def _reregister(classes):
    for c in reversed(classes):  # children first
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    for c in classes:  # parents first
        try:
            bpy.utils.register_class(c)
        except Exception as e:
            print(f"Lumber Studio: could not re-register {c.__name__}: {e}")


def _patch_sidebar():
    for classes, hide_fn in ((_sidebar_panels_to_hide(), _hide_in_any_studio),
                             (_object_panels_to_hide(), _hide_in_general_studio)):
        for c in classes:
            own = "poll" in c.__dict__
            orig = c.__dict__.get("poll")
            _patched_panels.append((c, own, orig))
            c.poll = _make_poll(_inherited_poll(c), hide_fn)
        _reregister(classes)


def _unpatch_sidebar():
    classes = []
    for c, own, orig in _patched_panels:
        if own:
            c.poll = orig
        else:
            try:
                del c.poll
            except AttributeError:
                pass
        classes.append(c)
    _patched_panels.clear()
    _reregister(classes)


# ---------------------------------------------------------------------------
# Shift+Right-click: swallow it in the studio workspace so the 3D cursor stays put
# ---------------------------------------------------------------------------

class LUMBERSTUDIO_OT_block_cursor(bpy.types.Operator):
    bl_idname = "lumberstudio.block_cursor"
    bl_label = "Block 3D Cursor"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return is_studio(context)  # outside the studio the default keymap runs

    def invoke(self, context, event):
        return {'FINISHED'}


_keymaps = []


def _register_keymap():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    kmi = km.keymap_items.new("lumberstudio.block_cursor", 'RIGHTMOUSE', 'PRESS', shift=True)
    _keymaps.append((km, kmi))
    km = kc.keymaps.new(name="Object Mode", space_type='EMPTY')
    kmi = km.keymap_items.new("lumberstudio.edit_enter", 'LEFTMOUSE', 'DOUBLE_CLICK')
    _keymaps.append((km, kmi))
    for name in ("Mesh", "Curve"):
        ekm = kc.keymaps.new(name=name, space_type='EMPTY')
        kmi = ekm.keymap_items.new("lumberstudio.edit_done", 'ESC', 'PRESS')
        _keymaps.append((ekm, kmi))
    for key in SHORTCUTS:
        parts = key.split()
        kmi = km.keymap_items.new("lumberstudio.shortcut", parts[-1], 'PRESS',
                                  ctrl="CTRL" in parts, shift="SHIFT" in parts)
        kmi.properties.key = key
        _keymaps.append((km, kmi))


def _unregister_keymap():
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _keymaps.clear()


# ---------------------------------------------------------------------------
# Always-present tabs: every file that's opened or created gets the Lumber and
# Studio workspaces, appended from the template that ships with the extension.
# ---------------------------------------------------------------------------

import os
from bpy.app.handlers import persistent

TEMPLATE = os.path.join(os.path.dirname(__file__), "studio_workspaces.blend")
STUDIO_WORKSPACES = ("Lumber", "Studio")       # the tabs every file gets
LEGACY_WORKSPACES = ("studioEdit",)            # older tabs still recognised as studio tabs


# The old studioEdit tab is no longer added to files. Files that already have it
# keep it (deleting workspaces from a script isn't safe in Blender: removing the
# data directly leaves broken screens behind), but Studio's menu no longer lists it.


def _ensure_workspaces():
    wm = bpy.context.window_manager
    if wm is None or not wm.windows:
        return 0.5                      # UI not ready yet: try again shortly
    if not os.path.exists(TEMPLATE):
        return None
    missing = [n for n in STUDIO_WORKSPACES if n not in bpy.data.workspaces]
    if not missing:
        _apply_owner_filter()
        return None
    win = wm.windows[0]
    prev = win.workspace.name
    for name in missing:
        try:
            with bpy.context.temp_override(window=win, screen=win.screen):
                bpy.ops.workspace.append_activate(idname=name, filepath=TEMPLATE)
        except Exception as e:
            print(f"Lumber Studio: could not add the {name} workspace: {e}")

    def _settle():                      # appending switches tabs; go back to where you were
        ws = bpy.data.workspaces.get(prev)
        if ws:
            win.workspace = ws
        _apply_owner_filter()
        return None
    bpy.app.timers.register(_settle, first_interval=0.05)
    return None


# ---------------------------------------------------------------------------
# Add-on filter: in Studio, only the Lumber extensions draw UI. BlenderKit's
# search bar, tabs and panels (and any other add-on's) are hidden there and
# still show everywhere else. Uses Blender's own per-workspace add-on filter.
# ---------------------------------------------------------------------------

def _studio_owner_ids():
    """Module names of the Lumber extensions that are enabled."""
    mine = __package__ or __name__
    prefix = mine.rsplit(".", 1)[0] + "." if "." in mine else ""
    names = {mine}
    for addon in bpy.context.preferences.addons:
        mod = addon.module
        if mod.startswith(prefix) and mod.rsplit(".", 1)[-1].startswith("lumber"):
            names.add(mod)
    return names


def _apply_owner_filter():
    for ws in bpy.data.workspaces:
        if ws.get("studio_profile") not in ("general", "edit"):
            continue
        try:
            have = {o.name for o in ws.owner_ids}
            for name in sorted(_studio_owner_ids() - have):
                ws.owner_ids.new(name)
            ws.use_filter_by_owner = True
        except Exception as e:
            print(f"Lumber Studio: could not set the add-on filter on {ws.name}: {e}")


def _clear_owner_filter():
    """Unregistering: give Studio back every add-on's UI."""
    for ws in bpy.data.workspaces:
        if ws.get("studio_profile") in ("general", "edit"):
            try:
                ws.use_filter_by_owner = False
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Orbit navigator: Blender's axis ball (drag to orbit, click an axis to snap
# to the X / Y / Z view) is kept on in studio tabs. The zoom / pan / camera
# buttons under it are a global preference, so the extension never touches it:
# the Studio application template hides them while it's active and puts your
# own setting back when you leave.
# ---------------------------------------------------------------------------

_nav_owner = object()


def _is_studio_ws(ws):
    return ws is not None and (ws.name in STUDIO_WORKSPACES or ws.name in LEGACY_WORKSPACES
                               or ws.get("studio_profile") or ws.get("lumber_studio"))


def _enable_orbit_ball():
    for ws in bpy.data.workspaces:
        if not _is_studio_ws(ws):
            continue
        general = ws.get("studio_profile") in ("general", "edit")
        for scr in ws.screens:
            for a in scr.areas:
                if a.type == 'VIEW_3D':
                    sp = a.spaces.active
                    # Only write what differs: this runs on every tab switch
                    if not sp.show_gizmo:
                        sp.show_gizmo = True
                    if not sp.show_gizmo_navigate:
                        sp.show_gizmo_navigate = True
                    if general:
                        # The right panel (Properties) already shows Scene / Design / Edit;
                        # the 3D sidebar only repeated it as a strip of Tool / Item tabs.
                        if sp.show_region_ui:
                            sp.show_region_ui = False
                        # Blender's select-mode and tool-option strip; snapping comes back
                        # here as Studio's own controls in a later phase.
                        if sp.show_region_tool_header:
                            sp.show_region_tool_header = False


def _sync_nav(*_args):
    win = bpy.context.window or (bpy.context.window_manager.windows[0]
                                 if bpy.context.window_manager and bpy.context.window_manager.windows else None)
    if win is None:
        return
    if _is_studio_ws(win.workspace):
        _enable_orbit_ball()


def _subscribe_nav():
    bpy.msgbus.clear_by_owner(_nav_owner)
    bpy.msgbus.subscribe_rna(key=(bpy.types.Window, "workspace"), owner=_nav_owner,
                             args=(), notify=_sync_nav)


def _nav_startup():
    if not bpy.context.window_manager or not bpy.context.window_manager.windows:
        return 0.5
    _subscribe_nav()
    _sync_nav()
    return None


@persistent
def _on_depsgraph_update(scene, depsgraph):
    """While previewing, keep the floor under the lowest object as things move or change size."""
    floor = bpy.data.objects.get(_FLOOR_OB)
    col = bpy.data.collections.get(_FLOOR_COL)
    if floor is None or col is None or col.hide_viewport:
        return
    for u in depsgraph.updates:
        ob = u.id
        if isinstance(ob, bpy.types.Object) and not ob.get("studio_helper") \
                and (u.is_updated_transform or u.is_updated_geometry):
            _fit_floor(scene, floor)
            return


@persistent
def _on_load_post(*_args):
    bpy.app.timers.register(_ensure_workspaces, first_interval=0.1)
    bpy.app.timers.register(_nav_startup, first_interval=0.3)   # msgbus is cleared on file load
    bpy.app.timers.register(_new_file_setup, first_interval=0.6)


# ---------------------------------------------------------------------------

classes = (
    LUMBERSTUDIO_OT_button,
    LUMBERSTUDIO_OT_button_undo,
    LUMBERSTUDIO_GGT_toolbar,
    LUMBERSTUDIO_OT_set_workspace,
    LUMBERSTUDIO_MT_workspaces,
    LUMBERSTUDIO_MT_main,
    LUMBERSTUDIO_OT_add,
    LUMBERSTUDIO_OT_plate,
    LUMBERSTUDIO_OT_print_setup,
    LUMBERSTUDIO_MT_add_shape,
    LUMBERSTUDIO_MT_add_object,
    LUMBERSTUDIO_PT_add_shape,
    LUMBERSTUDIO_PT_add_object,
    LUMBERSTUDIO_OT_add_material,
    LUMBERSTUDIO_OT_shape_mod,
    LUMBERSTUDIO_OT_align,
    LUMBERSTUDIO_OT_select_none,
    LUMBERSTUDIO_PT_scene,
    LUMBERSTUDIO_PT_multi,
    LUMBERSTUDIO_PT_design,
    LUMBERSTUDIO_OT_edit_enter,
    LUMBERSTUDIO_OT_edit_done,
    LUMBERSTUDIO_PT_edit,
    LUMBERSTUDIO_OT_shortcut,
    LUMBERSTUDIO_OT_group,
    LUMBERSTUDIO_OT_ungroup,
    LUMBERSTUDIO_OT_pen,
    LUMBERSTUDIO_OT_add_image,
    LUMBERSTUDIO_OT_preview_toggle,
    LUMBERSTUDIO_OT_block_cursor,
)


def register():
    global _draw_handle
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.WindowManager.lumberstudio_median = bpy.props.FloatVectorProperty(
        name="Selection Position", subtype='TRANSLATION', unit='LENGTH', size=3,
        get=_median_get, set=_median_set)
    bpy.types.WindowManager.lumberstudio_size_mm = bpy.props.FloatVectorProperty(
        name="Size (mm)", size=3, precision=2, step=100, min=0.0,
        get=_size_mm_get, set=_size_mm_set, description="Width, depth and height in millimetres")
    bpy.types.Scene.lumberstudio_lock_ratio = bpy.props.BoolProperty(
        name="Lock Proportions", default=False,
        description="Changing one side scales the others to keep the shape")
    bpy.types.Scene.lumberstudio_print_sizes = bpy.props.BoolProperty(
        name="Print-Size New Objects", default=True,
        description="New shapes get a real size in millimetres and are placed on the build plate")
    bpy.types.Scene.lumberstudio_new_size = bpy.props.FloatProperty(
        name="New Object Size", default=20.0, min=0.5, max=1000.0, precision=1,
        description="Longest side of newly added shapes, in millimetres")
    bpy.types.Scene.lumberstudio_preview_floor = bpy.props.BoolProperty(
        name="Floor in Preview", default=False, update=_on_preview_floor,
        description="Show a floor that catches shadows in Preview")
    bpy.types.Scene.lumberstudio_sun_height = bpy.props.FloatProperty(
        name="Sun Height", subtype='ANGLE', min=math.radians(5), max=math.radians(90),
        get=_sun_height_get, set=_sun_height_set,
        description="How high the sun is: low makes long shadows, overhead makes short ones")
    bpy.types.Scene.lumberstudio_sun_direction = bpy.props.FloatProperty(
        name="Sun Direction", subtype='ANGLE', min=0.0, max=2 * math.pi,
        get=_sun_direction_get, set=_sun_direction_set,
        description="Which side the sun shines from, so you can turn the shadow toward the view")
    bpy.types.Scene.lumberstudio_sun_brightness = bpy.props.FloatProperty(
        name="Sun Brightness", min=0.0, soft_max=10.0, precision=2,
        get=_sun_brightness_get, set=_sun_brightness_set, description="How strong the sunlight is")
    bpy.types.Scene.lumberstudio_sun_color = bpy.props.FloatVectorProperty(
        name="Sun Color", subtype='COLOR', size=3, min=0.0, max=1.0,
        get=_sun_color_get, set=_sun_color_set, description="Colour of the sunlight")
    bpy.types.Scene.lumberstudio_stage_color = bpy.props.FloatVectorProperty(
        name="Stage Color", subtype='COLOR', size=3, min=0.0, max=1.0,
        default=(0.80, 0.80, 0.82), update=_on_preview_floor,
        description="Backdrop and floor colour in Preview")
    _draw_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_pill, (), 'WINDOW', 'POST_VIEW')
    _patch_topbar()
    _patch_outliner()
    _patch_sidebar()
    _register_keymap()
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    bpy.app.timers.register(_ensure_workspaces, first_interval=0.1)   # the file open right now
    bpy.app.timers.register(_nav_startup, first_interval=0.3)
    bpy.app.timers.register(_new_file_setup, first_interval=0.6)


def unregister():
    global _draw_handle
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if bpy.app.timers.is_registered(_ensure_workspaces):
        bpy.app.timers.unregister(_ensure_workspaces)
    if bpy.app.timers.is_registered(_nav_startup):
        bpy.app.timers.unregister(_nav_startup)
    if bpy.app.timers.is_registered(_new_file_setup):
        bpy.app.timers.unregister(_new_file_setup)
    bpy.msgbus.clear_by_owner(_nav_owner)
    _unregister_keymap()
    _clear_owner_filter()
    _unpatch_sidebar()
    _unpatch_outliner()
    _unpatch_topbar()
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None
    for owner, name in ((bpy.types.WindowManager, "lumberstudio_size_mm"),
                        (bpy.types.Scene, "lumberstudio_lock_ratio"),
                        (bpy.types.Scene, "lumberstudio_print_sizes"),
                        (bpy.types.Scene, "lumberstudio_new_size")):
        if hasattr(owner, name):
            delattr(owner, name)
    if hasattr(bpy.types.Scene, "lumberstudio_preview_floor"):
        del bpy.types.Scene.lumberstudio_preview_floor
    for name in ("lumberstudio_sun_height", "lumberstudio_sun_direction",
                 "lumberstudio_sun_brightness", "lumberstudio_sun_color"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    if hasattr(bpy.types.Scene, "lumberstudio_stage_color"):
        del bpy.types.Scene.lumberstudio_stage_color
    if hasattr(bpy.types.WindowManager, "lumberstudio_median"):
        del bpy.types.WindowManager.lumberstudio_median
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
