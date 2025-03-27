import json
import pandas as pd
from pathlib import Path


def read_event_json(input_file_path: Path):
    with open(input_file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return data


def get_event_series(data: dict):
    event_dict = {
        "utc_start_time": data["utcStartTime"],
        "host": data["host"],
        "eventType": data["eventType"],
        "track_name": data["level"]["name"],
        "track_guid": data["level"]["guid"],
        "track_maker_id": data["level"]["makerId"],
        "track_type": data["level"]["levelType"],
        "finished_state": data["finishedState"],
        "max_laps": data["raceStats"]["maxLaps"],
        "max_time_without_start_time": data["raceStats"]["maxTimeWithoutStartTime"],
        "start_time": data["raceStats"]["startTime"],
        "hotlapping": data["raceStats"]["hotlapping"],
        "participants": len(data["players"]),
    }
    return pd.Series(event_dict)


def get_driver_df(data: dict):
    drivers = []

    for i, player in enumerate(data["players"]):
        driver = {
            "index": i,
            "name": player["player"]["name"],
            "steam_id": player["player"]["id"],
            "ai": player["player"]["ai"],
            "clan": player["player"]["clan"],
            "flag": player["player"]["flag"],
            "vehicle_name": player["vehicle"]["name"],
            "vehicle_guid": player["vehicle"]["guid"],
            "start_position": player["startPosition"],
        }

        drivers.append(driver)

    return pd.DataFrame.from_records(drivers)


def get_race_results_df(data: dict):
    race_results = []

    for entry in data["raceStats"]["raceRanking"]["entries"]:
        result = {
            "driver_index": entry["playerIndex"],
            "finish_time": entry["time"] / 10000.0,
            "laps_completed": entry["lapsCompleted"],
            "last_checkpoint": entry["lastCheckpoint"],
        }

        race_results.append(result)

    return pd.DataFrame.from_records(race_results)


def get_fastest_lap_results_df(data: dict):
    fastest_lap_results = []

    for entry in data["raceStats"]["lapRanking"]["entries"]:
        result = {
            "driver_index": entry["playerIndex"],
            "lap": entry["lap"],
            "lap_time": entry["time"] / 10000.0,
            "c_flag": entry["cFlags"],
        }

        fastest_lap_results.append(result)

    df_fastest_lap_results = pd.DataFrame.from_records(fastest_lap_results)

    df_fastest_lap_results["position"] = df_fastest_lap_results["lap_time"].rank(
        method="dense", ascending=True
    )

    return df_fastest_lap_results


def get_checkpoint_results_df(data: dict):
    cp_results = []

    sector_checkpoints = data["raceStats"]["checkpoints"]["sectorToCheckpoint"]

    for player_index, player_cp_results in enumerate(data["raceStats"]["playerStats"]):
        for lap, checkpoint_results in enumerate(
            player_cp_results["checkpointTimes"], start=1
        ):
            for cp, checkpoint_result in enumerate(checkpoint_results["times"]):
                result = {
                    "driver_index": player_index,
                    "lap": lap,
                    "lap_c_flag": checkpoint_results["cFlags"],
                    "cp": cp,
                    "is_sector": cp in sector_checkpoints,
                    "cp_time": checkpoint_result / 10000.0,
                }

                cp_results.append(result)

    df_checkpoint_results = pd.DataFrame.from_records(cp_results)

    df_checkpoint_results["position"] = df_checkpoint_results.groupby(["lap", "cp"])[
        "cp_time"
    ].rank(method="dense", ascending=True)

    return df_checkpoint_results


def extract_lap_results_from_cps(
    df_cps: pd.DataFrame, df_drivers: pd.DataFrame
) -> pd.DataFrame:
    """
    Creates a per-lap dataframe with these columns:
      driver_index, lap, lap_time, c_flag,
      time_start, time_end,
      position_start, position_end

    Parameters:
      df_cps: A DataFrame of checkpoints containing columns:
          driver_index, lap, cp, cp_time, lap_c_flag, is_sector
      df_drivers: A DataFrame of drivers containing columns:
          index, start_position
        where 'index' aligns with df_cps.driver_index
    """

    # ------------------------------------------------------------------
    # 1) Normalize times by subtracting each driver's very first cp_time
    #    (the "lights out") and drop that row.
    # ------------------------------------------------------------------
    df_cps = df_cps.sort_values(["driver_index", "lap", "cp"], ascending=True).copy()

    # Calculate the first cp_time per driver
    df_cps["first_cp_time"] = df_cps.groupby("driver_index")["cp_time"].transform(
        "first"
    )
    # Subtract
    df_cps["cp_time"] = df_cps["cp_time"] - df_cps["first_cp_time"]
    # Drop the "lights out" row (where cp_time == 0 after subtraction)
    df_cps = df_cps[df_cps["cp_time"] != 0].copy()
    df_cps.drop(columns="first_cp_time", inplace=True)

    # ------------------------------------------------------------------
    # 2) Filter to only cp=0 (crossing start/finish line).
    # ------------------------------------------------------------------
    df_cps = df_cps[df_cps["cp"] == 0].copy()
    # lap jumps to next lap when crossing start/finish line but we want that for the previous lap
    df_cps["lap"] = df_cps["lap"] - 1

    # ------------------------------------------------------------------
    # 3) Now each row in df_cps is the end of a lap -> rename fields.
    # ------------------------------------------------------------------
    df_cps.rename(columns={"cp_time": "time_end", "lap_c_flag": "c_flag"}, inplace=True)
    df_cps.sort_values(["driver_index", "lap"], inplace=True)

    # ------------------------------------------------------------------
    # 4) Determine position_end using an ascending rank of time_end
    #    within each lap.
    # ------------------------------------------------------------------
    #    The earliest time_end on lap L => position_end=1,
    #    the next earliest => position_end=2, etc.
    # ------------------------------------------------------------------
    df_cps["position_end"] = df_cps.groupby("lap")["time_end"].rank(
        method="dense", ascending=True
    )

    # ------------------------------------------------------------------
    # 5) For time_start and position_start, use shift(1) within each driver.
    #    The "position_start" for the very first lap each driver completes
    #    must come from df_drivers.start_position instead of a previous rank.
    # ------------------------------------------------------------------
    df_cps["time_start"] = df_cps.groupby("driver_index")["time_end"].shift(1)
    df_cps["position_start"] = df_cps.groupby("driver_index")["position_end"].shift(1)

    # Fill NaN time_start with 0.0 for the driver's first completed lap.
    df_cps["time_start"] = df_cps["time_start"].fillna(0.0)

    # Build a map: driver_index -> start_position from df_drivers
    driver_start_map = df_drivers.set_index("index")["start_position"].to_dict()

    # Fill the NaN position_start with that driver's start_position
    mask_first_lap = df_cps["position_start"].isna()
    df_cps.loc[mask_first_lap, "position_start"] = df_cps.loc[
        mask_first_lap, "driver_index"
    ].map(driver_start_map)

    # ------------------------------------------------------------------
    # 6) lap_time = time_end - time_start
    # ------------------------------------------------------------------
    df_cps["lap_time"] = df_cps["time_end"] - df_cps["time_start"]

    # ------------------------------------------------------------------
    # 7) Final reorder of columns
    # ------------------------------------------------------------------
    df_result = df_cps[
        [
            "driver_index",
            "lap",
            "lap_time",
            "c_flag",
            "time_start",
            "time_end",
            "position_start",
            "position_end",
        ]
    ].reset_index(drop=True)

    return df_result


if __name__ == "__main__":
    data = read_event_json("input_files/20250313_214747_AustralianGPv1.16_event.json")
    df_event = get_event_series(data)
    df_drivers = get_driver_df(data)
    df_race_results = get_race_results_df(data)
    df_fastest_lap_results = get_fastest_lap_results_df(data)
    df_checkpoint_results = get_checkpoint_results_df(data)

    df_lap_results = extract_lap_results_from_cps(df_checkpoint_results, df_drivers)

    print(df_event)
    print(df_drivers)
    print(df_race_results)
    print(df_fastest_lap_results)
    print(df_checkpoint_results)
    print(
        df_checkpoint_results.loc[
            (df_checkpoint_results["cp"] == 0) & (df_checkpoint_results["lap"] == 51), :
        ]
    )
    print(df_lap_results.loc[df_lap_results["driver_index"] == 0, :])
