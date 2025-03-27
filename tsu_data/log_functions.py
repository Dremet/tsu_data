import pandas as pd
from pathlib import Path


def read_event_log(input_file_path: Path):
    with open(input_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return lines


def parse_meta_data(lines):
    """
    Reads driver data, tire compounds, and MaxFuel.
    Returns: (df_drivers, df_compounds, max_fuel).
    """
    driver_data = []
    compounds = {}
    parse_mode = None
    max_fuel = None

    for line in lines:
        raw = line.strip()
        if raw.startswith("PlayerCount"):
            parse_mode = "players"
            continue
        elif raw.startswith("TireCompoundCount"):
            parse_mode = "tires"
            continue
        elif raw.startswith("MaxFuel"):
            parts = raw.split()
            if len(parts) > 1:
                max_fuel = float(parts[1])
            continue

        if raw.startswith("Events"):
            break
        if not parse_mode:
            continue
        if not raw or raw.startswith("#"):
            continue

        if parse_mode == "players":
            parts = raw.split(maxsplit=4)
            if len(parts) < 4:
                continue
            try:
                driver_id = int(parts[0])
                steam_id = parts[1]
                # parts[2] is just a zero we do not need
                if parts[3].startswith("["):
                    team = parts[3]
                    name = parts[4]
                else:
                    team = ""
                    name = parts[3]
                driver_data.append([driver_id, steam_id, team, name])
            except ValueError:
                pass

        elif parse_mode == "tires":
            parts = raw.split()
            if len(parts) < 4:
                continue
            try:
                idx = int(parts[0])
                name = parts[1]
                max_wear = float(parts[2])
                max_perf = float(parts[3])
                compounds[idx] = {
                    "name": name,
                    "max_wear": max_wear,
                    "max_performance": max_perf,
                }
            except ValueError:
                pass

    df_drivers = pd.DataFrame(
        driver_data, columns=["driver_id", "steam_id", "team", "name"]
    )

    df_compounds = pd.DataFrame.from_dict(compounds, orient="index")

    return df_drivers, df_compounds, max_fuel


def parse_events(lines, df_compounds, max_fuel):
    """
    Parses lines after 'Events' into a DataFrame:
     [time, type, driver_id, laps, fuel, tire_wear, tire_compound, hit_points,
      tire_percentage, fuel_percentage]

    tire_percentage = 100 - (tire_wear / max_wear * 100)
    fuel_percentage = 100 - (fuel / max_fuel * 100)
    """
    found_events = False
    ev_list = []

    for line in lines:
        raw = line.strip()
        if raw.startswith("Events"):
            found_events = True
            continue
        if not found_events:
            continue

        if not raw or raw.startswith("#"):
            continue

        parts = raw.split()
        if len(parts) < 8:
            continue

        try:
            time_ = int(parts[0])
            etype = parts[1]
            drv = int(parts[2])
            laps_ = int(parts[3])
            fuel_ = float(parts[4])
            wear_ = float(parts[5])
            comp_ = int(parts[6])
            hp_ = int(parts[7])

            max_wear = df_compounds.iloc[comp_]["max_wear"]

            mf = max_fuel if (max_fuel and max_fuel > 0) else 1.0

            t_pct = 100.0 - (wear_ / max_wear * 100.0)
            f_pct = fuel_ / mf * 100.0

            ev_list.append(
                [time_, etype, drv, laps_, fuel_, wear_, comp_, hp_, t_pct, f_pct]
            )
        except ValueError:
            pass

    cols = [
        "time",
        "type",
        "driver_id",
        "laps",
        "fuel",
        "tire_wear",
        "tire_compound",
        "hit_points",
        "tire_percentage",
        "fuel_percentage",
    ]
    df = pd.DataFrame(ev_list, columns=cols)

    # Get starting positions based on the "Start" event
    # The dictionary maps the driver's position index to their driver_id
    start_order = df.loc[df["type"] == "Start", "driver_id"].to_dict()

    # Create a mapping from driver_id to their starting position (1-based)
    # We need to swap keys and values correctly
    start_pos_by_driver_id = {
        driver_id: position + 1 for position, driver_id in start_order.items()
    }

    df.sort_values("time", inplace=True, ignore_index=True)

    return df, start_pos_by_driver_id


def find_best_lap_time(events_df):
    """
    Returns the minimal time difference (in milliseconds) between consecutive
    'Lap' events for any driver. If no laps exist, returns a fallback of 200000.
    """
    # Filter out only 'Lap' events
    lap_events = events_df[events_df["type"] == "Lap"].copy()
    if lap_events.empty:
        return 200000  # fallback if no Lap events

    # We'll group by player, so we can find consecutive Lap events for each driver
    best_lap_time = None
    grouped = lap_events.groupby("player")

    for drv, sub in grouped:
        # Sort that driver's Lap events by time
        sub_sorted = sub.sort_values("time", ascending=True)
        times = sub_sorted["time"].tolist()
        # Check consecutive differences
        for i in range(len(times) - 1):
            dt = times[i + 1] - times[i]  # difference
            if best_lap_time is None or dt < best_lap_time:
                best_lap_time = dt

    if best_lap_time is None:
        return 200000  # no consecutive laps found, fallback
    return best_lap_time


def is_pit_event_before_finish_line(time_lap_start, time_lap_end, pit_event_time):
    # if time diff to end of lap is bigger than to the start we have already crossed the line
    return time_lap_end - pit_event_time < pit_event_time - time_lap_start


def get_details_df(df_events, start_pos_by_driver_id):
    df_events = df_events.sort_values("time", ascending=True).reset_index(drop=True)
    driver_ids = pd.unique(df_events["driver_id"]).tolist()

    details_dict = {}

    # We always process data for one driver at a time
    for driver_id in driver_ids:
        # initialize driver data
        dd = {}

        # Process events chronologically
        # and skip pit events for now
        for _, ev in df_events.iterrows():
            drv_id = ev["driver_id"]
            type = ev["type"]

            if drv_id != driver_id or type in {"PitIn", "PitOut"}:
                continue

            laps_compl = ev["laps"]
            current_lap = laps_compl + 1
            tc = ev["tire_compound"]
            tw = ev["tire_wear"]
            tp = ev["tire_percentage"]
            f = ev["fuel"]
            fp = ev["fuel_percentage"]
            hp = ev["hit_points"]
            time = ev["time"]

            dd[current_lap] = {
                "driver_id": drv_id,
                "time_start": time,
                "time_end": None,
                "lap": current_lap,
                "tire_compound_start": tc,
                "tire_wear_start": tw,
                "tire_wear_end": None,
                "tire_perc_start": tp,
                "tire_perc_end": None,
                "fuel_used_start": f,
                "fuel_used_end": None,
                "fuel_perc_start": fp,
                "fuel_perc_end": None,
                "hit_points_start": hp,
                "hit_points_end": None,
                "is_inlap": False,
                "is_outlap": False,
            }

            if current_lap != 1:
                dd[laps_compl]["time_end"] = time
                dd[laps_compl]["tire_wear_end"] = tw
                dd[laps_compl]["tire_perc_end"] = tp
                dd[laps_compl]["fuel_used_end"] = f
                dd[laps_compl]["fuel_perc_end"] = fp
                dd[laps_compl]["hit_points_end"] = hp

        # now process pit events
        for _, ev in df_events.iterrows():
            drv_id = ev["driver_id"]
            type = ev["type"]

            if drv_id != driver_id or type not in {"PitIn", "PitOut"}:
                continue

            laps_compl = ev["laps"]
            current_lap = laps_compl + 1
            tc = ev["tire_compound"]
            tw = ev["tire_wear"]
            tp = ev["tire_percentage"]
            f = ev["fuel"]
            fp = ev["fuel_percentage"]
            hp = ev["hit_points"]
            time = ev["time"]

            if type == "PitIn":

                # before or after start/finish line?
                if is_pit_event_before_finish_line(
                    dd[current_lap]["time_start"], dd[current_lap]["time_end"], time
                ):
                    # not yet crossed the line
                    lap_for_assigment = current_lap
                else:
                    # already crossed the line
                    lap_for_assigment = laps_compl

                # print("Found a pitin event!")
                # print("Current Lap: ", current_lap)
                # print("Laps Completed: ", laps_compl)
                # print(
                #     'dd[current_lap]["time_start"], time, dd[current_lap]["time_end"]'
                # )
                # print(dd[current_lap]["time_start"], time, dd[current_lap]["time_end"])
                # print(
                #     "Decided that this pit event happened before the finish line: ",
                #     is_pit_event_before_finish_line(
                #         dd[current_lap]["time_start"], dd[current_lap]["time_end"], time
                #     ),
                # )
                # print("Will assign inlap and end values to lap ", lap_for_assigment)

                dd[lap_for_assigment]["tire_wear_end"] = tw
                dd[lap_for_assigment]["tire_perc_end"] = tp
                dd[lap_for_assigment]["fuel_used_end"] = f
                dd[lap_for_assigment]["fuel_perc_end"] = fp
                dd[lap_for_assigment]["hit_points_end"] = hp
                dd[lap_for_assigment]["is_inlap"] = True
            elif type == "PitOut":
                # before or after start/finish line?
                if is_pit_event_before_finish_line(
                    dd[current_lap]["time_start"], dd[current_lap]["time_end"], time
                ):
                    # not yet crossed the line
                    lap_for_assigment = current_lap + 1
                else:
                    # already crossed the line
                    lap_for_assigment = current_lap

                dd[lap_for_assigment]["tire_wear_start"] = tw
                dd[lap_for_assigment]["tire_perc_start"] = tp
                dd[lap_for_assigment]["fuel_used_start"] = f
                dd[lap_for_assigment]["fuel_perc_start"] = fp
                dd[lap_for_assigment]["hit_points_start"] = hp
                dd[lap_for_assigment]["is_outlap"] = True

        details_dict[driver_id] = dd

    details_list = []

    for _, val in details_dict.items():
        for _, row in val.items():
            details_list.append(row)

    df_details = pd.DataFrame.from_records(details_list)

    # due to the finished event, we got one entry per driver that added a lap too much at the end
    df_details = df_details.loc[df_details["lap"] != df_details["lap"].max(), :]

    df_details["tire_perc_avg"] = (
        df_details["tire_perc_start"] + df_details["tire_perc_end"]
    ) / 2

    df_details["fuel_perc_avg"] = (
        df_details["fuel_perc_start"] + df_details["fuel_perc_end"]
    ) / 2

    df_details["hit_points_avg"] = (
        df_details["hit_points_start"] + df_details["hit_points_end"]
    ) / 2

    df_details["fuel_used"] = (
        df_details["fuel_used_start"] - df_details["fuel_used_end"]
    )
    df_details["tire_used"] = (
        df_details["tire_wear_end"] - df_details["tire_wear_start"]
    )

    df_details["lap_time"] = (df_details["time_end"] - df_details["time_start"]) / 10000

    df_details.dropna(subset="time_end", inplace=True)

    # Apply the start position mapping to create the position_start column
    df_details["position_start"] = df_details["driver_id"].map(start_pos_by_driver_id)
    df_details.loc[df_details["lap"] > 1, "position_start"] = None

    # Calculate position_end based on time_end within each lap
    df_details["position_end"] = df_details.groupby("lap")["time_end"].rank(
        method="min"
    )

    # Sort by driver and lap to prepare for shift operations
    df_details.sort_values(by=["driver_id", "lap"], inplace=True)

    # For laps other than 1, set position_start from the previous lap's position_end
    df_details.loc[df_details["lap"] != 1, "position_start"] = (
        df_details.groupby("driver_id")["position_end"]
        .shift(1)
        .where(df_details["lap"] != 1)
    )

    # Convert to integer type
    df_details["position_start"] = df_details["position_start"].astype(int)
    df_details["position_end"] = df_details["position_end"].astype(int)

    df_details.sort_values(by=["lap", "driver_id"], inplace=True)
    # print(df_details[["driver_id", "position_start", "position_end"]])
    # exit()

    return df_details


if __name__ == "__main__":
    lines = read_event_log(
        "input_files/20250313_214747_AustralianGPv1.16_event.details.log"
    )

    df_drivers, df_compounds, max_fuel = parse_meta_data(lines)
    df_events, start_pos_by_driver_id = parse_events(lines, df_compounds, max_fuel)
    df_race_details = get_details_df(df_events, start_pos_by_driver_id)

    print(df_drivers)
    print(df_compounds)
    print(max_fuel)
    print(df_events)
    print(df_race_details)
    print(df_race_details.loc[df_race_details["driver_id"] == 3, :])
