import os
import json
import pandas as pd

# =========================================================
# Strategy → Path Mapping
# =========================================================
STRATEGY_CONFIG = {
    "traditional": {
        "mbfl_root": "/home/rs/WorkEx/Projects/SoftwareTesting/FaultLocalization/MBFL/Sus/Mutant/"
                     "Defects4J/D4JCleanCD4J/TraditionalMutation/major/kill_type3",

        "flim_roots": [
            "/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/"
            "FLIMRecognitionResult/TraditionalMutation/major/"
            "Defects4J/D4JCleanCD4J/FLIMRecognition4FaultFile",

            "/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/"
            "FLIMRecognitionResult/TraditionalMutation/major/"
            "Defects4J/D4JCleanCD4J/FLIMRecognition4FaultFile_added"
        ],

        "output_root": "/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/"
                       "FLIMRecognitionResult/TraditionalMutation/major/"
                       "Defects4J/D4JCleanCD4J/FLIMRecognition4FaultFile_full_added_csv"
    },

    "mbert": {
        "mbfl_root": "/home/rs/WorkEx/Projects/SoftwareTesting/FaultLocalization/MBFL/Sus/Mutant/"
                     "Defects4J/D4JCleanCD4J/NeuralMutation/mBERT/kill_type3",

        "flim_roots": [
            "/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/"
            "FLIMRecognitionResult/NeuralMutation/mBERT/"
            "Defects4J/D4JCleanCD4J/FLIMRecognition4FaultFile",

            "/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/"
            "FLIMRecognitionResult/NeuralMutation/mBERT/"
            "Defects4J/D4JCleanCD4J/FLIMRecognition4FaultFile_added"
        ],

        "output_root": "/home/rs/WorkEx/Projects/SoftwareTesting/MutationAnalysis/"
                       "FLIMRecognitionResult/NeuralMutation/mBERT/"
                       "Defects4J/D4JCleanCD4J/FLIMRecognition4FaultFile_full_added_csv"
    }
}

CSV_COLUMNS = [
    "project", "version", "mutant_id", "index",
    "akf", "faulty_status", "is_flim",
    "pred_flim", "Sus", "cost_time"
]


# =========================================================
# Core Functions
# =========================================================

def decide_gt_flim(akf, faulty_status):
    return (akf != 0) and (faulty_status is False)


def read_json_result(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pred_flim = data.get("is_flim")
    cost_time = data.get("time_cost", {}).get("total_time_seconds")
    return pred_flim, cost_time


def safe_read_excel(excel_path):
    try:
        return pd.read_excel(excel_path, sheet_name=0)
    except Exception as e:
        print(f"[WARN] Skip invalid Excel: {excel_path} ({e})")
        return None


# =========================================================
# Process Project
# =========================================================

def process_project(project, config):
    mbfl_root = config["mbfl_root"]
    flim_roots = config["flim_roots"]
    output_root = config["output_root"]

    project_dir = os.path.join(mbfl_root, project)
    if not os.path.isdir(project_dir):
        print(f"[WARN] Project dir not found: {project_dir}")
        return

    for excel_name in sorted(os.listdir(project_dir)):
        if not excel_name.endswith(".xlsx"):
            continue

        version = excel_name.replace(f"{project}_", "").replace(".xlsx", "")
        excel_path = os.path.join(project_dir, excel_name)

        print(f"[INFO] Processing {project} version {version}")

        df = safe_read_excel(excel_path)
        if df is None:
            continue

        rows = []

        json_version = f"{version}b"

        for _, row in df.iterrows():

            mutant_id = str(row.get("mutant_id", "")).strip()
            if not mutant_id:
                continue

            akf = row.get("akf")
            faulty_status = row.get("faulty_status")
            sus = row.get("Sus")

            # =========================
            # 过滤 akf == 0
            # =========================
            if akf == 0:
                continue

            gt_flim = decide_gt_flim(akf, faulty_status)

            # 用于避免重复 JSON
            seen_json = set()

            for flim_root in flim_roots:

                project_json_root = os.path.join(
                    flim_root, project, json_version
                )

                mutant_json_dir = os.path.join(
                    project_json_root, mutant_id
                )

                if not os.path.isdir(mutant_json_dir):
                    continue

                json_files = sorted(
                    f for f in os.listdir(mutant_json_dir)
                    if f.endswith(".json")
                )

                for jf in json_files:

                    json_path = os.path.join(mutant_json_dir, jf)

                    # =========================
                    # JSON 去重
                    # =========================
                    if json_path in seen_json:
                        continue

                    seen_json.add(json_path)

                    try:
                        pred_flim, cost_time = read_json_result(json_path)
                    except Exception as e:
                        print(f"[WARN] JSON read failed: {json_path} ({e})")
                        continue

                    rows.append([
                        project,
                        int(version),
                        mutant_id,
                        len(rows) + 1,
                        akf,
                        faulty_status,
                        gt_flim,
                        pred_flim,
                        sus,
                        cost_time
                    ])

        if not rows:
            print(f"[WARN] No records for {project} {version}")
            continue

        out_dir = os.path.join(output_root, project)
        os.makedirs(out_dir, exist_ok=True)

        out_csv = os.path.join(
            out_dir, f"{project.lower()}_{version}b.csv"
        )

        pd.DataFrame(rows, columns=CSV_COLUMNS).to_csv(out_csv, index=False)

        print(f"[OK] Written {out_csv}")


# =========================================================
# Main
# =========================================================

def main():

    # =========================================================
    # 实验配置区
    # =========================================================

    STRATEGY = "traditional"   # "traditional" | "mbert"
    PROJECT_MODE = "single"       # "single" | "all"
    PROJECT_NAME = "Chart"     # only used when single

    config = STRATEGY_CONFIG[STRATEGY]
    mbfl_root = config["mbfl_root"]

    if PROJECT_MODE == "all":

        projects = [
            d for d in os.listdir(mbfl_root)
            if os.path.isdir(os.path.join(mbfl_root, d))
        ]

    else:

        projects = [PROJECT_NAME]

    for project in projects:
        process_project(project, config)


if __name__ == "__main__":
    main()