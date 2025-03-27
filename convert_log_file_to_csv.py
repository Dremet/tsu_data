import sys
from pathlib import Path

from tsu_data.log_functions import *
from tsu_data.output_functions import *

if len(sys.argv) < 2:
    print("Usage: uv run convert_log_file_to_csv.py <path_to_details_file>")
    sys.exit(1)

input_file_path = Path(sys.argv[1])


lines = read_event_log(input_file_path)

df_drivers, df_compounds, max_fuel = parse_meta_data(lines)
df_events, start_pos_by_driver_id = parse_events(lines, df_compounds, max_fuel)
df_details = get_details_df(df_events, start_pos_by_driver_id)

# output
write_df_to_csv(input_file_path, df_details, ".main")
write_df_to_csv(input_file_path, df_drivers, ".driver")
write_df_to_csv(input_file_path, df_compounds, ".compounds")
