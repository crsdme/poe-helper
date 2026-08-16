# PoE Helper

Windows helper for **Path of Exile 1**. It maps your stash and inventory, then runs crafts and Heist chores with hotkeys so you are not clicking the same sequence by hand.

Version `0.4.0`. UI languages: English, Russian, German, French, Spanish, Portuguese, Chinese, Korean.

This is a local overlay and click helper. It is not an official Grinding Gear Games product and it does not talk to the game client beyond reading the screen and sending input.

## Features

### Craft scenarios
Build a reusable recipe: item type → method (currency / Harvest) → mods and stop conditions → confirm. Saved scenarios live under `data/scenarios/`.

**Run craft** hovers the mapped item slot, copies the item with `Ctrl+C`, checks the current step, and right-clicks currency onto it until the conditions match.

**Chain craft** walks an inventory grid (same overlay as Heist): each red cell in order, then the same scenario.

Craft sessions are stored under `data/logs/` so you can search past runs and see the copied item text.

### Blueprint Confirm
Heist planner helper. You map the inventory grid, **CONFIRM PLANS**, and the blueprint slot. The run `Ctrl+clicks` each blueprint, assigns the leftmost rogue to empty job slots, pans the map if the Fees panel covers nodes, then confirms.

### Blueprint Reveal
Opens each blueprint from the inventory grid, clicks the large wing reveal buttons (the gold eye), then `Shift+clicks` the blueprint back into the stash and takes the next one. Empty cells are skipped.

### Settings
- Currency stash overlay on top of `stash.jpg` (slot assignments)
- Item / HUD overlays
- Start, chain, and stop hotkeys

Game affix data is cached locally from RePoE-style metadata (`data/cache/game_catalog.json`).

## Requirements

- Windows 10/11
- Python 3.12+ (for source runs)
- Path of Exile 1 in **windowed** or **windowed fullscreen**, same monitor as the overlays
- In-game **Advanced Mod Descriptions** enabled (more reliable prefix/suffix reading)

## Run from source

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe main.py
```

Or double-click `start.vbs` after the venv exists.

First launch downloads / builds the local catalog. Home tiles for craft stay locked until that cache is ready.

## Build a folder exe

```powershell
.\build.ps1
```

Output: `dist\PoE Helper\PoE Helper.exe`

Bundled images (icon, stash layout, currency / item / Heist templates) live in `app/assets/`. System files such as `icon.png` and `stash.jpg` are in `app/assets/system/`.

## Typical setup

1. Open **Settings** and place the currency overlay on your stash tab (the picture in `app/assets/system/stash.jpg` is the layout reference).
2. Map the item slot (and inventory grid if you use Chain / Heist).
3. Create a craft scenario, or open **Blueprint Confirm** / **Blueprint Reveal** and set their overlays.
4. Switch to PoE, hover what the helper should click, press the start hotkey. Stop hotkey or `Esc` aborts.

Keep the PoE window focused while a job runs. Overlays are click-through maps; the helper clicks the game, not its own UI.

## What to add next

### Map Craft
Highest-priority missing loop: rolling maps in inventory the same way Chain rolls gear.

Worth covering:

- Inventory grid of maps (reuse the Chain overlay)
- Chisel to 20% quality, then Alchemy / Chaos / Scour cycles
- Stop rules: pack size, quantity, specific mods (e.g. “two extra league mechanics”, no “cannot leech”)
- Optional Vaal for 8-mod / unidentified
- Currency slots already mapped in Settings (chisel, alchemy, chaos, scour, vaal)

This is the natural next tile on the home screen next to Chain craft.

### Other useful additions
- **Map device** — after Map Craft, put the finished map in the device and hit Activate (with fragment / scarab slots if mapped)
- **Harvest bench** — more than the current “use this craft” step: pick a craft from the grove UI by name
- **Bulk identify / sell** — Ctrl+click a grid of rares into a dump tab or NPC
- **Flask / jewel recipes** — same scenario engine, different item classes and stop mods
- **Job queue** — Reveal → Confirm → Map Craft in one hotkey without going back to the home screen
- **PoE window bind** — lock overlays to the game client rectangle so they survive resolution / move

## License

Personal / local use. Path of Exile and related art are trademarks of Grinding Gear Games.
