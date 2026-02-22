import flet as ft
import json
import os
import re
import base64
import copy
from datetime import datetime, timedelta
from pathlib import Path
import threading

# ─── Core logic ───
import Trigger_LOT_SLT as tri

# ─── Optional imports ───
try:
    import obsplan as obs
    import matplotlib
    matplotlib.use('Agg')
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    HAS_SLACK = True
except ImportError:
    HAS_SLACK = False

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════
FILTERS = ["up", "gp", "rp", "ip", "zp", "U", "B", "V", "R", "I"]
PRIORITIES = ["Normal", "High", "Urgent"]
TELESCOPES = ["SLT", "LOT"]
DEFAULT_LOT_PROGRAMS = ["R01"]
APP_TITLE = "Kinder Trigger"
SCRIPT_FILE = "script.txt"  # basename only; full path resolved via _get_data_path()

# Use ~/.kinder_trigger/ for config so packaged app finds it reliably
_CONFIG_DIR = os.path.join(str(Path.home()), ".kinder_trigger")
os.makedirs(_CONFIG_DIR, exist_ok=True)
ENV_FILE = os.path.join(_CONFIG_DIR, ".env")
_PROGRAMS_FILE = os.path.join(_CONFIG_DIR, "programs.json")


def _load_lot_programs():
    """Load LOT programs list from persistent config."""
    if os.path.exists(_PROGRAMS_FILE):
        try:
            with open(_PROGRAMS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    return list(DEFAULT_LOT_PROGRAMS)


def _save_lot_programs(programs):
    """Save LOT programs list to persistent config."""
    with open(_PROGRAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(programs, f, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Coordinate / name helpers
# ═══════════════════════════════════════════════════════════════════════════════
def _is_decimal_coord(s):
    """Return True if s looks like a single decimal number (e.g. '180.123' or '-23.5')."""
    s = s.strip()
    try:
        float(s)
        # reject if already contains ':' (sexagesimal)
        return ':' not in s
    except ValueError:
        return False


def _deg_to_hms(deg):
    """Convert RA in decimal degrees to hh:mm:ss.ss string."""
    deg = float(deg) % 360
    h = deg / 15.0
    hh = int(h)
    m = (h - hh) * 60
    mm = int(m)
    ss = (m - mm) * 60
    return f"{hh:02d}:{mm:02d}:{ss:05.2f}"


def _deg_to_dms(deg):
    """Convert Dec in decimal degrees to +/-dd:mm:ss.ss string."""
    deg = float(deg)
    sign = '+' if deg >= 0 else '-'
    deg = abs(deg)
    dd = int(deg)
    m = (deg - dd) * 60
    mm = int(m)
    ss = (m - mm) * 60
    return f"{sign}{dd:02d}:{mm:02d}:{ss:05.2f}"


def _ensure_hms(ra_str):
    """If RA is decimal degrees, convert to hh:mm:ss.ss; otherwise keep as-is."""
    if _is_decimal_coord(ra_str):
        return _deg_to_hms(ra_str)
    return ra_str.strip()


def _ensure_dms(dec_str):
    """If Dec is decimal degrees, convert to ±dd:mm:ss.ss; otherwise keep as-is."""
    if _is_decimal_coord(dec_str):
        return _deg_to_dms(dec_str)
    return dec_str.strip()


def _sanitize_name(name):
    """Keep only letters, digits, and hyphens for ACP script target names."""
    return re.sub(r'[^A-Za-z0-9\-]', '', name)


# ═══════════════════════════════════════════════════════════════════════════════
# .env helpers
# ═══════════════════════════════════════════════════════════════════════════════
def _default_data_path():
    """Return a sensible default writable directory for data files."""
    docs = os.path.join(str(Path.home()), "Documents", "Kinder_Trigger")
    os.makedirs(docs, exist_ok=True)
    return docs


def _ensure_env_file():
    """Create .env with template if it doesn't exist, then load it."""
    if not os.path.exists(ENV_FILE):
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("# Kinder Trigger - Environment Variables\n")
            f.write(f"DATA_PATH={_default_data_path()}\n")
            f.write("SLACK_BOT_TOKEN=\n")
            f.write("SLACK_CHANNEL_ID_CONTROL_ROOM=\n")
    # Load
    try:
        import dotenv
        dotenv.load_dotenv(ENV_FILE, override=True)
    except ImportError:
        # Manual parse
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()


def _save_env_vars(env_dict):
    """Write multiple key=value pairs back to .env file."""
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    keys_written = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        matched = False
        for k, v in env_dict.items():
            if stripped.startswith(f"{k}="):
                new_lines.append(f"{k}={v}\n")
                keys_written.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line if line.endswith("\n") else line + "\n")

    for k, v in env_dict.items():
        if k not in keys_written:
            new_lines.append(f"{k}={v}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    for k, v in env_dict.items():
        os.environ[k] = v


def _save_env(token, channel):
    """Write token and channel back to .env file."""
    _save_env_vars({"SLACK_BOT_TOKEN": token, "SLACK_CHANNEL_ID_CONTROL_ROOM": channel})


def _get_data_path():
    """Return DATA_PATH from env, fallback to ~/Documents/Kinder_Trigger."""
    p = os.getenv("DATA_PATH", "").strip()
    if not p:
        p = _default_data_path()
    os.makedirs(p, exist_ok=True)
    return p


def _json_path(telescope):
    """Return full path for main_set_SLT.json or main_set_LOT.json."""
    return os.path.join(_get_data_path(), f"main_set_{telescope}.json")


def _ensure_json_files():
    """Create main_set_SLT.json and main_set_LOT.json if they don't exist."""
    for t in TELESCOPES:
        p = _json_path(t)
        if not os.path.exists(p):
            data = _empty_main_set(t)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# JSON format helpers
# ═══════════════════════════════════════════════════════════════════════════════
def _empty_main_set(telescope="SLT"):
    return {
        "version": 2,
        "settings": {"telescope": telescope},
        "targets": [],
    }


def load_json_any_version(filepath):
    """Load JSON and normalize to v2."""
    with open(filepath, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if raw.get("version") == 2:
        return raw

    # v1 legacy
    settings = raw.get("settings", {})
    telescope = "LOT" if settings.get("IS_LOT") == "True" else "SLT"
    old_targets = raw.get("targets", raw if isinstance(raw, list) else [])
    new_targets = []
    for t in old_targets:
        obs_list = []
        if t.get("Exp_By_Mag") != "True" and t.get("Filter"):
            filters = [x.strip() for x in str(t.get("Filter", "")).split(",")]
            exps = [x.strip() for x in str(t.get("Exp_Time", "")).split(",")]
            counts = [x.strip() for x in str(t.get("Num_of_Frame", "")).split(",")]
            for i in range(len(filters)):
                obs_list.append({
                    "filter": filters[i] if i < len(filters) else filters[-1],
                    "exp_time": int(exps[i]) if i < len(exps) and exps[i].isdigit() else 300,
                    "count": int(counts[i]) if i < len(counts) and counts[i].isdigit() else 1,
                })
        new_targets.append({
            "name": t.get("object name", ""),
            "ra": str(t.get("RA", "")),
            "dec": str(t.get("Dec", "")),
            "mag": t.get("Mag", ""),
            "priority": t.get("Priority", "Normal"),
            "auto_exposure": t.get("Exp_By_Mag") == "True",
            "observations": obs_list,
            "repeat": int(t.get("Repeat", 0)) if str(t.get("Repeat", 0)).isdigit() else 0,
            "note": "",
        })
    return {"version": 2, "settings": {"telescope": telescope}, "targets": new_targets}


def v2_to_v1_target(target):
    """Convert v2 target to v1 for script generation."""
    auto = target.get("auto_exposure", True)
    obs_list = target.get("observations", [])
    base = {
        "object name": target["name"], "RA": target["ra"], "Dec": target["dec"],
        "Mag": str(target.get("mag", "")), "Priority": target.get("priority", "Normal"),
        "Repeat": target.get("repeat", 0),
    }
    if auto or not obs_list:
        base.update({"Exp_By_Mag": "True", "Filter": "", "Exp_Time": "", "Num_of_Frame": ""})
    else:
        base.update({
            "Exp_By_Mag": "False",
            "Filter": ", ".join(o["filter"] for o in obs_list),
            "Exp_Time": ", ".join(str(o["exp_time"]) for o in obs_list),
            "Num_of_Frame": ", ".join(str(o["count"]) for o in obs_list),
        })
    return base


# ═══════════════════════════════════════════════════════════════════════════════
# Main App
# ═══════════════════════════════════════════════════════════════════════════════
def main(page: ft.Page):
    page.title = APP_TITLE
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 1100
    page.window.height = 800
    
    page.update()
    page.window.center()
    page.update()
    page.padding = 0

    # ── Init .env ──
    _ensure_env_file()

    # ── State ──
    lot_programs = _load_lot_programs()

    state = {
        "telescope": "SLT",
        "targets": [],
        "script": "",
        "img_path": "",
        "last_script_path": "",
    }

    def snack(msg, color=ft.Colors.GREEN):
        page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    # ── Auto-load JSON by telescope ──
    _ensure_json_files()

    def _load_main_set():
        """Load targets from main_set_{telescope}.json."""
        jp = _json_path(state["telescope"])
        if not os.path.exists(jp):
            data = _empty_main_set(state["telescope"])
            with open(jp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        data = load_json_any_version(jp)
        state["targets"] = data["targets"]

    def _save_main_set():
        out = {
            "version": 2,
            "settings": {"telescope": state["telescope"]},
            "targets": state["targets"],
        }
        jp = _json_path(state["telescope"])
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

    _load_main_set()

    # ═════════════════════════════════════════════════════════════════════════
    #  Visual helpers
    # ═════════════════════════════════════════════════════════════════════════
    def _filter_color(f):
        return {"up": ft.Colors.PURPLE_700, "gp": ft.Colors.GREEN_700,
                "rp": ft.Colors.RED_700, "ip": ft.Colors.ORANGE_700,
                "zp": ft.Colors.BLUE_GREY_700}.get(f, ft.Colors.GREY_700)

    def _priority_color(p):
        return {"Top": ft.Colors.RED_400, "Urgent": ft.Colors.ORANGE_400,
                "Urgent_Observe_When_Possible": ft.Colors.ORANGE_300,
                "High": ft.Colors.YELLOW_700, "Normal": ft.Colors.BLUE_400,
                "None": ft.Colors.GREY_500}.get(p, ft.Colors.GREY_500)

    def _make_obs_chip(o):
        return ft.Container(
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            content=ft.Row([
                ft.Container(bgcolor=_filter_color(o["filter"]), border_radius=4,
                             padding=ft.padding.symmetric(horizontal=8, vertical=3),
                             content=ft.Text(o["filter"], size=13,
                                             weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)),
                ft.Text(f'{o["exp_time"]}s', size=13),
                ft.Text("\u00d7", size=12, color=ft.Colors.GREY_500),
                ft.Text(str(o["count"]), size=13, weight=ft.FontWeight.BOLD),
            ], spacing=8),
        )

    # ═════════════════════════════════════════════════════════════════════════
    #  PAGE 1 — HOME (Targets)
    # ═════════════════════════════════════════════════════════════════════════
    target_cards = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)

    # Telescope selector in home header
    home_telescope_dd = ft.Dropdown(
        label="Telescope", width=140, value=state["telescope"],
        options=[ft.dropdown.Option(t) for t in TELESCOPES],
        on_select=lambda e: _on_telescope_change(e),
    )

    def _on_telescope_change(e):
        state["telescope"] = home_telescope_dd.value
        _load_main_set()
        rebuild_cards()
        auto_save_label.value = f"Auto-saved to {os.path.basename(_json_path(state['telescope']))}"
        page.update()



    def build_target_card(idx, target):
        priority = target.get("priority", "Normal")
        mag_display = str(target.get("mag", "")) if target.get("mag") else "\u2014"

        obs_chips = ft.Row(
            [_make_obs_chip(o) for o in target.get("observations", [])],
            spacing=6, wrap=True,
        ) if target.get("observations") else ft.Text(
            "Auto exposure by magnitude", size=12, italic=True, color=ft.Colors.GREY_400)

        repeat_ctrls = []
        if target.get("repeat", 0) > 0:
            repeat_ctrls = [ft.Icon(ft.Icons.REPEAT, size=14, color=ft.Colors.GREY_500),
                            ft.Text(f"\u00d7{target['repeat']}", size=13)]

        program_ctrls = []
        if state["telescope"] == "LOT" and target.get("program"):
            program_ctrls = [
                ft.Container(bgcolor=ft.Colors.TEAL_700, border_radius=8,
                             padding=ft.padding.symmetric(horizontal=8, vertical=3),
                             content=ft.Text(target["program"], size=11, color=ft.Colors.WHITE,
                                             weight=ft.FontWeight.BOLD)),
            ]

        note_ctrls = []
        if target.get("note"):
            note_ctrls = [ft.Text(f"Note: {target['note']}", size=12,
                                   color=ft.Colors.GREY_400, italic=True)]

        return ft.Card(elevation=3, content=ft.Container(padding=16, content=ft.Column([
            ft.Row([
                ft.Text(f"#{idx+1}", size=14, color=ft.Colors.GREY_500, weight=ft.FontWeight.BOLD),
                ft.Text(target["name"], size=18, weight=ft.FontWeight.BOLD, expand=True),
                ft.Container(bgcolor=_priority_color(priority), border_radius=12,
                             padding=ft.padding.symmetric(horizontal=10, vertical=3),
                             content=ft.Text(priority, size=11, color=ft.Colors.WHITE,
                                             weight=ft.FontWeight.BOLD)),
                ft.IconButton(ft.Icons.ARROW_UPWARD, icon_size=18, tooltip="Move Up",
                              icon_color=ft.Colors.GREY_400 if idx > 0 else ft.Colors.GREY_800,
                              on_click=lambda e, i=idx: _move_up(i)),
                ft.IconButton(ft.Icons.ARROW_DOWNWARD, icon_size=18, tooltip="Move Down",
                              icon_color=ft.Colors.GREY_400 if idx < len(state["targets"]) - 1 else ft.Colors.GREY_800,
                              on_click=lambda e, i=idx: _move_down(i)),
                ft.IconButton(ft.Icons.EDIT, icon_size=20, tooltip="Edit",
                              on_click=lambda e, i=idx: open_editor(i)),
                ft.IconButton(ft.Icons.CONTENT_COPY, icon_size=18, tooltip="Duplicate",
                              on_click=lambda e, i=idx: _dup(i)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=20, tooltip="Delete",
                              icon_color=ft.Colors.RED_300,
                              on_click=lambda e, i=idx: _del(i)),
            ], alignment=ft.MainAxisAlignment.START, spacing=6),
            ft.Row([
                ft.Icon(ft.Icons.LOCATION_ON, size=14, color=ft.Colors.GREY_500),
                ft.Text(f"RA {target['ra']}", size=13),
                ft.Text("|", size=13, color=ft.Colors.GREY_600),
                ft.Text(f"Dec {target['dec']}", size=13),
                ft.Container(width=20),
                ft.Icon(ft.Icons.BRIGHTNESS_5, size=14, color=ft.Colors.YELLOW_600),
                ft.Text(f"Mag {mag_display}", size=13),
                ft.Container(width=10),
                *repeat_ctrls,
                *program_ctrls,
            ], spacing=5),
            ft.Container(margin=ft.margin.only(top=6), content=obs_chips),
            *note_ctrls,
        ], spacing=6)))

    def rebuild_cards():
        target_cards.controls.clear()
        if not state["targets"]:
            target_cards.controls.append(ft.Container(
                alignment=ft.Alignment(0, 0), padding=60,
                content=ft.Column([
                    ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=64, color=ft.Colors.GREY_600),
                    ft.Text("No targets yet", size=20, color=ft.Colors.GREY_500),
                    ft.Text("Click + to add a target", size=14, color=ft.Colors.GREY_600),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            ))
            return
        for i, t in enumerate(state["targets"]):
            target_cards.controls.append(build_target_card(i, t))

    def _auto_save():
        try:
            _save_main_set()
        except Exception:
            pass

    def _move_up(idx):
        if idx <= 0:
            return
        state["targets"][idx], state["targets"][idx - 1] = state["targets"][idx - 1], state["targets"][idx]
        _auto_save()
        rebuild_cards()
        page.update()

    def _move_down(idx):
        if idx >= len(state["targets"]) - 1:
            return
        state["targets"][idx], state["targets"][idx + 1] = state["targets"][idx + 1], state["targets"][idx]
        _auto_save()
        rebuild_cards()
        page.update()

    def _dup(idx):
        t = copy.deepcopy(state["targets"][idx])
        t["name"] += "_copy"
        state["targets"].insert(idx + 1, t)
        _auto_save()
        rebuild_cards()
        page.update()
        snack(f"Duplicated: {state['targets'][idx]['name']}")

    def _del(idx):
        name = state["targets"][idx]["name"]
        state["targets"].pop(idx)
        _auto_save()
        rebuild_cards()
        page.update()
        snack(f"Deleted: {name}")

    # ── Target Editor Dialog ──
    ed_name = ft.TextField(label="Target Name", width=300, autofocus=True)
    ed_ra = ft.TextField(label="RA (h:m:s or deg)", width=300)
    ed_dec = ft.TextField(label="Dec (d:m:s or deg)", width=300)
    ed_mag = ft.TextField(label="Magnitude", width=300, on_change=lambda e: _on_mag_change(e))
    ed_priority = ft.Dropdown(label="Priority", width=200,
                               options=[ft.dropdown.Option(p) for p in PRIORITIES])
    ed_program = ft.Dropdown(label="Program (LOT)", width=150,
                              options=[ft.dropdown.Option(p) for p in lot_programs])
    ed_program_hint = ft.TextButton(
        "", icon=ft.Icons.SETTINGS,
        style=ft.ButtonStyle(color=ft.Colors.GREY_500),
        on_click=lambda e: _goto_settings_from_editor(),
    )
    ed_program_container = ft.Container(visible=False, content=ft.Row(
        [ed_program, ed_program_hint], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
    ))

    def _goto_settings_from_editor():
        editor_dlg.open = False
        page.update()
        nav_rail.selected_index = 3
        switch_view(3)

    def _refresh_program_options():
        """Refresh all program dropdowns with current lot_programs list."""
        ed_program.options = [ft.dropdown.Option(p) for p in lot_programs]
        if ed_program.value not in lot_programs:
            ed_program.value = lot_programs[0] if lot_programs else None
        gen_program_dd.options = [ft.dropdown.Option(p) for p in lot_programs]
        if gen_program_dd.value not in lot_programs:
            gen_program_dd.value = lot_programs[0] if lot_programs else None
    ed_auto = ft.Switch(label="Auto Exposure (by magnitude)", value=True)
    ed_auto_hint = ft.Text("", size=12, color=ft.Colors.ORANGE_300, italic=True)
    ed_repeat = ft.TextField(label="Repeat", width=150, value="0",
                              keyboard_type=ft.KeyboardType.NUMBER)
    ed_note = ft.TextField(label="Note (required for Urgent priority)", width=500, multiline=True,
                            min_lines=1, max_lines=3)

    def _update_auto_availability():
        """Disable auto exposure for LOT or SLT with mag outside 12-22."""
        tel = state["telescope"]
        if tel == "LOT":
            ed_auto.value = False
            ed_auto.disabled = True
            ed_auto_hint.value = "LOT requires manual exposure settings"
            obs_container.visible = True
        else:
            # SLT: check magnitude range
            mag_str = ed_mag.value.strip() if ed_mag.value else ""
            try:
                mag_val = float(mag_str)
                if mag_val > 22 or mag_val < 12:
                    ed_auto.value = False
                    ed_auto.disabled = True
                    ed_auto_hint.value = f"Mag {mag_val} outside 12-22, manual exposure required"
                    obs_container.visible = True
                else:
                    ed_auto.disabled = False
                    ed_auto_hint.value = ""
            except ValueError:
                # No valid mag entered — allow auto
                ed_auto.disabled = False
                ed_auto_hint.value = ""
        page.update()

    def _on_mag_change(e):
        _update_auto_availability()

    obs_rows_col = ft.Column(spacing=8)
    obs_rows_data = []

    def _build_obs_row(oi):
        o = obs_rows_data[oi]
        total = o["exp_time"] * o["count"]
        return ft.Row([
            ft.Dropdown(label="Filter", width=120, value=o["filter"],
                        options=[ft.dropdown.Option(f) for f in FILTERS],
                        on_select=lambda e, i=oi: _obs_ch(i, "filter", e.control.value)),
            ft.TextField(label="Exp (sec)", width=110, value=str(o["exp_time"]),
                         keyboard_type=ft.KeyboardType.NUMBER,
                         on_change=lambda e, i=oi: _obs_ch(i, "exp_time", e.control.value)),
            ft.TextField(label="Count", width=80, value=str(o["count"]),
                         keyboard_type=ft.KeyboardType.NUMBER,
                         on_change=lambda e, i=oi: _obs_ch(i, "count", e.control.value)),
            ft.Text(f"= {total}s", size=12, color=ft.Colors.GREY_400, width=90),
            ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_size=20,
                          icon_color=ft.Colors.RED_300, tooltip="Remove",
                          on_click=lambda e, i=oi: _rm_obs(i)),
        ], spacing=8)

    def _update_obs_total():
        """Update just the total text and per-row subtotals without rebuilding rows."""
        for i, row in enumerate(obs_rows_col.controls):
            if not isinstance(row, ft.Row) or i >= len(obs_rows_data):
                continue
            # Update the per-row subtotal text (4th control in row)
            o = obs_rows_data[i]
            sub = o["exp_time"] * o["count"]
            if len(row.controls) > 3 and isinstance(row.controls[3], ft.Text):
                row.controls[3].value = f"= {sub}s"
        # Update the grand total text (last control if it's a Text)
        if obs_rows_data and obs_rows_col.controls:
            last = obs_rows_col.controls[-1]
            if isinstance(last, ft.Text):
                total = sum(o["exp_time"] * o["count"] for o in obs_rows_data)
                last.value = f"Total exposure: {total}s ({total/60:.1f} min)"
        page.update()

    def _obs_ch(idx, field, val):
        if field == "filter":
            obs_rows_data[idx]["filter"] = val
            _refresh_obs()
            page.update()
        elif field == "exp_time":
            obs_rows_data[idx]["exp_time"] = int(val) if val.isdigit() else 0
            _update_obs_total()
        elif field == "count":
            obs_rows_data[idx]["count"] = int(val) if val.isdigit() else 0
            _update_obs_total()

    def _rm_obs(idx):
        obs_rows_data.pop(idx)
        _refresh_obs()
        page.update()

    def _add_obs(e=None):
        obs_rows_data.append({"filter": "rp", "exp_time": 300, "count": 1})
        _refresh_obs()
        page.update()

    def _add_ugriz(e=None):
        existing = {o["filter"] for o in obs_rows_data}
        ugriz = ["up", "gp", "rp", "ip", "zp"]
        for f in FILTERS:
            if f not in existing and f in ugriz:
                obs_rows_data.append({"filter": f, "exp_time": 300, "count": 1})
        _refresh_obs()
        page.update()
    
    def _add_UBVRI(e=None):
        existing = {o["filter"] for o in obs_rows_data}
        ubvri = ["U", "B", "V", "R", "I"]
        for f in FILTERS:
            if f not in existing and f in ubvri:
                obs_rows_data.append({"filter": f, "exp_time": 300, "count": 1})
        _refresh_obs()
        page.update()

    def _refresh_obs():
        obs_rows_col.controls.clear()
        for i in range(len(obs_rows_data)):
            obs_rows_col.controls.append(_build_obs_row(i))
        obs_rows_col.controls.append(ft.Row([
            ft.TextButton("Add Filter", icon=ft.Icons.ADD, on_click=_add_obs),
            ft.TextButton("+ All ugriz", icon=ft.Icons.AUTO_AWESOME, on_click=_add_ugriz),
            ft.TextButton("+ All UBVRI", icon=ft.Icons.AUTO_AWESOME, on_click=_add_UBVRI),
        ], spacing=10))
        if obs_rows_data:
            total = sum(o["exp_time"] * o["count"] for o in obs_rows_data)
            obs_rows_col.controls.append(
                ft.Text(f"Total exposure: {total}s ({total/60:.1f} min)", size=13,
                        weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_200))

    obs_container = ft.Container(visible=False, content=ft.Column([
        ft.Text("Observation Configuration", size=15, weight=ft.FontWeight.W_500),
        obs_rows_col,
    ], spacing=6))

    def _on_auto_toggle(e):
        obs_container.visible = not ed_auto.value
        page.update()

    ed_auto.on_change = _on_auto_toggle

    edit_idx = {"v": -1}

    def open_editor(idx):
        if idx < 0:
            edit_idx["v"] = -1
            ed_name.value = ed_ra.value = ed_dec.value = ed_mag.value = ed_note.value = ""
            ed_priority.value = "Normal"
            ed_program.value = lot_programs[0] if state["telescope"] == "LOT" and lot_programs else None
            ed_auto.value = True
            ed_repeat.value = "0"
            obs_rows_data.clear()
            editor_dlg.title = ft.Text("New Target")
        else:
            edit_idx["v"] = idx
            t = state["targets"][idx]
            ed_name.value = t.get("name", "")
            ed_ra.value = t.get("ra", "")
            ed_dec.value = t.get("dec", "")
            ed_mag.value = str(t.get("mag", ""))
            ed_priority.value = t.get("priority", "Normal")
            ed_auto.value = t.get("auto_exposure", True)
            ed_repeat.value = str(t.get("repeat", 0))
            ed_program.value = t.get("program", lot_programs[0] if lot_programs else "") if state["telescope"] == "LOT" else None
            ed_note.value = t.get("note", "")
            obs_rows_data.clear()
            obs_rows_data.extend(copy.deepcopy(t.get("observations", [])))
            editor_dlg.title = ft.Text(f"Edit: {t['name']}")
        ed_program_container.visible = (state["telescope"] == "LOT")
        obs_container.visible = not ed_auto.value
        _refresh_obs()
        _update_auto_availability()
        editor_dlg.open = True
        page.update()

    def _on_save_target(e):
        name = ed_name.value.strip()
        ra = ed_ra.value.strip()
        dec = ed_dec.value.strip()
        if not name or not ra or not dec:
            snack("Name, RA, Dec are required!", ft.Colors.ORANGE)
            return
        if ed_priority.value == "Urgent" and not ed_note.value.strip():
            snack("Urgent priority requires a note!", ft.Colors.ORANGE)
            return
        # Validate exposure rules
        if state["telescope"] == "LOT" and ed_auto.value:
            snack("LOT requires manual exposure settings!", ft.Colors.ORANGE)
            return
        if state["telescope"] == "SLT" and ed_auto.value:
            mag_str = ed_mag.value.strip()
            try:
                mv = float(mag_str)
                if mv > 22 or mv < 12:
                    snack(f"Mag {mv} outside 12-22, manual exposure required for SLT!", ft.Colors.ORANGE)
                    return
            except ValueError:
                pass
        t = {
            "name": name, "ra": ra, "dec": dec,
            "mag": ed_mag.value.strip(),
            "priority": ed_priority.value or "Normal",
            "auto_exposure": ed_auto.value,
            "observations": copy.deepcopy(obs_rows_data) if not ed_auto.value else [],
            "repeat": int(ed_repeat.value) if ed_repeat.value.isdigit() else 0,
            "program": ed_program.value if state["telescope"] == "LOT" else "",
            "note": ed_note.value.strip(),
        }
        idx = edit_idx["v"]
        if idx < 0:
            state["targets"].append(t)
        else:
            state["targets"][idx] = t
        editor_dlg.open = False
        _auto_save()
        rebuild_cards()
        page.update()
        snack(f"{'Added' if idx < 0 else 'Updated'}: {name}")

    def _on_cancel_editor(e):
        editor_dlg.open = False
        page.update()

    editor_dlg = ft.AlertDialog(
        modal=True, title=ft.Text("New Target"),
        content=ft.Container(width=650, height=540, content=ft.Column([
            ft.Row([ed_name, ed_mag], spacing=12),
            ft.Row([ed_ra, ed_dec], spacing=12),
            ft.Row([ed_priority, ed_repeat, ed_program_container], spacing=12),
            ft.Divider(height=1),
            ft.Row([ed_auto, ed_auto_hint], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            obs_container,
            ft.Divider(height=1),
            ed_note,
        ], spacing=10, scroll=ft.ScrollMode.AUTO)),
        actions=[
            ft.TextButton("Cancel", on_click=_on_cancel_editor),
            ft.Button("Save Target", icon=ft.Icons.CHECK, on_click=_on_save_target),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(editor_dlg)

    # ── Data path UI ──
    data_path_label = ft.Text(
        _get_data_path(), size=13, color=ft.Colors.GREY_300, expand=True,
    )

    folder_picker = ft.FilePicker()

    async def _on_pick_folder(e):
        result = await folder_picker.get_directory_path(
            dialog_title="Select Data Folder",
            initial_directory=_get_data_path(),
        )
        if result is None:
            return
        _save_env_vars({"DATA_PATH": result})
        data_path_label.value = result
        _ensure_json_files()
        _load_main_set()
        rebuild_cards()
        auto_save_label.value = f"Auto-saved to {os.path.basename(_json_path(state['telescope']))}"
        page.update()
        snack(f"Data path set to {result}")

    auto_save_label = ft.Text(
        f"Auto-saved to {os.path.basename(_json_path(state['telescope']))}",
        size=12, color=ft.Colors.GREY_500, italic=True,
    )

    # ── Home view ──
    home_view = ft.Container(padding=20, expand=True, content=ft.Column([
        ft.Row([
            ft.Icon(ft.Icons.FOLDER_OPEN, size=18, color=ft.Colors.GREY_400),
            data_path_label,
            ft.IconButton(ft.Icons.DRIVE_FILE_MOVE_OUTLINE, icon_size=20,
                          tooltip="Change Data Folder",
                          on_click=_on_pick_folder),
        ], spacing=8),
        ft.Row([
            ft.Button("Add Target", on_click=lambda e: open_editor(-1)),
            ft.Container(expand=True),
            home_telescope_dd,
        ], spacing=10),
        ft.Row([
            ft.Container(expand=True),
            auto_save_label,
        ], spacing=10),
        ft.Divider(),
        target_cards,
    ], expand=True))

    # ═════════════════════════════════════════════════════════════════════════
    #  PAGE 2 — Script Generator
    # ═════════════════════════════════════════════════════════════════════════
    script_output = ft.TextField(
        label="Generated Script (script.txt)", multiline=True,
        min_lines=18, max_lines=40, read_only=True,
        text_size=11, text_style=ft.TextStyle(font_family="Courier New"),
        expand=True,
    )
    # 1x1 transparent pixel as valid placeholder
    _PIXEL_URI = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    obs_image = ft.Image(src=_PIXEL_URI, width=520, fit=ft.BoxFit.CONTAIN, visible=False)
    gen_status = ft.Text("")

    sort_mode = ft.RadioGroup(
        value="rise",
        content=ft.Row([
            ft.Radio(value="home", label="Home order"),
            ft.Radio(value="rise", label="Rise time order"),
        ], spacing=16),
    )

    # Telescope & program selectors for script generation
    gen_telescope_dd = ft.Dropdown(
        label="Telescope", width=140, value=state["telescope"],
        options=[ft.dropdown.Option(t) for t in TELESCOPES],
        on_select=lambda e: _on_gen_telescope_change(e),
    )
    gen_program_dd = ft.Dropdown(
        label="Program", width=120,
        options=[ft.dropdown.Option(p) for p in lot_programs],
        value=lot_programs[0] if lot_programs else None,
        visible=state["telescope"] == "LOT",
    )

    def _on_gen_telescope_change(e):
        gen_program_dd.visible = gen_telescope_dd.value == "LOT"
        page.update()

    def _script_filename(telescope, program=""):
        """Return script filename like script_SLT.txt or script_LOT_R01.txt."""
        if telescope == "LOT" and program:
            return f"script_LOT_{program}.txt"
        return f"script_{telescope}.txt"

    def _sort_targets_by_rise_time(targets):
        """Sort targets by rise time (earliest rising first) using ephem."""
        if not HAS_PLOTTING:
            return targets  # no ephem available, keep original order
        try:
            import ephem as _ephem
            lulin = obs.create_ephem_observer(
                'Lulin Observatory', '120:52:21.5', '23:28:10.0', 2800)
            now = datetime.now()
            # Use tonight's sunset as reference (~18:00 local)
            tonight = now.replace(hour=10, minute=0, second=0)  # ~18:00 local in UTC
            lulin.date = _ephem.Date(tonight)

            def _rise_key(t):
                try:
                    ra_hms = _ensure_hms(t["ra"])
                    dec_dms = _ensure_dms(t["dec"])
                    ephem_t = obs.create_ephem_target(t["name"], ra_hms, dec_dms)
                    lulin_copy = lulin.copy()
                    rise = lulin_copy.next_rising(ephem_t)
                    return float(rise)
                except Exception:
                    return float('inf')  # never rises → put last

            return sorted(targets, key=_rise_key)
        except Exception:
            return targets

    def _on_generate(e):
        telescope = gen_telescope_dd.value or state["telescope"]
        IS_LOT = "True" if telescope == "LOT" else "False"
        program = gen_program_dd.value if telescope == "LOT" else ""
        if not state["targets"]:
            snack("No targets! Go to Home and add some.", ft.Colors.ORANGE)
            return

        # For LOT, filter targets by selected program
        if telescope == "LOT" and program:
            working_targets = [t for t in state["targets"] if t.get("program") == program]
            if not working_targets:
                snack(f"No targets for program {program}!", ft.Colors.ORANGE)
                return
        else:
            working_targets = list(state["targets"])

        use_rise = sort_mode.value == "rise"
        gen_status.value = "Generating..." + (" (sorting by rise time)" if use_rise else "")
        page.update()

        # Sort targets by selected order
        sorted_targets = _sort_targets_by_rise_time(working_targets) if use_rise else working_targets

        script = ""
        target_list = []
        current_day = datetime.now().strftime("%Y-%m-%d")

        for t in sorted_targets:
            v1 = v2_to_v1_target(t)
            # Convert RA/Dec to sexagesimal if given in decimal degrees
            ra_hms = _ensure_hms(v1["RA"])
            dec_dms = _ensure_dms(v1["Dec"])
            # Sanitize name: keep only alphanumeric + hyphen
            safe_name = _sanitize_name(v1["object name"])
            if HAS_PLOTTING:
                try:
                    target_list.append(obs.create_ephem_target(t["name"], ra_hms, dec_dms))
                except Exception:
                    pass
            # Insert note as ACP comment before this target's script
            note = t.get("note", "").strip()
            if note:
                script += f";{safe_name}: {note}\n"
            if v1["Exp_By_Mag"] == "True":
                script += tri.generate_script(
                    safe_name, ra_hms, dec_dms, v1["Mag"],
                    v1["Priority"], IS_LOT, v1["Repeat"], auto_exp=True)
            else:
                script += tri.generate_script(
                    safe_name, ra_hms, dec_dms, v1["Mag"],
                    v1["Priority"], IS_LOT, v1["Repeat"], auto_exp=False,
                    filter_input=v1["Filter"], exp_time=v1["Exp_Time"],
                    count=v1["Num_of_Frame"])

        state["script"] = script
        script_output.value = script

        # Save script file with telescope/program name
        fname = _script_filename(telescope, program)
        script_full = os.path.join(_get_data_path(), fname)
        state["last_script_path"] = script_full
        try:
            with open(script_full, "w", encoding="utf-8") as f:
                f.write(script)
        except Exception:
            pass

        # Generate plot
        if HAS_PLOTTING and target_list:
            try:
                plot_dir = os.path.join(_get_data_path(), "plot")
                os.makedirs(plot_dir, exist_ok=True)
                plot_name = f"obv_plot_{telescope}_{program}.jpg" if program else f"obv_plot_{telescope}.jpg"
                plot_dst = os.path.join(plot_dir, plot_name)
                img_path = tri.generate_img(current_day, target_list, plot_path=plot_dst)
                state["img_path"] = img_path
                with open(img_path, "rb") as imgf:
                    b64 = base64.b64encode(imgf.read()).decode()
                    obs_image.src = f"data:image/png;base64,{b64}"
                obs_image.visible = True
            except Exception as ex:
                gen_status.value = f"Plot error: {ex}"
                obs_image.visible = False
        else:
            obs_image.visible = False

        gen_status.value = f"Done \u2014 {len(sorted_targets)} targets \u2192 saved to {fname}"
        page.update()
        snack(f"Script generated and saved to {fname}!")

    def _on_copy_script(e):
        if state["script"]:
            page.set_clipboard(state["script"])
            snack("Copied to clipboard!")
        else:
            snack("Generate a script first.", ft.Colors.ORANGE)

    script_view = ft.Container(padding=20, expand=True, content=ft.Column([
        ft.Text("Script Generator", size=28, weight=ft.FontWeight.BOLD),
        ft.Divider(),
        ft.Row([
            gen_telescope_dd,
            gen_program_dd,
            ft.Container(width=10),
            ft.Text("Sort:", size=14, weight=ft.FontWeight.W_500),
            sort_mode,
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([
            ft.Button("Generate Script", icon=ft.Icons.PLAY_ARROW, on_click=_on_generate,
                      style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)),
            ft.Button("Copy to Clipboard", icon=ft.Icons.COPY, on_click=_on_copy_script),
        ], spacing=12),
        gen_status,
        ft.Row([
            script_output,
            ft.Column([
                ft.Text("Object Visibility", size=16, weight=ft.FontWeight.W_500),
                obs_image,
            ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=16, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
    ], spacing=10, expand=True))

    # ═════════════════════════════════════════════════════════════════════════
    #  PAGE 3 — Send to Control Room
    # ═════════════════════════════════════════════════════════════════════════
    send_script_preview = ft.TextField(
        label="Script content", multiline=True, min_lines=10, max_lines=20,
        read_only=True, text_size=12,
        text_style=ft.TextStyle(font_family="Courier New"),
        expand=True,
    )
    def _build_send_message(telescope="{telescope}", program="{program}"):
        return (f"您好，若天氣允許，以下是今日的觀測目標:\n"
                f"使用 {telescope} 觀測計劃 {program}\n"
                "If the weather permits, here are today's observation targets:\n"
                f"Use {telescope} with {program} program\n")

    send_message_field = ft.TextField(
        label="Message to send (editable)",
        multiline=True, min_lines=4, max_lines=8, width=800,
        value=_build_send_message(),
    )
    send_status = ft.Text("")
    send_progress = ft.ProgressRing(width=20, height=20, stroke_width=3, visible=False)
    send_btn = ft.Button("Send to Slack", icon=ft.Icons.SEND,
                         style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE))
    send_img_preview = ft.Image(src=_PIXEL_URI, width=600, fit=ft.BoxFit.CONTAIN, visible=False)

    send_script_dd = ft.Dropdown(label="Select script file", width=420)

    def _find_script_files():
        """Find all script_*.txt files in data path with modification dates."""
        dp = _get_data_path()
        files = []
        for f in os.listdir(dp):
            if f.startswith("script_") and f.endswith(".txt"):
                fp = os.path.join(dp, f)
                mtime = datetime.fromtimestamp(os.path.getmtime(fp))
                files.append((f, mtime))
        # Also check legacy script.txt
        legacy = os.path.join(dp, "script.txt")
        if os.path.exists(legacy):
            mtime = datetime.fromtimestamp(os.path.getmtime(legacy))
            files.append(("script.txt", mtime))
        files.sort(key=lambda x: x[1], reverse=True)
        return files

    def _refresh_script_list():
        """Refresh the dropdown with available script files."""
        files = _find_script_files()
        send_script_dd.options = [
            ft.dropdown.Option(
                key=f,
                text=f"{f}  ({mt.strftime('%Y-%m-%d %H:%M')})",
            ) for f, mt in files
        ]
        if files:
            send_script_dd.value = files[0][0]
        else:
            send_script_dd.value = None

    def _on_load_script(e):
        chosen = send_script_dd.value
        if not chosen:
            snack("No script file selected.", ft.Colors.ORANGE)
            return
        sf = os.path.join(_get_data_path(), chosen)
        if not os.path.exists(sf):
            snack(f"{chosen} not found.", ft.Colors.ORANGE)
            return
        with open(sf, "r", encoding="utf-8") as f:
            content = f.read()
        send_script_preview.value = content
        state["script"] = content
        state["last_script_path"] = sf

        # Parse telescope/program from filename like script_SLT.txt or script_LOT_R01.txt
        base = os.path.splitext(chosen)[0]          # e.g. "script_SLT" or "script_LOT_R01"
        parts = base.replace("script_", "", 1).split("_", 1)  # ["SLT"] or ["LOT", "R01"]
        tel = parts[0] if parts else "{telescope}"
        prog = parts[1] if len(parts) > 1 else "normal"
        send_message_field.value = _build_send_message(tel, prog)

        # Regenerate observation plot from current targets
        send_img_preview.visible = False
        if HAS_PLOTTING:
            try:
                jp = _json_path(tel)
                if os.path.exists(jp):
                    data = load_json_any_version(jp)
                    plot_targets = data["targets"]
                    if tel == "LOT" and prog and prog != "normal":
                        plot_targets = [t for t in plot_targets if t.get("program") == prog]
                    target_list = []
                    for t in plot_targets:
                        try:
                            target_list.append(obs.create_ephem_target(
                                t["name"], _ensure_hms(t["ra"]), _ensure_dms(t["dec"])))
                        except Exception:
                            pass
                    if target_list:
                        plot_dir = os.path.join(_get_data_path(), "plot")
                        os.makedirs(plot_dir, exist_ok=True)
                        plot_name = f"obv_plot_{tel}_{prog}.jpg" if prog and prog != "normal" else f"obv_plot_{tel}.jpg"
                        plot_dst = os.path.join(plot_dir, plot_name)
                        current_day = datetime.now().strftime("%Y-%m-%d")
                        img_path = tri.generate_img(current_day, target_list, plot_path=plot_dst)
                        state["img_path"] = img_path
                        with open(img_path, "rb") as imgf:
                            b64 = base64.b64encode(imgf.read()).decode()
                            send_img_preview.src = f"data:image/png;base64,{b64}"
                        send_img_preview.visible = True
            except Exception:
                pass

        page.update()
        snack(f"Loaded {chosen} ({len(content)} chars)")

    def _set_sending(is_sending):
        send_btn.disabled = is_sending
        send_progress.visible = is_sending
        if is_sending:
            send_status.value = "Sending..."
            send_status.color = ft.Colors.YELLOW_400
        page.update()

    def _do_send(e):
        if not HAS_SLACK:
            snack("slack_sdk not installed! pip install slack-sdk", ft.Colors.RED)
            return
        token = os.getenv("SLACK_BOT_TOKEN", "").strip()
        channel = os.getenv("SLACK_CHANNEL_ID_CONTROL_ROOM", "").strip()
        if not token or not channel:
            snack("Slack credentials not set. Go to Settings.", ft.Colors.ORANGE)
            return
        msg = send_message_field.value.strip()
        if not msg:
            snack("Message is empty!", ft.Colors.ORANGE)
            return

        _set_sending(True)

        def _send_worker():
            try:
                client = WebClient(token=token)
                client.chat_postMessage(channel=channel, text=msg)
                # Upload script file
                sf = state.get("last_script_path", os.path.join(_get_data_path(), SCRIPT_FILE))
                if sf and os.path.exists(sf):
                    client.files_upload_v2(channel=channel, file=sf)
                # Upload image
                if state["img_path"] and os.path.exists(state["img_path"]):
                    client.files_upload_v2(channel=channel, file=state["img_path"])
                send_status.value = "Sent successfully!"
                send_status.color = ft.Colors.GREEN
                snack("Sent to control room!")
            except Exception as ex:
                send_status.value = f"Error: {ex}"
                send_status.color = ft.Colors.RED_300
                snack(f"Send error: {ex}", ft.Colors.RED)
            finally:
                send_btn.disabled = False
                send_progress.visible = False
                page.update()

        threading.Thread(target=_send_worker, daemon=True).start()

    send_btn.on_click = lambda e: _on_send_click(e)

    def _on_send_click(e):
        confirm_dlg.open = True
        page.update()

    def _on_confirm_send(e):
        confirm_dlg.open = False
        page.update()
        _do_send(e)

    def _on_cancel_send(e):
        confirm_dlg.open = False
        page.update()

    confirm_dlg = ft.AlertDialog(
        modal=True, title=ft.Text("Confirm Send"),
        content=ft.Text("Are you sure you want to send this to Slack control room?"),
        actions=[
            ft.TextButton("Cancel", on_click=_on_cancel_send),
            ft.Button("Yes, Send", on_click=_on_confirm_send,
                      style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE)),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(confirm_dlg)

    send_view = ft.Container(padding=20, expand=True, content=ft.Column([
        ft.Text("Send to Control Room", size=28, weight=ft.FontWeight.BOLD),
        ft.Divider(),
        ft.Row([
            send_script_dd,
            ft.Button("Load", icon=ft.Icons.FILE_OPEN, on_click=_on_load_script),
        ], spacing=12),
        ft.Row([
            send_script_preview,
            ft.Container(
                content=send_img_preview,
                width=500,
                alignment=ft.Alignment(0, -1),
            ),
        ], spacing=16, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
        ft.Divider(),
        ft.Text("Message", size=18, weight=ft.FontWeight.W_500),
        send_message_field,
        ft.Row([send_btn, send_progress], spacing=12),
        send_status,
    ], spacing=10, expand=True))

    # ═════════════════════════════════════════════════════════════════════════
    #  PAGE 4 — Settings
    # ═════════════════════════════════════════════════════════════════════════
    set_token = ft.TextField(
        label="Slack Bot Token", password=True, can_reveal_password=True,
        width=550, value=os.getenv("SLACK_BOT_TOKEN", ""),
    )
    set_channel = ft.TextField(
        label="Slack Channel ID", width=550,
        value=os.getenv("SLACK_CHANNEL_ID_CONTROL_ROOM", ""),
    )
    set_status = ft.Text("")

    # ── LOT Programs management ──
    prog_input = ft.TextField(label="New Program (e.g. R07)", width=200)
    prog_chips_row = ft.Row(spacing=8, wrap=True)

    def _build_prog_chips():
        prog_chips_row.controls.clear()
        for p in lot_programs:
            prog_chips_row.controls.append(
                ft.Chip(
                    label=ft.Text(p),
                    bgcolor=ft.Colors.TEAL_700,
                    delete_icon_color=ft.Colors.RED_300,
                    on_delete=lambda e, prog=p: _del_program(prog),
                )
            )

    def _add_program(e):
        val = prog_input.value.strip().upper()
        if not val:
            return
        if val in lot_programs:
            snack(f"{val} already exists", ft.Colors.ORANGE)
            return
        lot_programs.append(val)
        lot_programs.sort()
        _save_lot_programs(lot_programs)
        prog_input.value = ""
        _build_prog_chips()
        _refresh_program_options()
        page.update()
        snack(f"Added program: {val}")

    def _del_program(prog):
        if prog in lot_programs:
            lot_programs.remove(prog)
            _save_lot_programs(lot_programs)
            _build_prog_chips()
            _refresh_program_options()
            page.update()
            snack(f"Removed program: {prog}")

    _build_prog_chips()

    def _on_save_settings(e):
        token = set_token.value.strip()
        channel = set_channel.value.strip()
        try:
            _save_env(token, channel)
            set_status.value = f"Saved to {ENV_FILE}"
            snack("Settings saved to .env")
        except Exception as ex:
            set_status.value = f"Error: {ex}"
            snack(f"Save error: {ex}", ft.Colors.RED)
        page.update()

    set_data_path_label = ft.Text(_get_data_path(), size=14, color=ft.Colors.GREY_300)

    async def _on_pick_folder_settings(e):
        result = await folder_picker.get_directory_path(
            dialog_title="Select Data Folder",
            initial_directory=_get_data_path(),
        )
        if result is None:
            return
        _save_env_vars({"DATA_PATH": result})
        data_path_label.value = result
        set_data_path_label.value = result
        _ensure_json_files()
        _load_main_set()
        rebuild_cards()
        set_status.value = f"Data path saved to {ENV_FILE}"
        page.update()
        snack(f"Data path set to {result}")

    def _on_reload_settings(e):
        _ensure_env_file()
        set_token.value = os.getenv("SLACK_BOT_TOKEN", "")
        set_channel.value = os.getenv("SLACK_CHANNEL_ID_CONTROL_ROOM", "")
        set_status.value = "Reloaded from .env"
        page.update()
        snack("Settings reloaded from .env")

    settings_view = ft.Container(padding=25, content=ft.Column([
        ft.Text("Settings", size=28, weight=ft.FontWeight.BOLD),
        ft.Divider(),
        ft.Text("Data Path", size=18, weight=ft.FontWeight.W_500),
        ft.Row([
            ft.Icon(ft.Icons.FOLDER_OPEN, size=18, color=ft.Colors.GREY_400),
            set_data_path_label,
            ft.Button("Change Folder", icon=ft.Icons.DRIVE_FILE_MOVE_OUTLINE,
                      on_click=_on_pick_folder_settings),
        ], spacing=10),
        ft.Divider(),
        ft.Text("LOT Programs", size=18, weight=ft.FontWeight.W_500),
        ft.Text("Add or remove LOT observation programs (e.g. R01, R07, R11)", size=13,
                color=ft.Colors.GREY_400, italic=True),
        prog_chips_row,
        ft.Row([
            prog_input,
            ft.Button("Add", icon=ft.Icons.ADD, on_click=_add_program),
        ], spacing=10),
        ft.Divider(),
        ft.Text("Slack Configuration", size=18, weight=ft.FontWeight.W_500),
        ft.Text(f"Credentials are stored in {ENV_FILE}", size=13,
                color=ft.Colors.GREY_400, italic=True),
        set_token,
        set_channel,
        ft.Row([
            ft.Button("Save to .env", icon=ft.Icons.SAVE, on_click=_on_save_settings),
            ft.Button("Reload .env", icon=ft.Icons.REFRESH, on_click=_on_reload_settings),
        ], spacing=12),
        set_status,
        ft.Divider(),
        ft.Text("About", size=18, weight=ft.FontWeight.W_500),
        ft.Text("Kinder Trigger - Cross-platform Observation Trigger", size=14),
        ft.Text("Platforms: Windows, macOS, Linux, iOS, Android, Web", size=13,
                color=ft.Colors.GREY_400),
        ft.Text("Telescopes: LOT / SLT", size=13, color=ft.Colors.GREY_400),
        ft.Text(f"Plotting: {'Available' if HAS_PLOTTING else 'Not available'}", size=13,
                color=ft.Colors.GREY_400),
        ft.Text(f"Slack SDK: {'Available' if HAS_SLACK else 'Not available (pip install slack-sdk)'}", size=13,
                color=ft.Colors.GREY_400),
    ], spacing=12, scroll=ft.ScrollMode.AUTO))

    # ═════════════════════════════════════════════════════════════════════════
    #  Navigation  —  Home(0), Script(1), Send(2), Settings(3)
    # ═════════════════════════════════════════════════════════════════════════
    content_area = ft.Container(expand=True)
    views = [home_view, script_view, send_view, settings_view]

    def switch_view(idx):
        if idx == 0:
            home_telescope_dd.value = state["telescope"]
            data_path_label.value = _get_data_path()
            auto_save_label.value = f"Auto-saved to {os.path.basename(_json_path(state['telescope']))}"
        elif idx == 1:
            gen_telescope_dd.value = state["telescope"]
            gen_program_dd.visible = state["telescope"] == "LOT"
        elif idx == 2:
            _refresh_script_list()
        elif idx == 3:
            set_data_path_label.value = _get_data_path()
        content_area.content = views[idx]
        page.update()

    def on_nav(e):
        switch_view(e.control.selected_index)

    is_mobile = page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)

    nav_dests = [
        ("Home", ft.Icons.HOME),
        ("Script", ft.Icons.CODE),
        ("Send", ft.Icons.SEND),
        ("Settings", ft.Icons.SETTINGS),
    ]

    # ── Load logo for sidebar (from assets/ directory) ──
    nav_rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=80, min_extended_width=180,
        leading=ft.Container(
            padding=ft.padding.only(top=10, bottom=6),
            content=ft.Image(src="Kinder_light.png", width=60, fit=ft.BoxFit.CONTAIN),
        ),
        destinations=[ft.NavigationRailDestination(icon=ic, label=lb) for lb, ic in nav_dests],
        on_change=on_nav,
    )

    nav_bar = ft.NavigationBar(
        selected_index=0,
        destinations=[ft.NavigationBarDestination(icon=ic, label=lb) for lb, ic in nav_dests],
        on_change=on_nav,
    )

    # ── Init ──
    rebuild_cards()
    switch_view(0)

    if is_mobile:
        page.navigation_bar = nav_bar
        page.add(ft.Container(content=content_area, expand=True))
    else:
        page.add(ft.Row([nav_rail, ft.VerticalDivider(width=1), content_area], expand=True))


if __name__ == "__main__":
    # ft.run(main)
    ft.app(target=main, assets_dir="assets")
