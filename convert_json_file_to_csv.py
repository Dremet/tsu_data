import sys
from pathlib import Path

from tsu_data.json_functions import *
from tsu_data.output_functions import *

if len(sys.argv) < 2:
    print("Usage: uv run convert_json_file_to_csv.py <path_to_details_file>")
    sys.exit(1)

input_file_path = Path(sys.argv[1])


data = read_event_json(input_file_path)
s_event = get_event_series(data)
df_drivers = get_driver_df(data)
df_race_results = get_race_results_df(data)
df_fastest_lap_results = get_fastest_lap_results_df(data)
df_checkpoint_results = get_checkpoint_results_df(data)

df_lap_results = extract_lap_results_from_cps(df_checkpoint_results, df_drivers)

# # output
df_event = s_event.to_frame().T

write_df_to_csv(input_file_path, df_event, ".event")
write_df_to_csv(input_file_path, df_drivers, ".drivers")
write_df_to_csv(input_file_path, df_race_results, ".race-results")
write_df_to_csv(input_file_path, df_fastest_lap_results, ".fastest-lap-results")
write_df_to_csv(input_file_path, df_checkpoint_results, ".checkpoint-results")
write_df_to_csv(input_file_path, df_lap_results, ".lap-results")
