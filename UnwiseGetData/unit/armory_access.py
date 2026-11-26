import json
import re
import logging
import os

FACTIONS = []
UNIT_CATEGORIES = ["HQ","Troops","Elite","Fast Attack","Heavy Support", "Transports", "Fortifications", "Flyers"]
UNIT_PATH = {
    "HQ":"hq",
    "Troops":"troops",
    "Elite":"elites",
    "Fast Attack":"fast_attack",
    "Heavy Support":"heavy_support",
    "Transports":"dedicated_transport",
    "Fortifications":"fortifications",
    "Flyers":"flyers"
}
CREATURE_FORMAT = ["No.","NAME","M","WS","BS","S","T","W","I","A","LD","SV","POINTS"]
VEHICLE_FORMAT = ["No.","NAME","M","WS","BS","S","FRONT", "SIDE", "REAR", "I","A","HP", "POINTS"]
WEAPON_FORMAT = ["WEAPON", "RANGE", "TYPE", "S", "AP", "D", "ABILITIES"]

NUMBERS_DICT = {"a": 1, "an": 1, "the": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
def convert_to_int(s):
    return NUMBERS_DICT[s.lower()] if s.lower() in NUMBERS_DICT else int(s)

# Sanitises a name
def sanitise_name(value):
    return str(value).lower().replace("'", "").replace(" ", "_").replace("\u00b4", "")

# Make a list of all the troops that exist in the faction's Index.json file. 
def process_faction_units(faction_path, faction_name):
    ret = {}
    with open(f"../raw/{faction_path}/index.json", "r") as f:
        #sheet is a list of lists, where each inner list is a row in the sheet. Data format: NxN
        sheet = json.load(f)
        #Make sure the correct faction is being processed. "join" is a syntax trick for converting strings. If it's correct, remove it.
        if "".join(sheet[0]) != faction_name:
            print(f"{sheet[0]} found, expected {faction_name}. Stopping the program.")
            exit()
        sheet = sheet[1:]
            
        #special rules are placed on the same collumn as HQ, so we remove them.
        sheet[0] = sheet[0][:sheet[0].index("Special rules")]
            
        for troop_category in sheet:
            # The first element of each troop_category should be the category name, check if it is valid
            category = "".join(troop_category[0])
            if category not in UNIT_CATEGORIES:
                print(f"{category} is not a valid unit category: {UNIT_CATEGORIES}. Stopping the program.")
                exit()
                
            ret[category] = troop_category[1:]
                
    return ret

def process_model(model_data, model_format):
    m, M = 1,1
    if "-" in str(model_data[0]):
        m, M = model_data[0].split("-")
    elif "*" in str(model_data[0]):
        m, M = 0, 1
    else:
        m, M = model_data[0], model_data[0]
    
    model_data = [str(x) for x in model_data]
    ret_model = {"stats": dict(zip(model_format[2:-1], model_data[2:-1]))}
    ret_model["name"] = model_data[1]
    ret_model["min"] = int(m)
    ret_model["max"] = int(M)
    ret_model["points"] = int(model_data[-1]) if "-" not in str(model_data[-1]) else 0
    
    # print(ret_model)
    return ret_model

# Takes a weapon column from the unit sheet and formats it into the app's weapon data format. Returns a dictionary with the weapon data.
def process_weapon(weapon_data):
    APP_FORMAT = "name", "range","type", "s", "ap", "d", "abilities"
    weapon_data = [str(x) for x in weapon_data]
    return dict(zip(APP_FORMAT, weapon_data))

# OPTION MAPPING
# "For every <n> models, <n> <model_name> may swap <number> <weapon/gear> for <number> <weapon/gear>."
# "For every <n> models, <n> <model_name> may be equipped with <number> <weapon/gear>."
def proccess_option(option_data):
    
    header = "".join(option_data[0])
    
    ret_option = {"header": header, "inline_pts": None, "variant_link": None, "is_unique_per_army": False}
    constraint = {}
    
    ### How many models can take this option - per_n / fixed_max / every
    if re.search(r"For every .* models?, ", header):  
        constraint["type"] = "per_n"
            
        number = re.findall(r"For every (.*) models?, ", header)[0]
        constraint["per_n"]: convert_to_int(number)
    
    elif re.search(r"up to .* models?, ", header):
        constraint["type"] = "fixed_max"
            
        number = re.findall(r"up to (.*) models?, ", header)[0]
        constraint["max"]: convert_to_int(number)
    
    elif re.search(r"The unit may ", header):
        constraint["type"] = "every"
        
    else:
        logging.error(f"NO VALID CONSTRAINT FOUND FOR OPTION HEADER: {header}. Stopping the program.")
        exit()
    
    ### REPLACEMENTS
    if re.search(r"[Mm]ay swap", header):
        number = re.split(r", (.*) [Mm]ay swap", header)[1].split(" ")[0]
        constraint["count_per_n"]: convert_to_int(number)
            
    
    #swaps
    if re.search(r" swap ", header):
        choices = []
        
        print(f"Processing option: {header}")
        
        ### X model(s) may swap its/their <weapon/gear> for <weapon/gear>
        
            
        ### "may swap its/their <weapon/gear>:"
        print("\n\n\n")
        print(re.split(r"[Mm]ay swap their ", header))
        print("\n\n\n")
        swapped_weapon = re.split(r"[Mm]ay swap their ", header)[1].split(":")[0]
        ret_option["replaces"] = swapped_weapon
    
        option_data = option_data[1:]
        
        ### Get the list of {name: <weapon/gear>, points: <points>} for the swapped weapons/gear.
        while "- " in option_data[0][0]:
            replacment_name = "".join(option_data[0][0]).replace("- ", "")
            
            #drop the + and points from the end of the name
            replacement_points = "".join(option_data[0][1])
            replacement_points = int(replacement_points.replace("+", "").replace("pts", "").replace("points", "").strip())
            
            choices.append({"name": replacment_name, "points": replacement_points})
            
            option_data = option_data[1:]
            
        ret_option["choices"] = choices
    
    #may be equipped with
    elif re.search(r"may be equipped with:", header):
        pass
        ### TODO: Implement the "may be equipped with" header processing.
        
    option_data = option_data[1:]
    ret_option["constraint"]: constraint
    return ret_option, option_data

def process_swap_option(header, option_data, unit):
    ret_option = {}
    print(f"------- SWAP --------")
    if (re.search(r"\b(may|can)\b swap \b(their|the|each|its)\b", header, re.IGNORECASE)):
        # Single model with swap each
        swappable = re.findall(r"swap \b(their|the|each|its)\b \b(.+?):{0,1}$", header, re.IGNORECASE)
        print(f"Found swappable {swappable} for {unit}")
        ret_option["replaces"] = [swappable[0][1]]
        ret_option["constraint"] = {"type":"one"}
        pass
    elif (re.search(r"\b(may|can)\b swap \b(both|one|a|an|any|\d+)\b", header, re.IGNORECASE)):
            # Single model with swap a number of
            
            pass
    elif (re.search(fr"\b(.+)\b \b{unit}\b may swap", header, re.IGNORECASE)):
        # Number of swappable units
        pass
    else:
        print(f"{unit} with {option_data} didn't match anything")

    print(ret_option)

def add_armory_to_models(armory, models):
    for m in models:
        add_armory_to_model(armory, m)

def add_armory_to_model(armory, model):
    if not "armory" in model:
        model.update({"armory": [armory]})
    else:
        model.update({"armory": model["armory"].append(armory)})

ARMORY_CATEGORIES = ["melee weapons", "ranged weapons", "gear", "vehicle equipment", "weapons"]

def get_armory_category(raw):
    cleaned = re.sub(r"\band\b", ",", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfrom\b", "", cleaned, flags=re.IGNORECASE)
    csv_cats = cleaned.split(",")
    # default access is weapons and gear
    if len(csv_cats) == 0 or len(csv_cats[0]) == 0:
        return ["weapons", "gear"]

    # Warn about missing categories
    unknown_entries = [c for c in list(map(lambda x: x.strip(), csv_cats)) if c not in ARMORY_CATEGORIES]
    if len(unknown_entries) > 0:
        print(f"Unknown armory categories: {unknown_entries}")

    # Map categories
    return [c for c in list(map(lambda x: x.strip(), csv_cats)) if c in ARMORY_CATEGORIES]

# When a different name is used
ALTERNATIVE_NAME_MAP = {
    "infiltrator_princeps": ["ruststalker_princeps"],
    "terminator_champion": ["deathshroud_terminator_champion"],
    "aspiring_chaos_space_marine_champion": ["aspiring_champion"]
}

def process_armory_access(header, app_unit_json):
    # NOTE: THIS IS NOT A gains CHECKS, JUST has have got
    # Typo in Custodes --> acces == access
    has_access = re.findall(r"(.*?)\b(has|have|got)\b \baccess?\b to\b (.*?)\bthe Armory\b(.*)", header, re.IGNORECASE)
    
    print(header)
    print(has_access)
    if (has_access):
        # match[0][0] = unit names or conditions
        model_or_condition = has_access[0][0]
        armory = {
            "name": "-", # General armory
            "categories": get_armory_category(has_access[0][2]),
            "conditions": re.sub(r"\.$", "", has_access[0][3].strip())
        }

        # if no model or condition, it applies to the whole unit
        # all/each/every, applies to the whole unit
        if (not model_or_condition or len(model_or_condition) == 0 or re.search(r"\b(all|every|each)\b model", header, re.IGNORECASE)):
            app_unit_json.update({"armory": armory})
            return True

        # Some entries use split upgrade/promoted. We are just setting the armory stuff, so ignore the rest (for now)
        # TODO - SET CHAMPION UPGRADE IF FOUND
        check_name = model_or_condition.split(".")[-1].strip()

        # Check for exact model in unit and apply armory to it instead
        check_name = sanitise_name(re.sub(r"^The\b", "", check_name, flags=re.IGNORECASE).strip())
        print(f"Checking -- {check_name}")
        found_model = False
        for m in app_unit_json["models"]:
            if check_name == sanitise_name(m["name"]) or (check_name in ALTERNATIVE_NAME_MAP and sanitise_name(m["name"]) in ALTERNATIVE_NAME_MAP[check_name]):
                found_model = True
                add_armory_to_model(armory, m)
        for m in app_unit_json["variant_models"]:
            if check_name == sanitise_name(m["name"]) or (check_name in ALTERNATIVE_NAME_MAP and sanitise_name(m["name"]) in ALTERNATIVE_NAME_MAP[check_name]):
                found_model = True
                add_armory_to_model(armory, m)
        if found_model:
            return True

    champion_has_access = re.findall(r"(.*?)\b(may|can) be\b \b(upgraded|promoted)\b \bto\b \ban?\b (.*?) (\bfor \+(.*)(pts|points)\b)? \band gains\b \baccess?\b to\b (.*?)\bthe Armory\b(.*)", header, re.IGNORECASE)
    if (champion_has_access):
        # TODO - SET CHAMPION UPGRADE IF FOUND
        print(f"CHAMP --> {champion_has_access}")
        champion_model = champion_has_access[0][3]
        armory = {
            "name": "-", # General armory
            "categories": get_armory_category(champion_has_access[0][7]),
            "conditions": re.sub(r"\.$", "", champion_has_access[0][8].strip())
        }

        # Check for exact model in unit and apply armory to it instead
        check_name = sanitise_name(re.sub(r"^The\b", "", champion_model, flags=re.IGNORECASE).strip())
        print(f"Checking -- {check_name}")
        found_model = False
        for m in app_unit_json["models"]:
            if check_name == sanitise_name(m["name"]) or (check_name in ALTERNATIVE_NAME_MAP and sanitise_name(m["name"]) in ALTERNATIVE_NAME_MAP[check_name]):
                found_model = True
                add_armory_to_model(armory, m)
        for m in app_unit_json["variant_models"]:
            if check_name == sanitise_name(m["name"]) or (check_name in ALTERNATIVE_NAME_MAP and sanitise_name(m["name"]) in ALTERNATIVE_NAME_MAP[check_name]):
                found_model = True
                add_armory_to_model(armory, m)
        if found_model:
            return True
        
        # The Infiltrator Princeps has access to weapons and gear from the Armory. >> Sicaran Ruststalkers

        #     add_armory_to_models(armory, app_unit_json["models"])
        #     add_armory_to_models(armory, app_unit_json["variant_models"])
        #     print(app_unit_json)
        #     return
                
    #         for m in app_unit_json["models"]:
    #             if model_or_condition == sanitise_name(m["name"]):
    #                 m["has_armory_access"] = True
    #                 m["categories"] = match[0][2]
    #                 m["conditions"] = match[0][3]
            
    #         for v in app_unit_json["variant_models"]:
    #             if model_or_condition == sanitise_name(v["name"]):
    #                 v["has_armory_access"] = True
    #                 v["categories"] = match[0][2]
    #                 v["conditions"] = match[0][3]

        # match[0][1] = has/have/got
        # match[0][2] => 
            # weapons and gear from
            # gear from
            # weapons from
            # vehicle equipment from
            # melee weapons from
            # empty string
        # match[0][3] = additional conditions
    return False


# Intermediary step. Take the formatted data and format it into the app's unit data format. Save it to the processed folder.
def main():
    
    with open("../factions.csv", "r") as f:
        FACTIONS = [line.split(",")[0] for line in f.readlines() if line.strip()]

    FACTIONS = ["Chaos Space Marines"]
    UNITS = []
    skipped_option = {}

    
    with open("skipped_options.txt", "w") as skipped_options_out:
        print(f"Factions found:{FACTIONS}")
        for faction in FACTIONS:
            
            faction_path = sanitise_name(faction)
            print(f"Processing {faction}...")
            faction_units = process_faction_units(faction_path, faction)
            print(f"Faction troops: {faction_units}")
            
            processed_faction_units = {}
            for category, units in faction_units.items():
                for unit in units:
                    unit_name = "".join(unit)
                    if UNITS and not unit_name in UNITS:
                        continue
                    unit_lowercase_name = sanitise_name(unit_name)
                    raw_unit_path = f"../raw/{faction_path}/{unit_lowercase_name}"
                    
                    app_unit_json = {"name" : unit_name, "models": []}
                    with open(f"{raw_unit_path}.json", "r") as f:
                        unit_sheet = json.load(f)
                        print(f"\nProcessing {unit} at {raw_unit_path}.json")
                        
                        # Make sure the models are in the correct format, then discard it.
                        if unit_sheet[0] != CREATURE_FORMAT:
                            if unit_sheet[0] != VEHICLE_FORMAT:
                                print(f"Model format mismatch for {unit}. Expected {CREATURE_FORMAT}, got {unit_sheet[0]}. Stopping the program.")
                                exit()
                            else:
                                model_format = VEHICLE_FORMAT
                        else:
                            model_format = CREATURE_FORMAT
                        
                        unit_sheet = unit_sheet[1:]
                        
                        ### MODELS
                        # Process all models in the unit sheet until we reach the weapons section.
                        while("equipped with" not in "".join(str(unit_sheet[0]))):
                            # print(f"raw data: {unit_sheet[0]}")
                            model = process_model(unit_sheet[0], model_format)
                            if "*" in str(unit_sheet[0][0]):
                                if "variant_models" not in app_unit_json:
                                    app_unit_json["variant_models"] = [model]
                                else:
                                    app_unit_json["variant_models"].append(model)
                            else:
                                app_unit_json["models"].append(model)
                            
                            # Make sure there is a variant_models field
                            if "variant_models" not in app_unit_json:
                                app_unit_json["variant_models"] = []
                            
                            unit_sheet = unit_sheet[1:]
                        
                        # calculate the min_cost of the unit based on the models and their points values
                        app_unit_json["min_cost"] = max(1, sum([(m["points"] * m["min"]) for m in app_unit_json["models"]]))
                        # make sure the min_cost isnt zero, if it is, set it to 1. 
                        # set the default size of the unit
                        app_unit_json["default_size"] = sum([m["min"] for m in app_unit_json["models"]])
                        
                        ### WEAPONS
                        app_unit_json["equipped_with"] = ""
                        while "equipped with" in "".join(unit_sheet[0]):
                            app_unit_json["equipped_with"] = (app_unit_json["equipped_with"] + " " + "".join(unit_sheet[0])).strip()
                            unit_sheet = unit_sheet[1:]
                        
                        # Make sure the weapons are in the correct format, then discard it.
                        if unit_sheet[0] != WEAPON_FORMAT:
                            print(f"Weapon format mismatch for {unit}. Expected {WEAPON_FORMAT}, got {unit_sheet[0]}. Stopping the program.")
                            exit()
                        unit_sheet = unit_sheet[1:]
                    
                        # Process all weapons in the unit sheet until we reach the options section.
                        app_unit_json["weapons"] = []
                        while "OPTIONS" not in unit_sheet[0]:
                            # print(f"{unit_sheet[0]}")
                            #check for no weapons
                            if "-" == "".join(unit_sheet[0][0]):
                                unit_sheet = unit_sheet[1:]
                                continue
                            #check for variant weapons. HILARIOUS - this accidentally handles the case where a unit has "* Choose one of the following profiles" at the end by deleting it.
                            if "*" in unit_sheet[0][0]:
                                temp_weapon_name = unit_sheet[0][0].replace("*", "")
                                unit_sheet = unit_sheet[1:]
                                while "- " in unit_sheet[0][0]:
                                    unit_sheet[0][0] = temp_weapon_name + unit_sheet[0][0]
                                    app_unit_json["weapons"].append(process_weapon(unit_sheet[0]))
                                    unit_sheet = unit_sheet[1:]
                            else:
                                app_unit_json["weapons"].append(process_weapon(unit_sheet[0]))
                                unit_sheet = unit_sheet[1:]
                        
                        ### OPTIONS           
                        unit_sheet = unit_sheet[1:]
                        option_groups = []

                        while "ABILITIES" not in unit_sheet[0]:
                            header = " ".join(unit_sheet[0])
                            header = re.sub(r"^[•]", "", header.strip()).strip()
                            if (process_armory_access(header, app_unit_json)):
                                print(f"ARMORY UPDATED -- {app_unit_json}")
                                unit_sheet = unit_sheet[1:]
                            # may swap X for Y 
                            elif re.search(r"\b(may|can)\b swap", header, re.IGNORECASE):
                                option_groups.append(process_swap_option(header, unit_sheet, unit))
                                unit_sheet = unit_sheet[1:]
                            else:
                                # Unsupported options
                                unit_sheet = unit_sheet[1:]
                                skipped_option[header] = unit_name
                        ### ABILITIES
                        unit_sheet = unit_sheet[1:]
                        app_unit_json["abilities"] = []
                        # Process all abilities in the unit sheet until we reach the UNIT TYPE section.
                        while "UNIT TYPE" not in unit_sheet[0]:
                            # ignore the "Upgrades:" row, as it is not needed in the app.
                            if "Upgrades:" in unit_sheet[0]:
                                unit_sheet = unit_sheet[1:]
                                continue
                            app_unit_json["abilities"] = app_unit_json["abilities"] + (unit_sheet[0])
                            unit_sheet = unit_sheet[1:]
                        
                        unit_sheet = unit_sheet[1:]
                        
                        ### UNIT TYPE
                        # Add the unit type, switch to the next row, which should be the KEYWORDS section.
                        app_unit_json["unit_type"] = "".join(unit_sheet[0])
                        app_unit_json["is_monster"] = "Monstrous Creature" in app_unit_json["unit_type"]
                        app_unit_json["is_character"] = "Character" in app_unit_json["unit_type"]
                        app_unit_json["is_vehicle"] = ("Vehicle" in app_unit_json["unit_type"]) | ("Walker" in app_unit_json["unit_type"])
                        unit_sheet = unit_sheet[1:]
                        
                        ### KEYWORDS  
                        #if there are no keywords this will be the last row, so we check for that and set keywords to an empty list if so.
                        if len(unit_sheet) == 0:
                            app_unit_json["keywords"] = []
                        elif unit_sheet[0] != ["KEYWORDS"]:
                            print(f"Keywords format mismatch for {unit}. Expected ['KEYWORDS'], got {unit_sheet[0]}. Stopping the program.")
                            exit()
                        else:
                            unit_sheet = unit_sheet[1:]
                            app_unit_json["keywords"] = unit_sheet[0]
            
                    # Save the processed unit data to its respective path.
                    processed_unit_dir = f"../processed/{faction_path}/{UNIT_PATH[category]}"
                    processed_unit_path = f"{processed_unit_dir}/{unit_lowercase_name}.json"
                    os.makedirs(processed_unit_dir, exist_ok=True)
                    with open(processed_unit_path, "w") as f:
                        json.dump(app_unit_json, f, indent=4)
            for k,v in skipped_option.items():
                skipped_options_out.write(f"{k} >> {v}\n")
                    
if __name__ == "__main__":
    main()