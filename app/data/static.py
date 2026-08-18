"""Справочники, которые не приходят из RePoE: типы слотов, валюта, Harvest."""

ITEM_TYPE_GROUPS = [
    {
        "id": "armour",
        "name_ru": "Броня",
        "classes": ["Gloves", "Boots", "Helmet", "Body Armour", "Shield"],
    },
    {
        "id": "jewellery",
        "name_ru": "Бижутерия",
        "classes": ["Amulet", "Ring", "Belt"],
    },
    {
        "id": "weapon",
        "name_ru": "Оружие",
        "classes": [
            "Claw",
            "Dagger",
            "Rune Dagger",
            "Wand",
            "One Hand Sword",
            "Thrusting One Hand Sword",
            "One Hand Axe",
            "One Hand Mace",
            "Sceptre",
            "Bow",
            "Staff",
            "Warstaff",
            "Two Hand Sword",
            "Two Hand Axe",
            "Two Hand Mace",
        ],
    },
    {
        "id": "other",
        "name_ru": "Прочее",
        "classes": ["Quiver"],
    },
    {
        "id": "heist",
        "name_ru": "Heist",
        "classes": [
            "HeistEquipmentReward",
            "HeistEquipmentUtility",
            "HeistEquipmentWeapon",
            "HeistEquipmentTool",
            "Trinket",
            "HeistContract",
        ],
    },
    {
        "id": "jewels",
        "name_ru": "Самоцветы",
        "classes": ["Jewel", "AbyssJewel", "ClusterJewel"],
    },
]

ITEM_TYPE_NAMES_RU = {
    "Gloves": "Перчатки",
    "Boots": "Сапоги",
    "Helmet": "Шлем",
    "Body Armour": "Нагрудник",
    "Shield": "Щит",
    "Amulet": "Амулет",
    "Ring": "Кольцо",
    "Belt": "Пояс",
    "Claw": "Когти",
    "Dagger": "Кинжалы",
    "Rune Dagger": "Рунные кинжалы",
    "Wand": "Жезлы",
    "One Hand Sword": "Одноручные мечи",
    "Thrusting One Hand Sword": "Рапиры",
    "One Hand Axe": "Одноручные топоры",
    "One Hand Mace": "Одноручные булавы",
    "Sceptre": "Скипетры",
    "Bow": "Луки",
    "Staff": "Посохи",
    "Warstaff": "Боевые посохи",
    "Two Hand Sword": "Двуручные мечи",
    "Two Hand Axe": "Двуручные топоры",
    "Two Hand Mace": "Двуручные булавы",
    "Quiver": "Колчаны",
    "Jewel": "Самоцветы",
    "AbyssJewel": "Самоцветы Бездны",
    "ClusterJewel": "Кластерные самоцветы",
    "HeistEquipmentReward": "Броши",
    "HeistEquipmentUtility": "Плащи",
    "HeistEquipmentWeapon": "Снаряжение",
    "HeistEquipmentTool": "Инструменты",
    "Trinket": "Безделушки",
    "HeistContract": "Контракты",
}

ITEM_TYPE_NAMES = {
    "HeistEquipmentReward": "Heist Brooches",
    "HeistEquipmentUtility": "Heist Cloaks",
    "HeistEquipmentWeapon": "Heist Gear",
    "HeistEquipmentTool": "Heist Tools",
    "Trinket": "Trinkets",
    "HeistContract": "Contracts",
}

CRAFTABLE_CLASSES = [cls for group in ITEM_TYPE_GROUPS for cls in group["classes"]]

CRAFT_TYPES = [
    {
        "id": "basic_currency",
        "name": "Basic Currency",
        "name_ru": "Обычная валюта",
        "description": "Хаос, алхимия, экзальт, аннул и остальные сферы",
    },
    {
        "id": "harvest",
        "name": "Harvest",
        "name_ru": "Harvest",
        "description": "Перековка, смена резистов и add/remove за lifeforce",
    },
]

BASIC_CURRENCY = [
    {"id": "transmutation", "name": "Orb of Transmutation", "name_ru": "Сфера превращения"},
    {"id": "augmentation", "name": "Orb of Augmentation", "name_ru": "Сфера улучшения"},
    {"id": "alteration", "name": "Orb of Alteration", "name_ru": "Сфера перемен"},
    {"id": "alchemy", "name": "Orb of Alchemy", "name_ru": "Сфера алхимии"},
    {"id": "chaos", "name": "Chaos Orb", "name_ru": "Сфера хаоса"},
    {"id": "regal", "name": "Regal Orb", "name_ru": "Сфера царей"},
    {"id": "exalted", "name": "Exalted Orb", "name_ru": "Сфера возвышения"},
    {"id": "annulment", "name": "Orb of Annulment", "name_ru": "Сфера отмены"},
    {"id": "scouring", "name": "Orb of Scouring", "name_ru": "Сфера очищения"},
    {"id": "blessed", "name": "Blessed Orb", "name_ru": "Благодатная сфера"},
    {"id": "divine", "name": "Divine Orb", "name_ru": "Божественная сфера"},
    {"id": "vaal", "name": "Vaal Orb", "name_ru": "Сфера ваал"},
    {"id": "chance", "name": "Orb of Chance", "name_ru": "Сфера удачи"},
]

HARVEST_ACTIONS = [
    {"id": "harvest_reforge_fire", "name": "Reforge including a Fire modifier", "name_ru": "Перековать с модом огня", "tag": "fire"},
    {"id": "harvest_reforge_cold", "name": "Reforge including a Cold modifier", "name_ru": "Перековать с модом холода", "tag": "cold"},
    {"id": "harvest_reforge_lightning", "name": "Reforge including a Lightning modifier", "name_ru": "Перековать с модом молнии", "tag": "lightning"},
    {"id": "harvest_reforge_physical", "name": "Reforge including a Physical modifier", "name_ru": "Перековать с физическим модом", "tag": "physical"},
    {"id": "harvest_reforge_life", "name": "Reforge including a Life modifier", "name_ru": "Перековать с модом жизни", "tag": "life"},
    {"id": "harvest_reforge_defence", "name": "Reforge including a Defence modifier", "name_ru": "Перековать с модом защиты", "tag": "defence"},
    {"id": "harvest_reforge_chaos", "name": "Reforge including a Chaos modifier", "name_ru": "Перековать с модом хаоса", "tag": "chaos"},
    {"id": "harvest_reforge_attack", "name": "Reforge including an Attack modifier", "name_ru": "Перековать с атакующим модом", "tag": "attack"},
    {"id": "harvest_reforge_caster", "name": "Reforge including a Caster modifier", "name_ru": "Перековать с кастерским модом", "tag": "caster"},
    {"id": "harvest_reforge_speed", "name": "Reforge including a Speed modifier", "name_ru": "Перековать с модом скорости", "tag": "speed"},
    {"id": "harvest_reforge_critical", "name": "Reforge including a Critical modifier", "name_ru": "Перековать с критическим модом", "tag": "critical"},
    {"id": "harvest_reforge_minion", "name": "Reforge including a Minion modifier", "name_ru": "Перековать с модом миньонов", "tag": "minion"},
    {"id": "harvest_reforge_elemental", "name": "Reforge including an Elemental modifier", "name_ru": "Перековать с стихийным модом", "tag": "elemental"},
    {"id": "harvest_reforge_attribute", "name": "Reforge including an Attribute modifier", "name_ru": "Перековать с модом характеристик", "tag": "attribute"},
    {"id": "harvest_reforge_mana", "name": "Reforge including a Mana modifier", "name_ru": "Перековать с модом маны", "tag": "mana"},
    {"id": "harvest_reforge_more_likely", "name": "Reforge, more likely same modifier types", "name_ru": "Перековать, те же типы модов вероятнее"},
    {"id": "harvest_reforge_less_likely", "name": "Reforge, less likely same modifier types", "name_ru": "Перековать, те же типы модов менее вероятны"},
    {"id": "harvest_swap_cold_to_fire_res", "name": "Change Cold Resistance into Fire Resistance", "name_ru": "Сопротивление холоду → огню"},
    {"id": "harvest_swap_lightning_to_fire_res", "name": "Change Lightning Resistance into Fire Resistance", "name_ru": "Сопротивление молнии → огню"},
    {"id": "harvest_swap_fire_to_cold_res", "name": "Change Fire Resistance into Cold Resistance", "name_ru": "Сопротивление огню → холоду"},
    {"id": "harvest_swap_lightning_to_cold_res", "name": "Change Lightning Resistance into Cold Resistance", "name_ru": "Сопротивление молнии → холоду"},
    {"id": "harvest_swap_fire_to_lightning_res", "name": "Change Fire Resistance into Lightning Resistance", "name_ru": "Сопротивление огню → молнии"},
    {"id": "harvest_swap_cold_to_lightning_res", "name": "Change Cold Resistance into Lightning Resistance", "name_ru": "Сопротивление холоду → молнии"},
    {"id": "harvest_add_remove_fire", "name": "Add a Fire modifier and remove another random modifier", "name_ru": "Добавить огонь, снять случайный мод"},
    {"id": "harvest_add_remove_cold", "name": "Add a Cold modifier and remove another random modifier", "name_ru": "Добавить холод, снять случайный мод"},
    {"id": "harvest_add_remove_lightning", "name": "Add a Lightning modifier and remove another random modifier", "name_ru": "Добавить молнию, снять случайный мод"},
    {"id": "harvest_add_remove_physical", "name": "Add a Physical modifier and remove another random modifier", "name_ru": "Добавить физ. мод, снять случайный"},
    {"id": "harvest_add_remove_life", "name": "Add a Life modifier and remove another random modifier", "name_ru": "Добавить жизнь, снять случайный мод"},
    {"id": "harvest_add_remove_defence", "name": "Add a Defence modifier and remove another random modifier", "name_ru": "Добавить защиту, снять случайный мод"},
    {"id": "harvest_add_remove_chaos", "name": "Add a Chaos modifier and remove another random modifier", "name_ru": "Добавить хаос, снять случайный мод"},
    {"id": "harvest_add_remove_attack", "name": "Add an Attack modifier and remove another random modifier", "name_ru": "Добавить атаку, снять случайный мод"},
    {"id": "harvest_add_remove_caster", "name": "Add a Caster modifier and remove another random modifier", "name_ru": "Добавить кастер, снять случайный мод"},
    {"id": "harvest_add_remove_speed", "name": "Add a Speed modifier and remove another random modifier", "name_ru": "Добавить скорость, снять случайный мод"},
    {"id": "harvest_add_remove_critical", "name": "Add a Critical modifier and remove another random modifier", "name_ru": "Добавить крит, снять случайный мод"},
    {"id": "harvest_reforge_influence", "name": "Reforge an Influenced Rare including an Influence modifier", "name_ru": "Перековать влияние с influence-модом"},
    {"id": "harvest_randomise_influence", "name": "Randomise Influence types and reforge modifiers", "name_ru": "Случайно сменить влияние и перековать"},
]


def actions_for_craft_type(craft_type_id: str) -> list[dict]:
    if craft_type_id == "harvest":
        return HARVEST_ACTIONS
    return BASIC_CURRENCY


def item_type_label(item_class: str) -> str:
    from app.i18n import t

    return t(f"item.{item_class}", default=item_class)


def action_label(action: dict) -> str:
    from app.i18n import t

    return t(f"action.{action['id']}", default=action.get("name") or action["id"])


def craft_type_label(craft_type_id: str) -> str:
    from app.i18n import t

    return t(f"craft.{craft_type_id}", default=craft_type_id)
