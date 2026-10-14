"""Studio: a beginner-friendly Blender for designing 3D prints.

This is a Blender *application template*. Choose it from File > New > Studio
(or the splash screen) to switch into Studio; choose File > New > General to go
back to stock Blender. Blender keeps Studio's theme, add-ons and keymaps in
their own preferences file, so nothing here changes your normal setup.

A few settings are global in Blender, and a template can't keep its own copy of
them (interface scale, the viewport navigation buttons). Studio sets those when
it starts and puts your own values back when you leave.
"""

import bpy
import addon_utils

# Extensions that make up Studio. Each is turned on if it is installed.
STUDIO_EXTENSIONS = ("lumber_studio", "lumber_supports")
# Tools for whoever maintains Studio (e.g. the Blender MCP connection).
# Kept on in Studio when they're installed, so switching templates doesn't cut them off.
CARRY_OVER_EXTENSIONS = ("mcp",)

# Global settings Studio uses while it's active: {(section, property): value}.
STUDIO_SETTINGS = {
    ("view", "ui_scale"): 1.25,            # bigger type and buttons for beginners
    ("view", "show_navigate_ui"): False,   # just the orbit ball, no zoom/pan/camera buttons
}

_saved = {}


def _find_module(short_name):
    """The installed module for an extension or add-on, e.g. 'bl_ext.user_default.lumber_studio'."""
    for mod in addon_utils.modules(refresh=False):
        name = mod.__name__
        if name == short_name or name.endswith("." + short_name):
            return name
    return None


def _enable_extensions():
    enabled = {a.module for a in bpy.context.preferences.addons}
    for short in STUDIO_EXTENSIONS + CARRY_OVER_EXTENSIONS:
        name = _find_module(short)
        if name is None:
            if short in STUDIO_EXTENSIONS:
                print(f"Studio: the {short} extension isn't installed")
            continue
        if name not in enabled:
            try:
                addon_utils.enable(name, default_set=True, persistent=True)
            except Exception as e:
                print(f"Studio: could not turn on {name}: {e}")


def _apply_settings():
    prefs = bpy.context.preferences
    was_dirty = prefs.is_dirty
    for (section, prop), value in STUDIO_SETTINGS.items():
        owner = getattr(prefs, section)
        if (section, prop) not in _saved:
            _saved[(section, prop)] = getattr(owner, prop)
        setattr(owner, prop, value)
    prefs.is_dirty = was_dirty      # Studio's values never become your saved preferences


def _restore_settings():
    prefs = bpy.context.preferences
    was_dirty = prefs.is_dirty
    for (section, prop), value in _saved.items():
        try:
            setattr(getattr(prefs, section), prop, value)
        except Exception:
            pass
    _saved.clear()
    prefs.is_dirty = was_dirty


@bpy.app.handlers.persistent
def _on_load_post(*_args):
    # Opening another Studio file reloads Studio's preferences without running
    # register() again; make sure Studio's extensions are still on.
    if bpy.context.preferences.app_template == "studio":
        _enable_extensions()


def register():
    _apply_settings()
    _enable_extensions()
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    _restore_settings()
