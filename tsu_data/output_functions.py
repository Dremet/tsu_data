from pathlib import Path
import pandas as pd


def write_df_to_csv(input_file_path: Path, df: pd.DataFrame, suffix: str = ""):
    output_dir = Path("output_files")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Nur den Dateinamen mit neuer Endung holen
    output_filename = input_file_path.stem + suffix + ".csv"

    # Zielpfad zusammenbauen
    output_file_path = output_dir / output_filename

    # Als CSV schreiben
    df.to_csv(output_file_path, index=False)
